from __future__ import annotations

import argparse
import json
import os
from typing import Iterable

import pymssql
import psycopg2
from psycopg2.extras import RealDictCursor

from realtime.consumer import source_row, upsert_delivery, upsert_inventory, upsert_order, upsert_procurement, upsert_sensor

RELIABILITY_LOCK_KEY = 807008

BUSINESS = {
    "orders": {
        "table": "current_order_state",
        "event_type": "order.changed",
        "proc": "GetOrderCurrentState",
        "pk": "order_id",
        "upsert": upsert_order,
        "seed": """
            INSERT INTO realtime.current_order_state
            (order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,backorder_order_id,picking_completed_when,last_edited_when,source_event_id)
            SELECT order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,backorder_order_id,picking_completed_when,last_edited_when,NULL
            FROM staging.order_state
        """,
    },
    "deliveries": {
        "table": "current_delivery_state",
        "event_type": "delivery.changed",
        "proc": "GetDeliveryCurrentState",
        "pk": "invoice_id",
        "upsert": upsert_delivery,
        "seed": """
            INSERT INTO realtime.current_delivery_state
            (invoice_id,order_id,customer_id,delivery_method_id,invoice_date,delivery_run,run_position,returned_delivery_data,confirmed_delivery_time,confirmed_received_by,last_edited_when,source_event_id)
            SELECT invoice_id,order_id,customer_id,delivery_method_id,invoice_date,delivery_run,run_position,
                   CASE WHEN returned_delivery_data IS NULL THEN NULL ELSE returned_delivery_data::jsonb END,
                   confirmed_delivery_time,confirmed_received_by,last_edited_when,NULL
            FROM staging.invoice_delivery
        """,
    },
    "procurement": {
        "table": "current_procurement_state",
        "event_type": "procurement.changed",
        "proc": "GetProcurementCurrentState",
        "pk": "purchase_order_id",
        "upsert": upsert_procurement,
        "seed": """
            INSERT INTO realtime.current_procurement_state
            (purchase_order_id,supplier_id,order_date,expected_delivery_date,is_order_finalized,ordered_outers,received_outers,under_received_line_count,last_edited_when,source_event_id)
            SELECT p.purchase_order_id,p.supplier_id,p.order_date,p.expected_delivery_date,p.is_order_finalized,
                   COALESCE(a.ordered_outers,0),COALESCE(a.received_outers,0),COALESCE(a.under_received_line_count,0),p.last_edited_when,NULL
            FROM staging.purchase_order_state p
            LEFT JOIN (
                SELECT wwi_purchase_order_id,
                       SUM(ordered_outers)::bigint AS ordered_outers,
                       SUM(received_outers)::bigint AS received_outers,
                       COUNT(*) FILTER (WHERE received_outers < ordered_outers)::integer AS under_received_line_count
                FROM staging.purchase_line
                GROUP BY wwi_purchase_order_id
            ) a ON a.wwi_purchase_order_id=p.purchase_order_id
        """,
    },
    "inventory": {
        "table": "current_inventory_state",
        "event_type": "inventory.changed",
        "proc": "GetInventoryCurrentState",
        "pk": "stock_item_id",
        "upsert": upsert_inventory,
        "seed": """
            INSERT INTO realtime.current_inventory_state
            (stock_item_id,stock_item_name,quantity_on_hand,last_stocktake_quantity,reorder_level,target_stock_level,last_edited_when,source_event_id)
            SELECT h.stock_item_id,p.stock_item_name,h.quantity_on_hand,h.last_stocktake_quantity,h.reorder_level,h.target_stock_level,h.last_edited_when,NULL
            FROM staging.stock_holding_current h
            JOIN staging.product_current p ON p.stock_item_id=h.stock_item_id
        """,
    },
}


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def sql_connect():
    return pymssql.connect(
        server=os.environ["WWI_HOST"],
        port=int(os.environ.get("WWI_PORT", "1433")),
        user=os.environ["WWI_EVENT_USER"],
        password=os.environ["WWI_EVENT_PASSWORD"],
        database=os.environ["WWI_DATABASE"],
        autocommit=True,
        login_timeout=10,
        timeout=60,
    )


def touched_entities(cur, event_type: str) -> list[int]:
    cur.execute(
        """
        SELECT DISTINCT (key_item->>'entity_id')::integer AS entity_id
        FROM realtime.event_log e
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(e.payload->'entity_keys','[]'::jsonb)) key_item
        WHERE e.event_type=%s
          AND key_item ? 'entity_id'
        ORDER BY 1
        """,
        (event_type,),
    )
    return [int(r[0]) for r in cur.fetchall()]


def rebuild_business(pg_conn, sql_conn, domain: str) -> dict:
    cfg = BUSINESS[domain]
    with pg_conn:
        cur = pg_conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (RELIABILITY_LOCK_KEY,))
        cur.execute(f"DELETE FROM realtime.{cfg['table']}")
        cur.execute(cfg["seed"])
        seeded = cur.rowcount
        touched = touched_entities(cur, cfg["event_type"])
        refreshed = 0
        deleted = 0
        for entity_id in touched:
            row = source_row(sql_conn, cfg["proc"], entity_id)
            if row is None:
                cur.execute(f"DELETE FROM realtime.{cfg['table']} WHERE {cfg['pk']}=%s", (entity_id,))
                deleted += cur.rowcount
            else:
                cfg["upsert"](cur, row, None)
                refreshed += 1
        cur.execute(f"SELECT count(*) FROM realtime.{cfg['table']}")
        final_count = int(cur.fetchone()[0])
    return {
        "domain": domain,
        "seeded": seeded,
        "event_touched_refreshed": refreshed,
        "event_touched_deleted": deleted,
        "final_count": final_count,
    }


def rebuild_sensors(pg_conn) -> dict:
    with pg_conn:
        cur = pg_conn.cursor()
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (RELIABILITY_LOCK_KEY,))
        cur.execute("DELETE FROM realtime.current_sensor_state")
        cur.execute(
            """
            INSERT INTO realtime.current_sensor_state
            (sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,reading_count,value_basis,source_event_id)
            SELECT 'coldroom:'||sensor_number,'coldroom',NULL,sensor_number,last_recorded_when,avg_temperature,reading_count::integer,'5m_seed',NULL
            FROM (
                SELECT DISTINCT ON (sensor_number) sensor_number,last_recorded_when,avg_temperature,reading_count,bucket_start
                FROM staging.coldroom_5m
                ORDER BY sensor_number,bucket_start DESC
            ) x
            """
        )
        cold_seed = cur.rowcount
        cur.execute(
            """
            INSERT INTO realtime.current_sensor_state
            (sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,reading_count,value_basis,source_event_id)
            SELECT 'vehicle:'||vehicle_registration||':'||sensor_number,'vehicle',vehicle_registration,sensor_number,last_recorded_when,avg_temperature,reading_count::integer,'5m_seed',NULL
            FROM (
                SELECT DISTINCT ON (vehicle_registration,sensor_number) vehicle_registration,sensor_number,last_recorded_when,avg_temperature,reading_count,bucket_start
                FROM staging.vehicle_5m
                ORDER BY vehicle_registration,sensor_number,bucket_start DESC
            ) x
            """
        )
        vehicle_seed = cur.rowcount
        cur.execute(
            """
            SELECT event_id::text,event_type,payload
            FROM realtime.event_log
            WHERE (event_type LIKE 'telemetry.coldroom.%'
                OR event_type LIKE 'telemetry.vehicle.%')
              AND source_table NOT LIKE 'Phase%Proof%'
            ORDER BY occurred_at_utc,event_id
            """
        )
        events = cur.fetchall()
        applied = 0
        for event_id, event_type, payload in events:
            body = payload if isinstance(payload, dict) else json.loads(payload)
            for key in body.get("entity_keys") or []:
                if upsert_sensor(cur, event_type, key, event_id):
                    applied += 1
        cur.execute("SELECT count(*) FROM realtime.current_sensor_state")
        final_count = int(cur.fetchone()[0])
    return {
        "domain": "sensors",
        "coldroom_seeded": cold_seed,
        "vehicle_seeded": vehicle_seed,
        "event_readings_applied": applied,
        "final_count": final_count,
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rebuild realtime realtime current-state projections deterministically.")
    p.add_argument(
        "--domain",
        choices=["all", "orders", "deliveries", "procurement", "inventory", "sensors"],
        default="all",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    pg_conn = pg_connect()
    sql_conn = sql_connect()
    results = []
    try:
        domains: Iterable[str] = BUSINESS.keys() if args.domain == "all" else ([args.domain] if args.domain in BUSINESS else [])
        for domain in domains:
            result = rebuild_business(pg_conn, sql_conn, domain)
            results.append(result)
            print("REBUILD_DOMAIN_PASS", json.dumps(result, sort_keys=True), flush=True)
        if args.domain in ("all", "sensors"):
            result = rebuild_sensors(pg_conn)
            results.append(result)
            print("REBUILD_DOMAIN_PASS", json.dumps(result, sort_keys=True), flush=True)
        print("REBUILD_COMPLETE", json.dumps(results, sort_keys=True), flush=True)
    finally:
        sql_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()

