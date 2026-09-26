# Multi-week synthetic stress corpus

This additive corpus contains 1,440 synthetic, non-sensitive interactions over
30 days. Its eight scenario templates were reviewed by local `gpt-oss:20b`
through `scripts/invoke_ollama_worker.ps1`; the checked-in generator then
expands them deterministically with seed `20260924`.

Use it for trend, retrieval, memory-supersession, and persistence stress checks.
The smaller `data/demo` corpus remains the golden regression fixture for exact
known-answer tests and browser reset behavior.

The first 14 days model a policy-v1 baseline. Day 15 begins a policy-v2
adaptation phase that increases the two preferred financing/pricing actions
from 25% to 62.5% while retaining both nonpreferred control actions. In the
checked-in seed, aggregate resolution rises from 64.58% to 75.52%. These are
synthetic evaluation characteristics, not production claims.

Regenerate with:

```powershell
.\services\api\.venv\Scripts\python.exe scripts\generate_synthetic_weeks.py --output-dir data\synthetic_weeks
```

Every row is marked `synthetic_non_sensitive` and is validated for its time
window, scope, allowed segment values, stable IDs, identifier-like content,
policy phase, preferred-action shift, and retained controls. The manifest
records weekly and phase summaries plus the interactions file hash.
