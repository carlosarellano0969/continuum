# Continuum V4 architecture

```text
Browser (React/Vite)
        |
        v
Vercel (web + Python API function)
        |
        +---- MongoDB Atlas Sandbox ----+
        |     (memories + vector index, |
        |      policies, outcomes,      |
        |      audit, bench_runs)       |
        |                               |
        +---- OpenRouter API ------+
        |     (openai/gpt-oss-20b) |
        |                          |
        +---- ai.mongodb.com ------+
              (Voyage, 1024-dim)
```

## Harness Bench

Three inference arms on the same task suite, deterministic seeding, all synthetic:

| Arm | Context | Retrieval | Citations |
|---|---|---|---|
| **out_of_box** | Role + task only | none | none |
| **context_stuffing** | Role + task + full log (truncated) | none | none |
| **continuum** | Role + task + active policy | top-5 filtered | memory IDs + policy v |

Per run: cost, latency (wall), vector calls, tokens, correctness %. Stored in Atlas `bench_runs`.

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
- Atlas and model API calls use bounded timeouts.
- Missing `MONGODB_URI` intentionally selects the deterministic, process-local repository. A configured Atlas backend fails application startup if initialization cannot complete, and later MongoDB operation failures surface as dependency errors; neither condition silently switches to memory.
- Deterministic fake embedders and chat models support contract tests.
- Reset deletes and recreates records only within the configured demo tenant.
