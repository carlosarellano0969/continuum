# Continuum

## Pitch

Continuum is an inspectable memory and policy layer for long-running agents. Built on MongoDB Atlas, it answers the critical question: **Why did you change your mind?** by tying every recommendation to retrieved memories, active policy versions, measured outcomes, and human approval events. The **Harness Bench** proves the value: three arms (out-of-the-box, context-stuffing, continuum) on the same task set show how memory and policy reduce cost, latency, and token usage while improving correctness on deterministic, auditable grounds.

## What We Built Today

- **Atlas Sandbox persistence**: Memories, policies, outcomes, audit events, and bench results stored in MongoDB with `$vectorSearch` filters and tenant scoping.
- **Hosted embeddings**: Voyage `voyage-4-large` (1024 dimensions) via `ai.mongodb.com`, replacing local Ollama.
- **OpenRouter chat adapter**: `openai/gpt-oss-20b` via OpenRouter, temperature 0, bounded 4K context.
- **Harness Bench**: Three inference arms on 12 synthetic deterministic tasks; metrics per run: cost, wall latency, vector calls, tokens, correctness %. Stored in Atlas, queryable via `/api/bench/runs`.
- **Vercel deployment**: Single unified service (Vite web + Python serverless API) with environment-driven provider selection.
- **CI/CD**: GitHub Actions for build and type checking on every push.

## Links

- **Live URL**: <DEPLOYED_URL>
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
