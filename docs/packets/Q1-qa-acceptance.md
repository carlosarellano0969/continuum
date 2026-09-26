# Q1: QA, acceptance vs deployed URL, reset, secret scan (Codex, Luna)

**Repo** `continuum/`, **branch** `qa/Q1-acceptance`. **Paths you own:** `tests/acceptance/**`, `scripts/reset_demo.py`, `scripts/README.md`, `scripts/check_secrets.py` (new), `docs/DEMO.md` (acceptance matrix rows only). Do not change application code; file findings in the PR description with repro steps.

## Tasks
1. Parameterize the acceptance suite by `BASE_URL` (default `http://127.0.0.1:8000`). Keep the 75-second bound for live-model calls. Skip Atlas-only checks when `/api/health` reports mongodb unconfigured.
2. New acceptance cases: (a) restart persistence: write a memory, restart the API (or use a second process), the memory is still found through the API; (b) `POST /api/bench/run` returns 3 arms × 12 rows and a second run has identical `correct` per arm; (c) every `memory_id` and `policy_version` in an explanation resolves through the API; (d) no trace has `fallback=true` when providers are configured.
3. One-command reset: `python scripts/reset_demo.py --base-url $BASE_URL`, idempotent, prints elapsed time, finishes under 60 s against Atlas.
4. `scripts/check_secrets.py`: regex scan of the tree for `mongodb+srv://`, `sk-or-`, `Bearer [A-Za-z0-9]`, and `.env` contents; exit 1 on a hit. Hand the command to L3 for CI.
5. Run the suite against the local API now, and against the deployed URL once L3 posts it. Record pass/fail counts in the `docs/DEMO.md` acceptance matrix.

## Done when
Suite green locally; secret scan clean; DEMO.md matrix updated with counts and the URL used.

## Report (≤ 15 lines)
Status · files changed · commands + results (pass/fail counts) · findings · open risks. PR title: `test: acceptance vs BASE_URL, reset, secret scan [Q1]`. One fix attempt per failure, then report.
