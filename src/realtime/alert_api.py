from __future__ import annotations

import os
from typing import Any

import pymssql
import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from psycopg2.extras import Json, RealDictCursor

from realtime.alerts import (
    acknowledge_alert,
    apply_platform_signal,
    evaluate_coldroom,
    evaluate_inventory,
    evaluate_vehicle,
    resolve_alert,
)
from realtime.deadlines import _sync_coldroom, _sync_vehicle

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


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
        autocommit=False,
        login_timeout=10,
        timeout=45,
    )


def _config_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": bool(row["enabled"]),
        "severity": row["severity"],
        "parameters": row["parameters"] or {},
    }


def _resolve_rule_alerts(pg, rule_id: str, actor: str, reason: str) -> int:
    pg.execute(
        """
        SELECT alert_id
        FROM alert.alerts
        WHERE rule_id=%s AND status IN ('open','acknowledged')
        FOR UPDATE
        """,
        (rule_id,),
    )
    rows = pg.fetchall()
    resolved = 0
    for row in rows:
        alert_id = row["alert_id"] if isinstance(row, dict) else row[0]
        pg.execute(
            """
            UPDATE alert.alerts
            SET status='resolved',
                resolved_at=now(),
                resolved_by=%s,
                resolution_reason=%s,
                last_observed_at=now()
            WHERE alert_id=%s
            """,
            (actor, reason, alert_id),
        )
        pg.execute(
            """
            INSERT INTO alert.alert_history(alert_id,action,actor,details)
            VALUES (%s,'resolved',%s,%s)
            """,
            (alert_id, actor, Json({"reason": reason, "rule_id": rule_id})),
        )
        resolved += 1
    return resolved


def _reevaluate_rule(pg_conn, rule_id: str, actor: str) -> dict[str, Any]:
    result: dict[str, Any] = {"rule_id": rule_id, "entities": 0, "resolved": 0}

    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            "SELECT enabled,severity FROM alert.rule_config WHERE rule_id=%s",
            (rule_id,),
        )
        config = pg.fetchone()
        if config is None:
            return result

        pg.execute(
            """
            UPDATE alert.alerts
            SET severity=%s,last_observed_at=now()
            WHERE rule_id=%s AND status IN ('open','acknowledged')
            """,
            (config["severity"], rule_id),
        )

        if not config["enabled"]:
            result["resolved"] = _resolve_rule_alerts(
                pg, rule_id, actor, "rule_disabled"
            )
            result["mode"] = "disabled_resolve"
            return result

        if rule_id.startswith("coldroom."):
            pg.execute(
                """
                SELECT sensor_key,sensor_number
                FROM realtime.current_sensor_state
                WHERE sensor_type='coldroom'
                ORDER BY sensor_key
                """
            )
            sensors = [dict(row) for row in pg.fetchall()]
            for sensor in sensors:
                evaluate_coldroom(pg, sensor["sensor_key"], None)
            result["entities"] = len(sensors)
            result["mode"] = "coldroom_full_reevaluation"

        elif rule_id.startswith("vehicle."):
            pg.execute(
                """
                SELECT sensor_key,vehicle_registration,sensor_number
                FROM realtime.current_sensor_state
                WHERE sensor_type='vehicle'
                ORDER BY sensor_key
                """
            )
            sensors = [dict(row) for row in pg.fetchall()]
            for sensor in sensors:
                evaluate_vehicle(pg, sensor["sensor_key"], None)
            result["entities"] = len(sensors)
            result["mode"] = "vehicle_full_reevaluation"

        elif rule_id == "inventory.target_watch":
            pg.execute(
                """
                SELECT stock_item_id
                FROM realtime.current_inventory_state
                ORDER BY stock_item_id
                """
            )
            ids = [int(row["stock_item_id"]) for row in pg.fetchall()]
            for stock_item_id in ids:
                evaluate_inventory(pg, stock_item_id, None)
            result["entities"] = len(ids)
            result["mode"] = "inventory_full_reevaluation"

        elif rule_id.startswith("platform."):
            result["mode"] = "platform_waits_for_next_signal"

        else:
            result["mode"] = "configuration_updated"

    return result


def _resync_cold_chain_deadlines(pg_conn, rule_id: str) -> dict[str, int]:
    if not (rule_id.startswith("coldroom.") or rule_id.startswith("vehicle.")):
        return {"deadlines_resynced": 0}

    sql_conn = sql_connect()
    count = 0
    try:
        if rule_id.startswith("coldroom."):
            with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
                pg.execute(
                    """
                    SELECT DISTINCT sensor_number
                    FROM realtime.current_sensor_state
                    WHERE sensor_type='coldroom'
                    ORDER BY sensor_number
                    """
                )
                sensor_numbers = [int(row["sensor_number"]) for row in pg.fetchall()]
            for sensor_number in sensor_numbers:
                _sync_coldroom(sql_conn, pg_conn, sensor_number)
                count += 1
        else:
            with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
                pg.execute(
                    """
                    SELECT DISTINCT vehicle_registration,sensor_number
                    FROM realtime.current_sensor_state
                    WHERE sensor_type='vehicle'
                    ORDER BY vehicle_registration,sensor_number
                    """
                )
                sensors = [dict(row) for row in pg.fetchall()]
            for sensor in sensors:
                _sync_vehicle(
                    sql_conn,
                    pg_conn,
                    str(sensor["vehicle_registration"]),
                    int(sensor["sensor_number"]),
                )
                count += 1
        sql_conn.commit()
    except Exception:
        sql_conn.rollback()
        raise
    finally:
        sql_conn.close()
    return {"deadlines_resynced": count}


class ActorRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=120)


class ResolveRequest(ActorRequest):
    reason: str = Field(min_length=1, max_length=500)


class RulePatch(BaseModel):
    enabled: bool | None = None
    severity: str | None = None
    parameters: dict[str, Any] | None = None
    actor: str = Field(default="admin-ui", min_length=1, max_length=120)


class PlatformSignal(BaseModel):
    rule_id: str
    entity_id: str = Field(min_length=1, max_length=200)
    active: bool
    observed_value: dict[str, Any] = Field(default_factory=dict)
    threshold_value: dict[str, Any] = Field(default_factory=dict)
    actor: str = Field(default="platform", min_length=1, max_length=120)


def _validate_rule_patch(rule_id: str, patch: RulePatch) -> None:
    if patch.severity is not None and patch.severity not in {"info", "warning", "critical"}:
        raise HTTPException(status_code=400, detail="severity must be info, warning, or critical")
    params = patch.parameters
    if params is None:
        return
    if rule_id in {"coldroom.stale", "coldroom.offline", "vehicle.stale", "vehicle.offline"}:
        seconds = params.get("seconds")
        if seconds is None or not isinstance(seconds, (int, float)) or seconds <= 0:
            raise HTTPException(status_code=400, detail="sensor freshness rule requires positive parameters.seconds")
    if rule_id in {
        "coldroom.temperature_warning",
        "coldroom.temperature_critical",
        "vehicle.temperature_warning",
        "vehicle.temperature_critical",
    }:
        low = params.get("low")
        high = params.get("high")
        if low is None and high is None:
            return
        if low is not None and not isinstance(low, (int, float)):
            raise HTTPException(status_code=400, detail="temperature low must be numeric or null")
        if high is not None and not isinstance(high, (int, float)):
            raise HTTPException(status_code=400, detail="temperature high must be numeric or null")
        if low is not None and high is not None and low >= high:
            raise HTTPException(status_code=400, detail="temperature low must be lower than high")


@router.get("/engine-state")
def engine_state() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT activated_at,backlog_policy,notes FROM alert.engine_state WHERE singleton=true")
            row = cur.fetchone()
    return JSONResponse(content=jsonable_encoder(row))


@router.get("/summary")
def alert_summary() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status='open') AS open,
                    count(*) FILTER (WHERE status='acknowledged') AS acknowledged,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='critical') AS active_critical,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='warning') AS active_warning,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='info') AS active_info
                FROM alert.alerts
                """
            )
            row = cur.fetchone()
    return JSONResponse(content=jsonable_encoder(row))


@router.get("/rules")
def list_rules() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT rule_id,domain,description,enabled,severity,source_native,parameters,updated_at FROM alert.rule_config ORDER BY domain,rule_id"
            )
            rows = cur.fetchall()
    return JSONResponse(content=jsonable_encoder(rows))


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: str, patch: RulePatch) -> JSONResponse:
    _validate_rule_patch(rule_id, patch)
    updates = []
    values: list[Any] = []

    with pg_connect() as conn:
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT rule_id,domain,description,enabled,severity,source_native,
                           parameters,updated_at
                    FROM alert.rule_config
                    WHERE rule_id=%s
                    FOR UPDATE
                    """,
                    (rule_id,),
                )
                before = cur.fetchone()
                if before is None:
                    raise HTTPException(status_code=404, detail="rule not found")
                if before["source_native"]:
                    raise HTTPException(
                        status_code=403,
                        detail="source-native rules are read-only",
                    )

                if patch.enabled is not None:
                    updates.append("enabled=%s")
                    values.append(patch.enabled)
                if patch.severity is not None:
                    updates.append("severity=%s")
                    values.append(patch.severity)
                if patch.parameters is not None:
                    updates.append("parameters=%s")
                    values.append(Json(patch.parameters))
                if not updates:
                    raise HTTPException(status_code=400, detail="no rule fields supplied")

                updates.append("updated_at=now()")
                values.append(rule_id)
                cur.execute(
                    f"""
                    UPDATE alert.rule_config
                    SET {','.join(updates)}
                    WHERE rule_id=%s
                    RETURNING rule_id,domain,description,enabled,severity,source_native,
                              parameters,updated_at
                    """,
                    values,
                )
                after = dict(cur.fetchone())

            reevaluation = _reevaluate_rule(conn, rule_id, patch.actor)
            deadline_result = _resync_cold_chain_deadlines(conn, rule_id)
            reevaluation.update(deadline_result)

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO alert.rule_config_history
                        (rule_id,actor,before_config,after_config,reevaluation_result)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING audit_id,changed_at
                    """,
                    (
                        rule_id,
                        patch.actor,
                        Json(_config_snapshot(dict(before))),
                        Json(_config_snapshot(after)),
                        Json(reevaluation),
                    ),
                )
                audit = dict(cur.fetchone())

            conn.commit()
        except HTTPException:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise

    result = dict(after)
    result["reevaluation"] = reevaluation
    result["audit_id"] = audit["audit_id"]
    result["changed_at"] = audit["changed_at"]
    return JSONResponse(content=jsonable_encoder(result))


@router.get("")
def list_alerts(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> JSONResponse:
    clauses = []
    values: list[Any] = []
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        invalid = set(statuses) - {"open", "acknowledged", "resolved"}
        if invalid:
            raise HTTPException(status_code=400, detail=f"invalid status: {sorted(invalid)}")
        clauses.append("a.status = ANY(%s)")
        values.append(statuses)
    if severity:
        severities = [s.strip() for s in severity.split(",") if s.strip()]
        invalid = set(severities) - {"info", "warning", "critical"}
        if invalid:
            raise HTTPException(status_code=400, detail=f"invalid severity: {sorted(invalid)}")
        clauses.append("a.severity = ANY(%s)")
        values.append(severities)
    if domain:
        clauses.append("r.domain=%s")
        values.append(domain)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    values.append(limit)

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT a.alert_id,a.rule_id,r.domain,a.entity_type,a.entity_id,a.severity,a.status,
                       a.opened_at,a.last_observed_at,a.acknowledged_at,a.acknowledged_by,
                       a.resolved_at,a.resolved_by,a.observed_value,a.threshold_value,
                       a.source_event_id,a.resolution_reason
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                {where}
                ORDER BY CASE a.status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                         CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         a.last_observed_at DESC
                LIMIT %s
                """,
                values,
            )
            rows = cur.fetchall()
    return JSONResponse(content=jsonable_encoder(rows))


@router.post("/platform-signal")
def platform_signal(signal: PlatformSignal) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                result = apply_platform_signal(
                    cur,
                    signal.rule_id,
                    signal.entity_id,
                    signal.active,
                    signal.observed_value,
                    signal.threshold_value,
                    signal.actor,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        conn.commit()
    return JSONResponse(content={"result": result, "rule_id": signal.rule_id, "entity_id": signal.entity_id})


@router.get("/{alert_id}")
def alert_detail(alert_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT a.alert_id,a.rule_id,r.domain,a.entity_type,a.entity_id,a.severity,a.status,
                       a.opened_at,a.last_observed_at,a.acknowledged_at,a.acknowledged_by,
                       a.resolved_at,a.resolved_by,a.observed_value,a.threshold_value,
                       a.source_event_id,a.resolution_reason
                FROM alert.alerts a JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE a.alert_id=%s
                """,
                (alert_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="alert not found")
            cur.execute(
                "SELECT history_id,action,actor,occurred_at,details FROM alert.alert_history WHERE alert_id=%s ORDER BY occurred_at,history_id",
                (alert_id,),
            )
            history = cur.fetchall()
    result = dict(row)
    result["history"] = history
    return JSONResponse(content=jsonable_encoder(result))


@router.post("/{alert_id}/acknowledge")
def acknowledge(alert_id: int, request: ActorRequest) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                row = acknowledge_alert(cur, alert_id, request.actor)
            except LookupError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        conn.commit()
    return JSONResponse(content=jsonable_encoder(row))


@router.post("/{alert_id}/resolve")
def resolve(alert_id: int, request: ResolveRequest) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            try:
                row = resolve_alert(cur, alert_id, request.actor, request.reason)
            except LookupError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        conn.commit()
    return JSONResponse(content=jsonable_encoder(row))
