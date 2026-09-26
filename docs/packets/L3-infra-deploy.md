# L3: Infra, deployed URL + CI (Claude Haiku 4.5; escalate to Sonnet 5 if stalled)

**Branch** `infra/L3-deploy`. **Paths you own:** `vercel.json`, `api/index.py` (new), root `requirements.txt`, `.github/workflows/ci.yml`, `apps/web/.env.production`, README "Deploy" section, `render.yaml` (fallback only). Do not edit application logic.
**Goal:** one public URL serving the web app and the API from the same Vercel project, hello-world by **12:45**; otherwise the API goes to Render (`render.yaml`) and the web stays on Vercel.

## Tasks
1. Vercel Python entry: `api/index.py` adds `services/api` to `sys.path` and exposes `from continuum_api.main import app`. `vercel.json`: builds for `apps/web` (Vite static, `outputDirectory: dist`) and `api/index.py` (`@vercel/python`); rewrites `/api/(.*)` → `/api/index.py`, everything else → the web app.
2. Env vars (Carlos sets them in the Vercel UI; list them in README): `MONGODB_URI`, `MONGODB_DATABASE`, `MONGODB_VECTOR_INDEX`, `MODEL_API_KEY`, `ENDPOINT`, `OPENROUTER_API_KEY`, `MODEL_PROVIDER=openrouter`, `EMBED_PROVIDER=voyage`, `CONTINUUM_CORS_ORIGINS=<vercel url>`, `VITE_API_BASE_URL=/api`.
3. CORS: allow the Vercel origin; the web uses a relative `/api` base in production.
4. CI (`ci.yml`): ruff + pytest in `services/api`; tsc + vitest + build in `apps/web`; secret scan (`python scripts/check_secrets.py` from Q1, or a grep for `mongodb+srv://` and `sk-or-` until it lands). Must pass on every PR.
5. Prove it: `GET /api/health` returns 200 from the deployed URL; the web loads and calls it.

## Constraints
One module-level pymongo client per process with `serverSelectionTimeoutMS=5000`; cold start under 10 s; no Ollama on the server; nothing from `Secrets/` in the repo.

## Done when
Deployed URL in the PR description; health 200; CI green on the PR.

## Report (≤ 15 lines)
Status · URL · files changed · commands + results · open risks. PR title: `ci: Vercel deploy + CI [L3]`. One fix attempt per failure, then report.
