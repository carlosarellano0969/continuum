# Continuum V1 HTTP contract

Base URL: `/api`. JSON only. V1 demo identity defaults to `demo-org` / `demo-agent`; every repository operation must still apply both filters.

## Health and demo control

### `GET /health`

Returns `{ status, version, services: { api, mongodb, ollama, embedding_model, chat_model } }`. Dependency states are `ok`, `degraded`, or `unconfigured`.

When `MONGODB_URI` is absent, the API intentionally uses its deterministic, process-local repository and reports MongoDB as `unconfigured`. When `MONGODB_URI` is configured, Atlas initialization must succeed or application startup fails; later MongoDB operation failures surface as dependency errors and never switch the repository to memory.

### `POST /demo/reset`

Body: `{ seed?: number }`. Returns record counts and active policy version. Reset must be deterministic and idempotent for the configured demo tenant.

### `GET /demo/summary`

Returns counts, active policy, pending proposal, and latest decision for UI bootstrap.

## Memories and recommendation

### `GET /memories`

Query: `type?`, `status?`, `limit?`, `query?`. Returns `{ items: Memory[], total }`.

### `POST /memories`

Body: `{ content, type, provenance, confidence, supersedes? }`. Returns a typed `Memory` with generated ID, timestamps, status, and embedding metadata.

### `POST /recommendations`

Body: `{ scenario, customer?: object }`. Returns `{ decision_id, recommendation, rationale, policy_version, cited_memory_ids, tool_trace, latency_ms }`.

The service retrieves at most five filtered memories and one active policy. Deterministic model or embedding fallback, and lexical fallback when Atlas Vector Search is unavailable, are allowed only when clearly marked in `tool_trace`; none changes the configured repository backend.

### `GET /decisions/{decision_id}/explanation`

Returns `{ decision_id, summary, before?, after?, policy_chain, memories, outcomes, approval, audit_event_ids }`.

## Outcomes, policy, and proposals

### `POST /outcomes`

Body: `{ decision_id, result, metrics, elapsed_seconds? }`. Returns the immutable outcome.

### `GET /policies`

Returns `{ active, history }`; only one policy may be active for a logical policy ID.

### `GET /proposals`

Returns `{ items: GuardrailProposal[] }`.

### `POST /proposals/analyze`

Runs deterministic outcome aggregation and returns a qualifying proposal or `{ proposal: null, reason }`.

### `POST /proposals/{proposal_id}/decision`

Body: `{ decision: "approve" | "reject", actor, note? }`. Approval transactionally writes the next immutable policy version and deactivates the previous version. Rejection never changes policy.

## Audit

### `GET /audit-events`

Query: `decision_id?`, `event_type?`, `limit?`. Returns append-only events in reverse chronological order.

## Core shapes

`Memory`: `id`, `organization_id`, `agent_id`, `content`, `type`, `provenance`, `confidence`, `status`, `supersedes`, `created_at`, `updated_at`, `embedding_model`, optional `score`.

`Policy`: `id`, `logical_policy_id`, `organization_id`, `agent_id`, `version`, `status`, `rule`, `risk`, `evidence_ids`, `approval`, `created_at`.

`GuardrailProposal`: `id`, `state`, `current_rule`, `proposed_rule`, `evidence`, `expected_effect`, `confidence`, `risk`, `approval_required`, `created_at`, `decided_at`.

## Acceptance invariants

- Cross-organization and cross-agent reads return no data.
- Invalid proposal transitions return HTTP 409.
- Unconfigured model dependencies produce clear degraded/unconfigured behavior; configured Atlas initialization failure prevents startup, and later Atlas operation failures return a bounded dependency error.
- Evidence IDs in recommendations and explanations resolve to persisted records.
