from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from realtime.supply_risk import fetch_order_supply_risks

router = APIRouter(prefix="/api/fulfillment", tags=["fulfillment"])


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def get_business_date(cur) -> tuple[datetime, Any]:
    cur.execute(
        "SELECT safe_through_cutoff FROM control.source_frontier "
        "WHERE source_name='WideWorldImporters'"
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("WideWorldImporters source frontier is not configured")
    frontier = row["safe_through_cutoff"]
    return frontier, (frontier - timedelta(days=1)).date()


LINE_AGG = """
    SELECT
        order_id,
        count(*)::int AS line_count,
        coalesce(sum(quantity),0)::bigint AS units_ordered,
        coalesce(sum(total_including_tax),0)::numeric(18,2) AS order_value,
        count(*) FILTER (WHERE picking_completed_when IS NOT NULL)::int AS picked_lines
    FROM core.fact_order_line
    GROUP BY order_id
"""


BASE_SELECT = f"""
    SELECT
        o.order_id,
        o.customer_id,
        coalesce(c.customer_name,'Customer '||o.customer_id::text) AS customer_name,
        o.order_date,
        o.expected_delivery_date,
        o.is_undersupply_backordered,
        o.backorder_order_id,
        o.picking_completed_when,
        o.last_edited_when,
        o.refreshed_at,
        coalesce(a.line_count,0)::int AS line_count,
        coalesce(a.units_ordered,0)::bigint AS units_ordered,
        coalesce(a.order_value,0)::numeric(18,2) AS order_value,
        coalesce(a.picked_lines,0)::int AS picked_lines,
        CASE
            WHEN o.picking_completed_when IS NOT NULL THEN 'completed'
            WHEN o.expected_delivery_date < %(as_of)s::date THEN 'overdue'
            WHEN o.expected_delivery_date = %(as_of)s::date THEN 'due_today'
            ELSE 'upcoming'
        END AS risk_state,
        greatest((%(as_of)s::date-o.expected_delivery_date),0)::int AS days_overdue,
        (o.picking_completed_when IS NULL AND o.backorder_order_id IS NOT NULL) AS active_backorder
    FROM realtime.current_order_state o
    LEFT JOIN staging.customer_current c ON c.customer_id=o.customer_id
    LEFT JOIN ({LINE_AGG}) a ON a.order_id=o.order_id
"""


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _, as_of_date = get_business_date(cur)

            cur.execute(
                """
                WITH scope AS (
                    SELECT *
                    FROM realtime.current_order_state
                    WHERE order_date >= %(as_of)s::date - INTERVAL '30 days'
                      AND order_date <= %(as_of)s::date
                )
                SELECT
                    count(*)::int AS orders_in_window,
                    count(*) FILTER (WHERE picking_completed_when IS NULL)::int AS open_orders,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND expected_delivery_date < %(as_of)s::date
                    )::int AS overdue_orders,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND expected_delivery_date = %(as_of)s::date
                    )::int AS due_today,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND expected_delivery_date > %(as_of)s::date
                    )::int AS upcoming_open,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND backorder_order_id IS NOT NULL
                    )::int AS backorders,
                    count(*) FILTER (WHERE picking_completed_when IS NOT NULL)::int AS completed_orders
                FROM scope
                """,
                {"as_of": as_of_date},
            )
            kpis = dict(cur.fetchone())

            cur.execute(
                """
                WITH overdue AS (
                    SELECT (%(as_of)s::date - expected_delivery_date)::int AS days_overdue
                    FROM realtime.current_order_state
                    WHERE order_date >= %(as_of)s::date - INTERVAL '30 days'
                      AND order_date <= %(as_of)s::date
                      AND picking_completed_when IS NULL
                      AND expected_delivery_date < %(as_of)s::date
                )
                SELECT
                    coalesce(max(days_overdue),0)::int AS oldest_days_overdue,
                    coalesce(
                        percentile_disc(0.5) WITHIN GROUP (ORDER BY days_overdue),
                        0
                    )::int AS median_days_overdue
                FROM overdue
                """,
                {"as_of": as_of_date},
            )
            exposure = dict(cur.fetchone())

            cur.execute(
                """
                WITH scope AS (
                    SELECT (%(as_of)s::date - expected_delivery_date)::int AS days_overdue
                    FROM realtime.current_order_state
                    WHERE order_date >= %(as_of)s::date - INTERVAL '30 days'
                      AND order_date <= %(as_of)s::date
                      AND picking_completed_when IS NULL
                      AND expected_delivery_date < %(as_of)s::date
                )
                SELECT bucket, count(*)::int AS value
                FROM (
                    SELECT CASE
                        WHEN days_overdue <= 2 THEN '1-2 days'
                        WHEN days_overdue <= 7 THEN '3-7 days'
                        WHEN days_overdue <= 14 THEN '8-14 days'
                        ELSE '15+ days'
                    END AS bucket
                    FROM scope
                ) x
                GROUP BY bucket
                ORDER BY CASE bucket
                    WHEN '1-2 days' THEN 1
                    WHEN '3-7 days' THEN 2
                    WHEN '8-14 days' THEN 3
                    ELSE 4
                END
                """,
                {"as_of": as_of_date},
            )
            aging = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT order_id
                FROM realtime.current_order_state
                WHERE order_date >= %(as_of)s::date - interval '29 days'
                  AND order_date <= %(as_of)s::date
                  AND picking_completed_when IS NULL
                ORDER BY order_id
                """,
                {"as_of": as_of_date},
            )
            open_order_ids = [int(row["order_id"]) for row in cur.fetchall()]
            open_order_risks = fetch_order_supply_risks(cur, open_order_ids)
            supply_exposed_orders = sum(
                1
                for risk in open_order_risks.values()
                if int(risk.get("supply_exposed_sku_count") or 0) > 0
            )
            critical_supply_orders = sum(
                1
                for risk in open_order_risks.values()
                if int(risk.get("critical_supply_sku_count") or 0) > 0
            )

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
                WHERE r.domain='fulfillment'
                """
            )
            alert_summary = dict(cur.fetchone())

    open_orders = int(kpis["open_orders"])
    overdue_orders = int(kpis["overdue_orders"])
    overdue_rate = round((overdue_orders / open_orders * 100.0), 1) if open_orders else 0.0

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc),
        "as_of_date": as_of_date,
        "lookback_days": 30,
        "kpis": kpis,
        "operational_context": {
            "overdue_rate": overdue_rate,
            "oldest_days_overdue": int(exposure["oldest_days_overdue"]),
            "median_days_overdue": int(exposure["median_days_overdue"]),
            "upcoming_open": int(kpis["upcoming_open"]),
            "completed_orders": int(kpis["completed_orders"]),
            "supply_exposed_orders": supply_exposed_orders,
            "critical_supply_orders": critical_supply_orders,
        },
        "aging": aging,
        "alert_summary": alert_summary,
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/list")
def fulfillment_list(
    status: str = Query(
        "open",
        pattern="^(all|open|upcoming|completed|overdue|overdue_1_2|overdue_3_7|overdue_8_14|overdue_15_plus|due_today|backorder)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    search: str = Query("", max_length=120),
) -> JSONResponse:
    filters = {
        "all": "TRUE",
        "open": "o.picking_completed_when IS NULL",
        "upcoming": (
            "o.picking_completed_when IS NULL "
            "AND o.expected_delivery_date > %(as_of)s::date"
        ),
        "completed": "o.picking_completed_when IS NOT NULL",
        "overdue": (
            "o.picking_completed_when IS NULL "
            "AND o.expected_delivery_date < %(as_of)s::date"
        ),
        "overdue_1_2": (
            "o.picking_completed_when IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 1 AND 2"
        ),
        "overdue_3_7": (
            "o.picking_completed_when IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 3 AND 7"
        ),
        "overdue_8_14": (
            "o.picking_completed_when IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 8 AND 14"
        ),
        "overdue_15_plus": (
            "o.picking_completed_when IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) >= 15"
        ),
        "due_today": (
            "o.picking_completed_when IS NULL "
            "AND o.expected_delivery_date = %(as_of)s::date"
        ),
        "backorder": (
            "o.picking_completed_when IS NULL "
            "AND o.backorder_order_id IS NOT NULL"
        ),
    }

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _, as_of = get_business_date(cur)
            conditions = [
                filters[status],
                "o.order_date >= %(as_of)s::date - interval '30 days'",
                "o.order_date <= %(as_of)s::date",
            ]
            params: dict[str, Any] = {
                "as_of": as_of,
                "page_size": page_size,
                "offset": (page - 1) * page_size,
            }

            if search.strip():
                params["search"] = f"%{search.strip()}%"
                conditions.append(
                    "(o.order_id::text ILIKE %(search)s "
                    "OR o.customer_id::text ILIKE %(search)s "
                    "OR coalesce(c.customer_name,'') ILIKE %(search)s)"
                )

            where_sql = " AND ".join(conditions)

            cur.execute(
                f"""
                SELECT count(*)::int AS total
                FROM realtime.current_order_state o
                LEFT JOIN staging.customer_current c ON c.customer_id=o.customer_id
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()["total"])

            cur.execute(
                f"""
                WITH selected AS (
                    SELECT
                        o.order_id,
                        o.customer_id,
                        coalesce(c.customer_name,'Customer '||o.customer_id::text) AS customer_name,
                        o.order_date,
                        o.expected_delivery_date,
                        o.is_undersupply_backordered,
                        o.backorder_order_id,
                        o.picking_completed_when,
                        o.last_edited_when,
                        o.refreshed_at,
                        CASE
                            WHEN o.picking_completed_when IS NOT NULL THEN 'completed'
                            WHEN o.expected_delivery_date < %(as_of)s::date THEN 'overdue'
                            WHEN o.expected_delivery_date = %(as_of)s::date THEN 'due_today'
                            ELSE 'upcoming'
                        END AS risk_state,
                        greatest((%(as_of)s::date-o.expected_delivery_date),0)::int AS days_overdue,
                        (o.picking_completed_when IS NULL AND o.backorder_order_id IS NOT NULL) AS active_backorder,
                        CASE
                            WHEN o.picking_completed_when IS NULL
                             AND o.expected_delivery_date < %(as_of)s::date THEN 0
                            WHEN o.picking_completed_when IS NULL
                             AND o.expected_delivery_date = %(as_of)s::date THEN 1
                            WHEN o.picking_completed_when IS NULL THEN 2
                            ELSE 3
                        END AS sort_rank,
                        CASE
                            WHEN o.picking_completed_when IS NULL
                             AND o.expected_delivery_date < %(as_of)s::date
                            THEN o.expected_delivery_date
                        END AS sort_due
                    FROM realtime.current_order_state o
                    LEFT JOIN staging.customer_current c ON c.customer_id=o.customer_id
                    WHERE {where_sql}
                    ORDER BY sort_rank, sort_due ASC NULLS LAST, o.order_date DESC, o.order_id DESC
                    LIMIT %(page_size)s OFFSET %(offset)s
                )
                SELECT
                    s.order_id, s.customer_id, s.customer_name, s.order_date,
                    s.expected_delivery_date, s.is_undersupply_backordered,
                    s.backorder_order_id, s.picking_completed_when, s.last_edited_when,
                    s.refreshed_at, s.risk_state, s.days_overdue, s.active_backorder,
                    coalesce(a.line_count,0)::int AS line_count,
                    coalesce(a.units_ordered,0)::bigint AS units_ordered,
                    coalesce(a.order_value,0)::numeric(18,2) AS order_value,
                    coalesce(a.picked_lines,0)::int AS picked_lines
                FROM selected s
                LEFT JOIN LATERAL (
                    SELECT
                        count(*)::int AS line_count,
                        coalesce(sum(f.quantity),0)::bigint AS units_ordered,
                        coalesce(sum(f.total_including_tax),0)::numeric(18,2) AS order_value,
                        count(*) FILTER (WHERE f.picking_completed_when IS NOT NULL)::int AS picked_lines
                    FROM core.fact_order_line f
                    WHERE f.order_id=s.order_id
                ) a ON true
                ORDER BY s.sort_rank, s.sort_due ASC NULLS LAST, s.order_date DESC, s.order_id DESC
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
            order_risks = fetch_order_supply_risks(
                cur,
                [int(row["order_id"]) for row in rows],
            )
            for row in rows:
                risk = order_risks.get(int(row["order_id"]), {})
                exposed = int(risk.get("supply_exposed_sku_count") or 0)
                critical_supply = int(risk.get("critical_supply_sku_count") or 0)
                row["supply_exposed_sku_count"] = exposed
                row["critical_supply_sku_count"] = critical_supply
                row["linked_pre_inbound_shortfall_units"] = int(
                    risk.get("linked_pre_inbound_shortfall_units") or 0
                )
                row["minimum_days_of_cover"] = risk.get("minimum_days_of_cover")
                if (
                    critical_supply > 0
                    or row["active_backorder"]
                    or (
                        row["risk_state"] == "overdue"
                        and int(row["days_overdue"]) >= 7
                    )
                ):
                    row["exception_priority"] = "high"
                elif (
                    exposed > 0
                    or row["risk_state"] in {"overdue", "due_today"}
                ):
                    row["exception_priority"] = "medium"
                else:
                    row["exception_priority"] = "low"

    total_pages = max(1, (total + page_size - 1) // page_size)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "as_of_date": as_of,
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


@router.get("/{order_id}")
def fulfillment_detail(order_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            _, as_of = get_business_date(cur)
            cur.execute(
                BASE_SELECT + " WHERE o.order_id=%(order_id)s",
                {"as_of": as_of, "order_id": order_id},
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail="Order not found")

            cur.execute(
                """
                SELECT
                    order_line_key,
                    stock_item_id,
                    description,
                    package_name,
                    quantity,
                    unit_price,
                    total_excluding_tax,
                    tax_amount,
                    total_including_tax,
                    picking_completed_when
                FROM core.fact_order_line
                WHERE order_id=%s
                ORDER BY order_line_key
                """,
                (order_id,),
            )
            lines = [dict(item) for item in cur.fetchall()]
            risk = fetch_order_supply_risks(cur, [order_id]).get(order_id, {})
            row = dict(row)
            row["supply_exposed_sku_count"] = int(
                risk.get("supply_exposed_sku_count") or 0
            )
            row["critical_supply_sku_count"] = int(
                risk.get("critical_supply_sku_count") or 0
            )
            row["linked_pre_inbound_shortfall_units"] = int(
                risk.get("linked_pre_inbound_shortfall_units") or 0
            )
            row["minimum_days_of_cover"] = risk.get("minimum_days_of_cover")
            if (
                row["critical_supply_sku_count"] > 0
                or row["active_backorder"]
                or (
                    row["risk_state"] == "overdue"
                    and int(row["days_overdue"]) >= 7
                )
            ):
                row["exception_priority"] = "high"
            elif (
                row["supply_exposed_sku_count"] > 0
                or row["risk_state"] in {"overdue", "due_today"}
            ):
                row["exception_priority"] = "medium"
            else:
                row["exception_priority"] = "low"

    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "as_of_date": as_of,
                "order": dict(row),
                "lines": lines,
            }
        )
    )
