# Continuum

## Pitch

Continuum is an inspectable memory and policy layer for long-running agents. Built on MongoDB Atlas, it answers the critical question: **Why did you change your mind?** by tying every recommendation to retrieved memories, active policy versions, measured outcomes, and human approval events. The **Harness Bench** proves the value: three arms (out-of-the-box, context-stuffing, continuum) on the same task set show how memory and policy reduce cost, latency, and token usage while improving correctness on deterministic, auditable grounds.

## What We Built Today

- **Atlas Sandbox persistence**: Memories, policies, outcomes, audit events, and bench results stored in MongoDB with `$vectorSearch` filters and tenant scoping.
- **Hosted embeddings**: Voyage `voyage-4-large` (1024 dimensions) via `ai.mongodb.com`, replacing local Ollama.
- **OpenRouter chat adapter**: `openai/gpt-oss-20b` via OpenRouter, temperature 0, bounded 4K context.
- **Harness Bench**: Three inference arms on 12 synthetic deterministic tasks; metrics per run: cost, wall latency, vector calls, tokens, correctness %. Stored in Atlas, queryable via `/api/bench/runs`.
- **Vercel deployment**: Single unified service (Vite web + Python serverless API) with environment-driven provider selection.
- **Harness report panel**: fifth UI panel with per-arm cost, wall time, vector calls, tokens and correctness, a live-run button, and each arm's answer text.
- **CI/CD**: GitHub Actions (API tests, web lint/typecheck/tests/build, secret scan) on every PR; acceptance suite passes against the deployed URL.

## Results (measured today)

Same model for every arm (`openai/gpt-oss-20b` via OpenRouter, temperature 0), same synthetic tasks, scored by the action label each arm names. Continuum is measured after its own loop: the seeded outcomes are analyzed and the resulting policy change is approved before any arm runs.

**Full task set (12 tasks, run against the Atlas Sandbox at 14:05):**

| Arm | Correct | Tokens | Cost |
|---|---|---|---|
| Out of the box (task only) | 83.3% | 4,983 | $0.0003 |
| Context stuffing (whole history in the prompt) | 91.7% | 56,000 | $0.0086 |
| **Continuum** (Atlas vector recall + approved policy) | **91.7%** | **8,265** | **$0.0020** |

Continuum matches the accuracy of stuffing the whole history into the prompt with 6.8x fewer tokens and 4.3x lower cost, and every answer cites the memory IDs and policy version behind it. The out-of-the-box agent is cheapest but misses the pricing-objection case and falls for the partner-directory distractor.

**Deployed URL, two consecutive live runs (3 tasks each):** identical correctness per arm (all 100%); Continuum did a real Atlas `$vectorSearch` on every task and used 2,483 tokens against 13,521 for context stuffing.

Caveat: in the 12-task run about half of Continuum's retrievals fell back to keyword search because the hosted embeddings key was rate-limited (3 requests/minute without a billing method); the deployed runs above had no fallbacks.

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
