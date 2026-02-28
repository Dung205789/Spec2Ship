# Spec2Ship Report

- **run_id**: `056b33fd-f27d-4a2b-8bb6-d8f30dc761c7`
- **workspace**: `/data/run_workspaces/056b33fd-f27d-4a2b-8bb6-d8f30dc761c7`
- **profile**: `tinyshop-python`
- **generated_at**: 2026-02-27T10:11:17.270136Z

## Outcome
- Report, logs, and diff are saved under the run artifacts.
- Patched source code is available in isolated run workspace: `/data/run_workspaces/056b33fd-f27d-4a2b-8bb6-d8f30dc761c7`
- Download ZIP (`/runs/{run_id}/download`) includes both `artifacts/` and `workspace/`.

## Steps
- 1. **Preflight** ✅ `success` — OK — profile: tinyshop-python
  - log: `preflight.log`
- 2. **Baseline checks** ✅ `success` — Found failures (exit 1)
  - log: `baseline.log`
- 3. **Summarize issues** ✅ `success` — 2 signal(s) extracted
  - artifact: `signals.txt`
- 4. **Context search** ✅ `success` — Context built — 2 doc(s) indexed
  - artifact: `context.md`
- 5. **Plan** ✅ `success` — Plan generated
  - artifact: `plan.md`
- 6. **Propose patch** ✅ `success` — Patch proposed via rules
  - log: `proposal.diff`
  - artifact: `proposal.md`
- 7. **Waiting for approval** ✅ `success` — Approved by user
- 8. **Apply patch** ✅ `success` — Applied: Fix discount calculation rounding
  - artifact: `apply_result.txt`
- 9. **Re-run checks** ✅ `success` — All checks passed
  - log: `post_checks.log`
- 10. **Smoke test** ✅ `success` — Smoke test passed
  - log: `smoke.log`
- 11. **Report** • `running`

## Changed files
- `tinyshop/pricing.py`

## Recovery hints
- If *Propose patch* failed with `invalid_patch` → click **Regenerate Patch**
- If *Re-run checks* failed → open `post_checks.log` then click **Regenerate Patch**
- If *Apply patch* failed → try **Regenerate Patch** or switch patcher mode
