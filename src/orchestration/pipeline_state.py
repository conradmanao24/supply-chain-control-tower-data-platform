from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extensions import connection as PgConnection


class PipelineStateError(RuntimeError):
    pass


class StaleRunError(PipelineStateError):
    pass


@dataclass(frozen=True)
class RunWindow:
    airflow_run_id: str
    pipeline_name: str
    start_cutoff: datetime
    end_cutoff: datetime
    status: str


def connect_from_env() -> PgConnection:
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
        raise ValueError("cutoff must include a timezone")
    return result


class PipelineStateStore:
    def __init__(self, connection_factory=connect_from_env):
        self._connection_factory = connection_factory

    def get_source_frontier(self, source_name: str) -> dict[str, Any]:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT source_name, safe_through_cutoff, basis, updated_at
                    FROM control.source_frontier
                    WHERE source_name = %s
                    """,
                    (source_name,),
                )
                row = cur.fetchone()
                if row is None:
                    raise PipelineStateError(f"source frontier not found: {source_name}")
                return {
                    "source_name": row[0],
                    "safe_through_cutoff": row[1],
                    "basis": row[2],
                    "updated_at": row[3],
                }
        finally:
            conn.close()

    def get_state(self, pipeline_name: str) -> dict[str, Any]:
        conn = self._connection_factory()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT pipeline_name, last_successful_cutoff,
                           last_successful_run_id, updated_at
                    FROM control.pipeline_state
                    WHERE pipeline_name = %s
                    """,
                    (pipeline_name,),
                )
                row = cur.fetchone()
                if row is None:
                    raise PipelineStateError(f"pipeline state not found: {pipeline_name}")
                return {
                    "pipeline_name": row[0],
                    "last_successful_cutoff": row[1],
                    "last_successful_run_id": row[2],
                    "updated_at": row[3],
                }
        finally:
            conn.close()

    def begin_run(
        self,
        pipeline_name: str,
        airflow_run_id: str,
        end_cutoff: datetime | str,
    ) -> RunWindow:
        desired_end = _as_datetime(end_cutoff)
        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true FOR UPDATE"
                    )
                    guard = cur.fetchone()
                    if guard is None:
                        raise PipelineStateError("processing guard is not provisioned")
                    if guard[0] not in (None, "incremental") or guard[1] not in (None, airflow_run_id):
                        raise PipelineStateError(f"processing guard owned by {guard[0]}:{guard[1]}")

                    cur.execute(
                        """
                        SELECT pipeline_name, start_cutoff, end_cutoff, status
                        FROM control.pipeline_run_history
                        WHERE airflow_run_id = %s
                        FOR UPDATE
                        """,
                        (airflow_run_id,),
                    )
                    existing = cur.fetchone()
                    if existing is not None:
                        if existing[0] != pipeline_name or existing[2] != desired_end:
                            raise PipelineStateError(
                                f"airflow_run_id already exists with a different contract: {airflow_run_id}"
                            )
                        if existing[3] != "running":
                            raise PipelineStateError(
                                f"run already finalized as {existing[3]}: {airflow_run_id}"
                            )
                        if guard[0] is None:
                            cur.execute(
                                "UPDATE control.processing_guard SET mode='incremental',owner_run_id=%s,acquired_at=now() WHERE singleton=true",
                                (airflow_run_id,),
                            )
                        return RunWindow(
                            airflow_run_id=airflow_run_id,
                            pipeline_name=pipeline_name,
                            start_cutoff=existing[1],
                            end_cutoff=existing[2],
                            status=existing[3],
                        )

                    if guard[0] is not None:
                        raise PipelineStateError(f"processing guard already owned by {guard[0]}:{guard[1]}")

                    cur.execute(
                        """
                        SELECT last_successful_cutoff
                        FROM control.pipeline_state
                        WHERE pipeline_name = %s
                        FOR UPDATE
                        """,
                        (pipeline_name,),
                    )
                    state = cur.fetchone()
                    if state is None:
                        raise PipelineStateError(f"pipeline state not found: {pipeline_name}")
                    start_cutoff = state[0]
                    if desired_end <= start_cutoff:
                        raise PipelineStateError(
                            f"end_cutoff must be greater than watermark: {desired_end} <= {start_cutoff}"
                        )

                    cur.execute(
                        "UPDATE control.processing_guard SET mode='incremental',owner_run_id=%s,acquired_at=now() WHERE singleton=true",
                        (airflow_run_id,),
                    )
                    cur.execute(
                        """
                        INSERT INTO control.pipeline_run_history (
                            pipeline_name, airflow_run_id, start_cutoff,
                            end_cutoff, status
                        )
                        VALUES (%s, %s, %s, %s, 'running')
                        """,
                        (pipeline_name, airflow_run_id, start_cutoff, desired_end),
                    )
                    return RunWindow(
                        airflow_run_id=airflow_run_id,
                        pipeline_name=pipeline_name,
                        start_cutoff=start_cutoff,
                        end_cutoff=desired_end,
                        status="running",
                    )
        finally:
            conn.close()

    def mark_failed(self, airflow_run_id: str, error_message: str | None = None) -> None:
        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT status
                        FROM control.pipeline_run_history
                        WHERE airflow_run_id = %s
                        FOR UPDATE
                        """,
                        (airflow_run_id,),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise PipelineStateError(f"run not found: {airflow_run_id}")
                    if row[0] == "failed":
                        return
                    if row[0] == "success":
                        raise PipelineStateError(f"cannot fail a successful run: {airflow_run_id}")

                    cur.execute(
                        """
                        UPDATE control.pipeline_run_history
                        SET status = 'failed',
                            finished_at = now(),
                            error_message = %s
                        WHERE airflow_run_id = %s
                        """,
                        (error_message, airflow_run_id),
                    )
                    cur.execute(
                        """
                        UPDATE control.processing_guard
                        SET mode=NULL,owner_run_id=NULL,acquired_at=NULL
                        WHERE singleton=true AND mode='incremental' AND owner_run_id=%s
                        """,
                        (airflow_run_id,),
                    )
        finally:
            conn.close()

    def commit_success(self, airflow_run_id: str) -> datetime:
        conn = self._connection_factory()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT mode,owner_run_id FROM control.processing_guard WHERE singleton=true FOR UPDATE"
                    )
                    guard = cur.fetchone()
                    if guard is None:
                        raise PipelineStateError("processing guard is not provisioned")
                    if guard[0] not in (None, "incremental") or guard[1] not in (None, airflow_run_id):
                        raise PipelineStateError(f"processing guard owned by {guard[0]}:{guard[1]}")

                    cur.execute(
                        """
                        SELECT pipeline_name, start_cutoff, end_cutoff, status
                        FROM control.pipeline_run_history
                        WHERE airflow_run_id = %s
                        FOR UPDATE
                        """,
                        (airflow_run_id,),
                    )
                    run = cur.fetchone()
                    if run is None:
                        raise PipelineStateError(f"run not found: {airflow_run_id}")
                    pipeline_name, start_cutoff, end_cutoff, status = run

                    cur.execute(
                        """
                        SELECT last_successful_cutoff, last_successful_run_id
                        FROM control.pipeline_state
                        WHERE pipeline_name = %s
                        FOR UPDATE
                        """,
                        (pipeline_name,),
                    )
                    state = cur.fetchone()
                    if state is None:
                        raise PipelineStateError(f"pipeline state not found: {pipeline_name}")

                    if status == "success":
                        if state[0] != end_cutoff or state[1] != airflow_run_id:
                            raise PipelineStateError(
                                f"successful run/state mismatch for {airflow_run_id}"
                            )
                        return end_cutoff
                    if status == "failed":
                        raise PipelineStateError(f"cannot commit a failed run: {airflow_run_id}")
                    if state[0] != start_cutoff:
                        raise StaleRunError(
                            f"watermark moved since run began: expected {start_cutoff}, found {state[0]}"
                        )

                    cur.execute(
                        """
                        UPDATE control.pipeline_run_history
                        SET status = 'success',
                            finished_at = now(),
                            error_message = NULL
                        WHERE airflow_run_id = %s
                        """,
                        (airflow_run_id,),
                    )
                    cur.execute(
                        """
                        UPDATE control.pipeline_state
                        SET last_successful_cutoff = %s,
                            last_successful_run_id = %s,
                            updated_at = now()
                        WHERE pipeline_name = %s
                          AND last_successful_cutoff = %s
                        """,
                        (end_cutoff, airflow_run_id, pipeline_name, start_cutoff),
                    )
                    if cur.rowcount != 1:
                        raise StaleRunError(f"watermark compare-and-set failed for {airflow_run_id}")
                    cur.execute(
                        """
                        UPDATE control.processing_guard
                        SET mode=NULL,owner_run_id=NULL,acquired_at=NULL
                        WHERE singleton=true AND mode='incremental' AND owner_run_id=%s
                        """,
                        (airflow_run_id,),
                    )
                    if cur.rowcount != 1:
                        raise PipelineStateError(f"incremental processing guard ownership mismatch for {airflow_run_id}")
                    return end_cutoff
        finally:
            conn.close()

