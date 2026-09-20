from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _evidence(*pairs: tuple[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for label, value in pairs:
        if value is None or value == "":
            continue
        rows.append({"label": label, "value": str(value)})
    return rows


def _safe_fallback(rule_id: str, description: str, observed: dict[str, Any], threshold: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_verified": False,
        "what_happened": (
            f"The alert engine has an active {rule_id} signal for this record. "
            "The stored evidence is not sufficient to restate the business condition safely."
        ),
        "why_it_matters": description,
        "business_evidence": _evidence(
            ("Rule", rule_id),
            ("Configured description", description),
        ),
    }


def explain_alert(
    rule_id: str,
    description: str,
    observed_value: Any,
    threshold_value: Any,
) -> dict[str, Any]:
    """
    Deterministic, fail-closed explanation of an alert.

    A business sentence is returned only when the stored observed/threshold payload
    independently satisfies the same condition used by the alert engine. If the
    evidence is missing or inconsistent, the function does not infer the condition;
    it returns a technical-safe fallback instead.
    """
    observed = _dict(observed_value)
    threshold = _dict(threshold_value)

    if rule_id == "delivery.receiver_not_present":
        latest = _dict(observed.get("latest_event"))
        event = _text(latest.get("Event"))
        comment = _text(latest.get("Comment"))
        verified = (
            (event or "").lower() == "deliveryattempt"
            and (comment or "").lower() == "receiver not present"
        )
        if not verified:
            return _safe_fallback(rule_id, description, observed, threshold)
        return {
            "evidence_verified": True,
            "what_happened": "The latest delivery attempt reports that the receiver was not present.",
            "why_it_matters": "The delivery remains incomplete and requires follow-up.",
            "business_evidence": _evidence(
                ("Order", f"#{observed.get('order_id')}" if observed.get("order_id") is not None else None),
                ("Expected delivery", observed.get("expected_delivery_date")),
                ("Delivery event", event),
                ("Event time", latest.get("EventTime")),
                ("Comment", comment),
                ("Driver", f"#{latest.get('DriverID')}" if latest.get("DriverID") is not None else None),
                ("Consignment", latest.get("ConNote")),
            ),
        }

    if rule_id in {"delivery.overdue", "delivery.due_today"}:
        due = _date(observed.get("expected_delivery_date"))
        evaluation = _date(threshold.get("evaluation_date"))
        completed = observed.get("completed")
        if due is None or evaluation is None or completed is not False:
            return _safe_fallback(rule_id, description, observed, threshold)

        if rule_id == "delivery.overdue":
            verified = due < evaluation
            what = f"Delivery was still incomplete after its expected delivery date of {due.isoformat()}."
            why = "The expected delivery date has passed, so the delivery requires follow-up."
        else:
            verified = due == evaluation
            what = f"Delivery was still incomplete on its expected delivery date of {due.isoformat()}."
            why = "The delivery is due today and has not yet reached a completed state."

        if not verified:
            return _safe_fallback(rule_id, description, observed, threshold)

        return {
            "evidence_verified": True,
            "what_happened": what,
            "why_it_matters": why,
            "business_evidence": _evidence(
                ("Order", f"#{observed.get('order_id')}" if observed.get("order_id") is not None else None),
                ("Expected delivery", due.isoformat()),
                ("Evaluation date", evaluation.isoformat()),
                ("Completed", "No"),
                ("Confirmed delivery time", observed.get("confirmed_delivery_time")),
            ),
        }

    if rule_id in {"fulfillment.overdue", "fulfillment.due_today"}:
        due = _date(observed.get("expected_delivery_date"))
        evaluation = _date(threshold.get("evaluation_date"))
        picking_completed = observed.get("picking_completed")
        if due is None or evaluation is None or picking_completed is not False:
            return _safe_fallback(rule_id, description, observed, threshold)

        if rule_id == "fulfillment.overdue":
            verified = due < evaluation
            what = f"Picking was still incomplete after the expected delivery date of {due.isoformat()}."
            why = "The order is past its expected delivery date while fulfillment remains incomplete."
        else:
            verified = due == evaluation
            what = f"Picking was still incomplete on the expected delivery date of {due.isoformat()}."
            why = "The order is due today and fulfillment is not yet complete."

        if not verified:
            return _safe_fallback(rule_id, description, observed, threshold)

        return {
            "evidence_verified": True,
            "what_happened": what,
            "why_it_matters": why,
            "business_evidence": _evidence(
                ("Expected delivery", due.isoformat()),
                ("Evaluation date", evaluation.isoformat()),
                ("Picking completed", "No"),
                ("Backorder order", f"#{observed.get('backorder_order_id')}" if observed.get("backorder_order_id") is not None else None),
                ("Undersupply backordered", observed.get("is_undersupply_backordered")),
            ),
        }

    if rule_id == "fulfillment.backorder":
        backorder_order_id = observed.get("backorder_order_id")
        picking_completed = observed.get("picking_completed")
        if backorder_order_id is None or picking_completed is not False:
            return _safe_fallback(rule_id, description, observed, threshold)
        return {
            "evidence_verified": True,
            "what_happened": f"This open order is a backorder of original order #{backorder_order_id}.",
            "why_it_matters": "The order is still open and was created as a backorder from an earlier order.",
            "business_evidence": _evidence(
                ("Original order", f"#{backorder_order_id}"),
                ("Expected delivery", observed.get("expected_delivery_date")),
                ("Picking completed", "No"),
            ),
        }

    if rule_id in {"inventory.negative_stock", "inventory.reorder", "inventory.target_watch"}:
        quantity = _number(observed.get("quantity_on_hand"))
        reorder = _number(threshold.get("reorder_level"))
        target = _number(threshold.get("target_stock_level"))
        if quantity is None:
            return _safe_fallback(rule_id, description, observed, threshold)

        if rule_id == "inventory.negative_stock":
            verified = quantity < 0
            what = f"Quantity on hand is {quantity:g}, which is below zero."
            why = "Negative on-hand stock indicates an inventory state that requires correction or investigation."
        elif rule_id == "inventory.reorder":
            if reorder is None:
                return _safe_fallback(rule_id, description, observed, threshold)
            verified = 0 <= quantity <= reorder
            what = f"Quantity on hand is {quantity:g}, at or below the reorder level of {reorder:g}."
            why = "The item has reached its configured replenishment trigger."
        else:
            if reorder is None or target is None:
                return _safe_fallback(rule_id, description, observed, threshold)
            verified = reorder < quantity < target
            what = f"Quantity on hand is {quantity:g}, above reorder level {reorder:g} but below target stock level {target:g}."
            why = "Stock is below the preferred operating target and should be monitored."

        if not verified:
            return _safe_fallback(rule_id, description, observed, threshold)

        return {
            "evidence_verified": True,
            "what_happened": what,
            "why_it_matters": why,
            "business_evidence": _evidence(
                ("Stock item", observed.get("stock_item_name")),
                ("Quantity on hand", f"{quantity:g}"),
                ("Reorder level", f"{reorder:g}" if reorder is not None else None),
                ("Target stock level", f"{target:g}" if target is not None else None),
            ),
        }

    if rule_id in {"procurement.overdue_under_received", "procurement.due_today_under_received"}:
        due = _date(observed.get("expected_delivery_date"))
        evaluation = _date(threshold.get("evaluation_date"))
        ordered = _number(observed.get("ordered_outers"))
        received = _number(observed.get("received_outers"))
        line_count = _number(observed.get("under_received_line_count"))
        finalized = observed.get("is_order_finalized")

        incomplete = bool(
            (line_count is not None and line_count > 0)
            or (ordered is not None and received is not None and received < ordered)
            or finalized is False
        )

        if due is None or evaluation is None or not incomplete:
            return _safe_fallback(rule_id, description, observed, threshold)

        if rule_id == "procurement.overdue_under_received":
            verified = due < evaluation
            what = f"The purchase order remained under-received or open after its expected delivery date of {due.isoformat()}."
            why = "The expected receipt date has passed while the purchase order is not fully received/finalized."
        else:
            verified = due == evaluation
            what = f"The purchase order is due on {due.isoformat()} and remains under-received or open."
            why = "The purchase order is due today but receipt/finalization is still incomplete."

        if not verified:
            return _safe_fallback(rule_id, description, observed, threshold)

        return {
            "evidence_verified": True,
            "what_happened": what,
            "why_it_matters": why,
            "business_evidence": _evidence(
                ("Expected delivery", due.isoformat()),
                ("Evaluation date", evaluation.isoformat()),
                ("Ordered outers", f"{ordered:g}" if ordered is not None else None),
                ("Received outers", f"{received:g}" if received is not None else None),
                ("Under-received lines", f"{line_count:g}" if line_count is not None else None),
                ("Order finalized", finalized),
            ),
        }

    if rule_id in {"coldroom.stale", "coldroom.offline", "vehicle.stale", "vehicle.offline"}:
        age = _number(observed.get("age_seconds"))
        seconds = _number(threshold.get("seconds"))
        if age is None or seconds is None or not (age > seconds):
            return _safe_fallback(rule_id, description, observed, threshold)
        state = "offline" if rule_id.endswith(".offline") else "stale"
        sensor_label = "cold-room" if rule_id.startswith("coldroom.") else "vehicle"
        return {
            "evidence_verified": True,
            "what_happened": f"The latest {sensor_label} reading is {age:g} seconds old, exceeding the {state} threshold of {seconds:g} seconds.",
            "why_it_matters": "Recent sensor data is not arriving within the configured monitoring interval.",
            "business_evidence": _evidence(
                ("Recorded when", observed.get("recorded_when")),
                ("Reading age (seconds)", f"{age:g}"),
                ("Threshold (seconds)", f"{seconds:g}"),
                ("Temperature", observed.get("temperature")),
                ("Reading count", observed.get("reading_count")),
                ("Vehicle", observed.get("vehicle_registration")),
            ),
        }

    if rule_id in {
        "coldroom.temperature_warning",
        "coldroom.temperature_critical",
        "vehicle.temperature_warning",
        "vehicle.temperature_critical",
    }:
        temperature = _number(observed.get("temperature"))
        low = _number(threshold.get("low"))
        high = _number(threshold.get("high"))
        if temperature is None or (low is None and high is None):
            return _safe_fallback(rule_id, description, observed, threshold)
        outside = bool((low is not None and temperature < low) or (high is not None and temperature > high))
        if not outside:
            return _safe_fallback(rule_id, description, observed, threshold)
        sensor_label = "Cold-room" if rule_id.startswith("coldroom.") else "Vehicle"
        return {
            "evidence_verified": True,
            "what_happened": f"{sensor_label} temperature is {temperature:g}, outside the configured {rule_id.split('.')[-1].replace('_', ' ')} band.",
            "why_it_matters": "The reading is outside a configured temperature alert band.",
            "business_evidence": _evidence(
                ("Temperature", f"{temperature:g}"),
                ("Low threshold", f"{low:g}" if low is not None else None),
                ("High threshold", f"{high:g}" if high is not None else None),
                ("Recorded when", observed.get("recorded_when")),
                ("Vehicle", observed.get("vehicle_registration")),
            ),
        }

    if rule_id in {
        "platform.data_quality_failed",
        "platform.pipeline_failed",
        "platform.reconciliation_mismatch",
    }:
        # Platform producers do not yet share one normalized evidence contract.
        # Fail closed rather than inventing a business-facing statement.
        return {
            "evidence_verified": False,
            "what_happened": (
                f"The platform alert rule {rule_id} is active. "
                "Its producer evidence is not normalized enough for a verified business restatement."
            ),
            "why_it_matters": description,
            "business_evidence": _evidence(
                ("Rule", rule_id),
                ("Observed at", observed.get("observed_at")),
                ("Run ID", observed.get("run_id")),
                ("Pipeline", observed.get("pipeline")),
                ("Status", observed.get("status")),
            ),
        }

    return _safe_fallback(rule_id, description, observed, threshold)
