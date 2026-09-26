# Continuum V1 Lessons Ledger

Status: **IN PROGRESS — V1 AUTHORIZED 2026-09-24**  
Owner: root PM agent  
Purpose: capture measured V1 results and convert them into event-day V2 decisions.

## How this ledger is used

Update after every milestone, meaningful failure, major performance result, or scope decision. Record evidence rather than impressions. Do not duplicate Kanban task status here.

## Baseline

| Item | Planned value |
|---|---|
| Application runtime | Local Windows workstation |
| Database | MongoDB Atlas |
| Generative model | `gpt-oss:20b` through Ollama |
| Embedding model | Local Ollama adapter; begin with `nomic-embed-text` |
| Initial context limit | 8K |
| Demo dataset | Deterministic synthetic interactions; optional CMS facility enrichment |
| Signature test | Policy approval changes replayed behavior and is fully explainable |

Initial environment check: Node 24.13.1, npm 11.8.0, Python 3.12.10, Git 2.53.0, Ollama 0.34.0. `nomic-embed-text` was installed; `gpt-oss:20b` was installed and checksum-verified during kickoff.

## Milestone findings

| Date/time | Milestone | Hypothesis | Observed result / metric | Root cause | Decision | V2 action | Evidence |
|---|---|---|---|---|---|---|---|
| 2026-09-24 kickoff | Local embedding smoke test | Installed `nomic-embed-text` will provide a stable local vector shape | 768 dimensions, 768 nonzero values, 4,233 ms cold request | Model cold load included in first request | Keep model; measure warm latency and configure Atlas index for 768 dimensions | Preload embeddings before demos and record warm benchmark | Ollama `/api/embed` response |
| 2026-09-24 kickoff | Local embedding warm benchmark | Warm embedding calls will be fast enough for interactive retrieval | 10/10 passed; mean 26 ms; observed P95 95 ms; stable 768 dimensions | Model remained resident after cold load | Keep `nomic-embed-text`; add startup warm-up | Configure Atlas vector index with 768 dimensions and cosine similarity | Ten sequential Ollama `/api/embed` calls |
| 2026-09-24 kickoff | Chat structured-output budget | A small output cap will be enough for strict JSON | A 200-token cap ended before answer content; 400 tokens produced valid JSON in 4.7 sec | `gpt-oss` spent completion tokens on reasoning before final content | Use low reasoning plus a bounded 512-token allowance and strict schema | Preserve a probe that rejects empty structured content | Ollama OpenAI-compatible endpoint |
| 2026-09-24 kickoff | 8K tool reliability | Local `gpt-oss:20b` can select typed tools reliably | 10/10 representative 8K calls had the correct tool and required arguments; mean 1,468 ms, P95 2,038 ms | Explicit schemas, required tool choice, and low reasoning | Keep local model/tool configuration | Run the same probe before event coding begins | Native Ollama tool-call suite |
| 2026-09-24 integration | Signature product loop | One focused agent can demonstrate governed adaptation | v1 recommendation -> proposal approval -> v2 recommendation -> explanation returned before/after policy, approver, 5 memories, 3 outcomes, and 2 audits | Application-owned state machine and immutable versions | Keep single-agent UX and signature question | Make this the first event-day vertical slice | Live FastAPI + Ollama + browser run |
| 2026-09-24 integration | Financial hallucination guardrail | Evidence-only prompt will prevent invented terms | Initial v2 run invented APR/payment examples; tightened prompt and policy then produced 0/10 unsafe numeric-term runs | Generic “do not invent evidence” was too weak for the financing scenario | Add explicit forbidden-term guardrail and safe handoff | Keep numeric-term regression check in event evals | Live run plus ten-run regex safety check |
| 2026-09-24 benchmark | 8K recommendation performance | Dual 3060 Ti system will meet the demo latency target with headroom | 10/10 real recommendations; mean 6,163.5 ms; P95 7,836 ms; zero fallback/OOM; only ~758 MB system RAM free at end | 14 GB model is 88% GPU / 12% CPU and both models stay resident; 8K KV/cache pressure reduces OS headroom | Change default demo context from 8K to 4K and remeasure | Close unnecessary apps; preload both models; retain 8K only as tested fallback | Ten sequential FastAPI recommendation calls plus `ollama ps`, GPU/RAM snapshot |
| 2026-09-24 benchmark | 4K recommendation comparison | Compact retrieval can preserve quality while restoring headroom | Cold load 33,961 ms; warm 10/10; mean 5,999.6 ms; P95 7,910 ms; zero fallback/OOM/unsafe-term runs; ~1,916 MB RAM free | Continuum needs far less than 4K prompt context; smaller KV/cache allocation returns about 1.16 GB of headroom with no material latency loss | Keep 4K as V1 and event default | Preload models before demo; expose 8K only as a measured fallback | Unloaded-model cold start followed by ten sequential live recommendations |
| 2026-09-24 final local verification | Reset-to-explanation rehearsal | The hardened signature flow will complete twice inside the three-minute presentation budget | Consecutive browser runs completed in 43.713 sec and 48.546 sec; embedded live-model latencies were 14.571 sec and 12.853 sec; both showed v1 -> human approval -> v2, 5 memories, 3 outcomes, 3 audit events, and no model/embedding fallback | Deterministic reset and fixture-driven proposal keep operator work bounded; warm local models dominate the remaining latency | Accept the local V1 demo path; do not treat it as Atlas verification | Preserve the same path and remeasure after Atlas is configured | Accessibility-backed browser runs against live FastAPI and Ollama |
| 2026-09-24 feedback follow-up | Multi-week synthetic corpus and UI polish | More temporal evidence and clearer dependency state will make the demo more credible | Ollama-reviewed 30-day blueprint expanded to 1,440 deterministic interactions; the repaired manifest and 6 corpus validators prove a day-15 v1→v2 shift, preferred policy-action growth from 25% to 62.5%, retained controls, and synthetic resolution movement from 64.58% to 75.52%; browser now says local-only mode explicitly and still records live Ollama provenance | The original fixture was intentionally small, the first stress manifest wrote an empty file list, the initial corpus labeled phases without changing behavior, and the old banner blurred unconfigured storage with model fallback | Keep the 360-row golden fixture, use the corrected stress corpus for temporal checks, and keep dependency state explicit in the UI | Exercise trend/retrieval/persistence under Atlas without presenting synthetic lifts as production claims | `data/synthetic_weeks`, 6 corpus validators, web suite, live browser smoke |
| 2026-09-24 V1.1 local rerun | One-page evidence loop | Putting the four product surfaces on one page will reduce navigation friction without weakening the governed signature flow | Decide, Explain, Remember, and Govern now coexist in one responsive DOM; 1440px, 768px, and 390px checks had no page overflow, explanation focus moved correctly, and the accessibility smoke found 0 duplicate IDs, unnamed buttons, or unlabeled inputs. Final consecutive reset-to-explanation runs were 42.287 sec and 50.152 sec with 14.854 sec and 26.451 sec live-model latency, 5 memories, 3 outcomes, 3 linked audits, and 0 model/embedding fallbacks. The full gate passed: 47 API tests at 80.04% exact coverage, 23 acceptance tests, web lint/typecheck/10 tests/build. | Conditional screen state hid the product relationship; replacing it with a numbered anchor rail and four persistent panels made the evidence loop legible. Local Ollama latency remains variable, so the black-box model request needs a separate 75-second bound. | Accept the local V1.1 demo path and use the one-page control room for the event outline; do not convert this into an Atlas-complete claim | Repeat the same flow against Atlas; run the corrected 1,440-row stress corpus through Atlas trend/retrieval/persistence checks before changing the 360-row golden demo seed | Live browser, API/web suites, CORS preflight, responsive DOM measurements |

## Performance scorecard

| Measure | V1 result | Target | Pass? | V2 decision |
|---|---:|---:|---|---|
| Valid tool/structured outputs | 10/10 (100%) at 8K | ≥95% | Pass | Retain schemas and preflight probe |
| P95 recommendation latency | 7.910 sec at 4K warm | ≤20 sec | Pass | Keep 4K; recheck on event host |
| GPU OOMs in ten sequential runs | 0; ~1.92 GB RAM free at 4K | 0 | Pass | Keep 4K; watch system RAM |
| Top-five retrieval hit rate | — | ≥80% | — | — |
| Tenant/filter isolation tests | 100% local repository/HTTP suite | 100% | Partial | Repeat against Atlas filters |
| Policy state-machine tests | 100%; 14 API tests pass | 100% | Pass locally | Repeat Atlas transaction path |
| Clean reset time | 2.554 sec measured local seed | <5 min | Pass | Add one-command startup/reset |
| Consecutive sub-three-minute demos | 2/2; 43.713 sec and 48.546 sec reset-to-explanation | 2 | Pass locally | Repeat after Atlas is configured; retain visible provenance checks |
| V1.1 one-page rehearsals | 2/2; 42.287 sec and 50.152 sec reset-to-explanation; live model 14.854 sec and 26.451 sec | 2 | Pass locally | Keep the one-page flow and 75-second bounded acceptance timeout; remeasure on event hardware |
| Primary screen changes during signature loop | 0; all four panels remain mounted on one route | 0 | Pass | Preserve anchor navigation and focused explanation handoff |

## Keep / change / cut / fallback

### Keep

- One focused agent with application-enforced tools and approvals.
- `gpt-oss:20b` plus `nomic-embed-text` through Ollama.
- Typed FastAPI contract, immutable policy history, and evidence-first UI.
- Deterministic 360-record golden demo dataset and safety labels, plus the separate 1,440-record/30-day stress corpus.

### Change

- Default context from 8K to 4K because the demo uses compact retrieval and 8K leaves too little RAM headroom.
- Explicitly prohibit invented rates, amounts, discounts, eligibility, and approvals in both prompt and policy.
- Refresh an open explanation immediately after approval so the UI cannot show stale policy state.
- Give live-model acceptance calls their own 75-second bound while keeping ordinary API-failure checks short.

### Cut

- Remote font dependency; use local/system fallbacks for venue resilience.
- Any UI or feature that does not strengthen the memory -> outcome -> approval -> explanation story.

### Fallbacks

- Deterministic chat and embedding adapters remain clearly trace-marked for development failures; never present a fallback result as a live-model/Atlas success.
- 4K context is the default; 8K is verified but memory-constrained.

## Ranked event-day improvements

| Priority | Improvement | Evidence | Expected impact | Owner | Acceptance |
|---:|---|---|---|---|---|
| 1 | One-command model/API/web warm-up and clean reset | Cold/resize costs and manual starts were measurable | Reduces demo risk and setup time | PM | Health ok, both models resident, reset under five minutes |
| 2 | Repeat isolation, vector retrieval, and approval transaction tests on Atlas | All current persistence results use the local repository | Converts the main unverified path into evidence | PM | Live insert/index/filter/query/approval suite passes |
| 3 | Keep explicit financing-term safety regression | Initial run invented APR/payment examples | Prevents unsafe-looking demo output | Eval owner | Zero forbidden numeric-term outputs in ten runs |
| 4 | Use 4K compact context unless event hardware proves more headroom | 8K ended with ~758 MB RAM free | Improves workstation stability | Runtime owner | Ten runs, zero OOM, improved free RAM |

## V1 conclusion

Local V1.1 verification is complete: 47 API tests pass with 80.04% exact coverage, the 23-test acceptance suite passes against the running API, web lint/typecheck/10 tests/production build pass, and the four-panel browser signature path completed twice under three minutes with live Ollama chat and embeddings and no fallback. The Atlas secrets file was found and loaded, but the configured SRV lookup timed out; live Atlas insert/index/vector/filter/restart/transaction verification and the Vector Search index therefore remain incomplete. No Git commit or remote provenance exists until the owner supplies Git identity, repository target/visibility, and explicit push authorization.
