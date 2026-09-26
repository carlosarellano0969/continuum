# L1: Atlas + hosted models (Claude Sonnet 5)

**Branch** `api/L1-atlas-hosted`. **Paths you own:** `services/api/continuum_api/adapters.py`, `config.py`, `repository.py` (Mongo parts only), `services/api/tests/test_adapters.py`, `docs/ATLAS_SETUP.md`, `.env.example`. Do not touch `bench.py`, `apps/web`, `tests/acceptance`.
**Secrets:** read from env only. Locally the values live in `../Secrets/atlas-credentials.env` (`MONGODB_URI`, `ENDPOINT=ai.mongodb.com`, `MODEL_API_KEY`, `OPENROUTER_API_KEY`). Never print, log or commit them.
**Goal:** the v1 signature flow (reset → recommend → propose → approve → recommend → explain) runs on Atlas with hosted models, no Ollama, no fallback trace.

## Tasks
1. `VoyageEmbedder` implementing `Embedder`: `POST https://ai.mongodb.com/v1/embeddings` with `{"input": [...], "model": "voyage-4-large"}`, header `Authorization: Bearer <MODEL_API_KEY>`; returns `data[i].embedding` (1024 floats) and `usage.total_tokens`. Verified working at 11:30 today.
2. `OpenRouterChatModel` implementing `ChatModel`: OpenAI-compatible `POST https://openrouter.ai/api/v1/chat/completions`, model from `OPENROUTER_CHAT_MODEL` (default `openai/gpt-oss-20b`; fallback `anthropic/claude-haiku-4.5`). Keep v1's tool schemas, strict JSON, low reasoning, 512-token cap. Send `"usage": {"include": true}` and record `prompt_tokens`, `completion_tokens`, `cost` on the trace.
3. Config: `MODEL_PROVIDER=openrouter|ollama|deterministic`, `EMBED_PROVIDER=voyage|ollama|deterministic`, `EMBED_DIMENSIONS=1024`. `/api/health` reports provider and model names.
4. Repository: count `$vectorSearch` calls per request and expose `tool_trace.vector_calls: int` (L2 depends on this exact field name).
5. Atlas: change `docs/ATLAS_SETUP.md` to `numDimensions: 1024`; create the index (`create_search_index` or Atlas UI); verify insert → filtered `$vectorSearch` (org/agent/type) → API restart → memory still found → approval transaction commits v2.
6. Tests: unit tests with mocked HTTP for both adapters. Atlas tests marked `@pytest.mark.atlas`, skipped without `MONGODB_URI`.

## Done when
`pytest` green; `/api/health` shows mongodb ok, chat openrouter, embed voyage; the signature flow works from the local web app against Atlas with `fallback=false` on every trace.

## Commands
```
cd services/api && .venv/Scripts/python -m pytest -q
.venv/Scripts/python -m uvicorn continuum_api.main:app --port 8000 --env-file ../../.env
```

## Report (≤ 15 lines)
Status · files changed · commands + results · index name and dims · open risks. PR title: `feat(api): Atlas + hosted models [L1]`. One fix attempt per failing test, then report.
