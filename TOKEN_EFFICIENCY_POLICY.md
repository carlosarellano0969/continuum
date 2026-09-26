# Continuum token-efficiency policy

Status: active for all Codex, subagent, and local-model work in this repository.

Purpose: minimize repeated context, tool output, and model usage without weakening correctness. This policy is a router, not required reading for every small edit; the five cardinal rules in `AGENTS.md` apply automatically.

## 1. Session start: narrow before reading

Start with only:

1. The current user request or approved task packet.
2. `git status --short`.
3. Targeted `rg -n` hits for the relevant task IDs, symbols, routes, or filenames.
4. The latest compact handoff, if the session is a continuation.

Do not begin with a recursive repository inventory, the full build plan, every status document, or every source file. Expand context only when the first scoped search cannot answer the next decision.

## 2. Document routing

Read each document only for its matching work:

| Work | Read |
|---|---|
| HTTP route or public model change | `docs/API_CONTRACT.md` |
| Service boundary, trust, or data-flow change | `docs/ARCHITECTURE.md` |
| Atlas persistence or Vector Search | `docs/ATLAS_SETUP.md` |
| Demo, reset, rehearsal, or presentation | `docs/DEMO.md` |
| Scope, approval gate, or event sequencing | `CONTINUUM_BUILD_PLAN.md` in the parent folder |
| Benchmark or event-day decision | `V1_LESSONS.md` in the parent folder |
| Task state | Only the matching rows and latest relevant log lines in `KANBAN.md` |

Never require an agent to read all of these as boilerplate.

## 3. Source-reading rules

- Use `rg -n` or a file list before opening source.
- Read the smallest useful line range. Read a full file only when it is short or the change genuinely spans it.
- Inspect the current diff before rereading unchanged code.
- Do not paste large logs, generated assets, lockfiles, fixture corpora, build output, or secrets into prompts.
- Summarize tool output into decisions and evidence; do not carry raw output into the next session.

Default limits, adjustable when the task requires more:

- Initial session context: at most 4 files or 800 source lines.
- Delegate context: at most 6 named files and 16,000 characters of excerpts.
- Task packet: at most 350 words.
- Handoff: at most 900 words, plus exact commands and blockers.
- Tool output: request no more than 12,000 tokens; narrow and retry if truncated.

## 4. Delegation rules

Delegate only a concrete, independently verifiable unit. Every packet must state:

```text
Goal:
Owned paths:
Forbidden paths:
Inputs / assumptions:
Done when:
Commands to verify:
Return: changed files, results, risks, no duplicated project summary.
```

Parallel agents must not edit the same files. Reuse an agent that already knows a workstream when doing so is cheaper than spawning a fresh agent. The PM alone updates canonical scope, Kanban, lessons, and final integration state.

## 5. Local Ollama policy

Use local `gpt-oss:20b` through `scripts/invoke_ollama_worker.ps1` for bounded, low-risk work such as:

- reviewing a small diff;
- drafting tests, fixtures, or documentation from named files;
- finding edge cases in an explicit API contract;
- producing a second opinion on a focused implementation;
- summarizing a bounded test failure.

Do not treat Ollama output as authoritative for secrets, authentication, destructive operations, production claims, Atlas verification, final security approval, or repository writes. Ollama proposes; Codex inspects the diff, runs tests, and applies or rejects the result. Provide only required excerpts—never the entire repository.

Ollama is not an unattended coding agent in this setup. “Continuous use” means the PM repeatedly assigns the next bounded task after validating the prior result; it does not mean an uncontrolled background loop.

## 6. Test and status efficiency

- Run the smallest affected test first. Run the full suite only at an integration gate, before a commit, or after cross-cutting changes.
- Do not rerun a passing suite without a relevant change or explicit verification gate.
- Update `KANBAN.md` only for material state changes, blockers, handoffs, or verification results—not for every command.
- Update `V1_LESSONS.md` only when a measured result changes a V2 decision.
- One artifact owns each fact: Kanban owns status, lessons owns measurements, architecture owns boundaries, and the handoff owns only the next-session delta.

## 7. Handoff and compaction

Before starting a new session, record only:

- objective and current state;
- verified results and exact failing/unfinished check;
- changed files that matter to the next task;
- human blockers and secrets that are still absent;
- the next 3–7 ordered actions;
- commands required to resume.

Do not include conversational history, full logs, or files the next session can locate with `rg`. Supersede stale handoffs instead of accumulating diaries.

## 8. Stop conditions

Stop expanding context when the next action is supported by the current evidence. Stop local delegation when its output becomes repetitive, speculative, or costs more validation than doing the task directly. Ask the human only when new authority, a secret, an external account, or a material product decision is required.

This policy follows the official OpenAI guidance to keep `AGENTS.md` current, use progressive disclosure, and read only what a task needs: [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).
