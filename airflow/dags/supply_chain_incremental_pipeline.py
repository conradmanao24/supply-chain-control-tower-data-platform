from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor
from airflow.sdk import dag, get_current_context, task

sys.path.insert(0, "/opt/airflow/src")
from orchestration.pipeline_state import PipelineStateStore
from realtime.alerts import apply_platform_signal

DAG_ID = "supply_chain_incremental_pipeline"
PIPELINE_NAME = DAG_ID
SOURCE_NAME = "WideWorldImporters"
SRC_ROOT = "/opt/airflow/src"
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt")
DBT_PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", DBT_PROJECT_DIR)
DBT_TARGET_PATH = os.environ.get("DBT_TARGET_PATH", "/opt/airflow/dbt-runtime/target")
DBT_BIN = os.environ.get("DBT_BIN", "/home/airflow/.dbt-venv/bin/dbt")
LATE_ARRIVAL_OVERLAP_HOURS = max(
    1,
    int(os.environ.get("INCREMENTAL_LATE_ARRIVAL_OVERLAP_HOURS", "24")),
)


def _run(cmd: list[str], *, cwd: str | None = None, env: dict[str, str] | None = None) -> None:
    print("RUN:", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _platform_signal(rule_id: str, active: bool, observed: dict | None = None) -> None:
    conn = psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            apply_platform_signal(
                cur,
                rule_id,
                PIPELINE_NAME,
                active,
                observed or {},
                {},
                "airflow",
            )
        conn.commit()
    finally:
        conn.close()


@dag(
    dag_id=DAG_ID,
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["supply-chain", "incremental", "stateful", "alerts"],
    doc_md="""
    # Supply Chain Incremental Pipeline

    Stateful analytical orchestration. The start cutoff is read from
    `control.pipeline_state`; the end cutoff is read from the durable
    `control.source_frontier`. No analytical cutoff is supplied from the UI.

    A successful run atomically advances the watermark. A failed processing
    run is recorded as failed and leaves the watermark unchanged. alert/exception
    additionally emits project-owned platform/data-quality alert signals.
    """,
)
def supply_chain_incremental_pipeline():
    @task
    def prepare_run() -> dict:
        context = get_current_context()
        airflow_run_id = str(context["run_id"])
        store = PipelineStateStore()
        state = store.get_state(PIPELINE_NAME)
        frontier = store.get_source_frontier(SOURCE_NAME)
        start = state["last_successful_cutoff"]
        end = frontier["safe_through_cutoff"]
        run_started_at = datetime.now(timezone.utc)

        overlap_start = start - timedelta(hours=LATE_ARRIVAL_OVERLAP_HOURS)

        if end <= start:
            payload = {
                "should_run": False,
                "tail_refresh": True,
                "airflow_run_id": airflow_run_id,
                "start_cutoff": _iso(start),
                "end_cutoff": _iso(start),
                "extract_start_cutoff": _iso(overlap_start),
                "extract_end_cutoff": _iso(start),
                "run_started_at": _iso(run_started_at),
                "staging_scope": "state",
            }
            print(
                "TAIL_REFRESH_WINDOW "
                f"watermark={payload['start_cutoff']} "
                f"extract_start={payload['extract_start_cutoff']} "
                f"extract_end={payload['extract_end_cutoff']}",
                flush=True,
            )
            return payload

        window = store.begin_run(PIPELINE_NAME, airflow_run_id, end)
        payload = {
            "should_run": True,
            "tail_refresh": True,
            "airflow_run_id": airflow_run_id,
            "start_cutoff": _iso(window.start_cutoff),
            "end_cutoff": _iso(window.end_cutoff),
            "extract_start_cutoff": _iso(
                window.start_cutoff - timedelta(hours=LATE_ARRIVAL_OVERLAP_HOURS)
            ),
            "extract_end_cutoff": _iso(window.end_cutoff),
            "run_started_at": _iso(run_started_at),
            "staging_scope": "all",
        }
        print(
            "STATEFUL_WINDOW_BEGIN "
            f"run_id={airflow_run_id} start={payload['start_cutoff']} end={payload['end_cutoff']}",
            flush=True,
        )
        return payload

    @task
    def incremental_staging(window: dict) -> str:
        _run(
            [
                sys.executable,
                f"{SRC_ROOT}/ingestion/incremental_load.py",
                "--start", window["extract_start_cutoff"],
                "--end", window["extract_end_cutoff"],
                "--scope", window["staging_scope"],
            ],
            cwd=SRC_ROOT,
        )
        return "PASS" if window["should_run"] else "TAIL_REFRESH"

    @task
    def incremental_telemetry(window: dict) -> str:
        # Even when the analytical watermark is already aligned with the source
        # frontier, re-read the late-arrival overlap before the committed cutoff.
        # Telemetry rows can arrive after the frontier is published while still
        # carrying RecordedWhen values before that cutoff. Projection-only refresh
        # would otherwise leave those late readings out of the 5-minute aggregates.
        start_cutoff = (
            window["extract_start_cutoff"]
            if not window["should_run"]
            else window["start_cutoff"]
        )
        end_cutoff = (
            window["extract_end_cutoff"]
            if not window["should_run"]
            else window["end_cutoff"]
        )
        _run(
            [
                sys.executable,
                f"{SRC_ROOT}/ingestion/incremental_telemetry.py",
                "--start", start_cutoff,
                "--end", end_cutoff,
                "--dataset", "all",
            ],
            cwd=SRC_ROOT,
        )
        return "TAIL_REFRESH" if not window["should_run"] else "PASS"

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
    def verify_core(window: dict) -> str:
        conn = psycopg2.connect(
            host=os.environ["DWH_HOST"],
            port=int(os.environ["DWH_PORT"]),
            dbname=os.environ["DWH_DB"],
            user=os.environ["DWH_USER"],
            password=os.environ["DWH_PASSWORD"],
        )
        try:
            with conn.cursor() as cur:
                checks = {
                    "fact_order_line": "select count(*) from core.fact_order_line",
                    "fact_sales_line": "select count(*) from core.fact_sales_line",
                    "fact_inventory_movement": "select count(*) from core.fact_inventory_movement",
                    "fact_delivery_event": "select count(*) from core.fact_delivery_event",
                    "delivery_event_duplicate_keys": "select count(*) from (select delivery_event_key from core.fact_delivery_event group by 1 having count(*)>1) d",
                    "order_line_duplicate_keys": "select count(*) from (select order_line_key from core.fact_order_line group by 1 having count(*)>1) d",
                }
                results = {}
                for name, sql in checks.items():
                    cur.execute(sql)
                    results[name] = cur.fetchone()[0]
                if results["delivery_event_duplicate_keys"] != 0 or results["order_line_duplicate_keys"] != 0:
                    _platform_signal(
                        "platform.data_quality_failed",
                        True,
                        {"run_id": window["airflow_run_id"], "checks": results},
                    )
                    raise RuntimeError(f"duplicate-key guard failed: {results}")
                _platform_signal(
                    "platform.data_quality_failed",
                    False,
                    {"run_id": window["airflow_run_id"], "checks": results},
                )
                print("CORE_VERIFY_PASS", results, flush=True)
        finally:
            conn.close()
        return "PASS"

    @task
    def commit_success(window: dict) -> str:
        if not window["should_run"]:
            _platform_signal(
                "platform.pipeline_failed",
                False,
                {"run_id": window["airflow_run_id"], "result": "noop_success"},
            )
            print(
                "TAIL_REFRESH_COMMIT watermark unchanged "
                f"cutoff={window['start_cutoff']}",
                flush=True,
            )
            return window["start_cutoff"]
        cutoff = PipelineStateStore().commit_success(window["airflow_run_id"])
        _platform_signal(
            "platform.pipeline_failed",
            False,
            {"run_id": window["airflow_run_id"], "result": "success"},
        )
        committed = _iso(cutoff)
        print(f"WATERMARK_COMMIT_SUCCESS cutoff={committed}", flush=True)
        return committed

    @task(trigger_rule="one_failed")
    def mark_failed(window: dict) -> None:
        error_message = "Airflow processing task failed; see task logs for root cause."
        if window["should_run"]:
            PipelineStateStore().mark_failed(
                window["airflow_run_id"],
                error_message,
            )
        _platform_signal(
            "platform.pipeline_failed",
            True,
            {
                "run_id": window["airflow_run_id"],
                "error": error_message,
                "tail_refresh": not window["should_run"],
            },
        )
        print(f"PIPELINE_RUN_MARKED_FAILED run_id={window['airflow_run_id']}", flush=True)

    window = prepare_run()
    staging = incremental_staging(window)
    telemetry = incremental_telemetry(window)
    core = dbt_core_refresh(window)
    verify = verify_core(window)
    commit = commit_success(window)
    failed = mark_failed(window)

    window >> [staging, telemetry]
    [staging, telemetry] >> core
    core >> verify
    verify >> commit
    [staging, telemetry, core, verify] >> failed


supply_chain_incremental_pipeline()

