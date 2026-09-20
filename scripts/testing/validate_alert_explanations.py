from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.alert_explanations import explain_alert


def main() -> int:
    conn = psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )

    with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT a.alert_id,a.rule_id,r.description,
                   a.observed_value,a.threshold_value
            FROM alert.alerts a
            JOIN alert.rule_config r ON r.rule_id=a.rule_id
            WHERE a.status IN ('open','acknowledged')
            ORDER BY a.rule_id,a.alert_id
            """
        )
        rows = cur.fetchall()

    counts: dict[str, dict[str, int]] = {}
    failures: list[tuple[int, str, str]] = []

    for row in rows:
        result = explain_alert(
            row["rule_id"],
            row["description"],
            row["observed_value"],
            row["threshold_value"],
        )
        bucket = counts.setdefault(
            row["rule_id"],
            {"total": 0, "verified": 0, "fallback": 0},
        )
        bucket["total"] += 1
        if result["evidence_verified"]:
            bucket["verified"] += 1
        else:
            bucket["fallback"] += 1
            failures.append(
                (
                    int(row["alert_id"]),
                    row["rule_id"],
                    result["what_happened"],
                )
            )

    print(f"ACTIVE_ALERTS={len(rows)}")
    for rule_id in sorted(counts):
        print(f"{rule_id}={counts[rule_id]}")

    print(f"UNVERIFIED_ACTIVE_ALERTS={len(failures)}")
    for alert_id, rule_id, explanation in failures[:20]:
        print(f"UNVERIFIED alert_id={alert_id} rule_id={rule_id} text={explanation}")

    # Current active exceptions must all be evidence-verifiable before the
    # business-facing What happened view is approved.
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
