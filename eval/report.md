# Spec2Ship Patcher Evaluation Report

| Mode | Case | Apply OK | Tests Pass | Half-up correct | Health OK | Latency |
|---|---|---|---|---|---|---|
| rules | discount-rounding-bug | True | True | True | - | 1.4s |
| rules | add-health-endpoint | True | - | - | True | 0.03s |
| openai | discount-rounding-bug | True | True | True | - | 23.96s |
| openai | add-health-endpoint | True | - | - | True | 13.02s |

## Summary by mode

### rules
- Apply success: 2/2
- Latency: mean 0.71s, max 1.40s

### openai
- Apply success: 2/2
- Latency: mean 18.49s, max 23.96s

## Iteration log (both real bugs, found and fixed via this eval)

This is the numbers-table state after 2 rounds of fixes. The harness caught 2 distinct, real defects in the OpenAI patcher along the way — recorded here because they're the actual reason the prompt in `OpenAIWorkspacePatcher.propose()` looks the way it does:

1. **Silent wrong-rounding bug.** Run 1: `tests_pass=True`, `half_up_correct=False`. The model's fix passed the **given** pytest suite using Python's built-in `round()` (round-half-to-even), which coincidentally matches half-up on the two values the given tests happen to check, but diverges on others (`round(894.5) == 894`; true half-up requires 895). Passing the given tests is not the same as satisfying the stated requirement — this is exactly why the half-up probe (4 values not in the original test file) exists as a separate check. Fix: added an explicit rounding-implementation rule to the prompt (`decimal.Decimal(...).quantize(..., ROUND_HALF_UP)`, not `round()`).
2. **Missing-import bug, surfaced by fix #1.** Run 2: `tests_pass=False` — the model correctly switched to `Decimal(...).quantize(...)` per the new prompt rule, but the diff never added `from decimal import Decimal, ROUND_HALF_UP`, so the patched code raised `NameError` at request time. `git apply --check` only validates diff *syntax*, not that the resulting code *runs* — a gap the pipeline doesn't currently self-check before declaring a patch applied. Fix: added an explicit self-check rule to the prompt (every referenced name must have a matching `+import` line). Run 3 (the numbers above): both checks green.

**Open gap, not fixed here:** the pipeline still has no automated compile/import-check step after `apply()` — run 2's NameError was only caught because this harness runs pytest afterward. A real hardening would add a cheap `python -m py_compile` (or import smoke test) into the same validate/repair retry loop that already exists for `git apply --check`, so this class of bug gets caught and auto-repaired without needing a full eval run.