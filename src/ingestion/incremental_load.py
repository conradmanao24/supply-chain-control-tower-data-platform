from __future__ import annotations

import argparse
import csv
import io
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

import pymssql
import psycopg2

from ingestion.initial_load import snake, serialize, pg_columns

FACT_PROCS = {
    "order_line": ("Integration.GetOrderUpdates", ("wwi_order_id", "wwi_stock_item_id")),
    "sale_line": ("Integration.GetSaleUpdates", ("wwi_invoice_id", "wwi_stock_item_id")),
    "inventory_movement": ("Integration.GetMovementUpdates", ("wwi_stock_item_transaction_id",)),
    "purchase_line": ("Integration.GetPurchaseUpdates", ("wwi_purchase_order_id", "wwi_stock_item_id")),
    "financial_transaction": (
        "Integration.GetTransactionUpdates",
        ("wwi_customer_transaction_id", "wwi_supplier_transaction_id"),
    ),
}

DELTA_QUERIES = {
    "order_state": (
        "SELECT * FROM ControlTowerExtract.OrderState WHERE LastEditedWhen > %s AND LastEditedWhen <= %s",
        ("order_id",),
    ),
    "invoice_delivery": (
        "SELECT * FROM ControlTowerExtract.InvoiceDelivery WHERE LastEditedWhen > %s AND LastEditedWhen <= %s",
        ("invoice_id",),
    ),
    "purchase_order_state": (
        "SELECT * FROM ControlTowerExtract.PurchaseOrderState WHERE LastEditedWhen > %s AND LastEditedWhen <= %s",
        ("purchase_order_id",),
    ),
    "customer_history": (
        "EXEC ControlTowerExtract.GetCustomerHistoryDelta @LastCutoff=%s, @NewCutoff=%s",
        ("customer_id", "valid_from"),
    ),
    "supplier_history": (
        "SELECT * FROM ControlTowerExtract.SupplierHistory WHERE ValidFrom > %s AND ValidFrom <= %s",
        ("supplier_id", "valid_from"),
    ),
    "product_history": (
        "SELECT * FROM ControlTowerExtract.ProductHistory WHERE ValidFrom > %s AND ValidFrom <= %s",
        ("stock_item_id", "valid_from"),
    ),
    "employee_current": (
        "SELECT * FROM ControlTowerExtract.EmployeeCurrent WHERE ValidFrom > %s AND ValidFrom <= %s",
        ("person_id",),
    ),
    "employee_history": (
        "SELECT * FROM ControlTowerExtract.EmployeeHistory WHERE ValidFrom > %s AND ValidFrom <= %s",
        ("person_id", "valid_from"),
    ),
}

# Small/current objects whose upstream dependencies or hard deletes are not fully
# represented by a single WWI cutoff column. Read the bounded source object, but
# write only rows that are new/changed and remove rows that disappeared.
DIFF_SNAPSHOTS = {
    "customer_current": ("EXEC ControlTowerExtract.GetCustomerCurrent", ("customer_id",)),
    "supplier_current": ("SELECT * FROM ControlTowerExtract.SupplierCurrent", ("supplier_id",)),
    "product_current": ("SELECT * FROM ControlTowerExtract.ProductCurrent", ("stock_item_id",)),
    "product_stock_group": ("SELECT * FROM ControlTowerExtract.ProductStockGroup", ("stock_item_stock_group_id",)),
    "stock_holding_current": ("SELECT * FROM ControlTowerExtract.StockHoldingCurrent", ("stock_item_id",)),
    "delivery_method_current": ("SELECT * FROM ControlTowerExtract.DeliveryMethodCurrent", ("delivery_method_id",)),
    "transaction_type_current": ("SELECT * FROM ControlTowerExtract.TransactionTypeCurrent", ("transaction_type_id",)),
    "payment_method_current": ("SELECT * FROM ControlTowerExtract.PaymentMethodCurrent", ("payment_method_id",)),
    "package_type_current": ("SELECT * FROM ControlTowerExtract.PackageTypeCurrent", ("package_type_id",)),
    "stock_group_current": ("SELECT * FROM ControlTowerExtract.StockGroupCurrent", ("stock_group_id",)),
}

HISTORY_KEYS = {
    "customer_history": "customer_id",
    "supplier_history": "supplier_id",
    "product_history": "stock_item_id",
    "employee_history": "person_id",
}


def copy_rows(cur, relation: str, columns: list[str], rows: Iterable[tuple]) -> int:
    rows = list(rows)
    if not rows:
        return 0
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow([serialize(v) for v in row])
    buf.seek(0)
    cols = ", ".join(columns)
    cur.copy_expert(
        f"COPY {relation} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
        buf,
    )
    return len(rows)


def join_condition(left: str, right: str, keys: tuple[str, ...]) -> str:
    return " AND ".join(f"{left}.{k} IS NOT DISTINCT FROM {right}.{k}" for k in keys)


def prepare_temp(pg_cur, table_name: str) -> str:
    temp = f"incremental_{table_name}"
    pg_cur.execute(f"DROP TABLE IF EXISTS {temp}")
    pg_cur.execute(
        f"CREATE TEMP TABLE {temp} (LIKE staging.{table_name} INCLUDING DEFAULTS) ON COMMIT DROP"
    )
    return temp


def fetch_to_temp(ms_cur, pg_cur, table_name: str, source_sql: str, params=(), batch_size=10000):
    ms_cur.execute(source_sql, params)
    source_columns = [snake(d[0]) for d in ms_cur.description]
    target_columns = pg_columns(pg_cur.connection, table_name)
    if source_columns != target_columns:
        raise RuntimeError(
            f"Column contract mismatch for {table_name}: source={source_columns}, target={target_columns}"
        )
    temp = prepare_temp(pg_cur, table_name)
    total = 0
    while True:
        rows = ms_cur.fetchmany(batch_size)
        if not rows:
            break
        total += copy_rows(pg_cur, temp, target_columns, rows)
    return temp, target_columns, total


def merge_temp(pg_cur, table_name: str, temp: str, columns: list[str], keys: tuple[str, ...]) -> tuple[int, int]:
    cond = join_condition("t", "s", keys)
    pg_cur.execute(f"DELETE FROM staging.{table_name} t USING {temp} s WHERE {cond}")
    replaced = pg_cur.rowcount
    insert_cols = columns + ["ingested_at"]
    cols = ", ".join(insert_cols)
    pg_cur.execute(f"INSERT INTO staging.{table_name} ({cols}) SELECT {cols} FROM {temp}")
    return replaced, pg_cur.rowcount


def recalc_history_validity(pg_cur, table_name: str, temp: str, business_key: str):
    pg_cur.execute(
        f"""
        WITH affected AS (
            SELECT DISTINCT {business_key} FROM {temp}
        ), sequenced AS (
            SELECT h.{business_key}, h.valid_from,
                   LEAD(h.valid_from) OVER (PARTITION BY h.{business_key} ORDER BY h.valid_from) AS next_valid_from
            FROM staging.{table_name} h
            JOIN affected a USING ({business_key})
        )
        UPDATE staging.{table_name} h
        SET valid_to = COALESCE(s.next_valid_from, timestamp '9999-12-31 23:59:59.999999')
        FROM sequenced s
        WHERE h.{business_key}=s.{business_key}
          AND h.valid_from=s.valid_from
          AND h.valid_to IS DISTINCT FROM COALESCE(s.next_valid_from, timestamp '9999-12-31 23:59:59.999999')
        """
    )
    return pg_cur.rowcount


def load_delta(ms_conn, pg_conn, table_name: str, source_sql: str, keys: tuple[str, ...], start: str, end: str):
    started = time.time()
    ms_cur = ms_conn.cursor()
    try:
        with pg_conn.cursor() as pg_cur:
            temp, columns, fetched = fetch_to_temp(ms_cur, pg_cur, table_name, source_sql, (start, end))
            if fetched == 0:
                pg_conn.rollback()  # drop temp and preserve target untouched
                print(f"PASS {table_name}: 0 changed rows", flush=True)
                return 0
            replaced, inserted = merge_temp(pg_cur, table_name, temp, columns, keys)
            validity_updates = 0
            if table_name in HISTORY_KEYS:
                validity_updates = recalc_history_validity(pg_cur, table_name, temp, HISTORY_KEYS[table_name])
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    print(
        f"PASS {table_name}: fetched={fetched:,} replaced={replaced:,} inserted={inserted:,} "
        f"validity_updates={validity_updates:,} in {time.time()-started:.2f}s",
        flush=True,
    )
    return fetched


def sync_snapshot(ms_conn, pg_conn, table_name: str, source_sql: str, keys: tuple[str, ...]):
    started = time.time()
    ms_cur = ms_conn.cursor()
    try:
        with pg_conn.cursor() as pg_cur:
            temp, columns, source_count = fetch_to_temp(ms_cur, pg_cur, table_name, source_sql)
            cond = join_condition("t", "s", keys)
            non_key_cols = [c for c in columns if c not in keys]
            if non_key_cols:
                left = ", ".join(f"t.{c}" for c in non_key_cols)
                right = ", ".join(f"s.{c}" for c in non_key_cols)
                changed_pred = f"ROW({left}) IS DISTINCT FROM ROW({right})"
            else:
                changed_pred = "FALSE"

            # Remove rows deleted from source.
            pg_cur.execute(
                f"DELETE FROM staging.{table_name} t WHERE NOT EXISTS (SELECT 1 FROM {temp} s WHERE {cond})"
            )
            deleted = pg_cur.rowcount

            # Remove changed versions; unchanged rows keep their original ingested_at.
            pg_cur.execute(
                f"DELETE FROM staging.{table_name} t USING {temp} s WHERE {cond} AND ({changed_pred})"
            )
            changed = pg_cur.rowcount

            # Insert rows not currently present (new + rows just removed as changed).
            insert_cols = columns + ["ingested_at"]
            cols = ", ".join(insert_cols)
            pg_cur.execute(
                f"INSERT INTO staging.{table_name} ({cols}) "
                f"SELECT {cols} FROM {temp} s "
                f"WHERE NOT EXISTS (SELECT 1 FROM staging.{table_name} t WHERE {cond})"
            )
            inserted = pg_cur.rowcount
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    print(
        f"PASS {table_name}: source={source_count:,} changed={changed:,} new_or_replaced={inserted:,} "
        f"deleted={deleted:,} in {time.time()-started:.2f}s",
        flush=True,
    )
    return changed + inserted + deleted


def load_geography_delta(ms_conn, pg_conn, start: str, end: str):
    started = time.time()
    src = ms_conn.cursor()
    src.execute("EXEC Integration.GetCityUpdates @LastCutoff=%s, @NewCutoff=%s", (start, end))
    city_ids = sorted({row[0] for row in src.fetchall()})
    if not city_ids:
        print("PASS geography_current: 0 changed cities", flush=True)
        return 0

    rows = []
    columns = None
    for i in range(0, len(city_ids), 1000):
        chunk = city_ids[i:i+1000]
        placeholders = ",".join(["%s"] * len(chunk))
        cur = ms_conn.cursor()
        cur.execute(
            f"SELECT * FROM ControlTowerExtract.GeographyCurrent WHERE CityID IN ({placeholders})",
            tuple(chunk),
        )
        if columns is None:
            columns = [snake(d[0]) for d in cur.description]
        rows.extend(cur.fetchall())

    target_columns = pg_columns(pg_conn, "geography_current")
    if columns != target_columns:
        raise RuntimeError(f"Column contract mismatch geography_current: source={columns}, target={target_columns}")
    try:
        with pg_conn.cursor() as pg_cur:
            temp = prepare_temp(pg_cur, "geography_current")
            copy_rows(pg_cur, temp, columns, rows)
            replaced, inserted = merge_temp(pg_cur, "geography_current", temp, columns, ("city_id",))
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    print(
        f"PASS geography_current: changed_ids={len(city_ids):,} replaced={replaced:,} inserted={inserted:,} "
        f"in {time.time()-started:.2f}s",
        flush=True,
    )
    return len(city_ids)


def main():
    p = argparse.ArgumentParser(description="incremental processing explicit-window incremental staging loader")
    p.add_argument("--start", required=True, help="exclusive last cutoff")
    p.add_argument("--end", required=True, help="inclusive new cutoff")
    p.add_argument("--scope", choices=["all", "facts", "state", "masters"], default="all")
    args = p.parse_args()
    if datetime.fromisoformat(args.end) <= datetime.fromisoformat(args.start):
        raise SystemExit("--end must be greater than --start")

    ms = pymssql.connect(
        server=os.environ["WWI_HOST"], port=int(os.environ["WWI_PORT"]),
        user=os.environ["WWI_SOURCE_USER"], password=os.environ["WWI_SOURCE_PASSWORD"],
        database=os.environ["WWI_DATABASE"], autocommit=True,
    )
    pg = psycopg2.connect(
        host=os.environ["DWH_HOST"], port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"], user=os.environ["DWH_USER"], password=os.environ["DWH_PASSWORD"],
    )
    results = {}
    try:
        if args.scope in ("all", "facts"):
            for table, (proc, keys) in FACT_PROCS.items():
                results[table] = load_delta(
                    ms, pg, table,
                    f"EXEC {proc} @LastCutoff=%s, @NewCutoff=%s",
                    keys, args.start, args.end,
                )

        if args.scope in ("all", "state"):
            for table in ("order_state", "invoice_delivery", "purchase_order_state"):
                sql, keys = DELTA_QUERIES[table]
                results[table] = load_delta(ms, pg, table, sql, keys, args.start, args.end)
            results["stock_holding_current"] = sync_snapshot(
                ms, pg, "stock_holding_current", *DIFF_SNAPSHOTS["stock_holding_current"]
            )

        if args.scope in ("all", "masters"):
            for table in ("customer_history", "supplier_history", "product_history", "employee_history", "employee_current"):
                sql, keys = DELTA_QUERIES[table]
                results[table] = load_delta(ms, pg, table, sql, keys, args.start, args.end)

            for table in (
                "customer_current", "supplier_current", "product_current",
                "delivery_method_current", "transaction_type_current", "payment_method_current",
                "package_type_current", "stock_group_current", "product_stock_group",
            ):
                source_sql, keys = DIFF_SNAPSHOTS[table]
                results[table] = sync_snapshot(ms, pg, table, source_sql, keys)

            results["geography_current"] = load_geography_delta(ms, pg, args.start, args.end)
    finally:
        ms.close()
        pg.close()

    print("SUMMARY", flush=True)
    for name, count in results.items():
        print(f"{name}={count}", flush=True)


if __name__ == "__main__":
    main()
