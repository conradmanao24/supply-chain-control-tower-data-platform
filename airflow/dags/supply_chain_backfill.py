from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone

import psycopg2
from airflow.sdk import dag, get_current_context, task

sys.path.insert(0, "/opt/airflow/src")
from orchestration.backfill_state import BackfillStateStore

DAG_ID = "supply_chain_backfill"
SRC_ROOT = "/opt/airflow/src"
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt")
DBT_PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", DBT_PROJECT_DIR)
DBT_TARGET_PATH = os.environ.get("DBT_TARGET_PATH", "/opt/airflow/dbt-runtime/target")
DBT_BIN = os.environ.get("DBT_BIN", "/home/airflow/.dbt-venv/bin/dbt")


def _run(cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> None:
    print("RUN:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


@dag(
    dag_id=DAG_ID,
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["supply-chain", "backfill", "historical-reprocessing"],
    doc_md="""
    # Controlled Historical Backfill

    Trigger with an explicit timezone-aware window, for example:

    `{"start":"2026-08-01T00:00:00+00:00","end":"2026-08-02T00:00:00+00:00"}`

    The run is recorded in `control.backfill_run_history`, uses the same
    idempotent staging/telemetry loaders and dbt/core build path, and must not
    move the production incremental watermark.
    """,
)
def supply_chain_backfill():
    @task
    def prepare_backfill() -> dict:
        context = get_current_context()
        airflow_run_id = str(context["run_id"])
        dag_run = context.get("dag_run")
        conf = getattr(dag_run, "conf", None) or {}
        start = conf.get("start")
        end = conf.get("end")
        if not start or not end:
            raise ValueError("backfill requires dag-run conf keys: start and end")

        window = BackfillStateStore().begin(airflow_run_id, start, end)
        payload = {
            "airflow_run_id": airflow_run_id,
            "start_cutoff": _iso(window.start_cutoff),
            "end_cutoff": _iso(window.end_cutoff),
            "production_watermark_before": _iso(window.production_watermark_before),
            "source_frontier_at_start": _iso(window.source_frontier_at_start),
            "run_started_at": datetime.now(timezone.utc).isoformat(),
        }
        print("BACKFILL_BEGIN", payload, flush=True)
        return payload

    @task
    def backfill_staging(window: dict) -> str:
        _run(
            [
                sys.executable,
                f"{SRC_ROOT}/ingestion/incremental_load.py",
                "--start", window["start_cutoff"],
                "--end", window["end_cutoff"],
                "--scope", "all",
            ],
            cwd=SRC_ROOT,
        )
        return "PASS"

    @task
    def backfill_telemetry(window: dict) -> str:
        _run(
            [
                sys.executable,
                f"{SRC_ROOT}/ingestion/incremental_telemetry.py",
                "--start", window["start_cutoff"],
                "--end", window["end_cutoff"],
                "--dataset", "all",
            ],
            cwd=SRC_ROOT,
        )
        return "PASS"

    @task
    def dbt_core_refresh(window: dict) -> str:
        env = os.environ.copy()
        env["INCREMENTAL_RUN_STARTED_AT"] = window["run_started_at"]
        _run(
            [
                DBT_BIN,
                "build",
                "--profiles-dir", DBT_PROFILES_DIR,
                "--target-path", DBT_TARGET_PATH,
            ],
            cwd=DBT_PROJECT_DIR,
            env=env,
        )
        return "PASS"

    @task
    def verify_backfill(window: dict) -> dict:
        fact_keys = {
            "fact_order_line": "order_line_key",
            "fact_sales_line": "sales_line_key",
            "fact_inventory_movement": "inventory_movement_key",
            "fact_purchase_order_line": "purchase_order_line_key",
            "fact_delivery_event": "delivery_event_key",
            "fact_customer_transaction": "customer_transaction_key",
            "fact_supplier_transaction": "supplier_transaction_key",
        }
        conn = _pg_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name='supply_chain_incremental_pipeline'"
                )
                production_watermark = cur.fetchone()[0]
                if _iso(production_watermark) != window["production_watermark_before"]:
                    raise RuntimeError(
                        f"production watermark changed during backfill: {production_watermark} != {window['production_watermark_before']}"
                    )

                counts: dict[str, int] = {}
                duplicate_groups: dict[str, int] = {}
                for table, key in fact_keys.items():
                    cur.execute(f"SELECT count(*) FROM core.{table}")
                    counts[table] = int(cur.fetchone()[0])
                    cur.execute(
                        f"SELECT count(*) FROM (SELECT {key} FROM core.{table} GROUP BY 1 HAVING count(*)>1) d"
                    )
                    duplicate_groups[table] = int(cur.fetchone()[0])

                cur.execute(
                    """
                    SELECT count(*) FROM (
                        SELECT sensor_number,bucket_start FROM staging.coldroom_5m
                        GROUP BY sensor_number,bucket_start HAVING count(*)>1
                    ) d
                    """
                )
                duplicate_groups["staging.coldroom_5m"] = int(cur.fetchone()[0])
                cur.execute(
                    """
                    SELECT count(*) FROM (
                        SELECT vehicle_registration,sensor_number,bucket_start FROM staging.vehicle_5m
                        GROUP BY vehicle_registration,sensor_number,bucket_start HAVING count(*)>1
                    ) d
                    """
                )
                duplicate_groups["staging.vehicle_5m"] = int(cur.fetchone()[0])

                if any(duplicate_groups.values()):
                    raise RuntimeError(f"backfill duplicate-key verification failed: {duplicate_groups}")

                cur.execute("SELECT count(*) FROM alert.alerts WHERE status IN ('open','acknowledged')")
                active_alerts = int(cur.fetchone()[0])

                result = {
                    "window": {"start": window["start_cutoff"], "end": window["end_cutoff"]},
                    "production_watermark": _iso(production_watermark),
                    "fact_counts": counts,
                    "duplicate_groups": duplicate_groups,
                    "active_alerts": active_alerts,
                }
                print("BACKFILL_VERIFY_PASS", result, flush=True)
                return result
        finally:
            conn.close()

    @task
    def complete_backfill(window: dict, verification: dict) -> str:
        watermark = BackfillStateStore().complete_success(window["airflow_run_id"], verification)
        print(
            f"BACKFILL_COMMIT_SUCCESS run_id={window['airflow_run_id']} production_watermark_unchanged={_iso(watermark)}",
            flush=True,
        )
        return _iso(watermark)

    @task(trigger_rule="one_failed")
    def mark_failed() -> None:
        context = get_current_context()
        airflow_run_id = str(context["run_id"])
        BackfillStateStore().mark_failed(
            airflow_run_id,
            "Backfill processing task failed; see Airflow task logs for root cause.",
        )
        print(f"BACKFILL_MARKED_FAILED run_id={airflow_run_id}", flush=True)

    window = prepare_backfill()
    staging = backfill_staging(window)
    telemetry = backfill_telemetry(window)
    core = dbt_core_refresh(window)
    verification = verify_backfill(window)
    complete = complete_backfill(window, verification)
    failed = mark_failed()

    window >> [staging, telemetry]
    [staging, telemetry] >> core
    core >> verification
    verification >> complete
    [window, staging, telemetry, core, verification, complete] >> failed


supply_chain_backfill()
