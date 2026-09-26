from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Identity(BaseModel):
    organization_id: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(min_length=1, max_length=200)


class MemoryCreate(StrictModel):
    content: str = Field(min_length=1, max_length=8_000)
    type: str = Field(min_length=1, max_length=80)
    provenance: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    supersedes: str | None = None

    @field_validator("content", "type", "provenance")
    @classmethod
    def no_blank_strings(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class Memory(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    content: str
    type: str
    provenance: str
    confidence: float
    status: str
    supersedes: str | None = None
    created_at: datetime
    updated_at: datetime
    embedding_model: str
    score: float | None = None
    embedding: list[float] = Field(default_factory=list, exclude=True)


class Approval(BaseModel):
    decision: Literal["approve", "reject"]
    actor: str
    note: str | None = None
    decided_at: datetime


class Policy(BaseModel):
    id: str
    logical_policy_id: str
    organization_id: str
    agent_id: str
    version: int = Field(ge=1)
    status: Literal["active", "inactive"]
    rule: str
    risk: str
    evidence_ids: list[str]
    proposal_id: str | None = None
    approval: Approval | None = None
    created_at: datetime


class GuardrailProposal(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    base_policy_id: str
    base_policy_version: int = Field(ge=1)
    state: Literal["pending", "approved", "rejected"]
    current_rule: str
    proposed_rule: str
    evidence: list[str]
    expected_effect: str
    confidence: float = Field(ge=0, le=1)
    risk: str
    approval_required: bool
    created_at: datetime
    decided_at: datetime | None = None


class ProposalDecisionRequest(StrictModel):
    decision: Literal["approve", "reject"]
    actor: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("actor")
    @classmethod
    def no_blank_actor(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RecommendationRequest(StrictModel):
    scenario: str = Field(min_length=1, max_length=8_000)
    customer: dict[str, Any] | None = None

    @field_validator("scenario")
    @classmethod
    def no_blank_scenario(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RecommendationResponse(BaseModel):
    decision_id: str
    recommendation: str
    rationale: str
    policy_version: int
    cited_memory_ids: list[str]
    tool_trace: list[dict[str, Any]]
    latency_ms: int


class Decision(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    scenario: str
    customer: dict[str, Any] | None = None
    recommendation: str
    rationale: str
    policy_id: str
    policy_version: int
    cited_memory_ids: list[str]
    tool_trace: list[dict[str, Any]]
    model: str
    latency_ms: int
    created_at: datetime


class OutcomeCreate(StrictModel):
    decision_id: str = Field(min_length=1)
    result: str = Field(min_length=1, max_length=100)
    metrics: dict[str, float | int | str | bool | None]
    elapsed_seconds: float | None = Field(default=None, ge=0)

    @field_validator("result")
    @classmethod
    def no_blank_result(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class Outcome(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    decision_id: str
    result: str
    metrics: dict[str, float | int | str | bool | None]
    elapsed_seconds: float | None = None
    created_at: datetime


class AuditEvent(BaseModel):
    id: str
    organization_id: str
    agent_id: str
    event_type: str
    actor: str
    decision_id: str | None = None
    subject_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class DemoResetRequest(StrictModel):
    seed: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "unconfigured"]
    version: str
    services: dict[str, str]
