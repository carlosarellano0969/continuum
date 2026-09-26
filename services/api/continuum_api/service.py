from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from .adapters import ChatModel, DeterministicChatModel, DeterministicEmbedder, Embedder
from .config import Settings
from .guardrails import RETRY_NOTE, invented_terms
from .errors import ConflictError, DependencyError, NotFoundError
from .models import (
    Approval,
    AuditEvent,
    Decision,
    GuardrailProposal,
    Identity,
    Memory,
    MemoryCreate,
    Outcome,
    OutcomeCreate,
    Policy,
    ProposalDecisionRequest,
    RecommendationRequest,
    RecommendationResponse,
    utc_now,
)
from .repository import Repository


FAILURE_RESULTS = {"failure", "failed", "negative", "bad", "escalated", "rejected", "unresolved"}
DEMO_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "demo"
# Three memories carry the evidence the policy needs; five doubled the prompt.
RECALL_LIMIT = 3


def _fixture_embeddings(model_name: str) -> dict[str, list[float]]:
    """Seed-memory vectors precomputed once with the hosted model, keyed by sha256.

    Resets reuse them instead of re-embedding six memories through a rate-limited
    API; any other model (or a missing file) falls back to live embedding.
    """
    path = DEMO_DATA_DIR / f"memory_embeddings.{model_name}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if payload.get("model") != model_name:
        return {}
    vectors = payload.get("vectors")
    return vectors if isinstance(vectors, dict) else {}


class ContinuumService:
    def __init__(
        self,
        settings: Settings,
        repository: Repository,
        chat_model: ChatModel,
        embedder: Embedder,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.chat_model = chat_model
        self.embedder = embedder
        self.fallback_chat = DeterministicChatModel()
        self.fallback_embedder = DeterministicEmbedder()

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex}"

    @staticmethod
    def _seed_id(seed: int, identity: Identity, prefix: str, index: int) -> str:
        value = f"continuum:{seed}:{identity.organization_id}:{identity.agent_id}:{prefix}:{index}"
        return f"{prefix}_{uuid5(NAMESPACE_URL, value).hex}"

    async def health(self) -> dict[str, Any]:
        mongodb = self.repository.health()
        chat = await self.chat_model.health()
        embedding = await self.embedder.health()
        if "degraded" in (chat, embedding):
            ollama = "degraded"
        elif chat == embedding == "unconfigured":
            ollama = "unconfigured"
        else:
            ollama = "ok"
        states = (mongodb, ollama, embedding, chat)
        if "degraded" in states:
            status = "degraded"
        elif all(state == "unconfigured" for state in states):
            status = "unconfigured"
        else:
            status = "ok"
        return {
            "status": status,
            "version": "0.1.0",
            "services": {
                "api": "ok",
                "mongodb": mongodb,
                "ollama": ollama,
                "embedding_model": embedding,
                "chat_model": chat,
            },
            "models": {
                "embedding": self.embedder.model_name if self.embedder.configured else None,
                "chat": self.chat_model.model_name if self.chat_model.configured else None,
            },
        }

    async def reset_demo(self, identity: Identity, seed: int | None = None) -> dict[str, Any]:
        seed = self.settings.demo_seed if seed is None else seed
        base = datetime(2026, 9, 24, 13, 0, tzinfo=timezone.utc) + timedelta(seconds=seed % 60)
        try:
            manifest = json.loads((DEMO_DATA_DIR / "manifest.json").read_text(encoding="utf-8"))
            memory_rows = [
                json.loads(line)
                for line in (DEMO_DATA_DIR / "memories.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError) as exc:
            raise DependencyError("deterministic demo fixtures are missing or invalid") from exc
        fixture_identity = manifest.get("identity", {})
        if fixture_identity != identity.model_dump():
            raise ConflictError("demo fixtures do not match the configured demo scope")
        memories: list[Memory] = []
        precomputed = _fixture_embeddings(self.embedder.model_name)
        for row in memory_rows:
            embedding_model = self.embedder.model_name
            try:
                fixture_key = hashlib.sha256(row["content"].encode("utf-8")).hexdigest()
                embedding = precomputed.get(fixture_key) or await self.embedder.embed(row["content"])
            except DependencyError:
                embedding = await self.fallback_embedder.embed(row["content"])
                embedding_model = self.fallback_embedder.model_name
            memories.append(
                Memory.model_validate(
                    {
                        **row,
                        "embedding_model": embedding_model,
                        "embedding": embedding,
                    }
                )
            )
        policy = Policy(
            id=self._seed_id(seed, identity, "pol", 0),
            logical_policy_id="financing-response",
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            version=1,
            status="active",
            rule="Answer pricing questions with general product information within thirty minutes; discounts are optional.",
            risk="medium",
            evidence_ids=[memories[0].id, memories[1].id],
            created_at=base + timedelta(minutes=10),
        )
        decisions: list[Decision] = []
        outcomes: list[Outcome] = []
        for index in range(3):
            decision = Decision(
                id=self._seed_id(seed, identity, "dec", index),
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                scenario="A prospective customer asks about financing and estimated monthly payments.",
                recommendation="Send general product information and offer a generic discount under policy v1.",
                rationale="Policy v1 does not prioritize financing-specific information or a five-minute response.",
                policy_id=policy.id,
                policy_version=policy.version,
                cited_memory_ids=[memories[0].id, memories[1].id],
                tool_trace=[{"tool": "demo_seed", "status": "deterministic"}],
                model="demo-seed",
                latency_ms=0,
                created_at=base + timedelta(minutes=20 + index),
            )
            decisions.append(decision)
            outcomes.append(
                Outcome(
                    id=self._seed_id(seed, identity, "out", index),
                    organization_id=identity.organization_id,
                    agent_id=identity.agent_id,
                    decision_id=decision.id,
                    result="failed",
                    metrics={
                        "converted": False,
                        "response_minutes": 38 + index * 7,
                        "fixture_source": "data/demo/manifest.json",
                        "fixture_interactions": manifest["interaction_count"],
                        "financing_success_lift": manifest["patterns"][
                            "financing_pricing_fast_information"
                        ]["absolute_success_lift"],
                        "pricing_explanation_success_lift": manifest["patterns"][
                            "generic_discount_first_underperformance"
                        ]["absolute_success_lift"],
                    },
                    elapsed_seconds=2_280 + index * 420,
                    created_at=base + timedelta(minutes=30 + index),
                )
            )
        audit = AuditEvent(
            id=self._seed_id(seed, identity, "aud", 0),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            event_type="demo.reset",
            actor="system",
            details={
                "seed": seed,
                "fixture_seed": manifest["seed"],
                "fixture_interactions": manifest["interaction_count"],
                "fixture_format": manifest["format_version"],
            },
            created_at=base,
        )
        records: dict[str, list[Any]] = {
            "memories": memories,
            "policies": [policy],
            "decisions": decisions,
            "outcomes": outcomes,
            "proposals": [],
            "audit_events": [audit],
        }
        self.repository.reset_scope(identity, records)
        analyzed = self._analyze_proposals(
            identity,
            proposal_id=self._seed_id(seed, identity, "prop", 0),
            audit_id=self._seed_id(seed, identity, "aud", 1),
            created_at=base + timedelta(minutes=40),
        )
        if analyzed["proposal"] is None:
            raise ConflictError(f"demo fixtures did not qualify a proposal: {analyzed['reason']}")
        counts = self.repository.counts(identity)
        return {"seed": seed, "counts": counts, "active_policy_version": policy.version}

    def demo_summary(self, identity: Identity) -> dict[str, Any]:
        active, _ = self.repository.get_policies(identity)
        proposals = self.repository.list_proposals(identity)
        pending = next((proposal for proposal in proposals if proposal.state == "pending"), None)
        latest = self.repository.latest_decision(identity)
        return {
            "counts": self.repository.counts(identity),
            "active_policy": active,
            "pending_proposal": pending,
            "latest_decision": latest,
        }

    async def create_memory(self, identity: Identity, request: MemoryCreate) -> Memory:
        if request.supersedes and not self.repository.get_memory(identity, request.supersedes):
            raise NotFoundError("superseded memory not found in this tenant and agent scope")
        trace_model = self.embedder.model_name
        try:
            embedding = await self.embedder.embed(request.content)
        except DependencyError:
            embedding = await self.fallback_embedder.embed(request.content)
            trace_model = self.fallback_embedder.model_name
        now = utc_now()
        memory = Memory(
            id=self._id("mem"),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            content=request.content,
            type=request.type,
            provenance=request.provenance,
            confidence=request.confidence,
            status="active",
            supersedes=request.supersedes,
            created_at=now,
            updated_at=now,
            embedding_model=trace_model,
            embedding=embedding,
        )
        self.repository.insert_memory(memory)
        self.repository.insert_audit(
            AuditEvent(
                id=self._id("aud"),
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                event_type="memory.created",
                actor="api",
                subject_id=memory.id,
                details={"type": memory.type, "embedding_model": memory.embedding_model},
                created_at=now,
            )
        )
        return memory

    async def list_memories(
        self,
        identity: Identity,
        memory_type: str | None,
        status: str | None,
        limit: int,
        query: str | None,
    ) -> tuple[list[Memory], int]:
        embedding: list[float] | None = None
        if query:
            try:
                embedding = await self.embedder.embed(query)
            except DependencyError:
                embedding = await self.fallback_embedder.embed(query)
        memories, total, _ = self.repository.list_memories(
            identity,
            memory_type=memory_type,
            status=status,
            limit=limit,
            query=query,
            query_embedding=embedding,
        )
        return memories, total

    async def recommend(self, identity: Identity, request: RecommendationRequest) -> RecommendationResponse:
        started = time.perf_counter()
        active, _ = self.repository.get_policies(identity)
        if active is None:
            raise ConflictError("no active policy; reset the demo or approve a policy first")
        trace: list[dict[str, Any]] = []
        try:
            query_embedding = await self.embedder.embed(request.scenario)
            embedding_model = self.embedder.model_name
            trace.append({"tool": "embed", "status": "ok", "model": embedding_model})
        except DependencyError as exc:
            query_embedding = await self.fallback_embedder.embed(request.scenario)
            embedding_model = self.fallback_embedder.model_name
            trace.append({"tool": "embed", "status": "fallback", "reason": str(exc), "model": embedding_model})
        memories, _, retrieval_mode = self.repository.list_memories(
            identity,
            status="active",
            limit=RECALL_LIMIT,
            query=request.scenario,
            query_embedding=query_embedding,
        )
        trace.append(
            {
                "tool": "memory_retrieval",
                "status": "fallback" if retrieval_mode == "lexical-fallback" else "ok",
                "backend": retrieval_mode,
                "count": len(memories),
                "limit": RECALL_LIMIT,
                "vector_calls": 1 if retrieval_mode == "atlas-vector" else 0,
            }
        )
        trace.append({"tool": "active_policy", "status": "ok", "policy_id": active.id, "version": active.version})
        zero_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}
        model_name = self.chat_model.model_name
        try:
            recommendation, rationale = await self.chat_model.recommend(
                request.scenario, request.customer, active, memories
            )
            usage = dict(getattr(self.chat_model, "last_usage", None) or zero_usage)
            violation = invented_terms(recommendation)
            if violation:
                # Output guardrail: the policy forbids invented terms, so regenerate once.
                recommendation, rationale = await self.chat_model.recommend(
                    request.scenario + RETRY_NOTE, request.customer, active, memories
                )
                retry_usage = getattr(self.chat_model, "last_usage", None) or zero_usage
                usage = {key: usage.get(key, 0) + retry_usage.get(key, 0) for key in zero_usage}
                trace.append(
                    {
                        "tool": "guardrail",
                        "status": "retried",
                        "violation": violation,
                        "resolved": invented_terms(recommendation) is None,
                    }
                )
            trace.append({"tool": "chat", "status": "ok", "model": model_name, "usage": usage})
        except DependencyError as exc:
            recommendation, rationale = await self.fallback_chat.recommend(
                request.scenario, request.customer, active, memories
            )
            model_name = self.fallback_chat.model_name
            trace.append(
                {
                    "tool": "chat",
                    "status": "fallback",
                    "reason": str(exc),
                    "model": model_name,
                    "usage": zero_usage,
                }
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        decision = Decision(
            id=self._id("dec"),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            scenario=request.scenario,
            customer=request.customer,
            recommendation=recommendation,
            rationale=rationale,
            policy_id=active.id,
            policy_version=active.version,
            cited_memory_ids=[memory.id for memory in memories],
            tool_trace=trace,
            model=model_name,
            latency_ms=latency_ms,
            created_at=utc_now(),
        )
        self.repository.insert_decision(decision)
        self.repository.insert_audit(
            AuditEvent(
                id=self._id("aud"),
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                event_type="decision.created",
                actor="agent",
                decision_id=decision.id,
                subject_id=decision.id,
                details={
                    "policy_version": active.version,
                    "memory_ids": decision.cited_memory_ids,
                    "model": decision.model,
                    "latency_ms": decision.latency_ms,
                    "tool_trace": decision.tool_trace,
                },
                created_at=decision.created_at,
            )
        )
        return RecommendationResponse(
            decision_id=decision.id,
            recommendation=decision.recommendation,
            rationale=decision.rationale,
            policy_version=decision.policy_version,
            cited_memory_ids=decision.cited_memory_ids,
            tool_trace=decision.tool_trace,
            latency_ms=decision.latency_ms,
        )

    def record_outcome(self, identity: Identity, request: OutcomeCreate) -> Outcome:
        decision = self.repository.get_decision(identity, request.decision_id)
        if decision is None:
            raise NotFoundError("decision not found in this tenant and agent scope")
        now = utc_now()
        outcome = Outcome(
            id=self._id("out"),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            decision_id=request.decision_id,
            result=request.result.strip().lower(),
            metrics=request.metrics,
            elapsed_seconds=request.elapsed_seconds,
            created_at=now,
        )
        self.repository.insert_outcome(outcome)
        self.repository.insert_audit(
            AuditEvent(
                id=self._id("aud"),
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                event_type="outcome.recorded",
                actor="api",
                decision_id=decision.id,
                subject_id=outcome.id,
                details={"result": outcome.result},
                created_at=now,
            )
        )
        return outcome

    def analyze_proposals(self, identity: Identity) -> dict[str, Any]:
        pending = next((p for p in self.repository.list_proposals(identity) if p.state == "pending"), None)
        if pending:
            return {"proposal": pending, "reason": "an existing proposal is awaiting a human decision"}
        return self._analyze_proposals(identity)

    def _analyze_proposals(
        self,
        identity: Identity,
        *,
        proposal_id: str | None = None,
        audit_id: str | None = None,
        created_at: datetime | None = None,
    ) -> dict[str, Any]:
        active, _ = self.repository.get_policies(identity)
        if active is None:
            return {"proposal": None, "reason": "no active policy"}
        outcomes_by_decision: dict[str, Outcome] = {}
        for outcome in self.repository.list_outcomes(identity):
            decision = self.repository.get_decision(identity, outcome.decision_id)
            if decision is not None and decision.policy_id == active.id:
                outcomes_by_decision.setdefault(outcome.decision_id, outcome)
        outcomes = list(outcomes_by_decision.values())
        if len(outcomes) < 3:
            return {
                "proposal": None,
                "reason": "at least three outcomes under the active policy are required",
            }
        failures = [outcome for outcome in outcomes if outcome.result.lower() in FAILURE_RESULTS]
        failure_rate = len(failures) / len(outcomes)
        if failure_rate < 0.6:
            return {"proposal": None, "reason": "the deterministic failure threshold was not met"}
        now = created_at or utc_now()
        fixture_metrics = next(
            (
                outcome.metrics
                for outcome in failures
                if outcome.metrics.get("fixture_source") == "data/demo/manifest.json"
            ),
            None,
        )
        if fixture_metrics:
            proposed_rule = (
                "For financing questions, share verified financing-path information right away. "
                "For pricing objections, explain value against the customer's stated needs instead of "
                "leading with a discount. Do not tailor replies to the lead source; that evidence is insufficient. "
                "Never invent rates, payments, or discounts."
            )
            expected_effect = (
                "Apply the two strong synthetic cohort findings: fast financing information improved success "
                f"by {float(fixture_metrics['financing_success_lift']):.1%}, and needs-based pricing "
                "explanations improved success over discount-first replies by "
                f"{float(fixture_metrics['pricing_explanation_success_lift']):.1%}."
            )
            confidence = 0.84
        else:
            proposed_rule = (
                f"{active.rule.rstrip('.')} Require a human checkpoint when repeated failures are detected."
            )
            expected_effect = "Reduce recurrence of the measured failure pattern."
            confidence = round(min(0.95, 0.5 + failure_rate / 2), 2)
        proposal = GuardrailProposal(
            id=proposal_id or self._id("prop"),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            base_policy_id=active.id,
            base_policy_version=active.version,
            state="pending",
            current_rule=active.rule,
            proposed_rule=proposed_rule,
            evidence=[outcome.id for outcome in failures[:10]],
            expected_effect=expected_effect,
            confidence=confidence,
            risk=active.risk,
            approval_required=True,
            created_at=now,
        )
        self.repository.insert_proposal(proposal)
        self.repository.insert_audit(
            AuditEvent(
                id=audit_id or self._id("aud"),
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                event_type="proposal.created",
                actor="analyzer",
                subject_id=proposal.id,
                details={
                    "failure_rate": failure_rate,
                    "evidence_ids": proposal.evidence,
                    "analysis_source": (
                        "deterministic-fixture-aggregate" if fixture_metrics else "recorded-outcomes"
                    ),
                },
                created_at=now,
            )
        )
        return {"proposal": proposal, "reason": "failure threshold met"}

    def decide_proposal(
        self, identity: Identity, proposal_id: str, request: ProposalDecisionRequest
    ) -> dict[str, Any]:
        proposal = next((p for p in self.repository.list_proposals(identity) if p.id == proposal_id), None)
        if proposal is None:
            raise NotFoundError("proposal not found")
        if proposal.state != "pending":
            raise ConflictError(f"proposal is already {proposal.state}")
        now = utc_now()
        decided = proposal.model_copy(update={"state": "approved" if request.decision == "approve" else "rejected", "decided_at": now})
        next_policy: Policy | None = None
        if request.decision == "approve":
            active, _ = self.repository.get_policies(identity)
            if active is None:
                raise ConflictError("no active policy to supersede")
            if active.id != proposal.base_policy_id or active.version != proposal.base_policy_version:
                raise ConflictError("active policy changed; analyze a new proposal")
            next_policy = Policy(
                id=self._id("pol"),
                logical_policy_id=active.logical_policy_id,
                organization_id=identity.organization_id,
                agent_id=identity.agent_id,
                version=active.version + 1,
                status="active",
                rule=proposal.proposed_rule,
                risk=proposal.risk,
                evidence_ids=proposal.evidence,
                proposal_id=proposal.id,
                approval=Approval(
                    decision="approve",
                    actor=request.actor,
                    note=request.note,
                    decided_at=now,
                ),
                created_at=now,
            )
        audit = AuditEvent(
            id=self._id("aud"),
            organization_id=identity.organization_id,
            agent_id=identity.agent_id,
            event_type=f"proposal.{decided.state}",
            actor=request.actor,
            subject_id=proposal.id,
            details={
                "note": request.note,
                "new_policy_id": next_policy.id if next_policy else None,
                "new_policy_version": next_policy.version if next_policy else None,
            },
            created_at=now,
        )
        decided, next_policy = self.repository.decide_proposal(
            identity, proposal_id, decided, next_policy, audit
        )
        return {"proposal": decided, "policy": next_policy}

    def explanation(self, identity: Identity, decision_id: str) -> dict[str, Any]:
        decision = self.repository.get_decision(identity, decision_id)
        if decision is None:
            raise NotFoundError("decision not found")
        active, history = self.repository.get_policies(identity)
        decision_policy = next((policy for policy in history if policy.id == decision.policy_id), None)
        logical_policy_id = decision_policy.logical_policy_id if decision_policy else ""
        policy_chain = sorted(
            [policy for policy in history if policy.logical_policy_id == logical_policy_id],
            key=lambda policy: policy.version,
        )
        prior = next(
            (policy for policy in reversed(policy_chain) if policy.version < decision.policy_version),
            None,
        )
        later = next(
            (policy for policy in policy_chain if policy.version > decision.policy_version),
            None,
        )
        if decision_policy and decision_policy.approval:
            before = prior
            after = decision_policy
        else:
            before = decision_policy
            after = later
        memories = [
            memory
            for memory_id in decision.cited_memory_ids
            if (memory := self.repository.get_memory(identity, memory_id)) is not None
        ]
        evidence_outcome_ids = set(after.evidence_ids) if after else set()
        outcomes = [
            outcome
            for outcome in self.repository.list_outcomes(identity)
            if outcome.decision_id == decision.id or outcome.id in evidence_outcome_ids
        ]
        audits = self.repository.list_audit(identity, decision_id=decision.id, limit=100)
        outcome_ids = {outcome.id for outcome in outcomes} | evidence_outcome_ids
        related_proposal_ids = {
            proposal.id
            for proposal in self.repository.list_proposals(identity)
            if outcome_ids.intersection(proposal.evidence)
        }
        if after and after.proposal_id:
            related_proposal_ids.add(after.proposal_id)
        if related_proposal_ids:
            related_audits = [
                event
                for event in self.repository.list_audit(identity, limit=500)
                if event.subject_id in related_proposal_ids
            ]
            known_ids = {event.id for event in audits}
            audits.extend(event for event in related_audits if event.id not in known_ids)
            audits.sort(key=lambda event: (event.created_at, event.id), reverse=True)
        approval = after.approval if after else None
        summary = (
            f"Decision {decision.id} used policy v{decision.policy_version} and "
            f"{len(memories)} persisted memor{'y' if len(memories) == 1 else 'ies'}."
        )
        if after and after.approval:
            summary += (
                f" Human approval by {after.approval.actor} activated policy v{after.version} "
                "from the recorded outcome evidence."
            )
        return {
            "decision_id": decision.id,
            "summary": summary,
            "before": before,
            "after": after,
            "policy_chain": policy_chain,
            "memories": memories,
            "outcomes": outcomes,
            "approval": approval,
            "audit_event_ids": [event.id for event in audits],
        }
