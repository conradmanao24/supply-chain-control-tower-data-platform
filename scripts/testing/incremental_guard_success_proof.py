from __future__ import annotations

import os
import psycopg2

from orchestration.pipeline_state import PipelineStateStore

PIPELINE = "backfill_incremental_guard_test"
RUN_ID = "backfill_incremental_guard_success_proof"


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
        cur.execute("DELETE FROM control.pipeline_run_history WHERE airflow_run_id=%s", (RUN_ID,))
        cur.execute("DELETE FROM control.pipeline_state WHERE pipeline_name=%s", (PIPELINE,))
        cur.execute(
            "INSERT INTO control.pipeline_state(pipeline_name,last_successful_cutoff,last_successful_run_id) VALUES (%s,%s,NULL)",
            (PIPELINE, "2026-08-01T00:00:00+00:00"),
        )
        cur.execute("UPDATE control.processing_guard SET mode=NULL,owner_run_id=NULL,acquired_at=NULL WHERE singleton=true")

store = PipelineStateStore()
window = store.begin_run(PIPELINE, RUN_ID, "2026-08-02T00:00:00+00:00")
print("BEGIN", window)

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true")
        print("GUARD_DURING", cur.fetchone())

store.mark_failed(RUN_ID, "deliberate backfill incremental-guard proof")

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true")
        print("GUARD_AFTER", cur.fetchone())
        cur.execute("SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name=%s", (PIPELINE,))
        print("TEST_WATERMARK_AFTER", cur.fetchone()[0])
        cur.execute("SELECT status FROM control.pipeline_run_history WHERE airflow_run_id=%s", (RUN_ID,))
        print("RUN_STATUS", cur.fetchone()[0])
        cur.execute("DELETE FROM control.pipeline_run_history WHERE airflow_run_id=%s", (RUN_ID,))
        cur.execute("DELETE FROM control.pipeline_state WHERE pipeline_name=%s", (PIPELINE,))

print("CLEANUP PASS")
