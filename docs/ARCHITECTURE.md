# Architecture

Spec2Ship runs an end-to-end delivery workflow:

1. Baseline checks (pytest)
2. Summarize issues
3. Search local context (docs)
4. Create a plan
5. Propose a patch (diff)
6. Wait for approval (approve / reject)
7. Apply patch
8. Re-run checks + smoke test
9. Produce a report

## Services

- **web** (Next.js): dashboard + run UI
- **api** (FastAPI): REST API + enqueue jobs
- **worker** (RQ): executes the pipeline and writes artifacts
- **postgres**: stores run / step / artifact metadata
- **redis**: job queue

## Data model

- `runs`: one row per workflow run
- `steps`: ordered state machine per run
- `artifacts`: pointers to files on disk

## Artifacts

Artifacts are stored as plain files under:

`./data/artifacts/<run_id>/...`

This makes debugging simple: open logs/diffs/reports directly without any special tooling.
