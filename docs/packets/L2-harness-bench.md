# L2: Harness Bench (Claude Sonnet 5)

**Branch** `api/L2-bench`. **Paths you own:** `services/api/continuum_api/bench.py` (new), `main.py` (three routes only), `models.py` (`Bench*` models only), `services/api/tests/test_bench.py`, `data/bench/tasks.json` (new), README section "Harness Bench". Do not edit `adapters.py` or `repository.py` (L1 owns them); consume the `ChatModel`/`Embedder`/`Repository` protocols.
**Purpose:** measure the same task under three harness arms with the same model, so judges see what the memory layer buys.

## Task set
`data/bench/tasks.json`: 12 scenarios drawn from `data/demo` fields (`source`, `concern`, `contact`, `day_of_week`) with `expected_action` from the designed patterns: `hospital_discharge + cost → same_day_call`; `physician + eligibility → email_checklist`; otherwise the policy default `mail_brochure`. Tuesday is a distractor with no effect. Four tasks per group. `synthetic: true` everywhere.

## Arms (same model, temperature 0)
- **A `out_of_box`:** system prompt = role + task. No memory, no policy, no tools.
- **B `context_stuffing`:** arm A plus the full `data/demo/interactions.jsonl` serialized into the prompt, truncated to the model context. First on the cut list.
- **C `continuum`:** the existing service recommendation path (top-5 filtered recall + active policy, citing memory IDs and policy version).

## Records
Per task per arm: `arm, task_id, model, action, expected_action, correct, wall_ms, prompt_tokens, completion_tokens, total_tokens, cost_usd, vector_calls, policy_version, memory_ids, ts, run_id`. `cost_usd` comes from the chat trace (0 for deterministic); `vector_calls` from `tool_trace.vector_calls` (0 for A/B).
Per arm aggregate: `cost_usd, wall_ms, vector_calls, tokens, correct_pct` plus `display: {cost: "$0.26", wall: "2m 55s", vector_calls: "5", tokens: "4,251"}`.
Storage: collection `bench_runs`, one document per run (`run_id, ts, model, seed, arms[], rows[]`), written through the repository's Mongo client, or an in-memory list when Atlas is off.

## Routes
`POST /api/bench/run` `{arms?: [...], repeats?: 1}` → run document. `GET /api/bench/runs` → last 20 summaries. `GET /api/bench/runs/{id}` → full document.

## Rules
Start on v1's `DeterministicChatModel`/`DeterministicEmbedder` so tests pass without keys; real numbers arrive when L1 merges. Same task order and seed every run: two runs must give identical `correct` per arm. Tests: scoring, aggregation, display formatting, one route test with the deterministic provider.

## Done when
`pytest` green; `POST /api/bench/run` returns 3 arms × 12 rows; `GET` lists it; README "Harness Bench" (10 lines) explains the arms.

## Report (≤ 15 lines)
Status · files changed · commands + results · sample aggregate per arm · open risks. PR title: `feat(api): Harness Bench [L2]`. One fix attempt per failing test, then report.
