# MongoDB Atlas setup and live-verification gate

> **Current state:** Atlas live verification is pending because this workspace does not yet have Atlas credentials. The local Ollama/in-memory build is verified; that does not verify Atlas persistence, transactions, or Vector Search.

Continuum uses database `continuum_v1`, collection `memories`, vector field `embedding`, and Vector Search index `memory_embedding_index`. Every application query includes both `organization_id` and `agent_id`.

## 1. Create Atlas access

In MongoDB Atlas:

1. Create or select a project and a cluster that supports MongoDB Vector Search.
2. Create a database user with only the access needed by this demo, including read/write access to `continuum_v1`.
3. Add the current development machine's public IP to the Atlas network access list. Do not use an unrestricted production allowlist.
4. Copy the driver connection string. URL-encode special characters in the username or password.

Use an organization-owned account for event work. Do not paste the URI into chat, screenshots, source files, shell output, or committed documentation.

## 2. Configure the application

Copy the example if `.env` does not already exist:

```powershell
Copy-Item .env.example .env
notepad .env
```

Set these values:

```dotenv
MONGODB_URI=mongodb+srv://<database-user>:<encoded-password>@<cluster-host>/?retryWrites=true&w=majority
MONGODB_DATABASE=continuum_v1
MONGODB_VECTOR_INDEX=memory_embedding_index
MONGODB_TIMEOUT_MS=4000

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=gpt-oss:20b
OLLAMA_EMBED_MODEL=nomic-embed-text:latest
OLLAMA_CONTEXT_WINDOW=4096
```

Never commit `.env`.

## 3. Seed Atlas through the API

Start the API from the repository root. `--env-file` is required here because the application intentionally reads environment variables rather than parsing `.env` itself.

```powershell
.\services\api\.venv\Scripts\python.exe -m uvicorn continuum_api.main:app `
  --app-dir services\api --host 127.0.0.1 --port 8000 --env-file .env
```

In another PowerShell window:

```powershell
$health = Invoke-RestMethod 'http://127.0.0.1:8000/api/health' -TimeoutSec 70
$health | ConvertTo-Json -Depth 6
if ($health.services.mongodb -ne 'ok') {
  throw 'Atlas is not healthy. Stop here; the API may be using its in-memory fallback.'
}
if ($health.services.ollama -ne 'ok' -or $health.services.embedding_model -ne 'ok') {
  throw 'Ollama embeddings are not healthy. Do not seed fallback vectors into Atlas.'
}

.\services\api\.venv\Scripts\python.exe scripts\reset_demo.py `
  --base-url http://127.0.0.1:8000/api --seed 20260924 --with-summary
```

The reset creates scoped documents and 768-dimensional `nomic-embed-text` embeddings in Atlas. Confirm in Atlas Data Explorer that `continuum_v1.memories` exists and that a memory document has an `embedding` array.

## 4. Create the Vector Search index

In Atlas Data Explorer, select `continuum_v1.memories`, open the Search Indexes view, choose **Create Search Index**, select **Vector Search** and the JSON editor, and name the index `memory_embedding_index`.

Use this definition:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 768,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "organization_id"
    },
    {
      "type": "filter",
      "path": "agent_id"
    },
    {
      "type": "filter",
      "path": "type"
    },
    {
      "type": "filter",
      "path": "status"
    }
  ]
}
```

The first two filter fields enforce the tenant and agent pre-filter used on every request. `type` and `status` are also indexed because the API can include them in the same `$vectorSearch.filter` expression. The 768 dimensions must match the local `nomic-embed-text:latest` output exactly.

Wait until Atlas reports the index as `READY`. Index creation is asynchronous.

The equivalent `mongosh` command is:

```javascript
use continuum_v1
db.memories.createSearchIndex(
  "memory_embedding_index",
  "vectorSearch",
  {
    fields: [
      { type: "vector", path: "embedding", numDimensions: 768, similarity: "cosine" },
      { type: "filter", path: "organization_id" },
      { type: "filter", path: "agent_id" },
      { type: "filter", path: "type" },
      { type: "filter", path: "status" }
    ]
  }
)
db.memories.getSearchIndexes()
```

See MongoDB's official [`createSearchIndex()` documentation](https://www.mongodb.com/docs/manual/reference/method/db.collection.createsearchindex/) and [Vector Search overview](https://www.mongodb.com/docs/vector-search/) for the current platform syntax and availability.

## 5. Prove a live vector round trip

Health and API results alone are not sufficient because Continuum deliberately falls back to scoped lexical ranking when the Vector Search index is missing or invalid.

Make `MONGODB_URI` available to the current PowerShell process through your approved secret-management method, then run this from the repository root. The command does not print the URI.

```powershell
@'
import os

import httpx
from pymongo import MongoClient

uri = os.environ["MONGODB_URI"]
vector = httpx.post(
    "http://127.0.0.1:11434/api/embed",
    json={"model": "nomic-embed-text:latest", "input": "financing monthly payment options"},
    timeout=60,
).json()["embeddings"][0]
assert len(vector) == 768, f"expected 768 dimensions, received {len(vector)}"

client = MongoClient(uri, serverSelectionTimeoutMS=4000)
collection = client["continuum_v1"]["memories"]
results = list(collection.aggregate([
    {
        "$vectorSearch": {
            "index": "memory_embedding_index",
            "path": "embedding",
            "queryVector": vector,
            "numCandidates": 50,
            "limit": 5,
            "filter": {
                "$and": [
                    {"organization_id": "demo-org"},
                    {"agent_id": "demo-agent"},
                    {"status": "active"},
                ]
            },
        }
    },
    {"$project": {"_id": 0, "id": 1, "organization_id": 1, "agent_id": 1, "score": {"$meta": "vectorSearchScore"}}},
]))
assert results, "Vector Search returned no demo records"
assert all(r["organization_id"] == "demo-org" and r["agent_id"] == "demo-agent" for r in results)
print({"dimensions": len(vector), "results": results})
'@ | .\services\api\.venv\Scripts\python.exe -
```

Then complete the application-level proof:

1. Reset the demo with seed `20260924`.
2. Stop and restart the API, without resetting.
3. Call `GET http://127.0.0.1:8000/api/demo/summary`; non-zero counts after restart prove the API is not using process-local storage.
4. Generate a financing recommendation in the UI.
5. Confirm its cited memory IDs resolve through `GET /api/memories` and its explanation chain resolves through `GET /api/decisions/{decision_id}/explanation`.
6. Approve the pending proposal and confirm policy v2 plus the approval audit event survive another restart.

Only after the index is `READY`, the direct `$vectorSearch` command succeeds, scoped records survive restart, and the full explanation/approval chain resolves may the team mark Atlas live verification complete.

## Troubleshooting without hiding failures

- `mongodb: unconfigured`: `MONGODB_URI` is blank or was not loaded. Check `--env-file .env`.
- `mongodb: degraded` at startup: the URI, database user, IP allowlist, DNS, TLS, or timeout is wrong. The API has fallen back to memory; do not continue an Atlas verification.
- API returns HTTP 503 after startup: Atlas became unavailable during an operation. Read the `{ "detail": "..." }` response and restore connectivity.
- Atlas is `ok` but semantic results look lexical: verify the exact index name, `READY` status, 768 dimensions, vector path, and all filter fields. Run the direct vector test above.
- Proposal approval fails only on Atlas: confirm the cluster supports transactions and that the database user can update policies, proposals, and audit events.
