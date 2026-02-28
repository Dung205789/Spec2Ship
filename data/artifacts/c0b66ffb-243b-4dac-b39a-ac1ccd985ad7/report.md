# Spec2Ship Report

- **run_id**: `c0b66ffb-243b-4dac-b39a-ac1ccd985ad7`
- **workspace**: `/data/run_workspaces/c0b66ffb-243b-4dac-b39a-ac1ccd985ad7`
- **profile**: `tinyshop-python`
- **generated_at**: 2026-02-27T07:30:47.109338Z

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
- 9. **Re-run checks** ❌ `failed`
  - ⚠️ error: Post-checks still failing. Use 'Regenerate Patch'.
  - log: `post_checks.log`
- 10. **Smoke test** ✅ `success` — Smoke test passed
  - log: `smoke.log`
- 11. **Report** • `running`

## Recovery hints
- If *Propose patch* failed with `invalid_patch` → click **Regenerate Patch**
- If *Re-run checks* failed → open `post_checks.log` then click **Regenerate Patch**
- If *Apply patch* failed → try **Regenerate Patch** or switch patcher mode
