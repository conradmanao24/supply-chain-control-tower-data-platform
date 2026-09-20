from __future__ import annotations

import argparse
import csv
import io
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal

import pymssql
import psycopg2

WINDOWED_DATASETS = {
    "order_line": "Integration.GetOrderUpdates",
    "sale_line": "Integration.GetSaleUpdates",
    "inventory_movement": "Integration.GetMovementUpdates",
    "purchase_line": "Integration.GetPurchaseUpdates",
    "financial_transaction": "Integration.GetTransactionUpdates",
}

SNAPSHOT_DATASETS = {
    "order_state": "SELECT * FROM ControlTowerExtract.OrderState",
    "invoice_delivery": "SELECT * FROM ControlTowerExtract.InvoiceDelivery",
    "purchase_order_state": "SELECT * FROM ControlTowerExtract.PurchaseOrderState",
    "customer_current": "EXEC ControlTowerExtract.GetCustomerCurrent",
    "customer_history": "EXEC ControlTowerExtract.GetCustomerHistory",
    "supplier_current": "SELECT * FROM ControlTowerExtract.SupplierCurrent",
    "supplier_history": "SELECT * FROM ControlTowerExtract.SupplierHistory",
    "product_current": "SELECT * FROM ControlTowerExtract.ProductCurrent",
    "product_history": "SELECT * FROM ControlTowerExtract.ProductHistory",
    "product_stock_group": "SELECT * FROM ControlTowerExtract.ProductStockGroup",
    "stock_holding_current": "SELECT * FROM ControlTowerExtract.StockHoldingCurrent",
    "employee_current": "SELECT * FROM ControlTowerExtract.EmployeeCurrent",
    "employee_history": "SELECT * FROM ControlTowerExtract.EmployeeHistory",
    "geography_current": "SELECT * FROM ControlTowerExtract.GeographyCurrent",
    "delivery_method_current": "SELECT * FROM ControlTowerExtract.DeliveryMethodCurrent",
    "transaction_type_current": "SELECT * FROM ControlTowerExtract.TransactionTypeCurrent",
    "payment_method_current": "SELECT * FROM ControlTowerExtract.PaymentMethodCurrent",
    "package_type_current": "SELECT * FROM ControlTowerExtract.PackageTypeCurrent",
    "stock_group_current": "SELECT * FROM ControlTowerExtract.StockGroupCurrent",
}

SPECIAL_NAMES = {
    "wwi_saleperson_id": "wwi_salesperson_id",
}


def snake(name: str) -> str:
    name = name.replace("WWI", "Wwi")
    name = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", name)
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return SPECIAL_NAMES.get(name, name)


def serialize(value):
    if value is None:
        return r"\N"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return "\\x" + value.hex()
    return str(value)


def pg_columns(pg_conn, table_name: str) -> list[str]:
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='staging' AND table_name=%s AND column_name <> 'ingested_at'
            ORDER BY ordinal_position
            """,
            (table_name,),
        )
        return [r[0] for r in cur.fetchall()]


def copy_batch(pg_cur, table_name: str, columns: list[str], rows) -> int:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    for row in rows:
        writer.writerow([serialize(v) for v in row])
    buf.seek(0)
    cols = ", ".join(columns)
    pg_cur.copy_expert(
        f"COPY staging.{table_name} ({cols}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')",
        buf,
    )
    return len(rows)


def load_dataset(ms_conn, pg_conn, table_name: str, source_sql: str, params=(), batch_size=10000) -> int:
    started = time.time()
    src = ms_conn.cursor()
    src.execute(source_sql, params)
    source_columns = [snake(d[0]) for d in src.description]
    target_columns = pg_columns(pg_conn, table_name)
    if source_columns != target_columns:
        raise RuntimeError(
            f"Column contract mismatch for {table_name}:\nsource={source_columns}\ntarget={target_columns}"
        )

    total = 0
    try:
        with pg_conn.cursor() as tgt:
            tgt.execute(f"TRUNCATE TABLE staging.{table_name}")
            while True:
                rows = src.fetchmany(batch_size)
                if not rows:
                    break
                total += copy_batch(tgt, table_name, target_columns, rows)
                if total % 100000 < batch_size:
                    print(f"  {table_name}: {total:,} rows copied", flush=True)
            tgt.execute(f"SELECT COUNT(*) FROM staging.{table_name}")
            target_count = tgt.fetchone()[0]
            if target_count != total:
                raise RuntimeError(f"Row-count mismatch for {table_name}: copied={total}, target={target_count}")
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    elapsed = time.time() - started
    print(f"PASS {table_name}: {total:,} rows in {elapsed:.1f}s", flush=True)
    return total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2026-09-01T00:00:00")
    p.add_argument("--end", default="2026-09-16T00:00:00")
    p.add_argument("--full", action="store_true", help="Use full baseline window 1900-01-01 through 2026-09-16")
    p.add_argument("--scope", choices=["all", "facts", "snapshots"], default="all")
    p.add_argument("--dataset", action="append", help="Load only named dataset(s)")
    args = p.parse_args()

    if args.full:
        args.start = "1900-01-01T00:00:00"
        args.end = "2026-09-16T00:00:00"

    ms_conn = pymssql.connect(
        server=os.environ["WWI_HOST"],
        port=int(os.environ["WWI_PORT"]),
        user=os.environ["WWI_SOURCE_USER"],
        password=os.environ["WWI_SOURCE_PASSWORD"],
        database=os.environ["WWI_DATABASE"],
        autocommit=True,
    )
    pg_conn = psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )

    selected = set(args.dataset or [])
    results = {}
    try:
        if args.scope in ("all", "facts"):
            for table_name, proc in WINDOWED_DATASETS.items():
                if selected and table_name not in selected:
                    continue
                print(f"LOAD {table_name} <- {proc} [{args.start}, {args.end}]", flush=True)
                results[table_name] = load_dataset(
                    ms_conn,
                    pg_conn,
                    table_name,
                    f"EXEC {proc} @LastCutoff=%s, @NewCutoff=%s",
                    (args.start, args.end),
                )
        if args.scope in ("all", "snapshots"):
            for table_name, source_sql in SNAPSHOT_DATASETS.items():
                if selected and table_name not in selected:
                    continue
                print(f"LOAD {table_name}", flush=True)
                results[table_name] = load_dataset(ms_conn, pg_conn, table_name, source_sql)
    finally:
        ms_conn.close()
        pg_conn.close()

    print("SUMMARY")
    for name, count in results.items():
        print(f"{name}={count}")


if __name__ == "__main__":
    main()