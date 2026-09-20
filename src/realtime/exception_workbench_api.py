from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from realtime.operational_semantics import DELIVERY_LIFECYCLE_MAX_DAYS
from realtime.supply_risk import (
    INVENTORY_PROJECTION_CTES,
    fetch_inventory_projection,
    fetch_open_orders_for_sku,
    fetch_open_pos_for_sku,
    fetch_supplier_performance,
)

router = APIRouter(prefix="/api/workbench", tags=["exception-workbench"])


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def business_date(cur: RealDictCursor):
    cur.execute(
        """
        SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
        FROM control.source_frontier
        WHERE source_name='WideWorldImporters'
        """
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("WideWorldImporters source frontier is unavailable")
    return row["as_of"]


def metric(label: str, value: Any, detail: str | None = None) -> dict[str, Any]:
    return {"label": label, "value": value, "detail": detail}


def relation(
    domain: str,
    entity_type: str,
    entity_id: int | str,
    label: str,
    relationship: str,
    status: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    return {
        "domain": domain,
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "label": label,
        "relationship": relationship,
        "status": status,
        "detail": detail,
    }


def timeline_event(
    label: str,
    timestamp: Any,
    detail: str | None = None,
    state: str = "observed",
) -> dict[str, Any]:
    return {
        "label": label,
        "timestamp": timestamp,
        "detail": detail,
        "state": state,
    }


def _coverage_title(state: str) -> str:
    return {
        "negative_stock": "Negative on-hand inventory",
        "projected_shortfall": "Projected supply shortfall",
        "stockout_before_inbound": "Stockout exposure before inbound supply",
        "coverage_gap": "Inventory cover shorter than inbound lead time",
        "reorder": "Reorder threshold reached",
        "healthy": "No current supply coverage exception",
    }.get(state, state.replace("_", " ").title())


def _coverage_cause_title(state: str) -> str:
    return {
        "negative_stock": "On-hand quantity is below zero",
        "projected_shortfall": "Demand exceeds on-hand plus scoped inbound supply",
        "stockout_before_inbound": "Demand is due before replenishment arrives",
        "coverage_gap": "Inventory cover expires before the next inbound receipt",
        "reorder": "On-hand inventory has reached the reorder threshold",
        "healthy": "No verified supply-coverage cause",
    }.get(state, state.replace("_", " ").title())


@router.get("/inventory/{stock_item_id}")
def inventory_workbench(stock_item_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            rows = fetch_inventory_projection(cur, stock_item_id=stock_item_id)
            if not rows:
                raise HTTPException(status_code=404, detail="Stock item not found")
            item = rows[0]
            orders = fetch_open_orders_for_sku(cur, stock_item_id, 12)
            pos = fetch_open_pos_for_sku(cur, stock_item_id, 12)

    coverage_state = str(item["coverage_state"])
    severity = str(item["coverage_severity"])
    next_inbound = item["next_inbound_date"]

    if coverage_state == "healthy":
        summary = "Current on-hand inventory covers the scoped operational demand."
    elif coverage_state == "stockout_before_inbound":
        summary = (
            "Demand due before the next inbound receipt exceeds current on-hand inventory."
        )
    elif coverage_state == "coverage_gap":
        summary = (
            "Historical demand velocity implies inventory cover expires before the next inbound date."
        )
    elif coverage_state == "projected_shortfall":
        summary = (
            "Current on-hand plus scoped inbound supply is below scoped open demand."
        )
    else:
        summary = _coverage_title(coverage_state) + "."

    related: list[dict[str, Any]] = []
    for order in orders[:8]:
        related.append(
            relation(
                "Fulfillment",
                "order",
                order["order_id"],
                f"Order #{order['order_id']}",
                "Open demand for this SKU",
                "overdue" if int(order["days_overdue"]) > 0 else "open",
                f"{order['demand_units']} units / {order['customer_name']}",
            )
        )
    for po in pos[:8]:
        related.append(
            relation(
                "Procurement",
                "purchase_order",
                po["purchase_order_id"],
                f"PO #{po['purchase_order_id']}",
                "Inbound supply for this SKU",
                "open",
                f"{po['outstanding_units']} units / {po['supplier_name']}",
            )
        )

    result = {
        "generated_at": datetime.now(timezone.utc),
        "entity": {
            "domain": "Inventory",
            "entity_type": "stock_item",
            "entity_id": str(stock_item_id),
            "label": item["stock_item_name"],
        },
        "issue": {
            "code": coverage_state,
            "title": _coverage_title(coverage_state),
            "severity": severity,
            "summary": summary,
        },
        "impact": [
            metric("On hand", int(item["quantity_on_hand"]), "units"),
            metric("Open demand", int(item["open_demand_units"]), "30-day operational window"),
            metric("Incoming supply", int(item["incoming_units"]), "open PO units"),
            metric("Projected available", int(item["projected_available"]), "on hand + incoming - demand"),
            metric("Orders affected", int(item["affected_orders"]), "open orders using this SKU"),
            metric(
                "Days of cover",
                float(item["days_of_cover"]) if item["days_of_cover"] is not None else None,
                "on hand / 30-day outbound demand velocity",
            ),
        ],
        "evidence": [
            metric("Demand due before inbound", int(item["demand_before_inbound_units"]), "units"),
            metric("Pre-inbound balance", int(item["pre_inbound_balance"]), "on hand - demand due before inbound"),
            metric("Pre-inbound shortfall", int(item["pre_inbound_shortfall_units"]), "units"),
            metric("Next inbound", next_inbound, f"{item['inbound_po_count']} open PO(s)"),
            metric("Earliest open demand due", item["earliest_demand_due"]),
            metric("30-day outbound movement", int(item["outbound_units_30d"]), "units"),
        ],
        "cause": {
            "classification": coverage_state,
            "title": _coverage_cause_title(coverage_state),
            "explanation": summary,
            "basis": (
                "Derived from current stock, unpicked order-line demand in the 30-day operational window, "
                "open PO supply in the same window, and 30-day actual outbound inventory movements."
            ),
        },
        "related_records": related,
        "timeline": [
            timeline_event("Latest inventory state edit", item["last_edited_when"]),
            timeline_event("Earliest open demand due", item["earliest_demand_due"], state="planned"),
            timeline_event(
                "Next inbound supply",
                next_inbound,
                f"{item['incoming_units']} units expected" if next_inbound else "No scoped inbound PO",
                state="planned",
            ),
        ],
        "projection": item,
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/fulfillment/{order_id}")
def fulfillment_workbench(order_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = business_date(cur)
            cur.execute(
                """
                SELECT
                    o.order_id,o.customer_id,
                    coalesce(c.customer_name,'Customer '||o.customer_id::text) AS customer_name,
                    o.order_date,o.expected_delivery_date,o.backorder_order_id,
                    o.is_undersupply_backordered,o.picking_completed_when,o.last_edited_when,
                    count(f.order_line_key)::int AS line_count,
                    coalesce(sum(f.quantity),0)::bigint AS units_ordered,
                    coalesce(sum(f.total_including_tax),0)::numeric(18,2) AS order_value,
                    count(*) FILTER (WHERE f.picking_completed_when IS NOT NULL)::int AS picked_lines
                FROM realtime.current_order_state o
                LEFT JOIN core.dim_customer c
                  ON c.customer_id=o.customer_id AND c.is_current
                LEFT JOIN core.fact_order_line f ON f.order_id=o.order_id
                WHERE o.order_id=%s
                GROUP BY
                    o.order_id,o.customer_id,c.customer_name,o.order_date,
                    o.expected_delivery_date,o.backorder_order_id,
                    o.is_undersupply_backordered,o.picking_completed_when,o.last_edited_when
                """,
                (order_id,),
            )
            order = cur.fetchone()
            if order is None:
                raise HTTPException(status_code=404, detail="Order not found")
            order = dict(order)

            cur.execute(
                INVENTORY_PROJECTION_CTES
                + """
                SELECT
                    f.stock_item_id,
                    coalesce(p.stock_item_name,'Stock item '||f.stock_item_id::text)
                        AS stock_item_name,
                    sum(f.quantity)::bigint AS order_units,
                    s.quantity_on_hand,s.open_demand_units,s.incoming_units,
                    s.projected_available,s.pre_inbound_balance,
                    s.pre_inbound_shortfall_units,s.projected_shortfall_units,
                    s.coverage_state,s.coverage_severity,s.next_inbound_date,
                    s.days_of_cover
                FROM core.fact_order_line f
                LEFT JOIN core.dim_product p
                  ON p.stock_item_id=f.stock_item_id AND p.is_current
                LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
                WHERE f.order_id=%s
                  AND f.picking_completed_when IS NULL
                GROUP BY
                    f.stock_item_id,p.stock_item_name,s.quantity_on_hand,
                    s.open_demand_units,s.incoming_units,s.projected_available,
                    s.pre_inbound_balance,s.pre_inbound_shortfall_units,
                    s.projected_shortfall_units,s.coverage_state,
                    s.coverage_severity,s.next_inbound_date,s.days_of_cover
                ORDER BY
                    CASE s.coverage_severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    s.pre_inbound_shortfall_units DESC NULLS LAST,
                    f.stock_item_id
                """,
                (order_id,),
            )
            sku_rows = [dict(row) for row in cur.fetchall()]
            risky_skus = [
                row for row in sku_rows
                if row.get("coverage_severity") in {"critical", "warning"}
            ]

            cur.execute(
                """
                SELECT
                    invoice_id,invoice_date,confirmed_delivery_time,
                    confirmed_received_by
                FROM realtime.current_delivery_state
                WHERE order_id=%s
                ORDER BY invoice_date,invoice_id
                """,
                (order_id,),
            )
            deliveries = [dict(row) for row in cur.fetchall()]

            po_rows: list[dict[str, Any]] = []
            seen_po: set[int] = set()
            for sku in risky_skus[:5]:
                for po in fetch_open_pos_for_sku(cur, int(sku["stock_item_id"]), 4):
                    po_id = int(po["purchase_order_id"])
                    if po_id not in seen_po:
                        seen_po.add(po_id)
                        po_rows.append(po)

    completed = order["picking_completed_when"] is not None
    days_overdue = max((as_of-order["expected_delivery_date"]).days, 0)
    backorder = order["backorder_order_id"] is not None
    critical_skus = [
        row for row in risky_skus if row.get("coverage_severity") == "critical"
    ]

    if completed:
        issue_code = "completed"
        severity = "healthy"
        issue_title = "Picking completed"
        issue_summary = "The order is no longer in the active picking queue."
    elif days_overdue > 0:
        issue_code = "overdue"
        severity = "critical" if days_overdue >= 7 or critical_skus or backorder else "warning"
        issue_title = f"Order overdue by {days_overdue} day(s)"
        issue_summary = "Expected delivery date has passed while picking remains incomplete."
    elif order["expected_delivery_date"] == as_of:
        issue_code = "due_today"
        severity = "critical" if critical_skus else "warning"
        issue_title = "Order due today"
        issue_summary = "Customer promise date is today and picking remains incomplete."
    else:
        issue_code = "open"
        severity = "warning" if risky_skus else "healthy"
        issue_title = "Open order"
        issue_summary = "Picking remains incomplete within the current operational window."

    if critical_skus:
        cause = {
            "classification": "inventory_supply_gap",
            "title": "Inventory supply coverage gap",
            "explanation": (
                f"{len(critical_skus)} order SKU(s) have a critical supply coverage condition "
                "based on current stock, scoped open demand, and inbound PO timing."
            ),
            "basis": "Derived from inventory projection; no inferred or AI-generated root cause.",
        }
    elif backorder:
        cause = {
            "classification": "backorder_dependency",
            "title": "Backorder dependency",
            "explanation": f"Order references backorder #{order['backorder_order_id']}.",
            "basis": "Direct source-field evidence from Sales.Orders.",
        }
    elif not completed:
        cause = {
            "classification": "picking_incomplete",
            "title": "Picking incomplete",
            "explanation": "No verified upstream supply shortfall was found for the unpicked order lines.",
            "basis": "Derived from picking state plus current supply projection.",
        }
    else:
        cause = {
            "classification": "none",
            "title": "No active fulfillment exception",
            "explanation": "Picking is complete.",
            "basis": "Direct current-order state.",
        }

    related: list[dict[str, Any]] = []
    for sku in risky_skus[:8]:
        related.append(
            relation(
                "Inventory",
                "stock_item",
                sku["stock_item_id"],
                sku["stock_item_name"],
                "Order line with supply exposure",
                sku["coverage_state"],
                f"{sku['order_units']} order units / projected {sku['projected_available']}",
            )
        )
    for po in po_rows[:8]:
        related.append(
            relation(
                "Procurement",
                "purchase_order",
                po["purchase_order_id"],
                f"PO #{po['purchase_order_id']}",
                "Inbound supply for exposed order SKU",
                "open",
                f"{po['outstanding_units']} units / {po['supplier_name']}",
            )
        )
    for delivery in deliveries[:4]:
        related.append(
            relation(
                "Delivery",
                "invoice",
                delivery["invoice_id"],
                f"Invoice #{delivery['invoice_id']}",
                "Delivery record for this order",
                "confirmed" if delivery["confirmed_delivery_time"] else "pending",
            )
        )

    timeline = [
        timeline_event("Order created", order["order_date"], state="observed"),
        timeline_event("Expected delivery", order["expected_delivery_date"], state="planned"),
    ]
    if order["picking_completed_when"]:
        timeline.append(timeline_event("Picking completed", order["picking_completed_when"]))
    else:
        timeline.append(timeline_event("Picking", None, "Current bottleneck / incomplete", "current"))
    for delivery in deliveries:
        timeline.append(timeline_event("Invoice created", delivery["invoice_date"], f"Invoice #{delivery['invoice_id']}"))
        if delivery["confirmed_delivery_time"]:
            timeline.append(
                timeline_event(
                    "Delivery confirmed",
                    delivery["confirmed_delivery_time"],
                    delivery["confirmed_received_by"],
                )
            )

    result = {
        "generated_at": datetime.now(timezone.utc),
        "entity": {
            "domain": "Fulfillment",
            "entity_type": "order",
            "entity_id": str(order_id),
            "label": f"Order #{order_id}",
        },
        "issue": {
            "code": issue_code,
            "title": issue_title,
            "severity": severity,
            "summary": issue_summary,
        },
        "impact": [
            metric("Customer", order["customer_name"], f"Customer {order['customer_id']}"),
            metric("Order value", float(order["order_value"]), "including tax"),
            metric("Order lines", int(order["line_count"])),
            metric("Units ordered", int(order["units_ordered"])),
            metric("Picking progress", f"{order['picked_lines']} / {order['line_count']} lines"),
            metric("Supply-exposed SKUs", len(risky_skus)),
        ],
        "evidence": [
            metric("Order date", order["order_date"]),
            metric("Expected delivery", order["expected_delivery_date"]),
            metric("Days overdue", days_overdue),
            metric("Backorder reference", order["backorder_order_id"]),
            metric("Critical supply SKUs", len(critical_skus)),
        ],
        "cause": cause,
        "related_records": related,
        "timeline": timeline,
        "supply_evidence": sku_rows,
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/procurement/{purchase_order_id}")
def procurement_workbench(purchase_order_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = business_date(cur)
            cur.execute(
                """
                SELECT
                    p.purchase_order_id,p.supplier_id,
                    coalesce(s.supplier_name,'Supplier '||p.supplier_id::text) AS supplier_name,
                    p.order_date,p.expected_delivery_date,p.is_order_finalized,
                    p.ordered_outers,p.received_outers,p.under_received_line_count,
                    p.last_edited_when,
                    greatest(p.ordered_outers-p.received_outers,0)::bigint AS outstanding_outers
                FROM realtime.current_procurement_state p
                LEFT JOIN core.dim_supplier s
                  ON s.supplier_id=p.supplier_id AND s.is_current
                WHERE p.purchase_order_id=%s
                """,
                (purchase_order_id,),
            )
            po = cur.fetchone()
            if po is None:
                raise HTTPException(status_code=404, detail="Purchase order not found")
            po = dict(po)

            cur.execute(
                INVENTORY_PROJECTION_CTES
                + """
                SELECT
                    f.stock_item_id,
                    coalesce(prod.stock_item_name,'Stock item '||f.stock_item_id::text)
                        AS stock_item_name,
                    f.ordered_outers,f.received_outers,
                    CASE
                        WHEN NOT f.is_order_finalized
                        THEN greatest(f.ordered_outers-f.received_outers,0)::bigint
                        ELSE 0::bigint
                    END AS outstanding_outers,
                    (
                        CASE
                            WHEN NOT f.is_order_finalized
                            THEN greatest(f.ordered_outers-f.received_outers,0)
                            ELSE 0
                        END
                        * CASE
                            WHEN f.ordered_outers > 0
                            THEN f.ordered_quantity::numeric/f.ordered_outers
                            ELSE 0
                          END
                    )::bigint AS outstanding_units,
                    s.quantity_on_hand,s.open_demand_units,s.projected_available,
                    s.pre_inbound_balance,s.coverage_state,s.coverage_severity,
                    s.affected_orders,s.days_of_cover,s.earliest_demand_due
                FROM core.fact_purchase_order_line f
                LEFT JOIN core.dim_product prod
                  ON prod.stock_item_id=f.stock_item_id AND prod.is_current
                LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
                WHERE f.purchase_order_id=%s
                ORDER BY
                    CASE s.coverage_severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    outstanding_units DESC
                """,
                (purchase_order_id,),
            )
            lines = [dict(row) for row in cur.fetchall()]
            risk_lines = (
                []
                if bool(po["is_order_finalized"])
                else [
                    row for row in lines
                    if row.get("coverage_severity") in {"critical", "warning"}
                    and int(row.get("outstanding_units") or 0) > 0
                ]
            )

            supplier_perf_rows = fetch_supplier_performance(
                cur, supplier_id=int(po["supplier_id"])
            )
            supplier_perf = supplier_perf_rows[0] if supplier_perf_rows else None

            cur.execute(
                """
                SELECT max(transaction_occurred_when::date) AS last_receipt_date
                FROM core.fact_inventory_movement
                WHERE purchase_order_id=%s
                  AND quantity>0
                """,
                (purchase_order_id,),
            )
            receipt = dict(cur.fetchone())

            stock_ids = [int(row["stock_item_id"]) for row in risk_lines[:12]]
            affected_orders: list[dict[str, Any]] = []
            if stock_ids:
                cur.execute(
                    """
                    WITH p AS (
                        SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
                        FROM control.source_frontier
                        WHERE source_name='WideWorldImporters'
                    )
                    SELECT DISTINCT
                        o.order_id,o.customer_id,
                        coalesce(c.customer_name,'Customer '||o.customer_id::text) AS customer_name,
                        o.expected_delivery_date,
                        f.stock_item_id
                    FROM core.fact_order_line f
                    JOIN realtime.current_order_state o ON o.order_id=f.order_id
                    CROSS JOIN p
                    LEFT JOIN core.dim_customer c
                      ON c.customer_id=o.customer_id AND c.is_current
                    WHERE f.stock_item_id=ANY(%s)
                      AND f.picking_completed_when IS NULL
                      AND o.picking_completed_when IS NULL
                      AND o.order_date BETWEEN p.as_of-interval '29 days' AND p.as_of
                    ORDER BY o.expected_delivery_date,o.order_id
                    LIMIT 20
                    """,
                    (stock_ids,),
                )
                affected_orders = [dict(row) for row in cur.fetchall()]

    finalized = bool(po["is_order_finalized"])
    days_overdue = (
        max((as_of-po["expected_delivery_date"]).days, 0)
        if po["expected_delivery_date"] is not None and not finalized
        else 0
    )
    if finalized:
        code = "finalized"
        severity = "healthy"
        title = "Purchase order finalized"
        summary = "No active inbound receipt exception remains on this purchase order."
    elif days_overdue > 0:
        code = "overdue"
        severity = "critical" if risk_lines or days_overdue >= 3 else "warning"
        title = f"Inbound PO overdue by {days_overdue} day(s)"
        summary = "Expected receipt date has passed while the purchase order remains open."
    elif risk_lines:
        code = "inbound_supply_risk"
        severity = "warning"
        title = "Inbound supply supports exposed inventory"
        summary = (
            f"{len(risk_lines)} PO line(s) supply SKUs with current coverage exposure."
        )
    else:
        code = "open"
        severity = "healthy"
        title = "Open purchase order"
        summary = "No downstream inventory coverage exception is currently linked to this PO."

    related: list[dict[str, Any]] = []
    for line in risk_lines[:10]:
        related.append(
            relation(
                "Inventory",
                "stock_item",
                line["stock_item_id"],
                line["stock_item_name"],
                "Inbound PO line supports exposed SKU",
                line["coverage_state"],
                f"{line['outstanding_units']} inbound units / projected {line['projected_available']}",
            )
        )
    for order in affected_orders[:10]:
        related.append(
            relation(
                "Fulfillment",
                "order",
                order["order_id"],
                f"Order #{order['order_id']}",
                "Open demand linked through PO SKU",
                "open",
                f"{order['customer_name']} / SKU {order['stock_item_id']}",
            )
        )

    supplier_detail = (
        f"180-day OTIF {supplier_perf['otif_pct']}% / "
        f"{supplier_perf['finalized_po_count']} finalized POs"
        if supplier_perf
        else "No finalized PO history in the 180-day window"
    )

    result = {
        "generated_at": datetime.now(timezone.utc),
        "entity": {
            "domain": "Procurement",
            "entity_type": "purchase_order",
            "entity_id": str(purchase_order_id),
            "label": f"PO #{purchase_order_id}",
        },
        "issue": {
            "code": code,
            "title": title,
            "severity": severity,
            "summary": summary,
        },
        "impact": [
            metric("Supplier", po["supplier_name"]),
            metric("Outstanding outers", int(po["outstanding_outers"])),
            metric("Outstanding lines", int(po["under_received_line_count"])),
            metric("Supply-exposed SKUs", len(risk_lines)),
            metric("Linked open orders", len({row["order_id"] for row in affected_orders})),
        ],
        "evidence": [
            metric("Order date", po["order_date"]),
            metric("Expected delivery", po["expected_delivery_date"]),
            metric("Days overdue", days_overdue),
            metric("Received / ordered", f"{po['received_outers']} / {po['ordered_outers']} outers"),
            metric("Last receipt", receipt.get("last_receipt_date")),
            metric("Supplier OTIF", supplier_perf.get("otif_pct") if supplier_perf else None, supplier_detail),
        ],
        "cause": {
            "classification": code,
            "title": (
                "No active inbound dependency"
                if finalized
                else "Receipt delay overlaps downstream inventory exposure"
                if days_overdue > 0 and risk_lines
                else "Expected receipt date has passed"
                if days_overdue > 0
                else "Current PO lines replenish supply-risk SKUs"
                if risk_lines
                else "No linked inventory coverage exposure"
            ),
            "explanation": summary,
            "basis": (
                "Inbound risk is derived from open PO receipt state and downstream inventory projection. "
                "Finalized POs are not treated as active inbound supply. Supplier OTIF is calculated from "
                "finalized POs and actual positive inventory receipt movements."
            ),
        },
        "related_records": related,
        "timeline": [
            timeline_event("Purchase order created", po["order_date"]),
            timeline_event("Expected receipt", po["expected_delivery_date"], state="planned"),
            timeline_event("Latest recorded receipt", receipt.get("last_receipt_date")),
        ],
        "supplier_performance": supplier_perf,
        "line_risk": lines,
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/delivery/{invoice_id}")
def delivery_workbench(invoice_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = business_date(cur)
            cur.execute(
                """
                SELECT
                    d.invoice_id,d.order_id,d.customer_id,
                    coalesce(c.customer_name,'Customer '||d.customer_id::text) AS customer_name,
                    d.invoice_date,d.confirmed_delivery_time,d.confirmed_received_by,
                    d.delivery_run,d.run_position,d.returned_delivery_data,d.last_edited_when,
                    o.order_date,o.expected_delivery_date,o.picking_completed_when,
                    count(f.order_line_key)::int AS line_count,
                    coalesce(sum(f.quantity),0)::bigint AS units,
                    coalesce(sum(f.total_including_tax),0)::numeric(18,2) AS order_value
                FROM realtime.current_delivery_state d
                LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
                LEFT JOIN core.dim_customer c
                  ON c.customer_id=d.customer_id AND c.is_current
                LEFT JOIN core.fact_order_line f ON f.order_id=d.order_id
                WHERE d.invoice_id=%s
                GROUP BY
                    d.invoice_id,d.order_id,d.customer_id,c.customer_name,d.invoice_date,
                    d.confirmed_delivery_time,d.confirmed_received_by,d.delivery_run,
                    d.run_position,d.returned_delivery_data,d.last_edited_when,
                    o.order_date,o.expected_delivery_date,o.picking_completed_when
                """,
                (invoice_id,),
            )
            delivery = cur.fetchone()
            if delivery is None:
                raise HTTPException(status_code=404, detail="Delivery not found")
            delivery = dict(delivery)

    confirmed = delivery["confirmed_delivery_time"] is not None
    lifecycle_gap_days = (
        (delivery["invoice_date"]-delivery["order_date"]).days
        if delivery["invoice_date"] is not None and delivery["order_date"] is not None
        else None
    )
    lifecycle_coherent = bool(
        lifecycle_gap_days is not None
        and 0 <= lifecycle_gap_days <= DELIVERY_LIFECYCLE_MAX_DAYS
    )
    days_overdue = (
        max((as_of-delivery["expected_delivery_date"]).days, 0)
        if delivery["expected_delivery_date"] is not None and not confirmed
        else 0
    )
    payload_text = str(delivery.get("returned_delivery_data") or "")
    receiver_absent = "Receiver not present" in payload_text
    order_to_pick_days = None
    if delivery["order_date"] and delivery["picking_completed_when"]:
        order_to_pick_days = round(
            (
                delivery["picking_completed_when"]
                - datetime.combine(delivery["order_date"], datetime.min.time())
            ).total_seconds()
            / 86400.0,
            2,
        )
    invoice_to_confirmation_days = None
    if confirmed:
        invoice_to_confirmation_days = round(
            (
                delivery["confirmed_delivery_time"]
                - datetime.combine(delivery["invoice_date"], datetime.min.time())
            ).total_seconds()
            / 86400.0,
            2,
        )

    if confirmed:
        code = "confirmed"
        severity = "healthy"
        title = "Delivery confirmed"
        summary = "The source has a confirmed delivery timestamp."
    elif days_overdue > 0:
        code = "overdue"
        severity = "critical" if days_overdue >= 3 or receiver_absent else "warning"
        title = f"Delivery confirmation overdue by {days_overdue} day(s)"
        summary = "Expected delivery date has passed without source confirmation."
    elif receiver_absent:
        code = "receiver_not_present"
        severity = "warning"
        title = "Receiver-not-present history"
        summary = "The source delivery event history contains a receiver-not-present event."
    else:
        code = "pending"
        severity = "monitoring"
        title = "Delivery confirmation pending"
        summary = "Invoice exists and delivery confirmation is still outstanding within the customer-promise window."

    if receiver_absent and not confirmed:
        cause = {
            "classification": "receiver_not_present",
            "title": "Receiver availability exception",
            "explanation": "Receiver-not-present is recorded in the source delivery event history.",
            "basis": "Direct source-event evidence from ReturnedDeliveryData.",
        }
    elif not confirmed:
        cause = {
            "classification": "confirmation_outstanding",
            "title": "Delivery confirmation outstanding",
            "explanation": "No more specific verified delivery cause is available in the current source fields.",
            "basis": "Direct invoice and confirmation state; no carrier/GPS inference.",
        }
    else:
        cause = {
            "classification": "none",
            "title": "No active delivery exception",
            "explanation": "Delivery is confirmed.",
            "basis": "Direct source confirmation timestamp.",
        }

    related = []
    if delivery["order_id"] is not None:
        related.append(
            relation(
                "Fulfillment",
                "order",
                delivery["order_id"],
                f"Order #{delivery['order_id']}",
                "Source order for this delivery",
                "completed" if delivery["picking_completed_when"] else "open",
            )
        )

    timeline = [
        timeline_event("Order created", delivery["order_date"]),
        timeline_event("Picking completed", delivery["picking_completed_when"]),
        timeline_event("Invoice created", delivery["invoice_date"]),
        timeline_event("Expected delivery", delivery["expected_delivery_date"], state="planned"),
        timeline_event(
            "Delivery confirmed" if confirmed else "Delivery confirmation",
            delivery["confirmed_delivery_time"],
            delivery["confirmed_received_by"] if confirmed else "Pending",
            state="observed" if confirmed else "planned",
        ),
    ]

    events = []
    returned = delivery.get("returned_delivery_data")
    if isinstance(returned, dict) and isinstance(returned.get("Events"), list):
        for event in returned["Events"]:
            if not isinstance(event, dict):
                continue
            events.append(
                timeline_event(
                    str(event.get("Event") or "Source event"),
                    event.get("EventTime"),
                    str(event.get("Comment") or event.get("ConNote") or "") or None,
                )
            )
    timeline.extend(events)

    result = {
        "generated_at": datetime.now(timezone.utc),
        "entity": {
            "domain": "Delivery",
            "entity_type": "invoice",
            "entity_id": str(invoice_id),
            "label": f"Invoice #{invoice_id}",
        },
        "issue": {
            "code": code,
            "title": title,
            "severity": severity,
            "summary": summary,
        },
        "impact": [
            metric("Customer", delivery["customer_name"], f"Customer {delivery['customer_id']}"),
            metric(
                "Order value",
                float(delivery["order_value"]) if int(delivery["line_count"]) > 0 else None,
                "including tax" if int(delivery["line_count"]) > 0 else "Awaiting warehouse line sync",
            ),
            metric(
                "Order lines",
                int(delivery["line_count"]) if int(delivery["line_count"]) > 0 else None,
                None if int(delivery["line_count"]) > 0 else "Awaiting warehouse line sync",
            ),
            metric(
                "Units",
                int(delivery["units"]) if int(delivery["line_count"]) > 0 else None,
                None if int(delivery["line_count"]) > 0 else "Awaiting warehouse line sync",
            ),
            metric("Days overdue", days_overdue),
        ],
        "evidence": [
            metric("Expected delivery", delivery["expected_delivery_date"]),
            metric(
                "Line facts",
                "Available" if int(delivery["line_count"]) > 0 else "Pending",
                "Analytical warehouse line facts" if int(delivery["line_count"]) > 0 else "Header arrived before warehouse line facts",
            ),
            metric("Order to pick", order_to_pick_days, "days; only source-supported stages"),
            metric("Invoice to confirmation", invoice_to_confirmation_days, "days"),
            metric("Receiver-not-present history", receiver_absent),
            metric(
                "Lifecycle coherence",
                lifecycle_coherent,
                f"{lifecycle_gap_days} day invoice-to-order gap; informational quality flag only",
            ),
        ],
        "cause": cause,
        "related_records": related,
        "timeline": timeline,
        "cycle_time": {
            "order_to_pick_days": order_to_pick_days,
            "invoice_to_confirmation_days": invoice_to_confirmation_days,
            "dispatch_stage_available": False,
            "lifecycle_coherent": lifecycle_coherent,
            "lifecycle_gap_days": lifecycle_gap_days,
            "lifecycle_quality_reference_days": DELIVERY_LIFECYCLE_MAX_DAYS,
        },
    }
    return JSONResponse(content=jsonable_encoder(result))
