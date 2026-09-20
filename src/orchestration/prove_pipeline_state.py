from __future__ import annotations

from datetime import datetime, timedelta, timezone

from orchestration.pipeline_state import (
    PipelineStateStore,
    StaleRunError,
    connect_from_env,
)

MAIN_PIPELINE = "supply_chain_incremental_pipeline"
PROOF_PIPELINE = "__pipeline_state_proof__"
BASE = datetime(2026, 9, 16, tzinfo=timezone.utc)


def reset_proof() -> None:
    conn = connect_from_env()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM control.pipeline_run_history WHERE pipeline_name = %s", (PROOF_PIPELINE,))
                cur.execute("DELETE FROM control.pipeline_state WHERE pipeline_name = %s", (PROOF_PIPELINE,))
                cur.execute(
                    """
                    INSERT INTO control.pipeline_state (
                        pipeline_name, last_successful_cutoff, last_successful_run_id
                    ) VALUES (%s, %s, NULL)
                    """,
                    (PROOF_PIPELINE, BASE),
                )
    finally:
        conn.close()


def cleanup_proof() -> None:
    conn = connect_from_env()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM control.pipeline_run_history WHERE pipeline_name = %s", (PROOF_PIPELINE,))
                cur.execute("DELETE FROM control.pipeline_state WHERE pipeline_name = %s", (PROOF_PIPELINE,))
    finally:
        conn.close()


def main() -> None:
    store = PipelineStateStore()
    main_before = store.get_state(MAIN_PIPELINE)["last_successful_cutoff"]
    reset_proof()
    try:
        failed_id = "pipeline-state-proof-failed"
        end_1 = BASE + timedelta(hours=1)
        first = store.begin_run(PROOF_PIPELINE, failed_id, end_1)
        assert first.start_cutoff == BASE
        assert store.get_state(PROOF_PIPELINE)["last_successful_cutoff"] == BASE
        store.mark_failed(failed_id, "intentional proof failure")
        assert store.get_state(PROOF_PIPELINE)["last_successful_cutoff"] == BASE

        retry_id = "pipeline-state-proof-retry"
        retry = store.begin_run(PROOF_PIPELINE, retry_id, end_1)
        assert retry.start_cutoff == BASE
        committed = store.commit_success(retry_id)
        assert committed == end_1
        assert store.get_state(PROOF_PIPELINE)["last_successful_cutoff"] == end_1
        assert store.commit_success(retry_id) == end_1

        stale_id = "pipeline-state-proof-stale"
        winner_id = "pipeline-state-proof-winner"
        stale_end = end_1 + timedelta(hours=2)
        winner_end = end_1 + timedelta(hours=1)
        stale = store.begin_run(PROOF_PIPELINE, stale_id, stale_end)
        winner = store.begin_run(PROOF_PIPELINE, winner_id, winner_end)
        assert stale.start_cutoff == end_1 and winner.start_cutoff == end_1
        store.commit_success(winner_id)
        try:
            store.commit_success(stale_id)
            raise AssertionError("stale run unexpectedly advanced the watermark")
        except StaleRunError:
            pass
        store.mark_failed(stale_id, "stale run correctly rejected")
        assert store.get_state(PROOF_PIPELINE)["last_successful_cutoff"] == winner_end

        conn = connect_from_env()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT airflow_run_id, status
                    FROM control.pipeline_run_history
                    WHERE pipeline_name = %s
                    ORDER BY run_id
                    """,
                    (PROOF_PIPELINE,),
                )
                statuses = dict(cur.fetchall())
        finally:
            conn.close()
        assert statuses == {
            failed_id: "failed",
            retry_id: "success",
            stale_id: "failed",
            winner_id: "success",
        }

        main_after = store.get_state(MAIN_PIPELINE)["last_successful_cutoff"]
        assert main_after == main_before
        print(
            "PIPELINE_STATE_PROOF_PASS",
            {
                "failed_run_no_advance": True,
                "retry_same_window": True,
                "success_advance_atomic": True,
                "success_commit_idempotent": True,
                "stale_run_rejected": True,
                "main_watermark_unchanged": str(main_after),
            },
            flush=True,
        )
    finally:
        cleanup_proof()


if __name__ == "__main__":
    main()
