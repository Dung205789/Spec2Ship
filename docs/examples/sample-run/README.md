# Sample run — what the agent actually produces

This folder is a **real, unedited set of artifacts** from one Spec2Ship run against
the bundled `sample_workspace/` ("tinyshop"). The ticket was simply *"Fix all
failing tests."* and the agent worked through its pipeline end to end.

Read these in order to follow the agent's reasoning:

| File | Stage | What it shows |
| --- | --- | --- |
| [`signals.txt`](signals.txt) | Summarize | The structured failure signal extracted from pytest output |
| [`context.md`](context.md) | Context search | The workspace context the agent retrieved to ground its fix |
| [`plan.md`](plan.md) | Plan | The approach the agent drafted from the ticket + signals |
| [`proposal.md`](proposal.md) | Propose | Human-readable rationale for the proposed change |
| [`proposal.diff`](proposal.diff) | Propose | The exact unified diff offered for approval |
| [`report.md`](report.md) | Report | The final per-step report after apply + re-verify |

## TL;DR of this run

The baseline suite failed with a rounding assertion
(`assert 895 == 896`). The agent identified **three** related pricing bugs and
proposed a `Decimal` / `ROUND_HALF_UP` fix:

1. `apply_discount` used Python banker's rounding → switched to `Decimal` half-up.
2. `apply_tax` used floor division (`//`) → switched to `Decimal` half-up.
3. `calculate_final_price` taxed the subtotal → now taxes the post-discount amount.

After approval the patch was applied and the suite re-verified green.

> These are illustrative outputs checked into the repo on purpose. Live runs write
> the same artifacts to `data/artifacts/<run_id>/`, which is git-ignored.
