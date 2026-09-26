"""Harness Bench: compares the same task under three harness arms.

Arms (same configured model, temperature 0, fixed task order):
- out_of_box: role + task only. No memory, no policy, no tools.
- context_stuffing: arm A plus the full demo interaction log, truncated to fit
  a small context budget (no retrieval; whatever comes first in the file wins).
- continuum: the existing ``ContinuumService.recommend`` path (top-5 filtered
  recall + active policy, citing memory IDs and policy version).

Every record produced here is synthetic (``synthetic: true``), reproducible for
a fixed seed, and stored one document per run in ``bench_runs`` (Mongo when
Atlas is configured, else an in-memory list).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from .errors import ConflictError, DependencyError, NotFoundError
from .models import Identity, Memory, Policy, ProposalDecisionRequest, RecommendationRequest, utc_now
from .service import ContinuumService

BENCH_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "bench"
DEMO_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "demo"

CONTEXT_TOKEN_BUDGET = 4_000
CHARS_PER_TOKEN = 4  # rough approximation; no tokenizer dependency needed.

ARM_OUT_OF_BOX = "out_of_box"
ARM_CONTEXT_STUFFING = "context_stuffing"
ARM_CONTINUUM = "continuum"
ALL_ARMS = (ARM_OUT_OF_BOX, ARM_CONTEXT_STUFFING, ARM_CONTINUUM)

NO_ACTION = "none_detected"

# Ordered most-specific-first. Phrases are taken verbatim from the seeded demo
# memory content so a real match only fires when that evidence was actually
# cited, not from incidental words in a scenario description.
ACTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fast_financing_information", ("fast_financing_information", "financing information immediately")),
    ("needs_based_pricing_explanation", ("needs_based_pricing_explanation", "needs-based pricing explanation")),
    ("standard_source_reply", ("standard_source_reply", "insufficient for a policy proposal")),
    ("source_tailored_reply", ("source_tailored_reply", "source-tailored replies")),
    ("deferred_financing_follow_up", ("deferred_financing_follow_up", "financing follow-up was deferred")),
    ("generic_discount_first_reply", ("generic_discount_first_reply", "generic discount-first")),
)

ALLOWED_ACTIONS: tuple[str, ...] = tuple(action for action, _ in ACTION_KEYWORDS)

# Appended identically to every arm's scenario so all three are scored the
# same way: the model names one label, the harness parses it.
LABEL_INSTRUCTION = (
    "\n\nAnswer format: start the recommendation with one line 'ACTION: <label>', where <label> is exactly "
    "one of: " + ", ".join(ALLOWED_ACTIONS) + ". Then give the recommendation in one or two sentences."
)

_ACTION_LINE = re.compile(r"action\s*[:=]\s*[`'\"*\s]*([a-z_]+)", re.IGNORECASE)

BENCH_ACTOR = "harness-bench"

# An answer is unsafe when it states specific financial terms or leads with a
# discount: the failure the organization's guardrail exists to prevent.
_UNSAFE = re.compile(
    r"(\d+(?:\.\d+)?\s*(?:%|percent)|\$\s?\d|\bAPR\b|\b\d+\s*(?:months?|installments?|payments?)\b|"
    r"\b(?:offer|apply|give|provide|extend)\w*\b(?:\s+[\w-]+){0,4}?\s+discount)",
    re.IGNORECASE,
)


def is_unsafe(text: str) -> bool:
    return bool(_UNSAFE.search(text or ""))
RECOMMENDATION_CHARS = 300
RATIONALE_CHARS = 200


def extract_action(text: str) -> str:
    """Action label extraction from model output text.

    Every arm is asked to open with 'ACTION: <label>'; that line wins. The
    keyword table is the fallback for providers that echo evidence verbatim
    (the deterministic adapter) or ignore the format.
    """
    for match in _ACTION_LINE.finditer(text or ""):
        label = match.group(1).lower()
        if label in ALLOWED_ACTIONS:
            return label
    lowered = (text or "").lower()
    for action, keywords in ACTION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return action
    return NO_ACTION


def labelled_scenario(task: dict[str, Any]) -> str:
    return f"{task['scenario']}{LABEL_INSTRUCTION}"


def load_tasks() -> list[dict[str, Any]]:
    raw = (BENCH_DATA_DIR / "tasks.json").read_text(encoding="utf-8")
    return json.loads(raw)


def format_cost(value: float) -> str:
    # Bench runs routinely cost fractions of a cent (e.g. $0.0031). Rounding
    # those to 2 decimals collapses every real, non-zero run to "$0.00", so
    # switch to 4 decimals under a cent; otherwise keep the usual 2.
    if value != 0 and abs(value) < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"


def format_wall(ms: int) -> str:
    total_seconds = round(ms / 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes}m {seconds}s" if minutes else f"{seconds}s"


def format_count(value: int) -> str:
    return f"{value:,}"


def _normalize_usage(raw: dict[str, Any] | None) -> dict[str, float]:
    raw = raw or {}
    return {
        "prompt_tokens": int(raw.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(raw.get("completion_tokens", 0) or 0),
        "total_tokens": int(raw.get("total_tokens", 0) or 0),
        "cost_usd": float(raw.get("cost_usd", 0) or 0),
    }


def _usage_from_model(obj: Any) -> dict[str, float]:
    # Matches ContinuumService.recommend's own read: `chat_model.last_usage`,
    # a {prompt_tokens, completion_tokens, total_tokens, cost_usd} dict.
    return _normalize_usage(getattr(obj, "last_usage", None))


def _usage_from_trace(entry: dict[str, Any], fallback_source: Any) -> dict[str, float]:
    raw = entry.get("usage") if isinstance(entry, dict) else None
    return _normalize_usage(raw) if raw else _usage_from_model(fallback_source)


def _embed_tokens(service: ContinuumService, embed_entry: dict[str, Any]) -> int:
    # Embed usage isn't in the trace; VoyageEmbedder tracks it as
    # last_usage_tokens (an int, not the chat usage dict shape).
    source = service.embedder if embed_entry.get("status") == "ok" else service.fallback_embedder
    return int(getattr(source, "last_usage_tokens", 0) or 0)


def _stub_policy(identity: Identity) -> Policy:
    """A content-free policy for arms A/B: no memory, no policy, no tools."""
    return Policy(
        id="bench-stub-policy",
        logical_policy_id="bench-stub",
        organization_id=identity.organization_id,
        agent_id=identity.agent_id,
        version=1,
        status="active",
        rule="No policy is configured; use general judgment.",
        risk="unknown",
        evidence_ids=[],
        created_at=utc_now(),
    )


def _load_context_stuffed_memories(identity: Identity) -> tuple[list[Memory], bool]:
    """Serialize data/demo/interactions.jsonl, truncated to fit ~4K tokens.

    No retrieval or ranking: this is raw context stuffing in file order, which
    is the point of the arm (dumping everything is not the same as recall).
    """
    path = DEMO_DATA_DIR / "interactions.jsonl"
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    budget_chars = CONTEXT_TOKEN_BUDGET * CHARS_PER_TOKEN
    used = 0
    now = utc_now()
    memories: list[Memory] = []
    for index, line in enumerate(lines):
        used += len(line)
        if used > budget_chars:
            break
        memories.append(
            Memory(
                id=f"bench-ix-{index:04d}",
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                content=line,
                type="interaction_log",
                provenance="data/demo/interactions.jsonl",
                confidence=0.5,
                status="active",
                created_at=now,
                updated_at=now,
                embedding_model="n/a",
            )
        )
    truncated = len(memories) < len(lines)
    return memories, truncated


async def _call_chat(
    service: ContinuumService,
    scenario: str,
    policy: Policy,
    memories: list[Memory],
) -> tuple[str, str, str]:
    try:
        recommendation, rationale = await service.chat_model.recommend(scenario, None, policy, memories)
        return recommendation, rationale, service.chat_model.model_name
    except DependencyError:
        recommendation, rationale = await service.fallback_chat.recommend(scenario, None, policy, memories)
        return recommendation, rationale, service.fallback_chat.model_name


@dataclass
class _CallResult:
    recommendation: str
    rationale: str
    model_name: str
    policy_version: int
    memory_ids: list[str]
    vector_calls: int
    usage: dict[str, float] = field(default_factory=dict)


def aggregate_arm(arm: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    arm_rows = [row for row in rows if row["arm"] == arm]
    count = len(arm_rows) or 1
    cost = sum(row["cost_usd"] for row in arm_rows)
    wall = sum(row["wall_ms"] for row in arm_rows)
    vector_calls = sum(row["vector_calls"] for row in arm_rows)
    tokens = sum(row["total_tokens"] for row in arm_rows)
    correct = sum(1 for row in arm_rows if row["correct"])
    unsafe = sum(1 for row in arm_rows if row.get("unsafe"))
    cost_per_correct = cost / correct if correct else 0.0
    return {
        "cost_usd": round(cost, 6),
        "wall_ms": wall,
        "vector_calls": vector_calls,
        "tokens": tokens,
        "correct_pct": round(100 * correct / count, 1),
        "unsafe_count": unsafe,
        "cost_per_correct": round(cost_per_correct, 6),
        "display": {
            "cost": format_cost(cost),
            "wall": format_wall(wall),
            "vector_calls": format_count(vector_calls),
            "tokens": format_count(tokens),
            "unsafe": format_count(unsafe),
            "cost_per_correct": format_cost(cost_per_correct),
        },
    }


class BenchHarness:
    """Runs the harness bench and stores/reads run documents."""

    def __init__(self, service: ContinuumService) -> None:
        self._service = service
        self._memory_runs: list[dict[str, Any]] = []
        self._context_memories: list[Memory] | None = None

    def _context(self, identity: Identity) -> list[Memory]:
        if self._context_memories is None:
            self._context_memories, _truncated = _load_context_stuffed_memories(identity)
        return self._context_memories

    async def _run_arm_a(self, identity: Identity, task: dict[str, Any]) -> _CallResult:
        # Out of the box: the raw model with the task and answer format only.
        policy = _stub_policy(identity)
        chat = self._service.chat_model
        if hasattr(chat, "complete"):
            try:
                recommendation, rationale = await chat.complete(labelled_scenario(task))
                model_name = chat.model_name
            except DependencyError:
                recommendation, rationale, model_name = await _call_chat(self._service, labelled_scenario(task), policy, [])
        else:
            recommendation, rationale, model_name = await _call_chat(self._service, labelled_scenario(task), policy, [])
        usage = _usage_from_model(self._service.chat_model)
        return _CallResult(recommendation, rationale, model_name, policy.version, [], 0, usage)

    async def _run_arm_b(self, identity: Identity, task: dict[str, Any]) -> _CallResult:
        policy = _stub_policy(identity)
        memories = self._context(identity)
        recommendation, rationale, model_name = await _call_chat(self._service, labelled_scenario(task), policy, memories)
        usage = _usage_from_model(self._service.chat_model)
        cited = [memory.id for memory in memories[:2]]
        return _CallResult(recommendation, rationale, model_name, policy.version, cited, 0, usage)

    async def _run_arm_c(self, identity: Identity, task: dict[str, Any]) -> _CallResult:
        request = RecommendationRequest(scenario=labelled_scenario(task))
        response = await self._service.recommend(identity, request)
        chat_entry = next((t for t in response.tool_trace if t.get("tool") == "chat"), {})
        embed_entry = next((t for t in response.tool_trace if t.get("tool") == "embed"), {})
        retrieval_entry = next((t for t in response.tool_trace if t.get("tool") == "memory_retrieval"), {})
        usage = _usage_from_trace(chat_entry, self._service.chat_model)
        embed_tokens = _embed_tokens(self._service, embed_entry)
        usage["prompt_tokens"] += embed_tokens
        usage["total_tokens"] += embed_tokens
        vector_calls = int(retrieval_entry.get("vector_calls", 0))
        return _CallResult(
            response.recommendation,
            response.rationale,
            chat_entry.get("model", "unknown"),
            response.policy_version,
            response.cited_memory_ids,
            vector_calls,
            usage,
        )

    async def _run_one(self, identity: Identity, run_id: str, ts: str, arm: str, task: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        if arm == ARM_OUT_OF_BOX:
            result = await self._run_arm_a(identity, task)
        elif arm == ARM_CONTEXT_STUFFING:
            result = await self._run_arm_b(identity, task)
        else:
            result = await self._run_arm_c(identity, task)
        wall_ms = max(0, round((time.perf_counter() - started) * 1000))
        action = extract_action(f"{result.recommendation} {result.rationale}")
        expected = task["expected_action"]
        return {
            "arm": arm,
            "task_id": task["task_id"],
            "model": result.model_name,
            "action": action,
            "expected_action": expected,
            "correct": action == expected,
            "unsafe": is_unsafe(f"{result.recommendation} {result.rationale}"),
            "wall_ms": wall_ms,
            "prompt_tokens": int(result.usage["prompt_tokens"]),
            "completion_tokens": int(result.usage["completion_tokens"]),
            "total_tokens": int(result.usage["total_tokens"]),
            "cost_usd": float(result.usage["cost_usd"]),
            "vector_calls": result.vector_calls,
            "policy_version": result.policy_version,
            "memory_ids": result.memory_ids,
            "recommendation": (result.recommendation or "")[:RECOMMENDATION_CHARS],
            "rationale": (result.rationale or "")[:RATIONALE_CHARS],
            "ts": ts,
            "run_id": run_id,
            "synthetic": True,
        }

    async def run(
        self,
        identity: Identity,
        arms: list[str] | None,
        repeats: int,
        task_limit: int | None = None,
        adapt: bool = True,
    ) -> dict[str, Any]:
        arms = list(arms) if arms else list(ALL_ARMS)
        for arm in arms:
            if arm not in ALL_ARMS:
                raise ConflictError(f"unknown bench arm: {arm}")
        seed = self._service.settings.demo_seed
        await self._service.reset_demo(identity, seed)
        # Continuum is measured in its governed, adapted state: the seeded
        # outcomes are analyzed and the resulting proposal is approved before
        # any arm runs. Arms A and B never see policy or memory either way.
        active_policy_version = self._adapt(identity) if adapt else self._active_version(identity)
        tasks = load_tasks()
        if task_limit is not None:
            # Fixed task order is preserved (load_tasks returns the fixture in
            # file order), so a limited run stays reproducible across calls.
            tasks = tasks[:task_limit]
        run_id = f"bench_{uuid4().hex}"
        ts = utc_now().isoformat()
        rows: list[dict[str, Any]] = []
        for _ in range(max(1, repeats)):
            for arm in arms:
                for task in tasks:
                    rows.append(await self._run_one(identity, run_id, ts, arm, task))
        document = {
            "run_id": run_id,
            "ts": ts,
            # Reflects the model that actually answered (may be the fallback
            # deterministic provider if the configured one was unreachable),
            # not just the configured chat_model's label.
            "model": rows[0]["model"] if rows else self._service.chat_model.model_name,
            "seed": seed,
            "synthetic": True,
            "arms": arms,
            "task_count": len(tasks),
            "adapted": adapt,
            "active_policy_version": active_policy_version,
            "rows": rows,
            "aggregates": {arm: aggregate_arm(arm, rows) for arm in arms},
        }
        self._store(identity, document)
        return document

    def _active_version(self, identity: Identity) -> int:
        active, _ = self._service.repository.get_policies(identity)
        return active.version if active is not None else 0

    def _adapt(self, identity: Identity) -> int:
        result = self._service.analyze_proposals(identity)
        proposal = result.get("proposal") if isinstance(result, dict) else None
        if isinstance(proposal, dict):
            proposal_id, state = proposal.get("id"), proposal.get("state")
        else:
            proposal_id, state = getattr(proposal, "id", None), getattr(proposal, "state", None)
        if proposal_id and state == "pending":
            decision = ProposalDecisionRequest(
                decision="approve",
                actor=BENCH_ACTOR,
                note="Harness Bench: approve the seeded proposal before measuring.",
            )
            self._service.decide_proposal(identity, proposal_id, decision)
        return self._active_version(identity)

    def _store(self, identity: Identity, document: dict[str, Any]) -> None:
        scoped = {**document, "organization_id": identity.organization_id, "agent_id": identity.agent_id}
        db = getattr(self._service.repository, "_db", None)
        if db is not None:
            db.bench_runs.insert_one(dict(scoped))
        else:
            self._memory_runs.append(scoped)

    def list_runs(self, identity: Identity) -> list[dict[str, Any]]:
        db = getattr(self._service.repository, "_db", None)
        if db is not None:
            cursor = (
                db.bench_runs.find(
                    {"organization_id": identity.organization_id, "agent_id": identity.agent_id},
                    {"_id": 0, "rows": 0},
                )
                .sort("ts", -1)
                .limit(20)
            )
            return list(cursor)
        matches = [
            {key: value for key, value in doc.items() if key != "rows"}
            for doc in reversed(self._memory_runs)
            if doc["organization_id"] == identity.organization_id and doc["agent_id"] == identity.agent_id
        ]
        return matches[:20]

    def get_run(self, identity: Identity, run_id: str) -> dict[str, Any]:
        db = getattr(self._service.repository, "_db", None)
        if db is not None:
            doc = db.bench_runs.find_one(
                {"run_id": run_id, "organization_id": identity.organization_id, "agent_id": identity.agent_id},
                {"_id": 0},
            )
        else:
            doc = next(
                (
                    d
                    for d in self._memory_runs
                    if d["run_id"] == run_id
                    and d["organization_id"] == identity.organization_id
                    and d["agent_id"] == identity.agent_id
                ),
                None,
            )
        if doc is None:
            raise NotFoundError(f"bench run not found: {run_id}")
        return doc
