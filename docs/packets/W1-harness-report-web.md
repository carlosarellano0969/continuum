# W1: Harness report panel (Codex, Sol)

**Repo** `continuum/`, **branch** `web/W1-harness-report`. **Paths you own:** `apps/web/src/**` only (`App.tsx`, `api.ts`, new `HarnessReport.tsx`, `styles.css`, tests). Do not edit `services/api`.
**Context:** the one-page UI has four panels (Decide · Explain · Remember · Govern). Add a fifth, **Harness report**, fed by `GET /api/bench/runs` and `POST /api/bench/run`. Stub the JSON until L2 merges.

## Contract (from L2)
```
run = { run_id, ts, model, seed,
  arms: [{ arm: "out_of_box" | "context_stuffing" | "continuum",
           cost_usd, wall_ms, vector_calls, tokens, correct_pct,
           display: { cost: "$0.26", wall: "2m 55s", vector_calls: "5", tokens: "4,251" } }],
  rows: [{ arm, task_id, action, expected_action, correct, wall_ms, total_tokens,
           cost_usd, vector_calls, policy_version, memory_ids }] }
```

## UI
- Three arm cards side by side, each showing exactly `Cost $0.26 · Wall 2m 55s · Vector calls 5 · Tokens 4,251` plus correct %. Labels: "Out of the box", "Context stuffing", "Continuum".
- "Run bench" button: disabled while running, shows elapsed seconds, then refreshes the list.
- Row table filterable by arm; `memory_ids` and `policy_version` render as links that focus the Remember/Explain panels (reuse the existing anchor and focus helpers). Show the run's Atlas document id.
- Header provenance from `/api/health`: "Atlas Sandbox", "OpenRouter <model>", "voyage-4-large"; a red **fallback** badge if any trace has `fallback=true`.
- Keep the no-remote-fonts rule, no new dependencies, no page overflow at 390 / 768 / 1440 px.

## Tests
vitest: display formatting and one render test with the stub run.

## Done when
`npm run lint`, typecheck, `npm test`, `npm run build` pass; screenshots at 1440 and 390 px attached to the PR.

## Report (≤ 15 lines)
Status · files changed · commands + results · open risks. PR title: `feat(web): Harness report panel [W1]`. One fix attempt per failure, then report.
