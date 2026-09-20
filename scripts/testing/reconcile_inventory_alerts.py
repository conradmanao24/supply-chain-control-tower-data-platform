from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.alerts import evaluate_inventory


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
            cur.execute("SELECT stock_item_id FROM realtime.current_inventory_state ORDER BY stock_item_id")
            ids = [int(row["stock_item_id"]) for row in cur.fetchall()]
            counts: dict[str, int] = {}
            for stock_item_id in ids:
                result = evaluate_inventory(cur, stock_item_id, None)
                for state in result.values():
                    counts[state] = counts.get(state, 0) + 1
            print(f"ITEMS_EVALUATED={len(ids)}")
            print("RESULTS=" + repr(counts))


if __name__ == "__main__":
    main()
