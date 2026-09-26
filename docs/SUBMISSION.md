# Continuum

## Pitch

Continuum is an inspectable memory and policy layer for long-running agents. Built on MongoDB Atlas, it answers the critical question: **Why did you change your mind?** by tying every recommendation to retrieved memories, active policy versions, measured outcomes, and human approval events. The **Harness Bench** proves the value: three arms (out-of-the-box, context-stuffing, continuum) on the same task set show how memory and policy reduce cost, latency, and token usage while improving correctness on deterministic, auditable grounds.

## What We Built Today

- **Atlas Sandbox persistence**: Memories, policies, outcomes, audit events, and bench results stored in MongoDB with `$vectorSearch` filters and tenant scoping.
- **Hosted embeddings**: Voyage `voyage-4-large` (1024 dimensions) via `ai.mongodb.com`, replacing local Ollama.
- **OpenRouter chat adapter**: `openai/gpt-oss-20b` via OpenRouter, temperature 0, bounded 4K context.
- **Harness Bench**: Three inference arms on 12 synthetic deterministic tasks; metrics per run: cost, wall latency, vector calls, tokens, correctness %. Stored in Atlas, queryable via `/api/bench/runs`.
- **Vercel deployment**: Single unified service (Vite web + Python serverless API) with environment-driven provider selection.
- **Harness report panel**: fifth UI panel with per-arm cost, wall time, vector calls, tokens, correctness, unsafe answers and tokens per correct answer, a live-run button, and each arm's answer text.
- **Output guardrail**: Continuum checks every recommendation for invented rates, prices or durations and regenerates once, recorded in the decision trace.
- **CI/CD**: GitHub Actions (API tests, web lint/typecheck/tests/build, secret scan) on every PR; acceptance suite passes against the deployed URL.

## Results (measured today)

Same model for every arm (`openai/gpt-oss-20b` via OpenRouter, temperature 0), same 12 synthetic tasks, scored by the action label each arm names. The tasks are cases where the right move depends on this organization's recorded outcomes: financing questions, pricing objections, and a partner-directory lead whose apparent uplift is not supported by enough evidence.

- **Out of the box:** the raw model with the task and answer format only.
- **Context stuffing:** the model plus the whole interaction history in the prompt.
- **Continuum:** Atlas vector recall of 3 memories, the approved policy version, and an output guardrail that regenerates any answer stating invented rates, prices or durations. Measured after its own loop: the seeded outcomes are analyzed and the policy change is approved before any arm runs.

**Live run, 12 tasks (run `bench_d672ac01…` in Atlas `bench_runs`):**

| Arm | Correct | Unsafe answers | Tokens | Tokens per correct answer | Atlas vector searches |
|---|---|---|---|---|---|
| Out of the box | 66.7% | 0 | 3,926 | 491 | 0 |
| Context stuffing | 91.7% | 0 | 58,103 | 5,282 | 0 |
| **Continuum** | **100%** | **0** | **8,003** | **667** | **12** |

- Continuum gets every case right. The raw model misses a third of them: it defers financing questions and tailors replies to the lead source, the opposite of what this organization's outcomes support.
- Against stuffing the whole history into the prompt, Continuum is more accurate with 7x fewer tokens and 8x fewer tokens per correct answer.
- Against the raw model, Continuum spends about 1.4x the tokens per correct answer. That premium buys the memory, the policy and the guardrail, and every answer cites the memory IDs and policy version behind it.
- Earlier runs caught the raw model and Continuum inventing a warranty length or a "0%" rate. Continuum's guardrail now regenerates those answers; the raw model has no such check.
- Dollar cost is recorded per call from OpenRouter, but it varies with the provider OpenRouter picks for each request, so tokens are the stable cost measure.

## Links

- **Live URL**: https://continuum-five-red.vercel.app
- **Repository**: https://github.com/carlosarellano0969/continuum
- **Architecture diagram**: docs/diagrams/03-architecture.svg
- **Harness diagram**: docs/diagrams/04-harness-bench.svg
- **Provenance (PRs + timing)**: docs/PROVENANCE.md
- **API routes**: `/api/health`, `/api/recommendations`, `/api/memories`, `/api/bench/run`, `/api/bench/runs`, `/api/bench/runs/{id}`, `/api/policies`, `/api/proposals`, `/api/proposals/analyze`, `/api/proposals/{id}/decision`, `/api/audit-events`, `/api/demo/reset`

## MongoDB Features Used

- **Atlas Sandbox cluster** (free tier, Sandbox environment)
- **Vector Search** with Voyage 1024-dim embeddings, tenant/type filter aggregation
- **Transactions** for approval state (policy version creation)
- **Atlas Search indexes** on memory type and status
- **Append-only audit collection** for compliance and explanation

## Partner Tools Used

- **OpenRouter** (hosted chat model endpoint)
- **ai.mongodb.com** (MongoDB-hosted Voyage embeddings)
- **Vercel** (web hosting + serverless Python)
- **GitHub Actions** (CI)

## Team

- **Carlos Arellano** (solo dev). All implementation, architecture, testing, docs, and deployment in this session.

## AI Tooling Disclosure

- **Claude Code** (Anthropic): Main dev harness, all lanes use it for investigation, planning, and implementation.
- **Codex agents** (Anthropic): Multi-agent orchestration for L1, L2, L3, W1, Q1 parallel tracks; all work visible in git history (PR #1–#3).
- **Language**: Python (FastAPI + Pydantic), TypeScript (React + Vite), standard library only for diagram generation.

---

All data is synthetic and labeled `synthetic: true` in every record. The demo is deterministic: same seed reproduces identical outcomes across runs. Git history from `kickoff` commit shows pre-event prototype; every commit after `kickoff` is event work.
