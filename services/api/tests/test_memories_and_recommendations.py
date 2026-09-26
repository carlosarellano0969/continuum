from __future__ import annotations

from fastapi.testclient import TestClient

from continuum_api.adapters import DeterministicEmbedder
from continuum_api.config import Settings
from continuum_api.errors import DependencyError
from continuum_api.main import create_app
from continuum_api.models import Memory, utc_now
from continuum_api.repository import InMemoryRepository, MongoRepository


def test_mongo_document_persists_embedding_without_exposing_it() -> None:
    now = utc_now()
    memory = Memory(
        id="mem_test",
        organization_id="demo-org",
        agent_id="demo-agent",
        content="Use needs-based financing explanations.",
        type="semantic",
        provenance="test",
        confidence=0.94,
        status="active",
        created_at=now,
        updated_at=now,
        embedding_model="nomic-embed-text",
        embedding=[0.1, 0.2, 0.3],
    )

    assert "embedding" not in memory.model_dump(mode="python")
    assert MongoRepository._document(memory)["embedding"] == [0.1, 0.2, 0.3]


def test_memory_create_filter_search_and_scope(seeded: TestClient) -> None:
    created = seeded.post(
        "/api/memories",
        json={
            "content": "Enterprise customers require a manager checkpoint.",
            "type": "pattern_evidence",
            "provenance": "operator-note",
            "confidence": 0.91,
        },
    )
    assert created.status_code == 200
    memory = created.json()
    assert memory["organization_id"] == "demo-org"
    assert memory["agent_id"] == "demo-agent"
    assert memory["embedding_model"] == "deterministic-local-v1"
    assert "embedding" not in memory

    result = seeded.get(
        "/api/memories", params={"type": "pattern_evidence", "query": "manager checkpoint"}
    )
    assert result.status_code == 200
    assert result.json()["total"] == 3
    assert result.json()["items"][0]["id"] == memory["id"]
    assert result.json()["items"][0]["score"] > 0

    foreign = seeded.get(
        "/api/memories",
        headers={"X-Organization-ID": "demo-org", "X-Agent-ID": "other-agent"},
    )
    assert foreign.json() == {"items": [], "total": 0}


def test_supersedes_must_resolve_inside_exact_scope(seeded: TestClient) -> None:
    memory_id = seeded.get("/api/memories").json()["items"][0]["id"]
    response = seeded.post(
        "/api/memories",
        headers={"X-Organization-ID": "other-org"},
        json={
            "content": "replacement",
            "type": "semantic",
            "provenance": "test",
            "confidence": 0.8,
            "supersedes": memory_id,
        },
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "superseded memory not found in this tenant and agent scope"}


def test_superseding_memory_deactivates_prior_record(seeded: TestClient) -> None:
    prior = seeded.get("/api/memories").json()["items"][0]
    replacement = seeded.post(
        "/api/memories",
        json={
            "content": "Replacement evidence with a narrower, reviewed scope.",
            "type": prior["type"],
            "provenance": "reviewed-test",
            "confidence": 0.98,
            "supersedes": prior["id"],
        },
    )
    assert replacement.status_code == 200

    all_records = seeded.get("/api/memories", params={"limit": 100}).json()["items"]
    prior_after = next(record for record in all_records if record["id"] == prior["id"])
    assert prior_after["status"] == "inactive"
    active_ids = {
        record["id"]
        for record in seeded.get("/api/memories", params={"status": "active", "limit": 100}).json()["items"]
    }
    assert prior["id"] not in active_ids
    assert replacement.json()["id"] in active_ids


def test_recommendation_citations_are_persisted_and_explainable(seeded: TestClient) -> None:
    response = seeded.post(
        "/api/recommendations",
        json={"scenario": "A loyal customer requests a $900 refund", "customer": {"tenure_years": 8}},
    )
    assert response.status_code == 200
    recommendation = response.json()
    assert recommendation["policy_version"] == 1
    assert 0 < len(recommendation["cited_memory_ids"]) <= 5
    assert all(entry["status"] == "ok" for entry in recommendation["tool_trace"])

    persisted_ids = {item["id"] for item in seeded.get("/api/memories").json()["items"]}
    assert set(recommendation["cited_memory_ids"]) <= persisted_ids

    explanation = seeded.get(
        f"/api/decisions/{recommendation['decision_id']}/explanation"
    ).json()
    assert explanation["decision_id"] == recommendation["decision_id"]
    assert {item["id"] for item in explanation["memories"]} == set(recommendation["cited_memory_ids"])
    audits = seeded.get(
        "/api/audit-events", params={"decision_id": recommendation["decision_id"]}
    ).json()["items"]
    assert explanation["audit_event_ids"] == [item["id"] for item in audits]


class FailingChat:
    model_name = "missing-chat"
    configured = True

    async def health(self) -> str:
        return "degraded"

    async def recommend(self, *args, **kwargs):
        raise DependencyError("bounded chat timeout")


class FailingEmbedder:
    model_name = "missing-embed"
    configured = True

    async def health(self) -> str:
        return "degraded"

    async def embed(self, text: str):
        raise DependencyError("bounded embedding timeout")


def test_dependency_failures_use_clearly_marked_deterministic_fallback() -> None:
    repository = InMemoryRepository()
    app = create_app(
        settings=Settings(ollama_base_url=None),
        repository=repository,
        chat_model=FailingChat(),
        embedder=FailingEmbedder(),
    )
    client = TestClient(app)
    client.post("/api/demo/reset", json={})

    response = client.post("/api/recommendations", json={"scenario": "refund request"})
    assert response.status_code == 200
    trace = response.json()["tool_trace"]
    assert [item["status"] for item in trace if item["tool"] in {"embed", "chat"}] == ["fallback", "fallback"]
    assert client.get("/api/health").json()["status"] == "degraded"
