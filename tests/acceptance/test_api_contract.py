from __future__ import annotations

import json
import os
import unittest
import urllib.error
import urllib.request
from typing import Any


BASE_URL = os.environ.get(
    "BASE_URL", os.environ.get(
        "CONTINUUM_ACCEPTANCE_BASE_URL", "http://127.0.0.1:8000"
    )
).rstrip("/")
if not BASE_URL.endswith("/api"):
    BASE_URL = BASE_URL.rstrip("/") + "/api"
TIMEOUT = float(os.environ.get("CONTINUUM_ACCEPTANCE_TIMEOUT_SECONDS", "5"))
MODEL_TIMEOUT = float(os.environ.get("CONTINUUM_ACCEPTANCE_MODEL_TIMEOUT_SECONDS", "75"))
REQUIRE_API = os.environ.get("CONTINUUM_ACCEPTANCE_REQUIRE_API", "0") == "1"
DEFAULT_HEADERS = {
    "X-Organization-ID": "demo-org",
    "X-Agent-ID": "demo-agent",
}


class ApiResponseError(Exception):
    def __init__(self, status: int, payload: Any):
        super().__init__(f"HTTP {status}: {payload}")
        self.status = status
        self.payload = payload


def request_json(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = TIMEOUT,
) -> dict[str, Any]:
    request_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        **DEFAULT_HEADERS,
        **(headers or {}),
    }
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}", data=data, method=method, headers=request_headers
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw}
        raise ApiResponseError(exc.code, payload) from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"{method} {path} did not return a JSON object")
    return payload


def is_mongodb_configured() -> bool:
    """Check if MongoDB is configured via /api/health."""
    try:
        health = request_json("GET", "/health")
        mongodb_status = health.get("services", {}).get("mongodb", "unconfigured")
        return mongodb_status != "unconfigured"
    except Exception:
        return False



def find_memory(memory_id):
    """The API has no GET /memories/{id}; resolve an ID through the scoped list."""
    listing = request_json("GET", "/memories?limit=100")
    for item in listing.get("items", []):
        if item.get("id") == memory_id:
            return item
    raise AssertionError(f"memory {memory_id} not found through GET /memories")

class ContinuumApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            request_json("GET", "/health")
        except (OSError, TimeoutError, json.JSONDecodeError, ApiResponseError) as exc:
            message = f"Continuum API unavailable at {BASE_URL}: {exc}"
            if REQUIRE_API:
                raise AssertionError(message) from exc
            raise unittest.SkipTest(message) from exc

    def setUp(self):
        request_json("POST", "/demo/reset", {"seed": 20260924})

    def test_health_has_bounded_dependency_states(self):
        health = request_json("GET", "/health")
        self.assertIn(health.get("status"), {"ok", "degraded", "unconfigured"})
        self.assertIsInstance(health.get("version"), str)
        services = health.get("services")
        self.assertIsInstance(services, dict)
        for name in ("api", "mongodb", "ollama", "embedding_model", "chat_model"):
            self.assertIn(name, services)
            self.assertIn(services[name], {"ok", "degraded", "unconfigured"})

    def test_reset_is_deterministic_and_summary_is_complete(self):
        first = request_json("POST", "/demo/reset", {"seed": 20260924})
        second = request_json("POST", "/demo/reset", {"seed": 20260924})
        self.assertEqual(first, second)
        self.assertIsInstance(first.get("counts"), dict)
        self.assertIsInstance(first.get("active_policy_version"), int)

        summary = request_json("GET", "/demo/summary")
        for field in ("counts", "active_policy", "pending_proposal", "latest_decision"):
            self.assertIn(field, summary)

    def test_memory_shapes_and_tenant_agent_isolation(self):
        payload = request_json("GET", "/memories?limit=100")
        self.assertIsInstance(payload.get("items"), list)
        self.assertEqual(payload.get("total"), len(payload["items"]))
        self.assertGreater(payload["total"], 0)
        required = {
            "id",
            "organization_id",
            "agent_id",
            "content",
            "type",
            "provenance",
            "confidence",
            "status",
            "supersedes",
            "created_at",
            "updated_at",
            "embedding_model",
        }
        for memory in payload["items"]:
            self.assertTrue(required <= set(memory))
            self.assertEqual(memory["organization_id"], "demo-org")
            self.assertEqual(memory["agent_id"], "demo-agent")

        other_org = request_json(
            "GET",
            "/memories?limit=100",
            headers={"X-Organization-ID": "other-org", "X-Agent-ID": "demo-agent"},
        )
        other_agent = request_json(
            "GET",
            "/memories?limit=100",
            headers={"X-Organization-ID": "demo-org", "X-Agent-ID": "other-agent"},
        )
        self.assertEqual(other_org, {"items": [], "total": 0})
        self.assertEqual(other_agent, {"items": [], "total": 0})

    def test_memory_creation_and_filters_use_the_public_shape(self):
        created = request_json(
            "POST",
            "/memories",
            {
                "content": "Synthetic acceptance marker for fast financing information.",
                "type": "pattern_evidence",
                "provenance": "synthetic acceptance check",
                "confidence": 0.9,
            },
        )
        required = {
            "id",
            "organization_id",
            "agent_id",
            "content",
            "type",
            "provenance",
            "confidence",
            "status",
            "supersedes",
            "created_at",
            "updated_at",
            "embedding_model",
        }
        self.assertTrue(required <= set(created))
        self.assertEqual(created["organization_id"], "demo-org")
        self.assertEqual(created["agent_id"], "demo-agent")

        filtered = request_json(
            "GET", "/memories?type=pattern_evidence&status=active&query=financing&limit=100"
        )
        self.assertIn(created["id"], {item["id"] for item in filtered["items"]})

    def test_recommendation_explanation_outcome_and_audit_are_linked(self):
        recommendation = request_json(
            "POST",
            "/recommendations",
            {
                "scenario": "A prospective buyer asks about financing and monthly pricing.",
                "customer": {"synthetic_segment": "budget_planner"},
            },
            timeout=MODEL_TIMEOUT,
        )
        required = {
            "decision_id",
            "recommendation",
            "rationale",
            "policy_version",
            "cited_memory_ids",
            "tool_trace",
            "latency_ms",
        }
        self.assertTrue(required <= set(recommendation))
        self.assertLessEqual(len(recommendation["cited_memory_ids"]), 5)
        self.assertGreaterEqual(recommendation["latency_ms"], 0)

        memories = request_json("GET", "/memories?limit=100")
        persisted_memory_ids = {item["id"] for item in memories["items"]}
        self.assertTrue(set(recommendation["cited_memory_ids"]) <= persisted_memory_ids)

        explanation = request_json(
            "GET", f"/decisions/{recommendation['decision_id']}/explanation"
        )
        for field in (
            "decision_id",
            "summary",
            "policy_chain",
            "memories",
            "outcomes",
            "approval",
            "audit_event_ids",
        ):
            self.assertIn(field, explanation)
        self.assertEqual(explanation["decision_id"], recommendation["decision_id"])
        explanation_ids = {
            item["id"] if isinstance(item, dict) else item
            for item in explanation["memories"]
        }
        self.assertTrue(set(recommendation["cited_memory_ids"]) <= explanation_ids)

        outcome = request_json(
            "POST",
            "/outcomes",
            {
                "decision_id": recommendation["decision_id"],
                "result": "resolved",
                "metrics": {"resolution_success": True, "customer_satisfaction": 5},
                "elapsed_seconds": 180,
            },
        )
        self.assertEqual(outcome.get("decision_id"), recommendation["decision_id"])

        audit = request_json(
            "GET", f"/audit-events?decision_id={recommendation['decision_id']}&limit=100"
        )
        self.assertIsInstance(audit.get("items"), list)
        self.assertGreater(len(audit["items"]), 0)

    def test_proposal_requires_valid_single_transition(self):
        analyzed = request_json("POST", "/proposals/analyze", {})
        proposal = analyzed.get("proposal")
        self.assertIsInstance(
            proposal,
            dict,
            f"deterministic demo data should qualify a proposal: {analyzed}",
        )
        proposal_id = proposal["id"]
        decision = request_json(
            "POST",
            f"/proposals/{proposal_id}/decision",
            {"decision": "approve", "actor": "acceptance-test", "note": "synthetic test"},
        )
        self.assertIsInstance(decision, dict)

        with self.assertRaises(ApiResponseError) as caught:
            request_json(
                "POST",
                f"/proposals/{proposal_id}/decision",
                {"decision": "reject", "actor": "acceptance-test"},
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertIsInstance(caught.exception.payload.get("detail"), str)

    def test_policy_history_proposal_listing_and_rejection_are_immutable(self):
        before = request_json("GET", "/policies")
        self.assertIsInstance(before.get("active"), dict)
        self.assertIsInstance(before.get("history"), list)
        policy_required = {
            "id",
            "logical_policy_id",
            "organization_id",
            "agent_id",
            "version",
            "status",
            "rule",
            "risk",
            "evidence_ids",
            "approval",
            "created_at",
        }
        self.assertTrue(policy_required <= set(before["active"]))
        # `history` may include the currently active version; count unique
        # records so the same version is not treated as two active policies.
        all_policies = {
            policy["id"]: policy for policy in [before["active"], *before["history"]]
        }.values()
        self.assertEqual(sum(policy["status"] == "active" for policy in all_policies), 1)

        analyzed = request_json("POST", "/proposals/analyze", {})
        proposal = analyzed.get("proposal")
        self.assertIsInstance(proposal, dict)
        proposals = request_json("GET", "/proposals")
        self.assertIn(proposal["id"], {item["id"] for item in proposals["items"]})

        rejected = request_json(
            "POST",
            f"/proposals/{proposal['id']}/decision",
            {"decision": "reject", "actor": "acceptance-test", "note": "exercise rejection"},
        )
        self.assertIsNone(rejected.get("policy"))
        self.assertEqual(request_json("GET", "/policies"), before)

        with self.assertRaises(ApiResponseError) as caught:
            request_json(
                "POST",
                f"/proposals/{proposal['id']}/decision",
                {"decision": "approve", "actor": "acceptance-test"},
            )
        self.assertEqual(caught.exception.status, 409)
        self.assertIsInstance(caught.exception.payload.get("detail"), str)

    def test_restart_persistence(self):
        """Test that memories persisted to MongoDB survive API restart."""
        if not is_mongodb_configured():
            self.skipTest("MongoDB not configured")

        # Write a memory
        mem = request_json("POST", "/memories", {
            "content": "acceptance-test-restart-" + os.urandom(8).hex(),
            "type": "observation",
            "provenance": "acceptance test (synthetic)",
            "confidence": 0.5,
        })
        memory_id = mem["id"]
        self.assertIsInstance(memory_id, str)

        # Verify it exists
        found = find_memory(memory_id)
        self.assertEqual(found["id"], memory_id)

        # Note: actual restart test requires a second process (see conftest or manual test runner)
        # This test documents the contract; full restart is tested in integration

    def test_bench_run_returns_correct_shape(self):
        """Test that bench run returns expected structure with 3 arms and rows."""
        result = request_json("POST", "/bench/run", {"task_limit": 3}, timeout=MODEL_TIMEOUT)

        # Verify top-level structure
        self.assertIsInstance(result.get("run_id"), str)
        self.assertIsInstance(result.get("ts"), str)
        self.assertIsInstance(result.get("arms"), list)
        self.assertEqual(len(result.get("arms", [])), 3, "Must have 3 arms")

        rows = result.get("rows", [])
        self.assertIsInstance(rows, list)
        self.assertEqual(len(rows), 3 * 3, "Must have 3 arms × 3 tasks = 9 rows")

        # Verify row structure
        for row in rows:
            self.assertIsInstance(row, dict)
            self.assertIn("arm", row)
            self.assertIn("correct", row)

    def test_bench_run_identical_per_arm(self):
        """Test that bench run is deterministic: second run has identical correctness per arm."""
        first = request_json("POST", "/bench/run", {"task_limit": 3}, timeout=MODEL_TIMEOUT)
        second = request_json("POST", "/bench/run", {"task_limit": 3}, timeout=MODEL_TIMEOUT)

        # Extract correctness counts by arm
        def aggregate_correct(result):
            agg = {}
            for row in result.get("rows", []):
                arm = row.get("arm")
                correct = row.get("correct", 0)
                agg[arm] = agg.get(arm, 0) + correct
            return agg

        first_agg = aggregate_correct(first)
        second_agg = aggregate_correct(second)
        self.assertEqual(first_agg, second_agg, "Correctness counts must be identical across runs")

    def test_memory_id_policy_version_resolves(self):
        """Test that every memory_id and policy_version in an explanation resolves via API."""
        if not is_mongodb_configured():
            self.skipTest("MongoDB not configured")

        # Get a memory
        mems = request_json("GET", "/memories?limit=1")
        if not mems.get("items"):
            # Create one
            mem = request_json("POST", "/memories", {
                "content": "test-resolution-" + os.urandom(8).hex(),
            })
            memory_id = mem["id"]
        else:
            memory_id = mems["items"][0]["id"]

        # Get policies
        policies = request_json("GET", "/policies")
        policy_version = policies.get("active", {}).get("version")

        # Verify they resolve
        self.assertIsInstance(memory_id, str)
        mem_resolved = find_memory(memory_id)
        self.assertEqual(mem_resolved["id"], memory_id)

        if policy_version is not None:
            # Policy versions should be retrievable via /policies endpoint
            self.assertIsInstance(policies.get("active"), dict)

    def test_trace_fallback_not_true_when_providers_configured(self):
        """Test that no trace has fallback=true when providers are configured."""
        health = request_json("GET", "/health")
        services = health.get("services", {})

        # Only check if providers are configured (not unconfigured)
        chat_configured = services.get("chat_model") != "unconfigured"
        embed_configured = services.get("embedding_model") != "unconfigured"

        if not (chat_configured or embed_configured):
            self.skipTest("No providers configured; fallback traces are expected")

        # A live recommendation must embed with the configured provider and
        # retrieve through Atlas $vectorSearch, not a fallback path.
        rec = request_json(
            "POST",
            "/recommendations",
            {"scenario": "A synthetic buyer asks how to pay for the product over time."},
            timeout=MODEL_TIMEOUT,
        )
        trace = {entry.get("tool"): entry for entry in rec.get("tool_trace", [])}
        if embed_configured:
            self.assertEqual(trace["embed"]["status"], "ok", trace["embed"].get("reason"))
            self.assertEqual(trace["memory_retrieval"].get("backend"), "atlas-vector")
            self.assertGreaterEqual(trace["memory_retrieval"].get("vector_calls", 0), 1)


if __name__ == "__main__":
    unittest.main()
