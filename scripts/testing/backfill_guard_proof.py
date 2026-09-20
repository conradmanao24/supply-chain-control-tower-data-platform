from __future__ import annotations

import os
import psycopg2

from orchestration.backfill_state import BackfillStateError, BackfillStateStore
from orchestration.pipeline_state import PipelineStateError, PipelineStateStore


def connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def set_guard(mode: str, owner: str) -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.processing_guard SET mode=%s,owner_run_id=%s,acquired_at=now() WHERE singleton=true",
                (mode, owner),
            )


def clear_guard() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE control.processing_guard SET mode=NULL,owner_run_id=NULL,acquired_at=NULL WHERE singleton=true"
            )


def scalar(sql: str, params=()):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


try:
    clear_guard()

    set_guard("backfill", "backfill_guard_backfill_proof")
    try:
        PipelineStateStore().begin_run(
            "supply_chain_incremental_pipeline",
            "backfill_incremental_conflict_proof",
            "2026-09-17T00:00:00+00:00",
        )
        raise RuntimeError("incremental pipeline unexpectedly acquired a backfill-owned guard")
    except PipelineStateError as exc:
        print(f"INCREMENTAL_BLOCKED_BY_BACKFILL PASS: {exc}")
    finally:
        clear_guard()

    set_guard("incremental", "backfill_guard_incremental_proof")
    try:
        BackfillStateStore().begin(
            "backfill_conflict_proof",
            "2026-08-01T00:00:00+00:00",
            "2026-08-02T00:00:00+00:00",
        )
        raise RuntimeError("backfill unexpectedly acquired an incremental-owned guard")
    except BackfillStateError as exc:
        print(f"BACKFILL_BLOCKED_BY_INCREMENTAL PASS: {exc}")
    finally:
        clear_guard()

    try:
        BackfillStateStore().begin(
            "backfill_frontier_rejection_proof",
            "2026-09-15T00:00:00+00:00",
            "2026-09-17T00:00:00+00:00",
        )
        raise RuntimeError("backfill beyond source frontier unexpectedly accepted")
    except BackfillStateError as exc:
        print(f"FRONTIER_REJECTION PASS: {exc}")

    print(
        "PROOF_ROWS",
        {
            "incremental_conflict_history": scalar(
                "SELECT count(*) FROM control.pipeline_run_history WHERE airflow_run_id=%s",
                ("backfill_incremental_conflict_proof",),
            ),
            "backfill_conflict_history": scalar(
                "SELECT count(*) FROM control.backfill_run_history WHERE airflow_run_id=%s",
                ("backfill_conflict_proof",),
            ),
            "frontier_rejection_history": scalar(
                "SELECT count(*) FROM control.backfill_run_history WHERE airflow_run_id=%s",
                ("backfill_frontier_rejection_proof",),
            ),
            "guard_free": scalar(
                "SELECT (mode IS NULL AND owner_run_id IS NULL)::int FROM control.processing_guard WHERE singleton=true"
            ),
        },
    )
finally:
    clear_guard()
