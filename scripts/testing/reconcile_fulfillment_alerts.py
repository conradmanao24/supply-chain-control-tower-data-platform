from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.alerts import evaluate_fulfillment


def main() -> None:
    conn = psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
        cursor_factory=RealDictCursor,
    )
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH frontier AS (
                    SELECT (safe_through_cutoff - interval '1 day')::date AS business_date
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                )
                SELECT DISTINCT entity_id::int AS order_id
                FROM alert.alerts
                WHERE rule_id LIKE 'fulfillment.%'
                  AND status IN ('open','acknowledged')
                UNION
                SELECT o.order_id
                FROM realtime.current_order_state o
                CROSS JOIN frontier f
                WHERE o.order_date >= f.business_date - interval '30 days'
                  AND o.order_date <= f.business_date
                """
            )
            ids = [int(row["order_id"]) for row in cur.fetchall()]

            counts: dict[str, int] = {}
            for order_id in ids:
                result = evaluate_fulfillment(cur, order_id, None)
                for state in result.values():
                    counts[state] = counts.get(state, 0) + 1

            print(f"ORDERS_EVALUATED={len(ids)}")
            print("RESULTS=" + repr(counts))


if __name__ == "__main__":
    main()
