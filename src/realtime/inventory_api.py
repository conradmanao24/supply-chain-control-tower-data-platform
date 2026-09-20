from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from realtime.supply_risk import INVENTORY_PROJECTION_CTES

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


INVENTORY_SELECT = """
    SELECT
        stock_item_id,
        stock_item_name,
        quantity_on_hand,
        last_stocktake_quantity,
        reorder_level,
        typical_order_quantity,
        last_edited_when,
        refreshed_at,
        CASE
            WHEN quantity_on_hand < 0 THEN 'negative'
            WHEN quantity_on_hand = 0 THEN 'out_of_stock'
            WHEN quantity_on_hand <= reorder_level THEN 'reorder'
            ELSE 'healthy'
        END AS stock_state,
        greatest(reorder_level-quantity_on_hand,0)::bigint AS below_reorder_by,
        (quantity_on_hand-last_stocktake_quantity)::bigint AS stocktake_delta,
        open_demand_units,
        demand_before_inbound_units,
        incoming_units,
        affected_orders,
        earliest_demand_due,
        next_inbound_date,
        inbound_po_count,
        outbound_units_30d,
        days_of_cover,
        days_to_next_inbound,
        pre_inbound_balance,
        projected_available,
        pre_inbound_shortfall_units,
        projected_shortfall_units,
        coverage_state,
        coverage_severity
    FROM scored
"""


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                INVENTORY_PROJECTION_CTES
                + """
                SELECT
                    count(*)::int AS total_items,
                    count(*) FILTER (WHERE quantity_on_hand < 0)::int AS negative_stock,
                    count(*) FILTER (WHERE quantity_on_hand = 0)::int AS out_of_stock,
                    count(*) FILTER (
                        WHERE quantity_on_hand >= 0
                          AND quantity_on_hand <= reorder_level
                    )::int AS reorder_required,
                    count(*) FILTER (
                        WHERE quantity_on_hand > 0
                          AND quantity_on_hand <= reorder_level
                    )::int AS reorder_positive,
                    count(*) FILTER (
                        WHERE quantity_on_hand > reorder_level
                    )::int AS above_reorder,
                    count(*) FILTER (
                        WHERE coverage_state IN (
                            'negative_stock',
                            'projected_shortfall',
                            'stockout_before_inbound',
                            'coverage_gap'
                        )
                    )::int AS supply_risk_items,
                    count(*) FILTER (
                        WHERE coverage_severity='critical'
                    )::int AS critical_supply_risk_items,
                    coalesce(sum(quantity_on_hand),0)::bigint AS units_on_hand,
                    coalesce(sum(open_demand_units),0)::bigint AS open_demand_units,
                    coalesce(sum(incoming_units),0)::bigint AS incoming_units,
                    coalesce(sum(pre_inbound_shortfall_units),0)::bigint
                        AS pre_inbound_shortfall_units,
                    coalesce(sum(projected_shortfall_units),0)::bigint
                        AS projected_shortfall_units,
                    coalesce(sum(
                        greatest(reorder_level-quantity_on_hand,0)
                    ) FILTER (
                        WHERE quantity_on_hand >= 0
                          AND quantity_on_hand <= reorder_level
                    ),0)::bigint AS total_below_reorder_by,
                    coalesce(sum(typical_order_quantity) FILTER (
                        WHERE quantity_on_hand >= 0
                          AND quantity_on_hand <= reorder_level
                    ),0)::bigint AS typical_order_qty_flagged,
                    max(last_edited_when) AS latest_state_edit
                FROM scored
                """
            )
            summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged')
                    )::int AS active,
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged')
                          AND a.severity='critical'
                    )::int AS critical,
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged')
                          AND a.severity='warning'
                    )::int AS warning,
                    count(*) FILTER (
                        WHERE a.status IN ('open','acknowledged')
                          AND a.severity='info'
                    )::int AS info
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE r.domain='inventory'
                """
            )
            alert_summary = dict(cur.fetchone())

    result = {
        "generated_at": datetime.now(timezone.utc),
        "kpis": {
            "total_items": int(summary["total_items"]),
            "reorder_required": int(summary["reorder_required"]),
            "out_of_stock": int(summary["out_of_stock"]),
            "negative_stock": int(summary["negative_stock"]),
            "supply_risk_items": int(summary["supply_risk_items"]),
            "critical_supply_risk_items": int(summary["critical_supply_risk_items"]),
        },
        "stock_health": [
            {"state": "negative", "value": int(summary["negative_stock"])},
            {"state": "out_of_stock", "value": int(summary["out_of_stock"])},
            {"state": "reorder", "value": int(summary["reorder_positive"])},
            {"state": "healthy", "value": int(summary["above_reorder"])},
        ],
        "operational_context": {
            "units_on_hand": int(summary["units_on_hand"]),
            "above_reorder": int(summary["above_reorder"]),
            "total_below_reorder_by": int(summary["total_below_reorder_by"]),
            "typical_order_qty_flagged": int(summary["typical_order_qty_flagged"]),
            "open_demand_units": int(summary["open_demand_units"]),
            "incoming_units": int(summary["incoming_units"]),
            "pre_inbound_shortfall_units": int(summary["pre_inbound_shortfall_units"]),
            "projected_shortfall_units": int(summary["projected_shortfall_units"]),
        },
        "projection_scope": {
            "operational_window_days": 30,
            "demand_basis": "unpicked order-line units in current 30-day operational window",
            "inbound_basis": "remaining units on open purchase-order lines in current 30-day operational window",
            "velocity_basis": "actual customer-linked outbound inventory movement over 30 days",
        },
        "alert_summary": alert_summary,
        "latest_state_edit": summary["latest_state_edit"],
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/list")
def inventory_list(
    status: str = Query(
        "risk",
        pattern="^(all|risk|negative|out_of_stock|reorder|healthy)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    search: str = Query("", max_length=120),
) -> JSONResponse:
    filters = {
        "all": "TRUE",
        "risk": (
            "coverage_state IN ("
            "'negative_stock','projected_shortfall',"
            "'stockout_before_inbound','coverage_gap'"
            ")"
        ),
        "negative": "quantity_on_hand < 0",
        "out_of_stock": "quantity_on_hand = 0",
        "reorder": (
            "quantity_on_hand >= 0 "
            "AND quantity_on_hand <= reorder_level"
        ),
        "healthy": "quantity_on_hand > reorder_level",
    }

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            params: dict[str, Any] = {
                "page_size": page_size,
                "offset": (page - 1) * page_size,
            }
            conditions = [filters[status]]

            if search.strip():
                params["search"] = f"%{search.strip()}%"
                conditions.append(
                    "(stock_item_id::text ILIKE %(search)s "
                    "OR stock_item_name ILIKE %(search)s)"
                )

            where_sql = " AND ".join(conditions)

            cur.execute(
                INVENTORY_PROJECTION_CTES
                + f"""
                SELECT count(*)::int AS total
                FROM scored
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()["total"])

            cur.execute(
                INVENTORY_PROJECTION_CTES
                + INVENTORY_SELECT
                + f"""
                WHERE {where_sql}
                ORDER BY
                    CASE coverage_severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    pre_inbound_shortfall_units DESC,
                    projected_shortfall_units DESC,
                    days_of_cover ASC NULLS LAST,
                    stock_item_id
                LIMIT %(page_size)s OFFSET %(offset)s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "status": status,
                "search": search,
                "count": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "items": rows,
            }
        )
    )


@router.get("/{stock_item_id}")
def inventory_detail(stock_item_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                INVENTORY_PROJECTION_CTES
                + INVENTORY_SELECT
                + " WHERE stock_item_id=%s",
                (stock_item_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Stock item not found")

    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "item": dict(row),
            }
        )
    )
