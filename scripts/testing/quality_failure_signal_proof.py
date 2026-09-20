from __future__ import annotations

import os
import sys

import psycopg2

sys.path.insert(0, "/opt/airflow/src")
from quality.quality_gate import QualityRun

FAIL_RUN = "quality_failure_signal_proof"
RECOVERY_RUN = "quality_recovery_signal_proof"
ENTITY = "supply_chain_quality_gate"


def connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def active_alerts():
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT alert_id,rule_id,status
                FROM alert.alerts
                WHERE entity_type='platform' AND entity_id=%s
                  AND rule_id IN ('platform.data_quality_failed','platform.reconciliation_mismatch')
                  AND status IN ('open','acknowledged')
                ORDER BY rule_id
                """,
                (ENTITY,),
            )
            return cur.fetchall()


with connect() as conn:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM quality.run_history WHERE airflow_run_id IN (%s,%s)", (FAIL_RUN, RECOVERY_RUN))
        cur.execute(
            "DELETE FROM alert.alerts WHERE entity_type='platform' AND entity_id=%s AND rule_id IN ('platform.data_quality_failed','platform.reconciliation_mismatch')",
            (ENTITY,),
        )

fail = QualityRun(FAIL_RUN, "standard")
fail.begin()
fail.record(
    "controlled_reconciliation_mismatch",
    "reconciliation",
    False,
    source_value=100,
    target_value=99,
    details={"proof": True},
)
fail_result = fail.finalize("controlled data quality/reconciliation failure-path proof")
print("FAIL_RUN_RESULT", fail_result)
opened = active_alerts()
print("ACTIVE_AFTER_FAILURE", opened)
if fail_result is not False or len(opened) != 2:
    raise RuntimeError("failure proof did not open both platform quality alerts")

recovery = QualityRun(RECOVERY_RUN, "standard")
recovery.begin()
recovery.record(
    "controlled_reconciliation_recovered",
    "reconciliation",
    True,
    source_value=100,
    target_value=100,
    details={"proof": True},
)
recovery_result = recovery.finalize()
print("RECOVERY_RUN_RESULT", recovery_result)
remaining = active_alerts()
print("ACTIVE_AFTER_RECOVERY", remaining)
if recovery_result is not True or remaining:
    raise RuntimeError("recovery proof did not clear platform quality alerts")

with connect() as conn:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT rule_id,status,resolution_reason
            FROM alert.alerts
            WHERE entity_type='platform' AND entity_id=%s
              AND rule_id IN ('platform.data_quality_failed','platform.reconciliation_mismatch')
            ORDER BY rule_id
            """,
            (ENTITY,),
        )
        print("RESOLVED_ALERTS", cur.fetchall())
        cur.execute("DELETE FROM quality.run_history WHERE airflow_run_id IN (%s,%s)", (FAIL_RUN, RECOVERY_RUN))
        cur.execute(
            "DELETE FROM alert.alerts WHERE entity_type='platform' AND entity_id=%s AND rule_id IN ('platform.data_quality_failed','platform.reconciliation_mismatch')",
            (ENTITY,),
        )

print("CLEANUP PASS")
