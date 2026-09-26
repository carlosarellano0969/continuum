# Continuum V1 architecture

```text
React/Vite browser
        |
        v
FastAPI contract and state enforcement
   |              |                 |
   v              v                 v
MongoDB Atlas   Ollama chat       Ollama embeddings
documents +     gpt-oss:20b       nomic-embed-text
Vector Search
```

## Trust boundaries

- Browser requests are untrusted and validated by Pydantic models.
- The model selects from explicit tools but never receives database credentials and never changes policy state directly.
- API code injects organization and agent scope into every query.
- Human approval is a validated application transition that writes an append-only audit event.
- Policy versions, outcomes, and audit events are immutable records.

## Decision loop

1. Retrieve up to five semantically relevant memories under exact tenant/type filters.
2. Read the one active policy with an exact query.
3. Ask the local model for a structured recommendation grounded in those records.
4. Persist the decision, citations, model identity, tool trace, and latency.
5. Record a later outcome and aggregate comparable results deterministically.
6. Create a bounded proposal; require a human decision.
7. On approval, create a new policy version and preserve the full explanation chain.

## Failure strategy

- Health reports distinguish unconfigured dependencies from runtime failures.
- Ollama and Atlas calls use bounded timeouts.
- Missing `MONGODB_URI` intentionally selects the deterministic, process-local repository. A configured Atlas backend fails application startup if initialization cannot complete, and later MongoDB operation failures surface as dependency errors; neither condition silently switches to memory.
- Deterministic fake repositories/models support contract tests, but the demo is accepted only after a live Atlas/Ollama path is measured.
- Reset deletes and recreates records only within the configured demo tenant.
