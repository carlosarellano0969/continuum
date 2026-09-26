# Continuum V1 Windows demo runbook

This runbook is the verified local path: React and FastAPI run on Windows, Ollama supplies chat and embeddings, and persistence is process-local unless Atlas is configured. Atlas is covered separately in [`ATLAS_SETUP.md`](ATLAS_SETUP.md).

## One-time setup

Use PowerShell from the repository root.

### 1. Verify prerequisites

```powershell
python --version
node --version
npm --version
ollama --version
```

Python must be 3.11 or newer. If the Ollama API is not already running, start `ollama serve` in its own PowerShell window.

### 2. Pull the exact models

```powershell
ollama pull gpt-oss:20b
ollama pull nomic-embed-text:latest
ollama list
```

Do not swap model tags on demo day: stored memory metadata and the Atlas index assume that the same embedding model is used for documents and queries.

### 3. Create local configuration

```powershell
Copy-Item .env.example .env
notepad .env
```

For the verified local-only mode, use these values and leave `MONGODB_URI` blank:

```dotenv
MONGODB_URI=
MONGODB_DATABASE=continuum_v1
MONGODB_VECTOR_INDEX=memory_embedding_index

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=gpt-oss:20b
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
OLLAMA_CONTEXT_WINDOW=4096
OLLAMA_MAX_OUTPUT_TOKENS=512
OLLAMA_REASONING_EFFORT=low
OLLAMA_TIMEOUT_SECONDS=60

CONTINUUM_ORG_ID=demo-org
CONTINUUM_AGENT_ID=demo-agent
CONTINUUM_DEMO_SEED=20260924
CONTINUUM_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

The API sends at most one policy and five memories to the model. A 4,096-token context gives the current demo enough prompt capacity while limiting KV-cache memory and keeping local inference latency predictable. It is the current verified choice; increase it only after re-running latency and resource checks.

### 4. Install the API and web dependencies

```powershell
Set-Location services\api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Set-Location ..\..

Set-Location apps\web
npm ci
Set-Location ..\..
```

## Warm Ollama before presenting

Pulling downloads the models; warming loads them and verifies their interfaces. Run this shortly before the demo.

```powershell
$embedBody = @{
  model = 'nomic-embed-text:latest'
  input = 'Continuum demo warm-up'
} | ConvertTo-Json
$embed = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:11434/api/embed' `
  -ContentType 'application/json' -Body $embedBody -TimeoutSec 60
if ($embed.embeddings[0].Count -ne 768) {
  throw "Expected 768 embedding dimensions; received $($embed.embeddings[0].Count)."
}

$schema = @{
  type = 'object'
  properties = @{
    recommendation = @{ type = 'string' }
    rationale = @{ type = 'string' }
  }
  required = @('recommendation', 'rationale')
  additionalProperties = $false
}
$chatBody = @{
  model = 'gpt-oss:20b'
  stream = $false
  think = 'low'
  format = $schema
  messages = @(@{
    role = 'user'
    content = 'Return recommendation READY and rationale READY.'
  })
  options = @{ temperature = 0; num_ctx = 4096; num_predict = 64 }
} | ConvertTo-Json -Depth 10
$chat = Invoke-RestMethod -Method Post `
  -Uri 'http://127.0.0.1:11434/api/chat' `
  -ContentType 'application/json' -Body $chatBody -TimeoutSec 120
$chat.message.content
```

The last line should contain a JSON object with `READY` values.

## Start the application

### Terminal 1: API

From the repository root:

```powershell
.\services\api\.venv\Scripts\python.exe -m uvicorn continuum_api.main:app `
  --app-dir services\api --host 127.0.0.1 --port 8000 --env-file .env
```

### Terminal 2: web

```powershell
Set-Location apps\web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api'
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173`.

## Preflight and reset

In a third PowerShell window at the repository root:

```powershell
$health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 70
$health | ConvertTo-Json -Depth 6

if ($health.services.api -ne 'ok') { throw 'API health failed.' }
if ($health.services.ollama -ne 'ok') { throw 'Ollama health failed.' }
if ($health.services.embedding_model -ne 'ok') { throw 'Embedding model health failed.' }
if ($health.services.chat_model -ne 'ok') { throw 'Chat model health failed.' }

.\services\api\.venv\Scripts\python.exe scripts\reset_demo.py `
  --base-url http://127.0.0.1:8000/api --seed 20260924 --with-summary
```

In local-only mode, `mongodb: unconfigured` and the yellow **Local-only mode** banner are expected and honest. The model fields should identify `nomic-embed-text:latest` and `gpt-oss:20b`. Refresh the browser after a command-line reset, or click **Reset demo** in the top bar.

Final presentation checks:

- `demo-org / demo-agent` is visible in the top bar.
- The one-page evidence loop shows **Decide**, **Explain**, **Remember**, and **Govern** together.
- **Decide** shows policy v1 active.
- **Govern** has one pending proposal.
- The proposal contrasts generic discount-first behavior with fast, verified financing information.
- No credentials, personal information, or invented financial terms appear on screen.

## Three-minute demo script

| Time | Action | What to say |
|---|---|---|
| 0:00–0:20 | Show the top-bar identity and System status. | “Continuum is an inspectable memory and policy layer. Every read is scoped to this organization and agent.” |
| 0:20–0:55 | Follow the evidence-loop rail to **Remember** and point to the financing and discount-first evidence. | “The agent remembers measured outcomes, not just chat history. The source and confidence stay attached.” |
| 0:55–1:25 | Continue to **Govern** and compare the current and proposed rules. | “Repeated failures produced a proposal, but the model cannot activate it. A human must decide.” |
| 1:25–1:40 | Click **Approve change**. | “Approval creates immutable policy v2 and an append-only audit event; it does not rewrite v1.” |
| 1:40–2:20 | Follow the rail to **Decide**, keep the financing scenario, and click **Generate recommendation**. | “The agent retrieves at most five scoped memories and exactly one active policy, then records the decision and citations.” |
| 2:20–2:50 | Click **Why did you change your mind?** to focus **Explain** on the same page. | “Here is the before/after policy chain, cited memory, measured outcomes, human approval, and audit linkage.” |
| 2:50–3:00 | Point to policy v2 and close. | “Continuum lets an agent adapt from evidence without silently changing its own guardrails.” |

If the live model is cold, do not fill the silence with extra clicks. Say that the request is bounded and inspectable, then let it complete.

## Degraded and unconfigured behavior

| Condition | Health/UI behavior | Request behavior |
|---|---|---|
| `MONGODB_URI` blank | `mongodb: unconfigured`; Local-only mode banner | Uses deterministic process-local storage. Data disappears when the API process stops. |
| Atlas URI unreachable during startup | Application startup fails with a bounded dependency error | Fix the Atlas URI, network access, or credentials and restart; the API never silently switches to process-local storage. |
| Atlas fails after startup | Health can become degraded | Affected database operations return a bounded JSON error, normally HTTP 503. |
| `OLLAMA_BASE_URL` blank | Ollama/model states unconfigured | Embeddings and recommendations use deterministic fallbacks marked `fallback` in `tool_trace`. |
| Ollama is configured but unavailable | Ollama/model states degraded | The API waits only for its configured timeout, then returns a trace-marked deterministic fallback. |
| Atlas Vector Search index is missing or wrong | MongoDB can still report `ok` | Scoped memory queries degrade to lexical ranking. Check that the index is `READY`; health alone does not prove vector search. |
| API is stopped | Web shows **Connection needs attention** | Start the API and click **Try again**. |

For a predictable non-model rehearsal, set `OLLAMA_BASE_URL=` in `.env` and restart the API. Never present fallback output as a live Ollama result.

## Test commands

Run from the repository root unless a command changes directories:

```powershell
# API
Set-Location services\api
.\.venv\Scripts\python.exe -m pytest
Set-Location ..\..

# Web
Set-Location apps\web
npm run test
npm run lint
npm run typecheck
npm run build
Set-Location ..\..

# Deterministic fixtures, reset client, and black-box API contract
$env:CONTINUUM_ACCEPTANCE_BASE_URL = 'http://127.0.0.1:8000/api'
$env:CONTINUUM_ACCEPTANCE_REQUIRE_API = '1'
$env:CONTINUUM_ACCEPTANCE_MODEL_TIMEOUT_SECONDS = '75'
.\services\api\.venv\Scripts\python.exe -m unittest discover -s tests\acceptance -v
```

Use `Ctrl+C` in the API and web terminals to stop them.
