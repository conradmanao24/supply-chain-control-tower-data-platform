from __future__ import annotations

import argparse
import os
import time
from datetime import datetime

import pymssql
import psycopg2

from ingestion.initial_load import copy_batch, pg_columns

COLDROOM_SQL = r"""
WITH raw AS (
    SELECT ColdRoomSensorNumber AS sensor_number, RecordedWhen AS recorded_when, Temperature AS temperature
    FROM Warehouse.ColdRoomTemperatures_Archive
    WHERE RecordedWhen >= %s AND RecordedWhen < %s
    UNION ALL
    SELECT ColdRoomSensorNumber, RecordedWhen, Temperature
    FROM Warehouse.ColdRoomTemperatures
    WHERE RecordedWhen >= %s AND RecordedWhen < %s
), bucketed AS (
    SELECT sensor_number, recorded_when, temperature,
           DATEADD(MINUTE,
                   (DATEDIFF(MINUTE, CAST('20000101' AS datetime2), recorded_when) / 5) * 5,
                   CAST('20000101' AS datetime2)) AS bucket_start
    FROM raw
), gapped AS (
    SELECT sensor_number, bucket_start, recorded_when, temperature,
           CAST(DATEDIFF_BIG(MILLISECOND,
                 LAG(recorded_when) OVER (PARTITION BY sensor_number, bucket_start ORDER BY recorded_when),
                 recorded_when) AS decimal(18,3)) / 1000.0 AS gap_seconds
    FROM bucketed
)
SELECT sensor_number, bucket_start,
       MIN(temperature) AS min_temperature,
       MAX(temperature) AS max_temperature,
       CAST(AVG(CAST(temperature AS decimal(18,4))) AS decimal(18,4)) AS avg_temperature,
       COUNT_BIG(*) AS reading_count,
       MIN(recorded_when) AS first_recorded_when,
       MAX(recorded_when) AS last_recorded_when,
       MAX(gap_seconds) AS max_gap_seconds
FROM gapped
GROUP BY sensor_number, bucket_start
ORDER BY sensor_number, bucket_start;
"""

VEHICLE_SQL = r"""
WITH raw AS (
    SELECT VehicleRegistration AS vehicle_registration,
           ChillerSensorNumber AS sensor_number,
           RecordedWhen AS recorded_when,
           Temperature AS temperature
    FROM Warehouse.VehicleTemperatures
    WHERE RecordedWhen >= %s AND RecordedWhen < %s
), bucketed AS (
    SELECT vehicle_registration, sensor_number, recorded_when, temperature,
           DATEADD(MINUTE,
                   (DATEDIFF(MINUTE, CAST('20000101' AS datetime2), recorded_when) / 5) * 5,
                   CAST('20000101' AS datetime2)) AS bucket_start
    FROM raw
), gapped AS (
    SELECT vehicle_registration, sensor_number, bucket_start, recorded_when, temperature,
           CAST(DATEDIFF_BIG(MILLISECOND,
                 LAG(recorded_when) OVER (
                     PARTITION BY vehicle_registration, sensor_number, bucket_start
                     ORDER BY recorded_when),
                 recorded_when) AS decimal(18,3)) / 1000.0 AS gap_seconds
    FROM bucketed
)
SELECT vehicle_registration, sensor_number, bucket_start,
       MIN(temperature) AS min_temperature,
       MAX(temperature) AS max_temperature,
       CAST(AVG(CAST(temperature AS decimal(18,4))) AS decimal(18,4)) AS avg_temperature,
       COUNT_BIG(*) AS reading_count,
       MIN(recorded_when) AS first_recorded_when,
       MAX(recorded_when) AS last_recorded_when,
       MAX(gap_seconds) AS max_gap_seconds
FROM gapped
GROUP BY vehicle_registration, sensor_number, bucket_start
ORDER BY vehicle_registration, sensor_number, bucket_start;
"""


def parse_dt(v: str) -> datetime:
    return datetime.fromisoformat(v)


def month_chunks(start: datetime, end: datetime):
    cur = start
    while cur < end:
        if cur.month == 12:
            next_month = cur.replace(year=cur.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = cur.replace(month=cur.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        chunk_end = min(next_month, end)
        yield cur, chunk_end
        cur = chunk_end


def source_columns(cursor):
    return [d[0].lower() for d in cursor.description]


def load_telemetry(ms_conn, pg_conn, table_name: str, sql: str, start: datetime, end: datetime, coldroom: bool):
    started = time.time()
    target_columns = pg_columns(pg_conn, table_name)
    total = 0
    try:
        with pg_conn.cursor() as tgt:
            tgt.execute(f'TRUNCATE TABLE staging.{table_name}')
            for chunk_start, chunk_end in month_chunks(start, end):
                src = ms_conn.cursor()
                if coldroom:
                    params = (chunk_start, chunk_end, chunk_start, chunk_end)
                else:
                    params = (chunk_start, chunk_end)
                src.execute(sql, params)
                cols = source_columns(src)
                if cols != target_columns:
                    raise RuntimeError(f'Column contract mismatch {table_name}: source={cols} target={target_columns}')
                chunk_rows = 0
                while True:
                    rows = src.fetchmany(10000)
                    if not rows:
                        break
                    n = copy_batch(tgt, table_name, target_columns, rows)
                    chunk_rows += n
                    total += n
                print(f'{table_name} {chunk_start:%Y-%m-%d}..{chunk_end:%Y-%m-%d}: {chunk_rows:,} buckets (total {total:,})', flush=True)
            tgt.execute(f'SELECT COUNT(*) FROM staging.{table_name}')
            target_count = tgt.fetchone()[0]
            if target_count != total:
                raise RuntimeError(f'Row-count mismatch {table_name}: copied={total} target={target_count}')
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        raise
    print(f'PASS {table_name}: {total:,} buckets in {time.time()-started:.1f}s', flush=True)
    return total


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--start', default='2026-09-01T00:00:00')
    p.add_argument('--end', default='2026-09-16T00:00:00')
    p.add_argument('--full', action='store_true')
    p.add_argument('--dataset', choices=['all','coldroom','vehicle'], default='all')
    args=p.parse_args()
    if args.full:
        cold_start=parse_dt('2015-12-20T00:00:00')
        vehicle_start=parse_dt('2016-01-01T00:00:00')
        end=parse_dt('2026-09-16T00:00:00')
    else:
        cold_start=vehicle_start=parse_dt(args.start)
        end=parse_dt(args.end)

    ms=pymssql.connect(server=os.environ['WWI_HOST'],port=int(os.environ['WWI_PORT']),user=os.environ['WWI_SOURCE_USER'],password=os.environ['WWI_SOURCE_PASSWORD'],database=os.environ['WWI_DATABASE'],autocommit=True)
    pg=psycopg2.connect(host=os.environ['DWH_HOST'],port=int(os.environ['DWH_PORT']),dbname=os.environ['DWH_DB'],user=os.environ['DWH_USER'],password=os.environ['DWH_PASSWORD'])
    try:
        if args.dataset in ('all','coldroom'):
            load_telemetry(ms,pg,'coldroom_5m',COLDROOM_SQL,cold_start,end,True)
        if args.dataset in ('all','vehicle'):
            load_telemetry(ms,pg,'vehicle_5m',VEHICLE_SQL,vehicle_start,end,False)
    finally:
        ms.close(); pg.close()

if __name__=='__main__':
    main()