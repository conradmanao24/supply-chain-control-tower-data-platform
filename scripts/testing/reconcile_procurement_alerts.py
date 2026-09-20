from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.alerts import evaluate_procurement


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
                SELECT p.purchase_order_id
                FROM realtime.current_procurement_state p
                CROSS JOIN frontier f
                WHERE p.order_date >= f.business_date - interval '29 days'
                  AND p.order_date <= f.business_date
                ORDER BY p.purchase_order_id
                """
            )
            ids = [int(row["purchase_order_id"]) for row in cur.fetchall()]
            counts: dict[str, int] = {}
            for po_id in ids:
                result = evaluate_procurement(cur, po_id, None)
                for state in result.values():
                    counts[state] = counts.get(state, 0) + 1
            print(f"POS_EVALUATED={len(ids)}")
            print("RESULTS=" + repr(counts))


if __name__ == "__main__":
    main()
