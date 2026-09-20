# Persisted State Operations

Implemented reusable state operations in `src/orchestration/pipeline_state.py`:

- `begin_run()` derives `start_cutoff` from the persisted watermark and records a `running` attempt without advancing state.
- `mark_failed()` finalizes a run as `failed` while leaving the watermark unchanged.
- `commit_success()` finalizes the run and advances `control.pipeline_state` in the same PostgreSQL transaction.
- Success commit is idempotent for an already committed run.
- Compare-and-set semantics reject stale runs if another successful run has already moved the watermark.

Proof executed through `src/orchestration/prove_pipeline_state.py` using an isolated temporary proof pipeline. The production pipeline watermark was not modified.

Verified:

- intentional failed run: watermark unchanged — PASS
- retry after failure starts from the same watermark — PASS
- successful run advances watermark atomically — PASS
- repeated success commit is idempotent — PASS
- stale concurrent run cannot advance watermark — PASS
- temporary proof rows/state cleaned up — PASS
- `supply_chain_incremental_pipeline` watermark remains `2026-09-16 00:00:00+00` — PASS

stateful Airflow orchestration stateful Airflow orchestration is not started by this checkpoint.
