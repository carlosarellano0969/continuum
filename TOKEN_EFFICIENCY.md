# Token Efficiency Policy

**Applies to** everyone and everything working in this folder: Claude Code sessions and subagents, Codex, and the people prompting them.
**Loaded automatically** for Claude Code via `CLAUDE.md`. Codex reads it via `AGENTS.md`. The `continuum/` repo gets the same text at kickoff.
**Owner:** Carlos. Adopted 2026-09-24.

**Why.** Usage is charged per model call, and every call re-sends the whole conversation plus every loaded tool, skill and rule. On Sep 24, two one-line turns in a 445K-token session used **16% of a Claude Pro 5-hour window**. Waste comes from four places: long sessions, re-reading, oversized tool output, and always-loaded extras.

## 1. Sessions: short and single-purpose
1. **One session = one task or phase.** Open a new session for anything unrelated, including quick questions.
2. **Context budget** (see the app's context meter):
   - **Under 100K tokens:** normal.
   - **100–150K:** finish the current task, hand off, then start fresh.
   - **Over 150K:** hand off now.
   - **Never go past 250K.**
3. **Hand off** with one board Activity entry: done / next / open questions. Update memory only if a lasting fact changed. Never rely on "it's somewhere in the conversation".
4. **Session start (≤ ~5K tokens):**
   - `CLAUDE.md` loads by itself.
   - Read the latest **10** board log entries.
   - Read only the plan sections the task needs.
5. **Batch your asks.** Put everything in one message, because every extra message re-sends the whole context. Don't send one-word follow-ups into a long session; open a new one.

## 2. Reading: never read the same thing twice
6. **Search first, then read a range.** Find it with Grep or Glob, then Read with `offset`/`limit`. Read a whole file only if it's under ~300 lines and you're editing it.
7. **Never read the plan whole** (937 lines, ~19K tokens). Grep `^## |^### ` for line numbers, then read just that section.
8. **Don't re-read after an edit.** The edit tool confirms success.
9. **Don't re-read a file already read this session** unless it changed on disk.
10. **Stay out of generated or vendor content** unless the task is about it: `node_modules`, `.venv`, `dist`, lockfiles, `.claude/skills`, `.claude/agents`, `.archive`. Scope every search with `path` or `glob`.
11. **Images are the most expensive input.** Look at a rendered diagram or screenshot once per change. For web pages, prefer page text or the accessibility tree over screenshots.

## 3. Tool output: ask for less
12. **Cap output:** `| Select-Object -First N` / `-Last N` (PowerShell), `| head` / `| tail` (bash), and quiet flags. For installs and test runs, show only failures or the last ~20 lines.
13. **Filter at the source:** `--json` + `--jq`, `git log --oneline -n 20`, and `git diff --stat` before any full diff.
14. **Board and database reads:** filter and limit (latest 10). Save bulk reads to files and open only what you need.
15. **Web:** give WebFetch a narrow prompt, and never fetch the same URL twice in a session. Record lasting findings once (plan *Sources*) instead of researching them again.

## 4. Writing: edit, don't rewrite
16. **Use targeted edits.** Rewrite a whole file only when most of it changes; rewriting a 900-line file costs ~20K output tokens.
17. **Generate repetitive content with scripts** (diagrams, fixtures, data) rather than typing it out.
18. **Keep replies short:** outcome first, then what the reader needs to act. Link plan sections instead of restating them, and never paste file contents into chat.

## 5. Models and effort: the cheapest one that does the job
19. **Claude models:**
    - **Haiku 4.5:** search, lookups, formatting, test runs, doc chores.
    - **Sonnet 5:** default for coding.
    - **Opus 5.5:** contracts, integration gates, hard debugging, deciding reviews.
    - **Fable 5.1:** only the approved jobs (plan §8.1).
20. **Effort:** low or medium for routine work, high for building, and xhigh or max only at gates or on stuck problems.
21. **Codex:** Luna for volume, Sol or Terra for building, Astra for at most 1–3 hard reviews per window. Prefer local tasks; cloud tasks cost more per message.

## 6. Subagents: protect the main context
22. **Delegate broad searches and bulk reading** to a subagent (Explore on Haiku). It returns the conclusion, not the files.
23. **Every delegated task** gets a self-contained packet (≤ 40 lines) and returns ≤ 15 lines: status, files changed, commands and results, risks.
24. **Continue an existing agent** (SendMessage) rather than spawning a new one. A new spawn has to rediscover everything.
25. **Don't spawn an agent for a task that takes 1–3 tool calls.**

## 7. Always-loaded context: lean and stable
26. **Keep `CLAUDE.md`, `AGENTS.md`, memory files and this policy short.** Keep status and dates out of them; those live on the board.
27. **Don't change `CLAUDE.md`, tools or MCP connectors mid-session.** It breaks prompt caching for the rest of that session.
28. **Load only what the task needs.**
    - ECC in `.claude/` currently adds up to **~35K tokens to every call** (292 skills, 94 commands, 68 agents, 11 always-on rules). Trim it to the build set in plan §15 by moving the rest to `.claude/skills-parked/`, which is reversible.
    - Disconnect connectors the session doesn't use.

## 8. Measure
29. **Check usage at session start and at milestones.** Claude: the app's usage card. Codex: its usage page. Log notable spend on the board.
30. **If one turn costs more than 5% of a 5-hour window, the session is too big.** Hand off and restart.
31. **Weekly:** name the biggest spend, and the rule that would have prevented it.

## Before you hit Enter
- Is this session under 100K tokens, and still the same task?
- Is everything batched into this one message?
- Am I reading a range, not a whole file?
- Is the output capped?
- Is this the cheapest model that can do it?
