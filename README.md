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

## Documentation

- `AGENTS.md` — contributor boundaries and verification rules
- `docs/API_CONTRACT.md` — frozen V1 HTTP interface
- `docs/ARCHITECTURE.md` — runtime and trust boundaries
- `docs/DEMO.md` — exact Windows runbook and three-minute demo
- `docs/ATLAS_SETUP.md` — Atlas credentials, Vector Search index, and live-verification gate
