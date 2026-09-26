# Continuum (hackathon repo)

@TOKEN_EFFICIENCY.md

- **Plan of record:** `../CONTINUUM_BUILD_PLAN.md` §0 (event-day v4). Board: https://claude.ai/artifact/WRbd3oR4jaKQKuF1jQcZ74 (PM writes; lanes report in their PR).
- **Your packet:** `docs/packets/<lane>.md`. Stay inside the paths it names. Never touch `Secrets/`, `.env`, or another lane's files.
- **Provenance:** first commit = pre-event prototype. Everything you write is event work; keep `docs/PROVENANCE.md` truthful.
- **Run:** API `services/api` (FastAPI, `.venv`), web `apps/web` (Vite). Tests: `pytest` in `services/api`, `pytest tests/acceptance` at root (needs API running), `npm test` in `apps/web`.
- **Today's rule:** no speculative refactors; one fix attempt per failing test, then report.
