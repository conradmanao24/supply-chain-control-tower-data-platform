from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta

import pymssql
import psycopg2

from ingestion.initial_load import copy_batch, pg_columns
from ingestion.telemetry_load import COLDROOM_SQL, VEHICLE_SQL


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def overlap_start(cutoff: datetime) -> datetime:
    bucket = cutoff.replace(second=0, microsecond=0) - timedelta(minutes=cutoff.minute % 5)
    return bucket - timedelta(minutes=5)


def load_incremental(ms, pg, table: str, sql: str, start: datetime, end: datetime, coldroom: bool) -> tuple[int, int]:
    recompute_from = overlap_start(start)
    src = ms.cursor()
    params = (recompute_from, end, recompute_from, end) if coldroom else (recompute_from, end)
    src.execute(sql, params)
    source_columns = [d[0].lower() for d in src.description]
    target_columns = pg_columns(pg, table)
    if source_columns != target_columns:
        raise RuntimeError(f"Column contract mismatch {table}: source={source_columns} target={target_columns}")

    rows = []
    while True:
        batch = src.fetchmany(10000)
        if not batch:
            break
        rows.extend(batch)

    started = time.time()
    try:
        with pg.cursor() as cur:
            cur.execute(
                f"DELETE FROM staging.{table} WHERE bucket_start >= %s AND bucket_start < %s",
                (recompute_from, end),
            )
            deleted = cur.rowcount
            inserted = copy_batch(cur, table, target_columns, rows)
        pg.commit()
    except Exception:
        pg.rollback()
        raise

    print(
        f"PASS {table}: recompute_from={recompute_from.isoformat()} end={end.isoformat()} "
        f"deleted={deleted:,} inserted={inserted:,} in {time.time()-started:.2f}s",
        flush=True,
    )
    return deleted, inserted


def refresh_sensor_projection(pg) -> dict[str, int]:
    """
    Refresh the operational sensor projection from the latest 5-minute staging
    buckets. Event-driven readings remain authoritative when they are newer.
    The same lightweight sweep also synchronizes freshness alerts.
    """
    from realtime.alerts import evaluate_coldroom, evaluate_vehicle

    try:
        with pg.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (sensor_number)
                        sensor_number,
                        last_recorded_when,
                        avg_temperature,
                        reading_count
                    FROM staging.coldroom_5m
                    ORDER BY sensor_number, bucket_start DESC
                )
                INSERT INTO realtime.current_sensor_state
                    (sensor_key,sensor_type,vehicle_registration,sensor_number,
                     recorded_when,temperature,reading_count,value_basis,
                     source_event_id,refreshed_at)
                SELECT
                    'coldroom:' || sensor_number::text,
                    'coldroom',
                    NULL,
                    sensor_number,
                    last_recorded_when,
                    avg_temperature,
                    reading_count::integer,
                    '5m_pipeline',
                    NULL,
                    now()
                FROM latest
                ON CONFLICT (sensor_key) DO UPDATE SET
                    sensor_type=EXCLUDED.sensor_type,
                    vehicle_registration=EXCLUDED.vehicle_registration,
                    sensor_number=EXCLUDED.sensor_number,
                    recorded_when=EXCLUDED.recorded_when,
                    temperature=EXCLUDED.temperature,
                    reading_count=EXCLUDED.reading_count,
                    value_basis=EXCLUDED.value_basis,
                    source_event_id=NULL,
                    refreshed_at=now()
                WHERE realtime.current_sensor_state.recorded_when <= EXCLUDED.recorded_when
                """
            )
            coldroom_upserts = cur.rowcount

            cur.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (vehicle_registration,sensor_number)
                        vehicle_registration,
                        sensor_number,
                        last_recorded_when,
                        avg_temperature,
                        reading_count
                    FROM staging.vehicle_5m
                    ORDER BY vehicle_registration, sensor_number, bucket_start DESC
                )
                INSERT INTO realtime.current_sensor_state
                    (sensor_key,sensor_type,vehicle_registration,sensor_number,
                     recorded_when,temperature,reading_count,value_basis,
                     source_event_id,refreshed_at)
                SELECT
                    'vehicle:' || vehicle_registration || ':' || sensor_number::text,
                    'vehicle',
                    vehicle_registration,
                    sensor_number,
                    last_recorded_when,
                    avg_temperature,
                    reading_count::integer,
                    '5m_pipeline',
                    NULL,
                    now()
                FROM latest
                ON CONFLICT (sensor_key) DO UPDATE SET
                    sensor_type=EXCLUDED.sensor_type,
                    vehicle_registration=EXCLUDED.vehicle_registration,
                    sensor_number=EXCLUDED.sensor_number,
                    recorded_when=EXCLUDED.recorded_when,
                    temperature=EXCLUDED.temperature,
                    reading_count=EXCLUDED.reading_count,
                    value_basis=EXCLUDED.value_basis,
                    source_event_id=NULL,
                    refreshed_at=now()
                WHERE realtime.current_sensor_state.recorded_when <= EXCLUDED.recorded_when
                """
            )
            vehicle_upserts = cur.rowcount

            cur.execute(
                "SELECT sensor_key,sensor_type FROM realtime.current_sensor_state "
                "WHERE sensor_type IN ('coldroom','vehicle') ORDER BY sensor_key"
            )
            sensor_rows = cur.fetchall()
            evaluated = 0
            for sensor_key, sensor_type in sensor_rows:
                if sensor_type == "coldroom":
                    evaluate_coldroom(cur, str(sensor_key), None)
                else:
                    evaluate_vehicle(cur, str(sensor_key), None)
                evaluated += 1

            payload = json.dumps(
                {
                    "event_kind": "update",
                    "event_type": "telemetry.projection.refreshed",
                    "domain": "cold_chain",
                    "source": "incremental_telemetry",
                },
                separators=(",", ":"),
            )
            cur.execute("SELECT pg_notify('control_tower_realtime', %s)", (payload,))
        pg.commit()
    except Exception:
        pg.rollback()
        raise

    result = {
        "coldroom_upserts": coldroom_upserts,
        "vehicle_upserts": vehicle_upserts,
        "sensors_evaluated": evaluated,
    }
    print(f"PASS sensor_projection: {result}", flush=True)
    return result


def main():
    p = argparse.ArgumentParser(description="incremental processing explicit-window incremental telemetry loader")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--dataset", choices=["all", "coldroom", "vehicle"], default="all")
    p.add_argument("--refresh-projection-only", action="store_true")
    args = p.parse_args()

    pg = psycopg2.connect(
        host=os.environ["DWH_HOST"], port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"], user=os.environ["DWH_USER"], password=os.environ["DWH_PASSWORD"],
    )

    if args.refresh_projection_only:
        try:
            refresh_sensor_projection(pg)
        finally:
            pg.close()
        return

    if not args.start or not args.end:
        pg.close()
        raise SystemExit("--start and --end are required unless --refresh-projection-only is used")

    start, end = parse_dt(args.start), parse_dt(args.end)
    if end <= start:
        pg.close()
        raise SystemExit("--end must be greater than --start")

    ms = pymssql.connect(
        server=os.environ["WWI_HOST"], port=int(os.environ["WWI_PORT"]),
        user=os.environ["WWI_SOURCE_USER"], password=os.environ["WWI_SOURCE_PASSWORD"],
        database=os.environ["WWI_DATABASE"], autocommit=True,
    )
    try:
        if args.dataset in ("all", "coldroom"):
            load_incremental(ms, pg, "coldroom_5m", COLDROOM_SQL, start, end, True)
        if args.dataset in ("all", "vehicle"):
            load_incremental(ms, pg, "vehicle_5m", VEHICLE_SQL, start, end, False)
        refresh_sensor_projection(pg)
    finally:
        ms.close()
        pg.close()


if __name__ == "__main__":
    main()
