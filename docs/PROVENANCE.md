# Provenance: what was built when

The hackathon rules require that judges can clearly identify the work created during the event. This file and the git history are that record.

## Built before the event (Sep 23–25, imported as the first commit, tag `kickoff`)

- Prototype **Continuum v1.1**: FastAPI + Pydantic API, React/Vite one-page UI (Decide · Explain · Remember · Govern), in-memory repository, Ollama adapters (`gpt-oss:20b`, `nomic-embed-text`), an unverified Atlas adapter, deterministic 360-row golden fixture and 1,440-row / 30-day synthetic corpus, 47 API tests, 23 acceptance tests, docs.
- Planning docs, diagrams, token-efficiency policy, Claude Code harness configuration.

## Built during the event (Sat Sep 26, every commit after `kickoff`)

| Item | Where | Status |
|---|---|---|
| Atlas-native persistence, `$vectorSearch` with tenant filters, restart persistence, approval transaction, verified on the Atlas Sandbox | `services/api/continuum_api/repository.py`, `docs/ATLAS_SETUP.md` | planned |
| Hosted model path: OpenRouter chat adapter, `voyage-4-large` embeddings via `ai.mongodb.com` (1024 dims) | `services/api/continuum_api/adapters.py` | planned |
| **Harness Bench**: same task set through out-of-the-box / context-stuffing / Continuum arms; cost, wall, vector calls, tokens, correctness per arm; stored in `bench_runs` | `services/api/continuum_api/bench.py`, `/api/bench/*` | planned |
| Harness report panel | `apps/web/src/` | planned |
| Deployed URL (Vercel), CI | `vercel.json`, `.github/workflows/` | planned |

Update the Status column as PRs merge. All data is synthetic and labeled `synthetic: true`.
