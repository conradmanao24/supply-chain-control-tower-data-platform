from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import RealDictCursor

from realtime.alerts import _delivery_context, _sensor_recorded_utc


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _schedule(sql_conn, key: str, due_at: datetime, event_type: str, entity_type: str, entity_keys: list[dict[str, Any]]) -> None:
    cur = sql_conn.cursor()
    cur.execute(
        "EXEC [ControlTower].[ScheduleDeadline] @DeadlineKey=%s,@DueAtUtc=%s,@EventType=%s,@EntityType=%s,@SourceTable=%s,@EntityKeys=%s",
        (
            key,
            _naive_utc(due_at),
            event_type,
            entity_type,
            "ControlTower.DeadlineSchedule",
            json.dumps(entity_keys, separators=(",", ":")),
        ),
    )


def _cancel(sql_conn, key: str) -> None:
    cur = sql_conn.cursor()
    cur.execute("EXEC [ControlTower].[CancelDeadline] @DeadlineKey=%s", (key,))


def _midnight_utc(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _sync_order(sql_conn, pg_conn, order_id: int) -> None:
    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            "SELECT order_id,expected_delivery_date,picking_completed_when FROM realtime.current_order_state WHERE order_id=%s",
            (order_id,),
        )
        row = pg.fetchone()

    due_key = f"fulfillment:{order_id}:due"
    overdue_key = f"fulfillment:{order_id}:overdue"
    if row is None or row["picking_completed_when"] is not None or row["expected_delivery_date"] is None:
        _cancel(sql_conn, due_key)
        _cancel(sql_conn, overdue_key)
        return

    today = datetime.now(timezone.utc).date()
    due = row["expected_delivery_date"]
    if due > today:
        _schedule(sql_conn, due_key, _midnight_utc(due), "deadline.fulfillment.due", "order", [{"entity_id": order_id}])
    else:
        _cancel(sql_conn, due_key)

    overdue_at = _midnight_utc(due + timedelta(days=1))
    if overdue_at > datetime.now(timezone.utc):
        _schedule(sql_conn, overdue_key, overdue_at, "deadline.fulfillment.overdue", "order", [{"entity_id": order_id}])
    else:
        _cancel(sql_conn, overdue_key)


def _sync_delivery(sql_conn, pg_conn, invoice_id: int) -> None:
    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            """
            SELECT
                d.invoice_id,d.returned_delivery_data,
                d.confirmed_delivery_time,o.expected_delivery_date
            FROM realtime.current_delivery_state d
            LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
            WHERE d.invoice_id=%s
            """,
            (invoice_id,),
        )
        row = pg.fetchone()

    due_key = f"delivery:{invoice_id}:due"
    overdue_key = f"delivery:{invoice_id}:overdue"
    if row is None or row["expected_delivery_date"] is None:
        _cancel(sql_conn, due_key)
        _cancel(sql_conn, overdue_key)
        return

    context = _delivery_context(row["returned_delivery_data"])
    completed = bool(
        context["delivered"]
        or (
            row["confirmed_delivery_time"] is not None
            and not context["receiver_not_present"]
        )
    )
    if completed:
        _cancel(sql_conn, due_key)
        _cancel(sql_conn, overdue_key)
        return

    today = datetime.now(timezone.utc).date()
    due = row["expected_delivery_date"]
    if due > today:
        _schedule(
            sql_conn,
            due_key,
            _midnight_utc(due),
            "deadline.delivery.due",
            "invoice",
            [{"entity_id": invoice_id}],
        )
    else:
        _cancel(sql_conn, due_key)

    overdue_at = _midnight_utc(due + timedelta(days=1))
    if overdue_at > datetime.now(timezone.utc):
        _schedule(
            sql_conn,
            overdue_key,
            overdue_at,
            "deadline.delivery.overdue",
            "invoice",
            [{"entity_id": invoice_id}],
        )
    else:
        _cancel(sql_conn, overdue_key)


def _sync_procurement(sql_conn, pg_conn, purchase_order_id: int) -> None:
    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            """
            SELECT purchase_order_id,expected_delivery_date,is_order_finalized,
                   ordered_outers,received_outers,under_received_line_count
            FROM realtime.current_procurement_state WHERE purchase_order_id=%s
            """,
            (purchase_order_id,),
        )
        row = pg.fetchone()

    due_key = f"procurement:{purchase_order_id}:due"
    overdue_key = f"procurement:{purchase_order_id}:overdue"
    if row is None or row["expected_delivery_date"] is None:
        _cancel(sql_conn, due_key)
        _cancel(sql_conn, overdue_key)
        return

    incomplete = bool(
        int(row["under_received_line_count"]) > 0
        or int(row["received_outers"]) < int(row["ordered_outers"])
        or not bool(row["is_order_finalized"])
    )
    if not incomplete:
        _cancel(sql_conn, due_key)
        _cancel(sql_conn, overdue_key)
        return

    today = datetime.now(timezone.utc).date()
    due = row["expected_delivery_date"]
    if due > today:
        _schedule(sql_conn, due_key, _midnight_utc(due), "deadline.procurement.due", "purchase_order", [{"entity_id": purchase_order_id}])
    else:
        _cancel(sql_conn, due_key)

    overdue_at = _midnight_utc(due + timedelta(days=1))
    if overdue_at > datetime.now(timezone.utc):
        _schedule(sql_conn, overdue_key, overdue_at, "deadline.procurement.overdue", "purchase_order", [{"entity_id": purchase_order_id}])
    else:
        _cancel(sql_conn, overdue_key)


def _sync_coldroom(sql_conn, pg_conn, sensor_number: int) -> None:
    sensor_key = f"coldroom:{sensor_number}"
    stale_key = f"coldroom:{sensor_number}:stale"
    offline_key = f"coldroom:{sensor_number}:offline"
    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            "SELECT sensor_key,recorded_when FROM realtime.current_sensor_state WHERE sensor_key=%s AND sensor_type='coldroom'",
            (sensor_key,),
        )
        row = pg.fetchone()
        pg.execute("SELECT rule_id,enabled,parameters FROM alert.rule_config WHERE rule_id IN ('coldroom.stale','coldroom.offline')")
        rules = {r["rule_id"]: r for r in pg.fetchall()}

    if row is None:
        _cancel(sql_conn, stale_key)
        _cancel(sql_conn, offline_key)
        return

    recorded = _sensor_recorded_utc(row["recorded_when"])
    now = datetime.now(timezone.utc)

    stale_rule = rules.get("coldroom.stale") or {"enabled": False, "parameters": {}}
    offline_rule = rules.get("coldroom.offline") or {"enabled": False, "parameters": {}}
    stale_at = recorded + timedelta(seconds=float(stale_rule["parameters"].get("seconds", 60)))
    offline_at = recorded + timedelta(seconds=float(offline_rule["parameters"].get("seconds", 120)))

    if stale_rule["enabled"] and stale_at > now:
        _schedule(sql_conn, stale_key, stale_at, "deadline.coldroom.stale", "sensor", [{"sensor_key": sensor_key}])
    else:
        _cancel(sql_conn, stale_key)

    if offline_rule["enabled"] and offline_at > now:
        _schedule(sql_conn, offline_key, offline_at, "deadline.coldroom.offline", "sensor", [{"sensor_key": sensor_key}])
    else:
        _cancel(sql_conn, offline_key)


def _sync_vehicle(sql_conn, pg_conn, vehicle_registration: str, sensor_number: int) -> None:
    sensor_key = f"vehicle:{vehicle_registration}:{sensor_number}"
    stale_key = f"{sensor_key}:stale"
    offline_key = f"{sensor_key}:offline"
    with pg_conn.cursor(cursor_factory=RealDictCursor) as pg:
        pg.execute(
            "SELECT sensor_key,recorded_when FROM realtime.current_sensor_state WHERE sensor_key=%s AND sensor_type='vehicle'",
            (sensor_key,),
        )
        row = pg.fetchone()
        pg.execute(
            "SELECT rule_id,enabled,parameters FROM alert.rule_config "
            "WHERE rule_id IN ('vehicle.stale','vehicle.offline')"
        )
        rules = {r["rule_id"]: r for r in pg.fetchall()}

    if row is None:
        _cancel(sql_conn, stale_key)
        _cancel(sql_conn, offline_key)
        return

    recorded = _sensor_recorded_utc(row["recorded_when"])
    now = datetime.now(timezone.utc)

    stale_rule = rules.get("vehicle.stale") or {"enabled": False, "parameters": {}}
    offline_rule = rules.get("vehicle.offline") or {"enabled": False, "parameters": {}}
    stale_at = recorded + timedelta(seconds=float(stale_rule["parameters"].get("seconds", 600)))
    offline_at = recorded + timedelta(seconds=float(offline_rule["parameters"].get("seconds", 1200)))

    if stale_rule["enabled"] and stale_at > now:
        _schedule(sql_conn, stale_key, stale_at, "deadline.vehicle.stale", "sensor", [{"sensor_key": sensor_key}])
    else:
        _cancel(sql_conn, stale_key)

    if offline_rule["enabled"] and offline_at > now:
        _schedule(sql_conn, offline_key, offline_at, "deadline.vehicle.offline", "sensor", [{"sensor_key": sensor_key}])
    else:
        _cancel(sql_conn, offline_key)


def sync_event_deadlines(sql_conn, pg_conn, payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type", "")
    if payload.get("operation") == "DEADLINE" or event_type.startswith("deadline."):
        return
    keys = payload.get("entity_keys") or []

    if event_type == "order.changed":
        for item in keys:
            if item.get("entity_id") is not None:
                _sync_order(sql_conn, pg_conn, int(item["entity_id"]))
    elif event_type == "delivery.changed":
        for item in keys:
            if item.get("entity_id") is not None:
                _sync_delivery(sql_conn, pg_conn, int(item["entity_id"]))
    elif event_type == "procurement.changed":
        for item in keys:
            if item.get("entity_id") is not None:
                _sync_procurement(sql_conn, pg_conn, int(item["entity_id"]))
    elif event_type.startswith("telemetry.coldroom."):
        for item in keys:
            if item.get("sensor_number") is not None:
                _sync_coldroom(sql_conn, pg_conn, int(item["sensor_number"]))
    elif event_type.startswith("telemetry.vehicle."):
        for item in keys:
            vehicle_registration = item.get("vehicle_registration")
            sensor_number = item.get("sensor_number")
            if vehicle_registration is not None and sensor_number is not None:
                _sync_vehicle(sql_conn, pg_conn, str(vehicle_registration), int(sensor_number))
