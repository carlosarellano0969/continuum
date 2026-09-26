# Continuum API

Run from this directory after installing the package:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m uvicorn continuum_api.main:app --reload
```

When `MONGODB_URI` is absent, the API uses its deterministic, process-local repository. Requests default to the configured demo identity and can be scoped with `X-Organization-ID` and `X-Agent-ID` headers. Ollama failures are surfaced by health and produce a trace-marked deterministic recommendation fallback rather than a request crash.

