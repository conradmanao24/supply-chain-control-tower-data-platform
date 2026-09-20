from __future__ import annotations

import os
import psycopg2

from orchestration.backfill_state import BackfillStateStore

RUN_ID = "backfill_failure_state_proof"


def connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM control.backfill_run_history WHERE airflow_run_id=%s", (RUN_ID,))
        cur.execute("UPDATE control.processing_guard SET mode=NULL,owner_run_id=NULL,acquired_at=NULL WHERE singleton=true")

store = BackfillStateStore()
window = store.begin(
    RUN_ID,
    "2026-08-03T00:00:00+00:00",
    "2026-08-04T00:00:00+00:00",
)
print("BEGIN", window)

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true")
        print("GUARD_DURING", cur.fetchone())

store.mark_failed(RUN_ID, "deliberate backfill failure-state proof")

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT status,production_watermark_before,production_watermark_after,error_message
            FROM control.backfill_run_history WHERE airflow_run_id=%s
            """,
            (RUN_ID,),
        )
        print("FAILED_ROW", cur.fetchone())
        cur.execute("SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true")
        print("GUARD_AFTER", cur.fetchone())
        cur.execute("SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name='supply_chain_incremental_pipeline'")
        print("PRODUCTION_WATERMARK_AFTER", cur.fetchone()[0])
        cur.execute("DELETE FROM control.backfill_run_history WHERE airflow_run_id=%s", (RUN_ID,))

print("CLEANUP PASS")
