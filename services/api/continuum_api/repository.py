from __future__ import annotations

import math
import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Protocol

from .errors import ConflictError, DependencyError, NotFoundError
from .models import (
    AuditEvent,
    Decision,
    GuardrailProposal,
    Identity,
    Memory,
    Outcome,
    Policy,
)


COLLECTIONS = ("memories", "policies", "decisions", "outcomes", "proposals", "audit_events")


class Repository(Protocol):
    backend_name: str

    def health(self) -> str: ...
    def reset_scope(self, identity: Identity, records: dict[str, list[Any]]) -> dict[str, int]: ...
    def insert_memory(self, memory: Memory) -> Memory: ...
    def get_memory(self, identity: Identity, memory_id: str) -> Memory | None: ...
    def list_memories(
        self,
        identity: Identity,
        *,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        query: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Memory], int, str]: ...
    def insert_decision(self, decision: Decision) -> Decision: ...
    def get_decision(self, identity: Identity, decision_id: str) -> Decision | None: ...
    def latest_decision(self, identity: Identity) -> Decision | None: ...
    def insert_outcome(self, outcome: Outcome) -> Outcome: ...
    def list_outcomes(self, identity: Identity, decision_id: str | None = None) -> list[Outcome]: ...
    def get_policies(self, identity: Identity) -> tuple[Policy | None, list[Policy]]: ...
    def insert_proposal(self, proposal: GuardrailProposal) -> GuardrailProposal: ...
    def list_proposals(self, identity: Identity) -> list[GuardrailProposal]: ...
    def decide_proposal(
        self,
        identity: Identity,
        proposal_id: str,
        proposal: GuardrailProposal,
        policy: Policy | None,
        audit: AuditEvent,
    ) -> tuple[GuardrailProposal, Policy | None]: ...
    def insert_audit(self, event: AuditEvent) -> AuditEvent: ...
    def list_audit(
        self,
        identity: Identity,
        *,
        decision_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]: ...
    def counts(self, identity: Identity) -> dict[str, int]: ...


def _words(value: str) -> set[str]:
    return {word.strip(".,:;!?()[]{}\"'").lower() for word in value.split() if word.strip()}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / denominator if denominator else 0.0


class InMemoryRepository:
    """Thread-safe deterministic repository used for tests and unconfigured mode."""

    backend_name = "memory"

    def __init__(self, health_state: str = "unconfigured") -> None:
        self._data: dict[str, dict[str, Any]] = {name: {} for name in COLLECTIONS}
        self._lock = threading.RLock()
        self._health_state = health_state

    def health(self) -> str:
        return self._health_state

    @staticmethod
    def _in_scope(record: Any, identity: Identity) -> bool:
        return record.organization_id == identity.organization_id and record.agent_id == identity.agent_id

    def reset_scope(self, identity: Identity, records: dict[str, list[Any]]) -> dict[str, int]:
        with self._lock:
            for name in COLLECTIONS:
                self._data[name] = {
                    key: value
                    for key, value in self._data[name].items()
                    if not self._in_scope(value, identity)
                }
                for record in records.get(name, []):
                    self._data[name][record.id] = deepcopy(record)
            return self.counts(identity)

    def insert_memory(self, memory: Memory) -> Memory:
        with self._lock:
            if memory.supersedes:
                prior = self._data["memories"].get(memory.supersedes)
                if prior is None or not self._in_scope(prior, Identity(
                    organization_id=memory.organization_id,
                    agent_id=memory.agent_id,
                )):
                    raise ConflictError("superseded memory changed or is outside this scope")
                self._data["memories"][prior.id] = prior.model_copy(
                    update={"status": "inactive", "updated_at": memory.created_at}
                )
            self._data["memories"][memory.id] = deepcopy(memory)
        return memory

    def get_memory(self, identity: Identity, memory_id: str) -> Memory | None:
        record = self._data["memories"].get(memory_id)
        return deepcopy(record) if record and self._in_scope(record, identity) else None

    def list_memories(
        self,
        identity: Identity,
        *,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        query: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Memory], int, str]:
        records = [
            deepcopy(record)
            for record in self._data["memories"].values()
            if self._in_scope(record, identity)
            and (memory_type is None or record.type == memory_type)
            and (status is None or record.status == status)
        ]
        total = len(records)
        if query:
            query_words = _words(query)
            for record in records:
                lexical = len(query_words & _words(record.content)) / max(len(query_words), 1)
                semantic = _cosine(query_embedding or [], record.embedding)
                record.score = round(max(lexical, semantic), 6)
            records.sort(key=lambda item: (item.score or 0.0, item.created_at, item.id), reverse=True)
        else:
            records.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return records[:limit], total, "local-hybrid" if query else "recency"

    def insert_decision(self, decision: Decision) -> Decision:
        with self._lock:
            policy = self._data["policies"].get(decision.policy_id)
            if policy is None or policy.status != "active":
                raise ConflictError("policy changed while the recommendation was being generated")
            if any(memory_id not in self._data["memories"] for memory_id in decision.cited_memory_ids):
                raise ConflictError("memory set changed while the recommendation was being generated")
            self._data["decisions"][decision.id] = deepcopy(decision)
        return decision

    def get_decision(self, identity: Identity, decision_id: str) -> Decision | None:
        record = self._data["decisions"].get(decision_id)
        return deepcopy(record) if record and self._in_scope(record, identity) else None

    def latest_decision(self, identity: Identity) -> Decision | None:
        records = [v for v in self._data["decisions"].values() if self._in_scope(v, identity)]
        return deepcopy(max(records, key=lambda item: (item.created_at, item.id))) if records else None

    def insert_outcome(self, outcome: Outcome) -> Outcome:
        with self._lock:
            self._data["outcomes"][outcome.id] = deepcopy(outcome)
        return outcome

    def list_outcomes(self, identity: Identity, decision_id: str | None = None) -> list[Outcome]:
        records = [
            deepcopy(v)
            for v in self._data["outcomes"].values()
            if self._in_scope(v, identity) and (decision_id is None or v.decision_id == decision_id)
        ]
        return sorted(records, key=lambda item: (item.created_at, item.id), reverse=True)

    def get_policies(self, identity: Identity) -> tuple[Policy | None, list[Policy]]:
        history = [deepcopy(v) for v in self._data["policies"].values() if self._in_scope(v, identity)]
        history.sort(key=lambda item: (item.version, item.created_at), reverse=True)
        active = next((policy for policy in history if policy.status == "active"), None)
        return active, history

    def insert_proposal(self, proposal: GuardrailProposal) -> GuardrailProposal:
        with self._lock:
            if any(
                item.state == "pending"
                and self._in_scope(
                    item,
                    Identity(
                        organization_id=proposal.organization_id,
                        agent_id=proposal.agent_id,
                    ),
                )
                for item in self._data["proposals"].values()
            ):
                raise ConflictError("a proposal is already awaiting a human decision")
            self._data["proposals"][proposal.id] = deepcopy(proposal)
        return proposal

    def list_proposals(self, identity: Identity) -> list[GuardrailProposal]:
        records = [deepcopy(v) for v in self._data["proposals"].values() if self._in_scope(v, identity)]
        return sorted(records, key=lambda item: (item.created_at, item.id), reverse=True)

    def decide_proposal(
        self,
        identity: Identity,
        proposal_id: str,
        proposal: GuardrailProposal,
        policy: Policy | None,
        audit: AuditEvent,
    ) -> tuple[GuardrailProposal, Policy | None]:
        with self._lock:
            current = self._data["proposals"].get(proposal_id)
            if current is None or not self._in_scope(current, identity):
                raise NotFoundError("proposal not found")
            if current.state != "pending":
                raise ConflictError(f"proposal is already {current.state}")
            if policy is not None:
                active, _ = self.get_policies(identity)
                if (
                    active is None
                    or active.id != current.base_policy_id
                    or active.version != current.base_policy_version
                    or policy.version != active.version + 1
                ):
                    raise ConflictError("active policy changed; analyze a new proposal")
                self._data["policies"][active.id] = active.model_copy(update={"status": "inactive"})
                self._data["policies"][policy.id] = deepcopy(policy)
            self._data["proposals"][proposal.id] = deepcopy(proposal)
            self._data["audit_events"][audit.id] = deepcopy(audit)
        return proposal, policy

    def insert_audit(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            self._data["audit_events"][event.id] = deepcopy(event)
        return event

    def list_audit(
        self,
        identity: Identity,
        *,
        decision_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        records = [
            deepcopy(v)
            for v in self._data["audit_events"].values()
            if self._in_scope(v, identity)
            and (decision_id is None or v.decision_id == decision_id)
            and (event_type is None or v.event_type == event_type)
        ]
        records.sort(key=lambda item: (item.created_at, item.id), reverse=True)
        return records[:limit]

    def counts(self, identity: Identity) -> dict[str, int]:
        return {
            name: sum(1 for record in self._data[name].values() if self._in_scope(record, identity))
            for name in COLLECTIONS
        }


class MongoRepository:
    """MongoDB Atlas implementation. All queries include organization and agent scope."""

    backend_name = "mongodb"

    def __init__(self, uri: str, database: str, vector_index: str, timeout_ms: int = 4_000) -> None:
        try:
            from pymongo import ASCENDING, DESCENDING, MongoClient
        except ImportError as exc:  # pragma: no cover - packaging guard
            raise DependencyError("pymongo is required when MONGODB_URI is configured") from exc
        self._ascending = ASCENDING
        self._descending = DESCENDING
        self._client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            appname="continuum-v1",
            tz_aware=True,
        )
        self._db = self._client[database]
        self._vector_index = vector_index
        self._ensure_indexes()

    @staticmethod
    def _scope(identity: Identity) -> dict[str, str]:
        return {"organization_id": identity.organization_id, "agent_id": identity.agent_id}

    @staticmethod
    def _document(record: Any) -> dict[str, Any]:
        document = record.model_dump(mode="python", exclude_none=False)
        # Memory embeddings are intentionally excluded from API serialization,
        # but Atlas must persist them for $vectorSearch.
        if isinstance(record, Memory):
            document["embedding"] = list(record.embedding)
        return document

    def _ensure_indexes(self) -> None:
        scoped = [("organization_id", self._ascending), ("agent_id", self._ascending)]
        for name in COLLECTIONS:
            self._db[name].create_index(scoped + [("id", self._ascending)], unique=True)
        self._db.policies.create_index(
            scoped + [("logical_policy_id", self._ascending), ("version", self._ascending)], unique=True
        )
        self._db.policies.create_index(
            scoped + [("logical_policy_id", self._ascending)],
            unique=True,
            partialFilterExpression={"status": "active"},
            name="one_active_policy",
        )
        self._db.proposals.create_index(
            scoped,
            unique=True,
            partialFilterExpression={"state": "pending"},
            name="one_pending_proposal",
        )

    def health(self) -> str:
        try:
            self._client.admin.command("ping")
            return "ok"
        except Exception:
            return "degraded"

    def reset_scope(self, identity: Identity, records: dict[str, list[Any]]) -> dict[str, int]:
        scope = self._scope(identity)
        try:
            with self._client.start_session() as session:
                with session.start_transaction():
                    for name in COLLECTIONS:
                        self._db[name].delete_many(scope, session=session)
                        documents = [self._document(record) for record in records.get(name, [])]
                        if documents:
                            self._db[name].insert_many(documents, ordered=True, session=session)
            return {name: len(records.get(name, [])) for name in COLLECTIONS}
        except Exception as exc:
            raise DependencyError(f"MongoDB demo reset failed: {exc.__class__.__name__}") from exc

    def insert_memory(self, memory: Memory) -> Memory:
        scope = {"organization_id": memory.organization_id, "agent_id": memory.agent_id}
        try:
            with self._client.start_session() as session:
                with session.start_transaction():
                    if memory.supersedes:
                        replaced = self._db.memories.update_one(
                            {**scope, "id": memory.supersedes, "status": "active"},
                            {"$set": {"status": "inactive", "updated_at": memory.created_at}},
                            session=session,
                        )
                        if replaced.modified_count != 1:
                            raise ConflictError("superseded memory changed or is outside this scope")
                    self._db.memories.insert_one(self._document(memory), session=session)
        except ConflictError:
            raise
        except Exception as exc:
            raise DependencyError(f"MongoDB memory write failed: {exc.__class__.__name__}") from exc
        return memory

    def get_memory(self, identity: Identity, memory_id: str) -> Memory | None:
        doc = self._db.memories.find_one({**self._scope(identity), "id": memory_id}, {"_id": 0})
        return Memory.model_validate(doc) if doc else None

    def list_memories(
        self,
        identity: Identity,
        *,
        memory_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        query: str | None = None,
        query_embedding: list[float] | None = None,
    ) -> tuple[list[Memory], int, str]:
        match: dict[str, Any] = self._scope(identity)
        if memory_type:
            match["type"] = memory_type
        if status:
            match["status"] = status
        total = self._db.memories.count_documents(match)
        if query and query_embedding:
            try:
                pipeline = [
                    {
                        "$vectorSearch": {
                            "index": self._vector_index,
                            "path": "embedding",
                            "queryVector": query_embedding,
                            "numCandidates": max(50, limit * 10),
                            "limit": limit,
                            "filter": {"$and": [{key: value} for key, value in match.items()]},
                        }
                    },
                    {"$set": {"score": {"$meta": "vectorSearchScore"}}},
                    {"$project": {"_id": 0}},
                ]
                return (
                    [Memory.model_validate(doc) for doc in self._db.memories.aggregate(pipeline)],
                    total,
                    "atlas-vector",
                )
            except Exception:
                # Preserve demo availability, but callers must surface this fallback.
                retrieval_mode = "lexical-fallback"
        else:
            retrieval_mode = "recency"
        candidate_limit = min(1_000, max(100, limit * 20)) if query else limit
        docs = list(
            self._db.memories.find(match, {"_id": 0})
            .sort("created_at", self._descending)
            .limit(candidate_limit)
        )
        records = [Memory.model_validate(doc) for doc in docs]
        if query:
            query_words = _words(query)
            for record in records:
                record.score = len(query_words & _words(record.content)) / max(len(query_words), 1)
            records.sort(key=lambda item: (item.score or 0.0, item.created_at), reverse=True)
        return records[:limit], total, retrieval_mode

    def insert_decision(self, decision: Decision) -> Decision:
        scope = {"organization_id": decision.organization_id, "agent_id": decision.agent_id}
        try:
            with self._client.start_session() as session:
                with session.start_transaction():
                    policy = self._db.policies.count_documents(
                        {**scope, "id": decision.policy_id, "status": "active"},
                        session=session,
                    )
                    memories = self._db.memories.count_documents(
                        {**scope, "id": {"$in": decision.cited_memory_ids}},
                        session=session,
                    )
                    if policy != 1:
                        raise ConflictError("policy changed while the recommendation was being generated")
                    if memories != len(set(decision.cited_memory_ids)):
                        raise ConflictError("memory set changed while the recommendation was being generated")
                    self._db.decisions.insert_one(self._document(decision), session=session)
        except ConflictError:
            raise
        except Exception as exc:
            raise DependencyError(f"MongoDB decision write failed: {exc.__class__.__name__}") from exc
        return decision

    def get_decision(self, identity: Identity, decision_id: str) -> Decision | None:
        doc = self._db.decisions.find_one({**self._scope(identity), "id": decision_id}, {"_id": 0})
        return Decision.model_validate(doc) if doc else None

    def latest_decision(self, identity: Identity) -> Decision | None:
        doc = self._db.decisions.find_one(self._scope(identity), {"_id": 0}, sort=[("created_at", self._descending)])
        return Decision.model_validate(doc) if doc else None

    def insert_outcome(self, outcome: Outcome) -> Outcome:
        self._db.outcomes.insert_one(self._document(outcome))
        return outcome

    def list_outcomes(self, identity: Identity, decision_id: str | None = None) -> list[Outcome]:
        match: dict[str, Any] = self._scope(identity)
        if decision_id:
            match["decision_id"] = decision_id
        docs = self._db.outcomes.find(match, {"_id": 0}).sort("created_at", self._descending)
        return [Outcome.model_validate(doc) for doc in docs]

    def get_policies(self, identity: Identity) -> tuple[Policy | None, list[Policy]]:
        docs = list(self._db.policies.find(self._scope(identity), {"_id": 0}).sort("version", self._descending))
        history = [Policy.model_validate(doc) for doc in docs]
        return next((policy for policy in history if policy.status == "active"), None), history

    def insert_proposal(self, proposal: GuardrailProposal) -> GuardrailProposal:
        try:
            self._db.proposals.insert_one(self._document(proposal))
        except Exception as exc:
            try:
                from pymongo.errors import DuplicateKeyError
            except ImportError:  # pragma: no cover - dependency is declared
                DuplicateKeyError = ()  # type: ignore[assignment]
            if DuplicateKeyError and isinstance(exc, DuplicateKeyError):
                raise ConflictError("a proposal is already awaiting a human decision") from exc
            raise
        return proposal

    def list_proposals(self, identity: Identity) -> list[GuardrailProposal]:
        docs = self._db.proposals.find(self._scope(identity), {"_id": 0}).sort("created_at", self._descending)
        return [GuardrailProposal.model_validate(doc) for doc in docs]

    def decide_proposal(
        self,
        identity: Identity,
        proposal_id: str,
        proposal: GuardrailProposal,
        policy: Policy | None,
        audit: AuditEvent,
    ) -> tuple[GuardrailProposal, Policy | None]:
        from pymongo import ReturnDocument

        scope = self._scope(identity)
        try:
            with self._client.start_session() as session:
                with session.start_transaction():
                    current = self._db.proposals.find_one_and_update(
                        {**scope, "id": proposal_id, "state": "pending"},
                        {"$set": {"state": proposal.state, "decided_at": proposal.decided_at}},
                        projection={"_id": 0},
                        return_document=ReturnDocument.BEFORE,
                        session=session,
                    )
                    if current is None:
                        existing = self._db.proposals.find_one({**scope, "id": proposal_id}, session=session)
                        if existing:
                            raise ConflictError(f"proposal is already {existing['state']}")
                        raise NotFoundError("proposal not found")
                    if policy is not None:
                        result = self._db.policies.update_one(
                            {
                                **scope,
                                "id": proposal.base_policy_id,
                                "status": "active",
                                "version": proposal.base_policy_version,
                            },
                            {"$set": {"status": "inactive"}},
                            session=session,
                        )
                        if result.modified_count != 1:
                            raise ConflictError("active policy changed; analyze a new proposal")
                        self._db.policies.insert_one(self._document(policy), session=session)
                    self._db.audit_events.insert_one(self._document(audit), session=session)
        except (ConflictError, NotFoundError):
            raise
        except Exception as exc:
            raise DependencyError(f"MongoDB proposal transaction failed: {exc.__class__.__name__}") from exc
        return proposal, policy

    def insert_audit(self, event: AuditEvent) -> AuditEvent:
        self._db.audit_events.insert_one(self._document(event))
        return event

    def list_audit(
        self,
        identity: Identity,
        *,
        decision_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        match: dict[str, Any] = self._scope(identity)
        if decision_id:
            match["decision_id"] = decision_id
        if event_type:
            match["event_type"] = event_type
        docs = self._db.audit_events.find(match, {"_id": 0}).sort("created_at", self._descending).limit(limit)
        return [AuditEvent.model_validate(doc) for doc in docs]

    def counts(self, identity: Identity) -> dict[str, int]:
        scope = self._scope(identity)
        return {name: self._db[name].count_documents(scope) for name in COLLECTIONS}
