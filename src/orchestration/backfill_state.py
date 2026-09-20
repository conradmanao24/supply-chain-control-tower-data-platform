from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import Json


PIPELINE_NAME = "supply_chain_incremental_pipeline"
SOURCE_NAME = "WideWorldImporters"


class BackfillStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackfillWindow:
    airflow_run_id: str
    start_cutoff: datetime
    end_cutoff: datetime
    production_watermark_before: datetime
    source_frontier_at_start: datetime
    status: str


def connect_from_env():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ["DWH_PORT"]),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def _as_datetime(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise BackfillStateError("backfill cutoff must include timezone")
    return result


class BackfillStateStore:
    def __init__(self, connection_factory=connect_from_env):
        self._connection_factory = connection_factory

    def begin(self, airflow_run_id: str, start_cutoff: datetime | str, end_cutoff: datetime | str) -> BackfillWindow:
        start = _as_datetime(start_cutoff)
        end = _as_datetime(end_cutoff)
        if end <= start:
            raise BackfillStateError(f"backfill end must be greater than start: {end} <= {start}")

        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT airflow_run_id,start_cutoff,end_cutoff,status,
                               production_watermark_before,source_frontier_at_start
                        FROM control.backfill_run_history
                        WHERE airflow_run_id=%s
                        FOR UPDATE
                        """,
                        (airflow_run_id,),
                    )
                    existing = cur.fetchone()

                    cur.execute(
                        "SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true FOR UPDATE"
                    )
                    guard = cur.fetchone()
                    if guard is None:
                        raise BackfillStateError("processing guard is not provisioned")

                    if existing is not None:
                        if existing[1] != start or existing[2] != end:
                            raise BackfillStateError("airflow_run_id already exists with a different backfill window")
                        if existing[3] != "running":
                            raise BackfillStateError(f"backfill run already finalized as {existing[3]}")
                        if guard[0] not in (None, "backfill") or (guard[1] not in (None, airflow_run_id)):
                            raise BackfillStateError(f"processing guard owned by {guard[0]}:{guard[1]}")
                        if guard[0] is None:
                            cur.execute(
                                "UPDATE control.processing_guard SET mode='backfill',owner_run_id=%s,acquired_at=now() WHERE singleton=true",
                                (airflow_run_id,),
                            )
                        return BackfillWindow(
                            airflow_run_id=existing[0],
                            start_cutoff=existing[1],
                            end_cutoff=existing[2],
                            production_watermark_before=existing[4],
                            source_frontier_at_start=existing[5],
                            status=existing[3],
                        )

                    if guard[0] is not None:
                        raise BackfillStateError(f"processing guard already owned by {guard[0]}:{guard[1]}")

                    cur.execute(
                        "SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name=%s FOR UPDATE",
                        (PIPELINE_NAME,),
                    )
                    watermark_row = cur.fetchone()
                    if watermark_row is None:
                        raise BackfillStateError("production pipeline state not found")
                    watermark = watermark_row[0]

                    cur.execute(
                        "SELECT safe_through_cutoff FROM control.source_frontier WHERE source_name=%s",
                        (SOURCE_NAME,),
                    )
                    frontier_row = cur.fetchone()
                    if frontier_row is None:
                        raise BackfillStateError("source frontier not found")
                    frontier = frontier_row[0]
                    if end > frontier:
                        raise BackfillStateError(f"backfill end exceeds safe source frontier: {end} > {frontier}")

                    cur.execute(
                        "SELECT count(*) FROM control.pipeline_run_history WHERE status='running'"
                    )
                    if cur.fetchone()[0] != 0:
                        raise BackfillStateError("production analytical pipeline is currently running")

                    cur.execute(
                        "UPDATE control.processing_guard SET mode='backfill',owner_run_id=%s,acquired_at=now() WHERE singleton=true",
                        (airflow_run_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO control.backfill_run_history
                            (airflow_run_id,start_cutoff,end_cutoff,status,
                             production_watermark_before,source_frontier_at_start)
                        VALUES (%s,%s,%s,'running',%s,%s)
                        """,
                        (airflow_run_id, start, end, watermark, frontier),
                    )
                    return BackfillWindow(
                        airflow_run_id=airflow_run_id,
                        start_cutoff=start,
                        end_cutoff=end,
                        production_watermark_before=watermark,
                        source_frontier_at_start=frontier,
                        status="running",
                    )
        finally:
            conn.close()

    def complete_success(self, airflow_run_id: str, verification: dict[str, Any]) -> datetime:
        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT status,production_watermark_before
                        FROM control.backfill_run_history
                        WHERE airflow_run_id=%s
                        FOR UPDATE
                        """,
                        (airflow_run_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise BackfillStateError(f"backfill run not found: {airflow_run_id}")
                    if row[0] == "success":
                        return row[1]
                    if row[0] == "failed":
                        raise BackfillStateError("cannot complete a failed backfill")

                    cur.execute(
                        "SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name=%s FOR UPDATE",
                        (PIPELINE_NAME,),
                    )
                    current_watermark = cur.fetchone()[0]
                    if current_watermark != row[1]:
                        raise BackfillStateError(
                            f"production watermark moved during backfill: before={row[1]} after={current_watermark}"
                        )

                    cur.execute(
                        """
                        UPDATE control.backfill_run_history
                        SET status='success',finished_at=now(),production_watermark_after=%s,
                            error_message=NULL,verification=%s
                        WHERE airflow_run_id=%s
                        """,
                        (current_watermark, Json(verification), airflow_run_id),
                    )
                    cur.execute(
                        """
                        UPDATE control.processing_guard
                        SET mode=NULL,owner_run_id=NULL,acquired_at=NULL
                        WHERE singleton=true AND mode='backfill' AND owner_run_id=%s
                        """,
                        (airflow_run_id,),
                    )
                    if cur.rowcount != 1:
                        raise BackfillStateError("backfill processing guard ownership mismatch")
                    return current_watermark
        finally:
            conn.close()

    def mark_failed(self, airflow_run_id: str, error_message: str) -> None:
        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT status FROM control.backfill_run_history WHERE airflow_run_id=%s FOR UPDATE",
                        (airflow_run_id,),
                    )
                    row = cur.fetchone()
                    if row is not None and row[0] == "running":
                        cur.execute(
                            "SELECT last_successful_cutoff FROM control.pipeline_state WHERE pipeline_name=%s",
                            (PIPELINE_NAME,),
                        )
                        watermark = cur.fetchone()[0]
                        cur.execute(
                            """
                            UPDATE control.backfill_run_history
                            SET status='failed',finished_at=now(),production_watermark_after=%s,error_message=%s
                            WHERE airflow_run_id=%s
                            """,
                            (watermark, error_message, airflow_run_id),
                        )
                    cur.execute(
                        """
                        UPDATE control.processing_guard
                        SET mode=NULL,owner_run_id=NULL,acquired_at=NULL
                        WHERE singleton=true AND mode='backfill' AND owner_run_id=%s
                        """,
                        (airflow_run_id,),
                    )
        finally:
            conn.close()

    def get_run(self, airflow_run_id: str) -> dict[str, Any]:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT airflow_run_id,start_cutoff,end_cutoff,status,
                           production_watermark_before,production_watermark_after,
                           source_frontier_at_start,started_at,finished_at,error_message,verification
                    FROM control.backfill_run_history WHERE airflow_run_id=%s
                    """,
                    (airflow_run_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise BackfillStateError(f"backfill run not found: {airflow_run_id}")
                keys = [d[0] for d in cur.description]
                return dict(zip(keys, row))
        finally:
            conn.close()
