from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from psycopg2.extras import Json, RealDictCursor


SOURCE_TIMEZONE = ZoneInfo(os.environ.get("COLD_CHAIN_SOURCE_TIMEZONE", "Asia/Jakarta"))


def _sensor_recorded_utc(recorded: datetime) -> datetime:
    if recorded.tzinfo is None:
        return recorded.replace(tzinfo=SOURCE_TIMEZONE).astimezone(timezone.utc)
    return recorded.astimezone(timezone.utc)


def _rule(pg, rule_id: str) -> dict[str, Any] | None:
    pg.execute(
        "SELECT rule_id,domain,enabled,severity,source_native,parameters FROM alert.rule_config WHERE rule_id=%s",
        (rule_id,),
    )
    row = pg.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    columns = [d[0] for d in pg.description]
    return dict(zip(columns, row))


def _active_alert(pg, rule_id: str, entity_type: str, entity_id: str) -> dict[str, Any] | None:
    pg.execute(
        """
        SELECT alert_id,rule_id,entity_type,entity_id,severity,status,opened_at,
               acknowledged_at,acknowledged_by,observed_value,threshold_value
        FROM alert.alerts
        WHERE rule_id=%s AND entity_type=%s AND entity_id=%s
          AND status IN ('open','acknowledged')
        FOR UPDATE
        """,
        (rule_id, entity_type, entity_id),
    )
    row = pg.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return row
    columns = [d[0] for d in pg.description]
    return dict(zip(columns, row))


def sync_alert(
    pg,
    rule_id: str,
    entity_type: str,
    entity_id: str | int,
    active: bool,
    observed_value: dict[str, Any] | None = None,
    threshold_value: dict[str, Any] | None = None,
    source_event_id: str | None = None,
    resolution_reason: str = "condition_cleared",
    actor: str = "engine",
) -> str:
    entity_id_text = str(entity_id)
    observed = observed_value or {}
    threshold = threshold_value or {}
    rule = _rule(pg, rule_id)
    if rule is None:
        raise KeyError(f"unknown alert rule: {rule_id}")

    existing = _active_alert(pg, rule_id, entity_type, entity_id_text)
    enabled = bool(rule["enabled"])
    should_open = bool(active and enabled)

    if should_open:
        if existing is None:
            pg.execute(
                """
                INSERT INTO alert.alerts
                    (rule_id,entity_type,entity_id,severity,status,observed_value,
                     threshold_value,source_event_id)
                VALUES (%s,%s,%s,%s,'open',%s,%s,%s)
                RETURNING alert_id
                """,
                (
                    rule_id,
                    entity_type,
                    entity_id_text,
                    rule["severity"],
                    Json(observed),
                    Json(threshold),
                    source_event_id,
                ),
            )
            inserted = pg.fetchone()
            alert_id = inserted["alert_id"] if isinstance(inserted, dict) else inserted[0]
            pg.execute(
                "INSERT INTO alert.alert_history(alert_id,action,actor,details) VALUES (%s,'opened',%s,%s)",
                (alert_id, actor, Json({"observed": observed, "threshold": threshold, "source_event_id": source_event_id})),
            )
            return "opened"

        alert_id = existing["alert_id"]
        pg.execute(
            """
            UPDATE alert.alerts
            SET severity=%s,last_observed_at=now(),observed_value=%s,
                threshold_value=%s,source_event_id=%s
            WHERE alert_id=%s
            """,
            (rule["severity"], Json(observed), Json(threshold), source_event_id, alert_id),
        )
        pg.execute(
            "INSERT INTO alert.alert_history(alert_id,action,actor,details) VALUES (%s,'observed',%s,%s)",
            (alert_id, actor, Json({"observed": observed, "threshold": threshold, "source_event_id": source_event_id})),
        )
        return "observed"

    if existing is not None:
        reason = "rule_disabled" if not enabled else resolution_reason
        pg.execute(
            """
            UPDATE alert.alerts
            SET status='resolved',resolved_at=now(),resolved_by=%s,
                resolution_reason=%s,last_observed_at=now(),source_event_id=%s
            WHERE alert_id=%s
            """,
            (actor, reason, source_event_id, existing["alert_id"]),
        )
        pg.execute(
            "INSERT INTO alert.alert_history(alert_id,action,actor,details) VALUES (%s,'resolved',%s,%s)",
            (existing["alert_id"], actor, Json({"reason": reason, "source_event_id": source_event_id})),
        )
        return "resolved"

    return "clear"


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _business_date(pg) -> date:
    pg.execute(
        "SELECT safe_through_cutoff FROM control.source_frontier "
        "WHERE source_name='WideWorldImporters'"
    )
    row = pg.fetchone()
    if row is None:
        return _today_utc()
    cutoff = row["safe_through_cutoff"] if isinstance(row, dict) else row[0]
    return (cutoff - timedelta(days=1)).date()


def evaluate_inventory(pg, stock_item_id: int, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT stock_item_id,stock_item_name,quantity_on_hand,reorder_level,target_stock_level
        FROM realtime.current_inventory_state WHERE stock_item_id=%s
        """,
        (stock_item_id,),
    )
    row = pg.fetchone()
    if row is None:
        return {
            rule: sync_alert(pg, rule, "stock_item", stock_item_id, False, source_event_id=event_id, resolution_reason="entity_missing")
            for rule in ("inventory.negative_stock", "inventory.reorder", "inventory.target_watch")
        }
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    qoh = int(row["quantity_on_hand"])
    reorder = int(row["reorder_level"])
    typical_order_quantity = int(row["target_stock_level"])
    observed = {"quantity_on_hand": qoh, "stock_item_name": row["stock_item_name"]}
    threshold = {
        "reorder_level": reorder,
        "typical_order_quantity": typical_order_quantity,
    }
    return {
        "inventory.negative_stock": sync_alert(pg, "inventory.negative_stock", "stock_item", stock_item_id, qoh < 0, observed, threshold, event_id),
        "inventory.reorder": sync_alert(pg, "inventory.reorder", "stock_item", stock_item_id, 0 <= qoh <= reorder, observed, threshold, event_id),
        "inventory.target_watch": sync_alert(pg, "inventory.target_watch", "stock_item", stock_item_id, False, observed, threshold, event_id, resolution_reason="invalid_threshold_semantics"),
    }


def evaluate_fulfillment(pg, order_id: int, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT order_id,order_date,expected_delivery_date,picking_completed_when,backorder_order_id,
               is_undersupply_backordered
        FROM realtime.current_order_state WHERE order_id=%s
        """,
        (order_id,),
    )
    row = pg.fetchone()
    rules = ("fulfillment.overdue", "fulfillment.due_today", "fulfillment.backorder")
    if row is None:
        return {rule: sync_alert(pg, rule, "order", order_id, False, source_event_id=event_id, resolution_reason="entity_missing") for rule in rules}
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    today = _business_date(pg)
    order_date = row["order_date"]
    due = row["expected_delivery_date"]
    in_scope = bool(
        order_date
        and order_date >= today - timedelta(days=30)
        and order_date <= today
    )
    unpicked = bool(in_scope and row["picking_completed_when"] is None)
    backorder = bool(unpicked and row["backorder_order_id"] is not None)
    observed = {
        "order_date": order_date.isoformat() if order_date else None,
        "operational_scope": in_scope,
        "expected_delivery_date": due.isoformat() if due else None,
        "picking_completed": not unpicked,
        "backorder_order_id": row["backorder_order_id"],
        "is_undersupply_backordered": bool(row["is_undersupply_backordered"]),
    }
    return {
        "fulfillment.overdue": sync_alert(pg, "fulfillment.overdue", "order", order_id, bool(unpicked and due and due < today), observed, {"evaluation_date": today.isoformat()}, event_id),
        "fulfillment.due_today": sync_alert(pg, "fulfillment.due_today", "order", order_id, bool(unpicked and due == today), observed, {"evaluation_date": today.isoformat()}, event_id),
        "fulfillment.backorder": sync_alert(pg, "fulfillment.backorder", "order", order_id, backorder, observed, {}, event_id),
    }


def _delivery_context(returned: Any) -> dict[str, Any]:
    if returned is None:
        return {"latest_event": None, "receiver_not_present": False, "delivered": False}
    if isinstance(returned, str):
        try:
            returned = json.loads(returned)
        except Exception:
            return {"latest_event": None, "receiver_not_present": False, "delivered": False}
    events = returned.get("Events") or [] if isinstance(returned, dict) else []
    latest = events[-1] if events else None
    receiver_not_present = bool(
        latest
        and str(latest.get("Event", "")).lower() == "deliveryattempt"
        and str(latest.get("Comment", "")).lower() == "receiver not present"
    )
    delivered = bool(
        latest
        and str(latest.get("Event", "")).lower() == "deliveryattempt"
        and str(latest.get("Status", "")).lower() == "delivered"
    )
    return {"latest_event": latest, "receiver_not_present": receiver_not_present, "delivered": delivered}


def evaluate_delivery(pg, invoice_id: int, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT
            d.invoice_id,d.order_id,d.invoice_date,d.returned_delivery_data,
            d.confirmed_delivery_time,d.confirmed_received_by,
            o.order_date,o.expected_delivery_date
        FROM realtime.current_delivery_state d
        LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
        WHERE d.invoice_id=%s
        """,
        (invoice_id,),
    )
    row = pg.fetchone()
    rules = ("delivery.overdue", "delivery.due_today", "delivery.receiver_not_present")
    if row is None:
        return {
            rule: sync_alert(
                pg,
                rule,
                "invoice",
                invoice_id,
                False,
                source_event_id=event_id,
                resolution_reason="entity_missing",
            )
            for rule in rules
        }
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    context = _delivery_context(row["returned_delivery_data"])
    completed = bool(
        row["confirmed_delivery_time"] is not None
        or context["delivered"]
    )
    receiver_not_present_active = bool(
        context["receiver_not_present"] and not completed
    )
    due = row["expected_delivery_date"]
    today = _business_date(pg)
    lifecycle_gap_days = (
        (row["invoice_date"] - row["order_date"]).days
        if row["invoice_date"] is not None and row["order_date"] is not None
        else None
    )
    observed = {
        "order_id": row["order_id"],
        "order_date": row["order_date"].isoformat() if row["order_date"] else None,
        "invoice_date": row["invoice_date"].isoformat() if row["invoice_date"] else None,
        "lifecycle_gap_days": lifecycle_gap_days,
        "expected_delivery_date": due.isoformat() if due else None,
        "confirmed_delivery_time": (
            row["confirmed_delivery_time"].isoformat()
            if row["confirmed_delivery_time"] else None
        ),
        "latest_event": context["latest_event"],
        "completed": completed,
    }
    return {
        "delivery.overdue": sync_alert(
            pg,
            "delivery.overdue",
            "invoice",
            invoice_id,
            bool(not completed and due and due < today),
            observed,
            {"evaluation_date": today.isoformat()},
            event_id,
        ),
        "delivery.due_today": sync_alert(
            pg,
            "delivery.due_today",
            "invoice",
            invoice_id,
            bool(not completed and due == today),
            observed,
            {"evaluation_date": today.isoformat()},
            event_id,
        ),
        "delivery.receiver_not_present": sync_alert(
            pg,
            "delivery.receiver_not_present",
            "invoice",
            invoice_id,
            receiver_not_present_active,
            observed,
            {},
            event_id,
        ),
    }


def evaluate_procurement(pg, purchase_order_id: int, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT purchase_order_id,expected_delivery_date,is_order_finalized,
               ordered_outers,received_outers,under_received_line_count
        FROM realtime.current_procurement_state WHERE purchase_order_id=%s
        """,
        (purchase_order_id,),
    )
    row = pg.fetchone()
    rules = ("procurement.overdue_under_received", "procurement.due_today_under_received")
    if row is None:
        return {rule: sync_alert(pg, rule, "purchase_order", purchase_order_id, False, source_event_id=event_id, resolution_reason="entity_missing") for rule in rules}
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    incomplete = bool(
        int(row["under_received_line_count"]) > 0
        or int(row["received_outers"]) < int(row["ordered_outers"])
        or not bool(row["is_order_finalized"])
    )
    due = row["expected_delivery_date"]
    today = _business_date(pg)
    observed = {
        "expected_delivery_date": due.isoformat() if due else None,
        "is_order_finalized": bool(row["is_order_finalized"]),
        "ordered_outers": int(row["ordered_outers"]),
        "received_outers": int(row["received_outers"]),
        "under_received_line_count": int(row["under_received_line_count"]),
    }
    return {
        "procurement.overdue_under_received": sync_alert(pg, "procurement.overdue_under_received", "purchase_order", purchase_order_id, bool(incomplete and due and due < today), observed, {"evaluation_date": today.isoformat()}, event_id),
        "procurement.due_today_under_received": sync_alert(pg, "procurement.due_today_under_received", "purchase_order", purchase_order_id, bool(incomplete and due == today), observed, {"evaluation_date": today.isoformat()}, event_id),
    }


def _outside(value: float, params: dict[str, Any]) -> bool:
    low = params.get("low")
    high = params.get("high")
    return bool((low is not None and value < float(low)) or (high is not None and value > float(high)))


def evaluate_coldroom(pg, sensor_key: str, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT sensor_key,sensor_type,sensor_number,recorded_when,temperature,reading_count
        FROM realtime.current_sensor_state WHERE sensor_key=%s AND sensor_type='coldroom'
        """,
        (sensor_key,),
    )
    row = pg.fetchone()
    rules = ("coldroom.stale", "coldroom.offline", "coldroom.temperature_warning", "coldroom.temperature_critical")
    if row is None:
        return {rule: sync_alert(pg, rule, "sensor", sensor_key, False, source_event_id=event_id, resolution_reason="entity_missing") for rule in rules}
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    recorded = row["recorded_when"]
    recorded_utc = _sensor_recorded_utc(recorded)
    age_seconds = max(0.0, (datetime.now(timezone.utc) - recorded_utc).total_seconds())
    temperature = float(row["temperature"])

    stale_rule = _rule(pg, "coldroom.stale")
    offline_rule = _rule(pg, "coldroom.offline")
    warn_temp_rule = _rule(pg, "coldroom.temperature_warning")
    crit_temp_rule = _rule(pg, "coldroom.temperature_critical")
    stale_seconds = float((stale_rule or {}).get("parameters", {}).get("seconds", 60))
    offline_seconds = float((offline_rule or {}).get("parameters", {}).get("seconds", 120))
    offline_active = age_seconds > offline_seconds
    stale_active = age_seconds > stale_seconds and not offline_active
    critical_temp = _outside(temperature, (crit_temp_rule or {}).get("parameters", {}))
    warning_temp = _outside(temperature, (warn_temp_rule or {}).get("parameters", {})) and not critical_temp
    observed = {
        "recorded_when": recorded_utc.isoformat(),
        "age_seconds": round(age_seconds, 3),
        "temperature": temperature,
        "reading_count": row["reading_count"],
    }
    return {
        "coldroom.stale": sync_alert(pg, "coldroom.stale", "sensor", sensor_key, stale_active, observed, {"seconds": stale_seconds}, event_id),
        "coldroom.offline": sync_alert(pg, "coldroom.offline", "sensor", sensor_key, offline_active, observed, {"seconds": offline_seconds}, event_id),
        "coldroom.temperature_warning": sync_alert(pg, "coldroom.temperature_warning", "sensor", sensor_key, warning_temp, observed, (warn_temp_rule or {}).get("parameters", {}), event_id),
        "coldroom.temperature_critical": sync_alert(pg, "coldroom.temperature_critical", "sensor", sensor_key, critical_temp, observed, (crit_temp_rule or {}).get("parameters", {}), event_id),
    }


def evaluate_vehicle(pg, sensor_key: str, event_id: str | None) -> dict[str, str]:
    pg.execute(
        """
        SELECT sensor_key,sensor_type,vehicle_registration,sensor_number,
               recorded_when,temperature,reading_count
        FROM realtime.current_sensor_state
        WHERE sensor_key=%s AND sensor_type='vehicle'
        """,
        (sensor_key,),
    )
    row = pg.fetchone()
    rules = ("vehicle.stale", "vehicle.offline", "vehicle.temperature_warning", "vehicle.temperature_critical")
    if row is None:
        return {
            rule: sync_alert(
                pg,
                rule,
                "sensor",
                sensor_key,
                False,
                source_event_id=event_id,
                resolution_reason="entity_missing",
            )
            for rule in rules
        }
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))

    recorded_utc = _sensor_recorded_utc(row["recorded_when"])
    age_seconds = max(0.0, (datetime.now(timezone.utc) - recorded_utc).total_seconds())
    temperature = float(row["temperature"])

    stale_rule = _rule(pg, "vehicle.stale")
    offline_rule = _rule(pg, "vehicle.offline")
    warn_temp_rule = _rule(pg, "vehicle.temperature_warning")
    crit_temp_rule = _rule(pg, "vehicle.temperature_critical")
    stale_seconds = float((stale_rule or {}).get("parameters", {}).get("seconds", 600))
    offline_seconds = float((offline_rule or {}).get("parameters", {}).get("seconds", 1200))
    offline_active = age_seconds > offline_seconds
    stale_active = age_seconds > stale_seconds and not offline_active
    critical_temp = _outside(temperature, (crit_temp_rule or {}).get("parameters", {}))
    warning_temp = _outside(temperature, (warn_temp_rule or {}).get("parameters", {})) and not critical_temp
    observed = {
        "recorded_when": recorded_utc.isoformat(),
        "age_seconds": round(age_seconds, 3),
        "temperature": temperature,
        "reading_count": row["reading_count"],
        "vehicle_registration": row["vehicle_registration"],
    }
    return {
        "vehicle.stale": sync_alert(pg, "vehicle.stale", "sensor", sensor_key, stale_active, observed, {"seconds": stale_seconds}, event_id),
        "vehicle.offline": sync_alert(pg, "vehicle.offline", "sensor", sensor_key, offline_active, observed, {"seconds": offline_seconds}, event_id),
        "vehicle.temperature_warning": sync_alert(pg, "vehicle.temperature_warning", "sensor", sensor_key, warning_temp, observed, (warn_temp_rule or {}).get("parameters", {}), event_id),
        "vehicle.temperature_critical": sync_alert(pg, "vehicle.temperature_critical", "sensor", sensor_key, critical_temp, observed, (crit_temp_rule or {}).get("parameters", {}), event_id),
    }


def evaluate_event(pg, payload: dict[str, Any]) -> dict[str, Any]:
    event_id = payload.get("event_id")
    event_type = payload.get("event_type", "")
    keys = payload.get("entity_keys") or []
    results: dict[str, Any] = {}

    if event_type == "order.changed" or event_type.startswith("deadline.fulfillment."):
        for item in keys:
            entity_id = item.get("entity_id")
            if entity_id is not None:
                results[f"order:{entity_id}"] = evaluate_fulfillment(pg, int(entity_id), event_id)
    elif event_type == "delivery.changed" or event_type.startswith("deadline.delivery."):
        for item in keys:
            entity_id = item.get("entity_id")
            if entity_id is not None:
                results[f"invoice:{entity_id}"] = evaluate_delivery(pg, int(entity_id), event_id)
    elif event_type == "procurement.changed" or event_type.startswith("deadline.procurement."):
        for item in keys:
            entity_id = item.get("entity_id")
            if entity_id is not None:
                results[f"purchase_order:{entity_id}"] = evaluate_procurement(pg, int(entity_id), event_id)
    elif event_type == "inventory.changed":
        for item in keys:
            entity_id = item.get("entity_id")
            if entity_id is not None:
                results[f"stock_item:{entity_id}"] = evaluate_inventory(pg, int(entity_id), event_id)
    elif event_type.startswith("telemetry.coldroom."):
        for item in keys:
            sensor_number = item.get("sensor_number")
            if sensor_number is not None:
                key = f"coldroom:{int(sensor_number)}"
                results[key] = evaluate_coldroom(pg, key, event_id)
    elif event_type.startswith("deadline.coldroom."):
        for item in keys:
            sensor_key = item.get("sensor_key")
            if sensor_key:
                results[str(sensor_key)] = evaluate_coldroom(pg, str(sensor_key), event_id)
    elif event_type.startswith("telemetry.vehicle."):
        for item in keys:
            vehicle_registration = item.get("vehicle_registration")
            sensor_number = item.get("sensor_number")
            if vehicle_registration is not None and sensor_number is not None:
                key = f"vehicle:{vehicle_registration}:{int(sensor_number)}"
                results[key] = evaluate_vehicle(pg, key, event_id)
    elif event_type.startswith("deadline.vehicle."):
        for item in keys:
            sensor_key = item.get("sensor_key")
            if sensor_key:
                results[str(sensor_key)] = evaluate_vehicle(pg, str(sensor_key), event_id)

    return results


def apply_platform_signal(
    pg,
    rule_id: str,
    entity_id: str,
    active: bool,
    observed_value: dict[str, Any] | None = None,
    threshold_value: dict[str, Any] | None = None,
    actor: str = "platform",
) -> str:
    rule = _rule(pg, rule_id)
    if rule is None or rule["domain"] != "platform":
        raise KeyError(f"unknown platform rule: {rule_id}")
    result = sync_alert(
        pg,
        rule_id,
        "platform",
        entity_id,
        active,
        observed_value or {},
        threshold_value or {},
        None,
        resolution_reason="platform_recovered",
        actor=actor,
    )
    return result


def acknowledge_alert(pg, alert_id: int, actor: str) -> dict[str, Any]:
    pg.execute(
        """
        UPDATE alert.alerts
        SET status='acknowledged',acknowledged_at=now(),acknowledged_by=%s
        WHERE alert_id=%s AND status='open'
        RETURNING alert_id,rule_id,entity_type,entity_id,severity,status,opened_at,
                  acknowledged_at,acknowledged_by,resolved_at,resolution_reason
        """,
        (actor, alert_id),
    )
    row = pg.fetchone()
    if row is None:
        raise LookupError("alert is not open or does not exist")
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))
    pg.execute(
        "INSERT INTO alert.alert_history(alert_id,action,actor,details) VALUES (%s,'acknowledged',%s,'{}'::jsonb)",
        (alert_id, actor),
    )
    return row


def resolve_alert(pg, alert_id: int, actor: str, reason: str) -> dict[str, Any]:
    pg.execute(
        """
        UPDATE alert.alerts
        SET status='resolved',resolved_at=now(),resolved_by=%s,resolution_reason=%s
        WHERE alert_id=%s AND status IN ('open','acknowledged')
        RETURNING alert_id,rule_id,entity_type,entity_id,severity,status,opened_at,
                  acknowledged_at,acknowledged_by,resolved_at,resolved_by,resolution_reason
        """,
        (actor, reason, alert_id),
    )
    row = pg.fetchone()
    if row is None:
        raise LookupError("alert is already resolved or does not exist")
    if not isinstance(row, dict):
        row = dict(zip([d[0] for d in pg.description], row))
    pg.execute(
        "INSERT INTO alert.alert_history(alert_id,action,actor,details) VALUES (%s,'resolved',%s,%s)",
        (alert_id, actor, Json({"reason": reason})),
    )
    return row




