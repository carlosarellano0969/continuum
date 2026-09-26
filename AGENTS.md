# Continuum agent instructions

## Scope

Build only the approved V1: local React web, FastAPI API, Ollama model/embeddings, MongoDB Atlas memory/policy/outcome/audit path, deterministic demo data, and tests. Do not touch sibling workspace projects.

## Ownership

- `services/api/**`: API specialist
- `apps/web/**`: web specialist
- `scripts/**`, `data/demo/**`, `tests/acceptance/**`: data/eval specialist
- Root files, `docs/**`, integration, Kanban, lessons, Git, and cross-cutting contracts: root PM

Do not edit paths owned by another active specialist. Propose contract changes to the root PM instead of changing shared docs.

## Fixed interface

Read `docs/API_CONTRACT.md` before implementation. IDs are strings. Timestamps are UTC ISO 8601. API errors use `{ "detail": string }`. Demo defaults are `demo-org` and `demo-agent`.

## Token-efficiency cardinal rules

- Start with the user request, `git status --short`, and targeted `rg` results. Do not inventory or read the whole repository.
- Read a document only when its routing topic applies: API contract for HTTP changes, architecture for boundaries, Atlas setup for database work, demo guide for rehearsal, and the build plan only for scope changes.
- Prefer diffs and line ranges over whole files. Reuse verified facts from the current handoff instead of rediscovering them.
- Give every delegate exact owned paths, acceptance checks, and a bounded context packet. Never send the full repository by default.
- Use `TOKEN_EFFICIENCY_POLICY.md` only for orchestration, delegation, handoff, or cost-efficiency decisions; ordinary focused edits do not need to reread it.

## Engineering rules

- Keep tenant and agent scoping in application code and repository queries.
- Policy versions and audit events are immutable.
- The model may propose; application code validates state transitions and approvals.
- Do not log secrets, raw credentials, or private data.
- Support deterministic tests without an Atlas account; never claim Atlas verification until a live round trip passes.
- Add bounded timeouts and actionable failure states for Ollama and Atlas.
- Run the tests for owned code before handoff.

## Handoff format

Report changed files, commands/tests run, results, remaining risks, and any required integration work. Do not commit or push; the root PM owns repository history.
