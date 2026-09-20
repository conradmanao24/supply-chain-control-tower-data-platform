from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pymssql
import psycopg2
from psycopg2.extras import Json, RealDictCursor

from realtime.alerts import apply_platform_signal

DBT_BIN = os.environ.get("DBT_BIN", "/home/airflow/.dbt-venv/bin/dbt")
DBT_PROJECT_DIR = os.environ.get("DBT_PROJECT_DIR", "/opt/airflow/dbt")
DBT_PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR", DBT_PROJECT_DIR)
DBT_TARGET_PATH = os.environ.get("DBT_TARGET_PATH", "/opt/airflow/dbt-runtime/target")
CURRENT_STATE_MAX_LAG_MINUTES = max(
    1,
    int(os.environ.get("QUALITY_CURRENT_STATE_MAX_LAG_MINUTES", "20")),
)


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def ms_connect():
    return pymssql.connect(
        server=os.environ["WWI_HOST"],
        port=int(os.environ.get("WWI_PORT", "1433")),
        user=os.environ["WWI_SOURCE_USER"],
        password=os.environ["WWI_SOURCE_PASSWORD"],
        database=os.environ["WWI_DATABASE"],
        autocommit=True,
        login_timeout=10,
        timeout=180,
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, Decimal)):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    return value


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class QualityRun:
    def __init__(self, airflow_run_id: str, mode: str):
        self.airflow_run_id = airflow_run_id
        self.mode = mode
        self.quality_run_id = str(uuid.uuid4())
        self.failed_categories: set[str] = set()

    def begin(self) -> None:
        with pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO quality.run_history(quality_run_id,airflow_run_id,mode,status)
                    VALUES (%s,%s,%s,'running')
                    """,
                    (self.quality_run_id, self.airflow_run_id, self.mode),
                )

    def record(
        self,
        check_name: str,
        category: str,
        passed: bool,
        *,
        severity: str = "critical",
        source_value: Any = None,
        target_value: Any = None,
        details: dict[str, Any] | None = None,
        warning: bool = False,
    ) -> None:
        status = "warning" if warning else ("pass" if passed else "fail")
        if status == "fail":
            self.failed_categories.add(category)
        with pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO quality.check_result
                        (quality_run_id,check_name,category,severity,status,source_value,target_value,details)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (quality_run_id,check_name) DO UPDATE SET
                        category=EXCLUDED.category,
                        severity=EXCLUDED.severity,
                        status=EXCLUDED.status,
                        source_value=EXCLUDED.source_value,
                        target_value=EXCLUDED.target_value,
                        details=EXCLUDED.details,
                        checked_at=now()
                    """,
                    (
                        self.quality_run_id,
                        check_name,
                        category,
                        severity,
                        status,
                        _text(source_value),
                        _text(target_value),
                        Json(_json_value(details or {})),
                    ),
                )
        print(
            f"QUALITY_CHECK {status.upper()} category={category} name={check_name} "
            f"source={_text(source_value)} target={_text(target_value)}",
            flush=True,
        )

    def finalize(self, error_message: str | None = None) -> bool:
        with pg_connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        count(*) FILTER (WHERE status='pass') AS passed,
                        count(*) FILTER (WHERE status='fail') AS failed,
                        count(*) FILTER (WHERE status='warning') AS warnings
                    FROM quality.check_result
                    WHERE quality_run_id=%s
                    """,
                    (self.quality_run_id,),
                )
                counts = cur.fetchone()
                failed = int(counts["failed"] or 0)
                status = "fail" if failed else "pass"
                cur.execute(
                    """
                    UPDATE quality.run_history
                    SET status=%s,finished_at=now(),passed_checks=%s,failed_checks=%s,
                        warning_checks=%s,error_message=%s
                    WHERE quality_run_id=%s
                    """,
                    (
                        status,
                        int(counts["passed"] or 0),
                        failed,
                        int(counts["warnings"] or 0),
                        error_message,
                        self.quality_run_id,
                    ),
                )
                dq_failed = failed > 0
                recon_failed = bool(self.failed_categories & {"reconciliation", "volume", "freshness"})
                apply_platform_signal(
                    cur,
                    "platform.data_quality_failed",
                    "supply_chain_quality_gate",
                    dq_failed,
                    {
                        "airflow_run_id": self.airflow_run_id,
                        "quality_run_id": self.quality_run_id,
                        "failed_checks": failed,
                    },
                    {},
                    "quality-gate",
                )
                apply_platform_signal(
                    cur,
                    "platform.reconciliation_mismatch",
                    "supply_chain_quality_gate",
                    recon_failed,
                    {
                        "airflow_run_id": self.airflow_run_id,
                        "quality_run_id": self.quality_run_id,
                        "failed_categories": sorted(self.failed_categories),
                    },
                    {},
                    "quality-gate",
                )
        print(
            f"QUALITY_RUN_FINAL status={'FAIL' if failed else 'PASS'} run={self.quality_run_id} "
            f"passed={counts['passed']} failed={counts['failed']} warnings={counts['warnings']}",
            flush=True,
        )
        return failed == 0


def run_dbt_tests(run: QualityRun) -> None:
    cmd = [
        DBT_BIN,
        "test",
        "--profiles-dir",
        DBT_PROFILES_DIR,
        "--target-path",
        DBT_TARGET_PATH,
    ]
    env = os.environ.copy()
    proc = subprocess.run(
        cmd,
        cwd=DBT_PROJECT_DIR,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(proc.stdout, flush=True)
    match = re.search(r"PASS=(\d+) WARN=(\d+) ERROR=(\d+) SKIP=(\d+).*TOTAL=(\d+)", proc.stdout)
    summary = {}
    if match:
        summary = {
            "pass": int(match.group(1)),
            "warn": int(match.group(2)),
            "error": int(match.group(3)),
            "skip": int(match.group(4)),
            "total": int(match.group(5)),
        }
    passed = proc.returncode == 0
    for name, category in (
        ("dbt_structural_integrity", "structural"),
        ("dbt_referential_integrity", "referential"),
        ("dbt_semantic_integrity", "semantic"),
    ):
        run.record(
            name,
            category,
            passed,
            source_value=summary.get("total"),
            target_value=summary.get("pass"),
            details={"dbt_return_code": proc.returncode, "dbt_summary": summary},
        )


def _pipeline_contract(pg) -> tuple[datetime, datetime, str | None]:
    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT p.last_successful_cutoff,
                   f.safe_through_cutoff,
                   p.last_successful_run_id
            FROM control.pipeline_state p
            JOIN control.source_frontier f
              ON f.source_name='WideWorldImporters'
            WHERE p.pipeline_name='supply_chain_incremental_pipeline'
            """
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("incremental pipeline state/source frontier unavailable")
    return (
        row["last_successful_cutoff"],
        row["safe_through_cutoff"],
        row["last_successful_run_id"],
    )


def run_freshness_checks(run: QualityRun, ms, pg) -> None:
    watermark, frontier, committed_run_id = _pipeline_contract(pg)

    run.record(
        "pipeline_watermark_matches_source_frontier",
        "freshness",
        watermark == frontier,
        source_value=frontier,
        target_value=watermark,
    )

    with pg.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT airflow_run_id,status,start_cutoff,end_cutoff,finished_at
            FROM control.pipeline_run_history
            WHERE airflow_run_id=%s
            """,
            (committed_run_id,),
        )
        committed_run = cur.fetchone()

    committed_ok = bool(
        committed_run
        and committed_run["status"] == "success"
        and committed_run["end_cutoff"] == watermark
    )
    run.record(
        "latest_incremental_run_committed",
        "freshness",
        committed_ok,
        source_value=committed_run_id,
        target_value=(
            f"{committed_run['status']}@{committed_run['end_cutoff'].isoformat()}"
            if committed_run
            else "missing"
        ),
        details={
            "watermark": _text(watermark),
            "run": _json_value(dict(committed_run)) if committed_run else None,
        },
    )

    # Mutable delta-state views are not historical snapshots. A source row can
    # be updated again after the committed cutoff, which removes its prior
    # LastEditedWhen from the live view while staging correctly retains the
    # state extracted before the cutoff. Therefore:
    #   1) staging must never advance past the committed watermark; and
    #   2) staging may be newer than MAX(source LastEditedWhen <= watermark).
    # A positive source->target lag is tolerated only within the SLA.
    delta_pairs = [
        ("order_state", "ControlTowerExtract.OrderState", "LastEditedWhen", "staging.order_state", "last_edited_when"),
        ("invoice_delivery", "ControlTowerExtract.InvoiceDelivery", "LastEditedWhen", "staging.invoice_delivery", "last_edited_when"),
        ("purchase_order_state", "ControlTowerExtract.PurchaseOrderState", "LastEditedWhen", "staging.purchase_order_state", "last_edited_when"),
    ]
    watermark_n = _normalize_dt(watermark)
    for name, source_relation, source_col, target_relation, target_col in delta_pairs:
        mcur = ms.cursor()
        mcur.execute(
            f"SELECT MAX({source_col}) FROM {source_relation} WHERE {source_col} <= %s",
            (watermark,),
        )
        source_max = mcur.fetchone()[0]
        with pg.cursor() as pcur:
            pcur.execute(f"SELECT MAX({target_col}) FROM {target_relation}")
            target_max = pcur.fetchone()[0]
        source_n = _normalize_dt(source_max)
        target_n = _normalize_dt(target_max)

        if source_n is None or target_n is None or watermark_n is None:
            passed = source_n == target_n
            lag_seconds = None
            within_cutoff = target_n is None or watermark_n is None or target_n <= watermark_n
        else:
            lag_seconds = (source_n - target_n).total_seconds()
            within_cutoff = target_n <= watermark_n
            passed = within_cutoff and lag_seconds <= CURRENT_STATE_MAX_LAG_MINUTES * 60

        run.record(
            f"freshness_{name}",
            "freshness",
            passed,
            source_value=source_max,
            target_value=target_max,
            details={
                "committed_cutoff": _text(watermark),
                "lag_seconds": lag_seconds,
                "max_lag_minutes": CURRENT_STATE_MAX_LAG_MINUTES,
                "target_within_committed_cutoff": within_cutoff,
                "comparison_basis": "mutable delta state at committed cutoff",
            },
        )

    # Stock holding is intentionally synchronized as a full current snapshot on
    # every tail refresh. It is therefore allowed to move beyond the analytical
    # watermark and must be compared with the current live source, not a
    # source value artificially capped at the committed cutoff.
    mcur = ms.cursor()
    mcur.execute("SELECT MAX(LastEditedWhen) FROM ControlTowerExtract.StockHoldingCurrent")
    source_max = mcur.fetchone()[0]
    with pg.cursor() as pcur:
        pcur.execute("SELECT MAX(last_edited_when) FROM staging.stock_holding_current")
        target_max = pcur.fetchone()[0]
    source_n = _normalize_dt(source_max)
    target_n = _normalize_dt(target_max)
    if source_n is None or target_n is None:
        passed = source_n == target_n
        lag_seconds = None
    else:
        lag_seconds = (source_n - target_n).total_seconds()
        passed = 0 <= lag_seconds <= CURRENT_STATE_MAX_LAG_MINUTES * 60

    run.record(
        "freshness_stock_holding_current",
        "freshness",
        passed,
        source_value=source_max,
        target_value=target_max,
        details={
            "committed_cutoff": _text(watermark),
            "lag_seconds": lag_seconds,
            "max_lag_minutes": CURRENT_STATE_MAX_LAG_MINUTES,
            "comparison_basis": "live current snapshot",
        },
    )


def run_volume_reconciliation(run: QualityRun, ms, pg) -> None:
    watermark, _, _ = _pipeline_contract(pg)
    mcur = ms.cursor()
    mcur.execute("EXEC ControlTowerExtract.GetReconciliationCounts")
    source_counts = {str(name): int(count) for name, count in mcur.fetchall()}

    with pg.cursor() as pcur:
        for name, source_count in sorted(source_counts.items()):
            pcur.execute(f"SELECT count(*) FROM staging.{name}")
            target_count = int(pcur.fetchone()[0])
            matches = source_count == target_count
            run.record(
                f"source_to_staging_count_{name}",
                "volume",
                matches,
                severity="warning" if not matches else "info",
                source_value=source_count,
                target_value=target_count,
                warning=not matches,
                details={
                    "comparison_basis": (
                        "current live source versus committed staging snapshot"
                    ),
                    "committed_cutoff": _text(watermark),
                    "live_source_drift": source_count - target_count,
                    "hard_parity_basis": (
                        "pipeline commit evidence plus staging-to-core reconciliation"
                    ),
                },
            )


def run_core_reconciliation(run: QualityRun, pg) -> None:
    count_checks = [
        ("fact_order_line", "staging.order_line", "core.fact_order_line", None),
        ("fact_sales_line", "staging.sale_line", "core.fact_sales_line", None),
        ("fact_inventory_movement", "staging.inventory_movement", "core.fact_inventory_movement", None),
        ("fact_purchase_order_line", "staging.purchase_line", "core.fact_purchase_order_line", None),
        ("fact_customer_transaction", "staging.financial_transaction", "core.fact_customer_transaction", "wwi_customer_transaction_id IS NOT NULL"),
        ("fact_supplier_transaction", "staging.financial_transaction", "core.fact_supplier_transaction", "wwi_supplier_transaction_id IS NOT NULL"),
        ("bridge_product_stock_group", "staging.product_stock_group", "core.bridge_product_stock_group", None),
    ]
    with pg.cursor() as cur:
        for name, source_table, target_table, predicate in count_checks:
            where = f" WHERE {predicate}" if predicate else ""
            cur.execute(f"SELECT count(*) FROM {source_table}{where}")
            source_count = int(cur.fetchone()[0])
            cur.execute(f"SELECT count(*) FROM {target_table}")
            target_count = int(cur.fetchone()[0])
            run.record(
                f"staging_to_core_count_{name}",
                "reconciliation",
                source_count == target_count,
                source_value=source_count,
                target_value=target_count,
            )

        cur.execute(
            """
            SELECT COALESCE(SUM(jsonb_array_length(returned_delivery_data::jsonb -> 'Events')),0)
            FROM staging.invoice_delivery WHERE returned_delivery_data IS NOT NULL
            """
        )
        source_delivery = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM core.fact_delivery_event")
        target_delivery = int(cur.fetchone()[0])
        run.record(
            "staging_to_core_count_fact_delivery_event",
            "reconciliation",
            source_delivery == target_delivery,
            source_value=source_delivery,
            target_value=target_delivery,
        )

        measure_checks = [
            ("order_total_including_tax", "SELECT SUM(total_including_tax) FROM staging.order_line", "SELECT SUM(total_including_tax) FROM core.fact_order_line"),
            ("sales_total_including_tax", "SELECT SUM(total_including_tax) FROM staging.sale_line", "SELECT SUM(total_including_tax) FROM core.fact_sales_line"),
            ("sales_profit", "SELECT SUM(profit) FROM staging.sale_line", "SELECT SUM(profit) FROM core.fact_sales_line"),
            ("inventory_quantity", "SELECT SUM(quantity) FROM staging.inventory_movement", "SELECT SUM(quantity) FROM core.fact_inventory_movement"),
            ("customer_transaction_total", "SELECT SUM(total_including_tax) FROM staging.financial_transaction WHERE wwi_customer_transaction_id IS NOT NULL", "SELECT SUM(total_including_tax) FROM core.fact_customer_transaction"),
            ("supplier_transaction_total", "SELECT SUM(total_including_tax) FROM staging.financial_transaction WHERE wwi_supplier_transaction_id IS NOT NULL", "SELECT SUM(total_including_tax) FROM core.fact_supplier_transaction"),
        ]
        for name, source_sql, target_sql in measure_checks:
            cur.execute(source_sql)
            source_value = cur.fetchone()[0]
            cur.execute(target_sql)
            target_value = cur.fetchone()[0]
            run.record(
                f"measure_{name}",
                "reconciliation",
                source_value == target_value,
                source_value=source_value,
                target_value=target_value,
            )


def run_delivery_source_behavior(run: QualityRun, pg) -> None:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM staging.invoice_delivery i
            CROSS JOIN LATERAL jsonb_array_elements(i.returned_delivery_data::jsonb -> 'Events') e
            WHERE i.returned_delivery_data IS NOT NULL
              AND e->>'Event'='DeliveryAttempt'
              AND e->>'Status' IS NULL
            """
        )
        source_null_status = int(cur.fetchone()[0])
        cur.execute(
            "SELECT count(*) FROM core.fact_delivery_event WHERE event_type='DeliveryAttempt' AND event_status IS NULL"
        )
        core_null_status = int(cur.fetchone()[0])
        cur.execute("SELECT count(*) FROM core.fact_delivery_event WHERE is_unconfirmed_attempt")
        flag_count = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT count(*) FROM core.fact_delivery_event
            WHERE is_unconfirmed_attempt
              AND NOT (event_type='DeliveryAttempt' AND event_status IS NULL)
            """
        )
        invalid_flags = int(cur.fetchone()[0])
    passed = source_null_status == core_null_status == flag_count and invalid_flags == 0
    run.record(
        "known_source_behavior_delivery_attempt_status_absent",
        "source_behavior",
        passed,
        source_value=source_null_status,
        target_value=core_null_status,
        details={"is_unconfirmed_attempt_count": flag_count, "invalid_flag_rows": invalid_flags},
    )


def _telemetry_source_stats(ms, kind: str, cutoff: datetime):
    cur = ms.cursor()
    if kind == "coldroom":
        cur.execute(
            """
            SELECT COUNT_BIG(*), MIN(Temperature), MAX(Temperature),
                   MIN(RecordedWhen), MAX(RecordedWhen)
            FROM (
                SELECT Temperature, RecordedWhen
                FROM Warehouse.ColdRoomTemperatures_Archive
                WHERE RecordedWhen < %s
                UNION ALL
                SELECT Temperature, RecordedWhen
                FROM Warehouse.ColdRoomTemperatures
                WHERE RecordedWhen < %s
            ) x
            """,
            (cutoff, cutoff),
        )
    else:
        cur.execute(
            """
            SELECT COUNT_BIG(*), MIN(Temperature), MAX(Temperature),
                   MIN(RecordedWhen), MAX(RecordedWhen)
            FROM Warehouse.VehicleTemperatures
            WHERE RecordedWhen < %s
            """,
            (cutoff,),
        )
    return cur.fetchone()


def run_telemetry_checks(run: QualityRun, ms, pg, full: bool) -> None:
    watermark, _, _ = _pipeline_contract(pg)
    for kind, table in (("coldroom", "coldroom_5m"), ("vehicle", "vehicle_5m")):
        if full:
            raw_count, raw_min, raw_max, raw_first, raw_last = _telemetry_source_stats(
                ms, kind, watermark
            )
        else:
            cur = ms.cursor()
            if kind == "coldroom":
                cur.execute(
                    """
                    SELECT MAX(RecordedWhen) FROM (
                        SELECT RecordedWhen
                        FROM Warehouse.ColdRoomTemperatures_Archive
                        WHERE RecordedWhen < %s
                        UNION ALL
                        SELECT RecordedWhen
                        FROM Warehouse.ColdRoomTemperatures
                        WHERE RecordedWhen < %s
                    ) x
                    """,
                    (watermark, watermark),
                )
            else:
                cur.execute(
                    "SELECT MAX(RecordedWhen) FROM Warehouse.VehicleTemperatures WHERE RecordedWhen < %s",
                    (watermark,),
                )
            raw_last = cur.fetchone()[0]
            raw_count = raw_min = raw_max = raw_first = None

        with pg.cursor() as cur:
            cur.execute(
                f"""
                SELECT count(*),COALESCE(sum(reading_count),0),min(min_temperature),max(max_temperature),
                       min(bucket_start),max(bucket_start),
                       count(*) FILTER (WHERE NOT (min_temperature <= avg_temperature AND avg_temperature <= max_temperature)),
                       count(*) FILTER (WHERE reading_count <= 0),
                       count(*) FILTER (WHERE EXTRACT(MINUTE FROM bucket_start)::int % 5 <> 0 OR EXTRACT(SECOND FROM bucket_start) <> 0),
                       count(*) FILTER (WHERE max_gap_seconds < 0)
                FROM staging.{table}
                """
            )
            agg = cur.fetchone()

        agg_last_bucket = agg[5]
        expected_last_bucket = None
        if raw_last is not None:
            raw_last_n = _normalize_dt(raw_last)
            expected_last_bucket = (
                raw_last_n.replace(second=0, microsecond=0)
                - timedelta(minutes=raw_last_n.minute % 5)
            )
        run.record(
            f"telemetry_freshness_{kind}",
            "freshness",
            _normalize_dt(agg_last_bucket) == expected_last_bucket,
            source_value=expected_last_bucket,
            target_value=agg_last_bucket,
            details={
                "source_max_recorded_when": _text(raw_last),
                "committed_cutoff": _text(watermark),
            },
        )
        invariants = [int(v or 0) for v in agg[6:]]
        run.record(
            f"telemetry_bucket_integrity_{kind}",
            "semantic",
            all(v == 0 for v in invariants),
            source_value="expected zero invariant violations",
            target_value=invariants,
            details={
                "avg_outside_min_max": invariants[0],
                "nonpositive_reading_count": invariants[1],
                "misaligned_bucket": invariants[2],
                "negative_gap": invariants[3],
            },
        )
        if full:
            run.record(
                f"telemetry_reading_count_{kind}",
                "reconciliation",
                int(raw_count) == int(agg[1]),
                source_value=int(raw_count),
                target_value=int(agg[1]),
            )
            run.record(
                f"telemetry_min_temperature_{kind}",
                "reconciliation",
                Decimal(str(raw_min)) == Decimal(str(agg[2])),
                source_value=raw_min,
                target_value=agg[2],
            )
            run.record(
                f"telemetry_max_temperature_{kind}",
                "reconciliation",
                Decimal(str(raw_max)) == Decimal(str(agg[3])),
                source_value=raw_max,
                target_value=agg[3],
            )


def execute(airflow_run_id: str, mode: str) -> str:
    run = QualityRun(airflow_run_id, mode)
    run.begin()
    error_message = None
    ms = None
    pg = None
    try:
        run_dbt_tests(run)
        ms = ms_connect()
        pg = pg_connect()
        run_freshness_checks(run, ms, pg)
        run_volume_reconciliation(run, ms, pg)
        run_core_reconciliation(run, pg)
        run_delivery_source_behavior(run, pg)
        run_telemetry_checks(run, ms, pg, full=(mode == "full"))
    except Exception as exc:
        error_message = f"{type(exc).__name__}: {exc}"
        run.record(
            "quality_gate_execution",
            "structural",
            False,
            source_value="successful execution",
            target_value=error_message,
            details={"exception_type": type(exc).__name__},
        )
    finally:
        if ms is not None:
            ms.close()
        if pg is not None:
            pg.close()
    passed = run.finalize(error_message)
    if not passed:
        raise RuntimeError(f"quality gate failed: quality_run_id={run.quality_run_id}")
    return run.quality_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="data quality/reconciliation data quality and reconciliation gate")
    parser.add_argument("--airflow-run-id", default=f"manual_quality_{uuid.uuid4()}")
    parser.add_argument("--mode", choices=["standard", "full"], default="full")
    args = parser.parse_args()
    quality_run_id = execute(args.airflow_run_id, args.mode)
    print(f"QUALITY_GATE_PASS quality_run_id={quality_run_id}", flush=True)


if __name__ == "__main__":
    main()
