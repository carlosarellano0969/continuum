# Demo and acceptance scripts

These scripts use only the Python standard library.

## Generate deterministic fixtures

```powershell
python scripts/generate_demo_data.py --seed 20260924 --count 360
```

`--count` accepts 200 through 1000 interactions. The command writes
`data/demo/interactions.jsonl`, `memories.jsonl`, `retrieval_cases.json`, and
`manifest.json`. Repeating the command with identical arguments produces
byte-identical files.

Run `python scripts/generate_demo_data.py --help` for all options.

## Generate the multi-week stress corpus

```powershell
python scripts/generate_synthetic_weeks.py --output-dir data/synthetic_weeks --days 30 --per-day 48
```

This additive corpus keeps `data/demo` unchanged. It deterministically models
14 baseline days under policy v1 followed by a policy-v2 adaptation phase,
retains nonpreferred controls, and writes weekly/phase trend summaries and an
interaction-file hash to its manifest.

## Run the harness bench against a live API

```powershell
python scripts/run_bench.py --base-url http://127.0.0.1:8000/api --task-limit 4
```

Calls `POST /api/bench/run` with a 900-second timeout (a full 3-arm, 12-task
run takes minutes), then prints one summary line per arm (correct %, cost to
4 decimals, wall, vector_calls, tokens) and the `run_id`. `--arms` takes a
comma list (default: all three) and `--repeats` repeats the task set per arm.

## Reset a running demo

```powershell
python scripts/reset_demo.py --with-summary
```

The default API base is `http://127.0.0.1:8000/api`. Override it with
`--base-url` or `CONTINUUM_API_BASE_URL`. The client has a bounded timeout and
returns a non-zero status with an actionable error when the API is unavailable.

Run `python scripts/reset_demo.py --help` for identity, seed, and timeout
options.

## Run owned checks

All service-independent checks (the HTTP suite skips when the API is absent):

```powershell
python -m unittest discover -s tests/acceptance -v
```

Black-box HTTP checks use a running API. If the default API is unavailable,
they skip unless `CONTINUUM_ACCEPTANCE_REQUIRE_API=1` is set:

```powershell
$env:CONTINUUM_ACCEPTANCE_BASE_URL = 'http://127.0.0.1:8000/api'
$env:CONTINUUM_ACCEPTANCE_REQUIRE_API = '1'
$env:CONTINUUM_ACCEPTANCE_MODEL_TIMEOUT_SECONDS = '75'
python -m unittest tests.acceptance.test_api_contract -v
```

The ordinary request timeout remains short so a missing API fails quickly. The
separate model timeout is bounded at 75 seconds because local Ollama inference
can take longer on a cold or resource-constrained machine.
