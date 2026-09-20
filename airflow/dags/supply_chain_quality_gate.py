from __future__ import annotations

import sys

from airflow.sdk import dag, get_current_context, task

sys.path.insert(0, "/opt/airflow/src")
from quality.quality_gate import execute

DAG_ID = "supply_chain_quality_gate"


@dag(
    dag_id=DAG_ID,
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["supply-chain", "data-quality", "reconciliation"],
    doc_md="""
    # Supply Chain Data Quality & Reconciliation Gate

    data quality/reconciliation quality gate. The DAG is read-only against authoritative WWI
    business data and analytical warehouse facts; it persists only quality-run
    evidence and platform-alert lifecycle state.

    Trigger configuration:

    - `mode=standard` (default): structural/semantic dbt tests, source-to-staging
      volume parity, current-state freshness, staging-to-core reconciliation,
      source-behavior checks, and telemetry freshness/invariants.
    - `mode=full`: all standard checks plus raw telemetry count/min/max
      reconciliation against SQL Server.
    """,
)
def supply_chain_quality_gate():
    @task
    def run_quality_gate() -> str:
        context = get_current_context()
        dag_run = context["dag_run"]
        conf = dag_run.conf or {}
        mode = str(conf.get("mode", "standard")).lower()
        if mode not in {"standard", "full"}:
            raise ValueError("mode must be 'standard' or 'full'")
        return execute(str(context["run_id"]), mode)

    run_quality_gate()


supply_chain_quality_gate()
