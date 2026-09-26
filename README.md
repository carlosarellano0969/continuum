# Continuum V1

Continuum is an inspectable memory and policy layer for long-running agents. V1.1 presents the complete Decide → Explain → Remember → Govern evidence loop on one responsive page. The web application, API, generative model, and embeddings run locally and can persist evidence and vector-searchable memories in MongoDB Atlas when Atlas is configured.

The signature experience answers: **Why did you change your mind?** It ties the answer to immutable policy versions, retrieved memories, measured outcomes, and the human approval that authorized the change.

## Status

The Windows local path is implemented and verified with:

- React/Vite in the browser;
- FastAPI and Pydantic locally;
- `gpt-oss:20b` and `nomic-embed-text:latest` through Ollama; and
- deterministic process-local persistence when Atlas is not configured.

The application currently bounds Ollama chat to a 4,096-token context, 512 output tokens, and low reasoning effort. This is the rehearsed V1 demo setting, not the model's maximum context.

**Atlas live verification is pending.** The Atlas adapter and Vector Search query path are implemented, but they must not be described as verified until cluster connectivity and index setup succeed and the checklist in [`docs/ATLAS_SETUP.md`](docs/ATLAS_SETUP.md) passes against a live cluster.

## Runtime

- Web: React, TypeScript, Vite
- API: FastAPI, Pydantic, PyMongo
- Model: `gpt-oss:20b` through Ollama
- Embeddings: `nomic-embed-text:latest` through Ollama, 768 dimensions
- Data: process-local deterministic repository by default; MongoDB Atlas with Vector Search when configured

## Windows quick start

Prerequisites are Python 3.11 or newer, Node.js/npm, and Ollama. From PowerShell in the repository root:

```powershell
ollama pull gpt-oss:20b
ollama pull nomic-embed-text:latest

Copy-Item .env.example .env
# For the verified local-only path, edit .env and leave MONGODB_URI blank.
notepad .env

Set-Location services\api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Set-Location ..\..

Set-Location apps\web
npm ci
Set-Location ..\..
```

Start the API in one PowerShell window:

```powershell
.\services\api\.venv\Scripts\python.exe -m uvicorn continuum_api.main:app `
  --app-dir services\api --host 127.0.0.1 --port 8000 --env-file .env
```

Start the web app in another:

```powershell
Set-Location apps\web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api'
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`. Before presenting, follow the model warm-up, reset, preflight, and three-minute script in [`docs/DEMO.md`](docs/DEMO.md).

Never commit `.env`, paste credentials into documentation, or claim Atlas verification from the in-memory fallback.

## Harness Bench

Compares the same task, same model, temperature 0, across three arms so judges can see what the memory layer buys:

- **`out_of_box`** — role + task only. No memory, no policy, no tools.
- **`context_stuffing`** — arm A plus the full `data/demo/interactions.jsonl` log serialized in file order, truncated to fit a ~4K-token budget (no retrieval, so relevance is luck of the file order).
- **`continuum`** — the real `ContinuumService.recommend` path: top-5 filtered recall plus the active policy, citing memory IDs and policy version.

`POST /api/bench/run` (`{arms?, repeats?}`) seeds the deterministic demo fixtures, runs 12 synthetic tasks per arm, and stores one document per run in `bench_runs` (Atlas when configured, else in-memory). `GET /api/bench/runs` lists the last 20 run summaries; `GET /api/bench/runs/{id}` returns the full row-level document. Every record is `synthetic: true`, and two runs with the same seed produce identical `correct` results per arm.

## Documentation

- `AGENTS.md` — contributor boundaries and verification rules
- `docs/API_CONTRACT.md` — frozen V1 HTTP interface
- `docs/ARCHITECTURE.md` — runtime and trust boundaries
- `docs/DEMO.md` — exact Windows runbook and three-minute demo
- `docs/ATLAS_SETUP.md` — Atlas credentials, Vector Search index, and live-verification gate

## Deploy

Continuum is deployed as a single unified service on Vercel (web app + API) with Render as the fallback API host.

### Required Environment Variables

Add these to the Vercel project settings (as plain environment variables in the UI):

- **MongoDB**: `MONGODB_URI`, `MONGODB_DATABASE`, `MONGODB_VECTOR_INDEX`
- **Models**: `MODEL_API_KEY`, `ENDPOINT`, `OPENROUTER_API_KEY`, `OPENROUTER_CHAT_MODEL`, `MODEL_PROVIDER=openrouter`, `EMBED_PROVIDER=voyage`, `EMBED_DIMENSIONS=1024`
- **CORS**: `CONTINUUM_CORS_ORIGINS` (set to the Vercel deployment URL, e.g., `https://continuum-app.vercel.app`)
- **Web**: `VITE_API_BASE_URL=/api` (relative path in production)

### Deploy to Vercel

1. Push this branch to GitHub.
2. In the [Vercel dashboard](https://vercel.com/dashboard), click **Add New Project**.
3. Import the GitHub repository.
4. Set the **Framework** to **Vite** and **Root Directory** to `.` (repository root).
5. Add the environment variables listed above.
6. Deploy.

The Vercel project will:
- Build the web app (`npm run build` in `apps/web`).
- Run the API as a Python serverless function (`api/index.py`).
- Rewrite `/api/*` requests to the serverless function.
- Serve the web app for all other requests.

### Fallback: Deploy API to Render

If Vercel deployment fails, deploy the API separately to Render:

1. Push to GitHub.
2. In [Render](https://render.com), create a new **Web Service**.
3. Connect your GitHub repository.
4. Set **Runtime** to **Python 3.12**.
5. Set **Start Command** to `uvicorn continuum_api.main:app --host 0.0.0.0 --port $PORT` (from `services/api`).
6. Set **Root Directory** to `services/api`.
7. Add the environment variables (MongoDB, model, CORS).
8. Deploy.

Then, update the web app to call the Render API URL:
```powershell
$env:VITE_API_BASE_URL = "https://your-render-app.onrender.com/api"
npm run build --prefix apps/web
```
