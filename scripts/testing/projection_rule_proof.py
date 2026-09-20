from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.alerts import (
    evaluate_delivery,
    evaluate_fulfillment,
    evaluate_inventory,
    evaluate_procurement,
)

conn = psycopg2.connect(
    host=os.environ["DWH_HOST"],
    port=int(os.environ.get("DWH_PORT", "5432")),
    dbname=os.environ["DWH_DB"],
    user=os.environ["DWH_USER"],
    password=os.environ["DWH_PASSWORD"],
)

today = datetime.now(timezone.utc).date()
ids = {
    "inventory_negative": 990000001,
    "inventory_reorder": 990000002,
    "inventory_watch": 990000003,
    "fulfillment_overdue": 990000011,
    "fulfillment_due_today": 990000012,
    "fulfillment_backorder": 990000013,
    "delivery_overdue_order": 990000021,
    "delivery_due_order": 990000022,
    "delivery_overdue_invoice": 990000031,
    "delivery_due_invoice": 990000032,
    "procurement_overdue": 990000041,
    "procurement_due": 990000042,
}

try:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Everything is kept inside one transaction and rolled back at the end.
        cur.execute(
            "DELETE FROM alert.alerts WHERE entity_id = ANY(%s)",
            ([str(v) for v in ids.values()],),
        )

        # Inventory: critical negative, reorder warning, target watch info.
        inventory_cases = [
            (ids["inventory_negative"], "ALERT NEGATIVE", -5, 10, 20),
            (ids["inventory_reorder"], "ALERT REORDER", 8, 10, 20),
            (ids["inventory_watch"], "ALERT WATCH", 15, 10, 20),
        ]
        for stock_id, name, qoh, reorder, target in inventory_cases:
            cur.execute(
                """
                INSERT INTO realtime.current_inventory_state
                (stock_item_id,stock_item_name,quantity_on_hand,last_stocktake_quantity,
                 reorder_level,target_stock_level,last_edited_when)
                VALUES (%s,%s,%s,0,%s,%s,now())
                """,
                (stock_id, name, qoh, reorder, target),
            )

        # Fulfillment: overdue, due-today, and backorder context.
        fulfillment_cases = [
            (ids["fulfillment_overdue"], today - timedelta(days=1), False, None, False),
            (ids["fulfillment_due_today"], today, False, None, False),
            (ids["fulfillment_backorder"], today + timedelta(days=3), False, 12345, True),
        ]
        for order_id, due, picked, backorder_id, under_supply in fulfillment_cases:
            cur.execute(
                """
                INSERT INTO realtime.current_order_state
                (order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,
                 backorder_order_id,picking_completed_when,last_edited_when)
                VALUES (%s,1,%s,%s,%s,%s,%s,now())
                """,
                (
                    order_id,
                    today - timedelta(days=5),
                    due,
                    under_supply,
                    backorder_id,
                    datetime.now() if picked else None,
                ),
            )

        # Delivery: use a linked order for due date semantics. Receiver-not-present
        # is intentionally allowed to contradict ConfirmedDeliveryTime because WWI can
        # contain this source quirk and the rule must preserve event context.
        delivery_orders = [
            (ids["delivery_overdue_order"], today - timedelta(days=1)),
            (ids["delivery_due_order"], today),
        ]
        for order_id, due in delivery_orders:
            cur.execute(
                """
                INSERT INTO realtime.current_order_state
                (order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,
                 picking_completed_when,last_edited_when)
                VALUES (%s,1,%s,%s,false,now(),now())
                """,
                (order_id, today - timedelta(days=5), due),
            )

        receiver_not_present = {
            "Events": [
                {"Event": "Ready for collection", "EventTime": f"{today.isoformat()}T08:00:00"},
                {
                    "Event": "DeliveryAttempt",
                    "Comment": "Receiver not present",
                    "EventTime": f"{today.isoformat()}T09:00:00",
                },
            ]
        }
        ready_only = {
            "Events": [
                {"Event": "Ready for collection", "EventTime": f"{today.isoformat()}T08:00:00"}
            ]
        }
        cur.execute(
            """
            INSERT INTO realtime.current_delivery_state
            (invoice_id,order_id,customer_id,delivery_method_id,invoice_date,
             returned_delivery_data,confirmed_delivery_time,last_edited_when)
            VALUES (%s,%s,1,1,%s,%s,now(),now())
            """,
            (
                ids["delivery_overdue_invoice"],
                ids["delivery_overdue_order"],
                today - timedelta(days=1),
                json.dumps(receiver_not_present),
            ),
        )
        cur.execute(
            """
            INSERT INTO realtime.current_delivery_state
            (invoice_id,order_id,customer_id,delivery_method_id,invoice_date,
             returned_delivery_data,confirmed_delivery_time,last_edited_when)
            VALUES (%s,%s,1,1,%s,%s,NULL,now())
            """,
            (
                ids["delivery_due_invoice"],
                ids["delivery_due_order"],
                today,
                json.dumps(ready_only),
            ),
        )

        # Procurement: overdue-under-received and due-today-under-received.
        procurement_cases = [
            (ids["procurement_overdue"], today - timedelta(days=1)),
            (ids["procurement_due"], today),
        ]
        for po_id, due in procurement_cases:
            cur.execute(
                """
                INSERT INTO realtime.current_procurement_state
                (purchase_order_id,supplier_id,order_date,expected_delivery_date,is_order_finalized,
                 ordered_outers,received_outers,under_received_line_count,last_edited_when)
                VALUES (%s,1,%s,%s,false,10,5,1,now())
                """,
                (po_id, today - timedelta(days=5), due),
            )

        results = {
            "inventory_negative": evaluate_inventory(cur, ids["inventory_negative"], None),
            "inventory_reorder": evaluate_inventory(cur, ids["inventory_reorder"], None),
            "inventory_watch": evaluate_inventory(cur, ids["inventory_watch"], None),
            "fulfillment_overdue": evaluate_fulfillment(cur, ids["fulfillment_overdue"], None),
            "fulfillment_due_today": evaluate_fulfillment(cur, ids["fulfillment_due_today"], None),
            "fulfillment_backorder": evaluate_fulfillment(cur, ids["fulfillment_backorder"], None),
            "delivery_overdue": evaluate_delivery(cur, ids["delivery_overdue_invoice"], None),
            "delivery_due_today": evaluate_delivery(cur, ids["delivery_due_invoice"], None),
            "procurement_overdue": evaluate_procurement(cur, ids["procurement_overdue"], None),
            "procurement_due_today": evaluate_procurement(cur, ids["procurement_due"], None),
        }

        cur.execute(
            """
            SELECT rule_id,entity_type,entity_id,severity,status
            FROM alert.alerts
            WHERE entity_id = ANY(%s)
            ORDER BY rule_id,entity_id
            """,
            ([str(v) for v in ids.values()],),
        )
        alerts = cur.fetchall()

        cur.execute(
            """
            SELECT rule_id,entity_type,entity_id,count(*) AS active_count
            FROM alert.alerts
            WHERE entity_id = ANY(%s) AND status IN ('open','acknowledged')
            GROUP BY rule_id,entity_type,entity_id
            HAVING count(*) > 1
            """,
            ([str(v) for v in ids.values()],),
        )
        duplicate_active = cur.fetchall()

        required_rules = {
            "inventory.negative_stock",
            "inventory.reorder",
            "inventory.target_watch",
            "fulfillment.overdue",
            "fulfillment.due_today",
            "fulfillment.backorder",
            "delivery.overdue",
            "delivery.due_today",
            "delivery.receiver_not_present",
            "procurement.overdue_under_received",
            "procurement.due_today_under_received",
        }
        opened_rules = {row["rule_id"] for row in alerts}
        missing = sorted(required_rules - opened_rules)
        if missing:
            raise RuntimeError(f"required rules did not open: {missing}")
        if duplicate_active:
            raise RuntimeError(f"duplicate active alerts found: {duplicate_active}")

        print(
            json.dumps(
                {
                    "today_utc": today.isoformat(),
                    "results": results,
                    "opened_rules": sorted(opened_rules),
                    "active_duplicate_rows": duplicate_active,
                    "proof_alert_count": len(alerts),
                },
                indent=2,
                default=str,
            )
        )
finally:
    conn.rollback()
    conn.close()
