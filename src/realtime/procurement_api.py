from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from realtime.supply_risk import (
    fetch_po_risks,
    fetch_supplier_inbound_risk,
    fetch_supplier_performance,
)

router = APIRouter(prefix="/api/procurement", tags=["procurement"])


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def get_business_date(cur):
    cur.execute(
        "SELECT safe_through_cutoff FROM control.source_frontier "
        "WHERE source_name='WideWorldImporters'"
    )
    row = cur.fetchone()
    if row is None:
        raise RuntimeError("WideWorldImporters source frontier is not configured")
    return (row["safe_through_cutoff"] - timedelta(days=1)).date()


PROCUREMENT_SELECT = """
    SELECT
        p.purchase_order_id,
        p.supplier_id,
        s.supplier_name,
        p.order_date,
        p.expected_delivery_date,
        p.is_order_finalized,
        p.ordered_outers,
        p.received_outers,
        p.under_received_line_count AS outstanding_line_count,
        p.last_edited_when,
        p.refreshed_at,
        greatest(p.ordered_outers-p.received_outers,0)::bigint AS outstanding_outers,
        CASE
            WHEN NOT p.is_order_finalized
             AND p.expected_delivery_date < %(as_of)s::date THEN 'overdue'
            WHEN NOT p.is_order_finalized
             AND p.expected_delivery_date = %(as_of)s::date THEN 'due_today'
            WHEN NOT p.is_order_finalized THEN 'awaiting_receipt'
            ELSE 'finalized'
        END AS procurement_state,
        CASE
            WHEN NOT p.is_order_finalized
             AND p.expected_delivery_date < %(as_of)s::date
            THEN (%(as_of)s::date-p.expected_delivery_date)::int
            ELSE 0
        END AS days_overdue,
        CASE
            WHEN NOT p.is_order_finalized
             AND p.expected_delivery_date > %(as_of)s::date
            THEN (p.expected_delivery_date-%(as_of)s::date)::int
            ELSE 0
        END AS days_until_due
    FROM realtime.current_procurement_state p
    LEFT JOIN core.dim_supplier s
      ON s.supplier_id=p.supplier_id
     AND s.is_current
"""


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)

            cur.execute(
                """
                WITH scope AS (
                    SELECT *
                    FROM realtime.current_procurement_state
                    WHERE order_date >= %(as_of)s::date - interval '29 days'
                      AND order_date <= %(as_of)s::date
                )
                SELECT
                    count(*)::int AS po_30d,
                    count(*) FILTER (WHERE NOT is_order_finalized)::int AS open_po,
                    count(*) FILTER (WHERE is_order_finalized)::int AS finalized_po,
                    count(*) FILTER (
                        WHERE NOT is_order_finalized
                          AND expected_delivery_date < %(as_of)s::date
                    )::int AS overdue,
                    count(*) FILTER (
                        WHERE NOT is_order_finalized
                          AND expected_delivery_date = %(as_of)s::date
                    )::int AS due_today,
                    count(*) FILTER (
                        WHERE NOT is_order_finalized
                          AND expected_delivery_date > %(as_of)s::date
                    )::int AS upcoming_open,
                    coalesce(sum(ordered_outers),0)::bigint AS ordered_outers,
                    coalesce(sum(received_outers),0)::bigint AS received_outers,
                    coalesce(sum(greatest(ordered_outers-received_outers,0))
                        FILTER (WHERE NOT is_order_finalized),0)::bigint AS outstanding_open_outers,
                    coalesce(sum(under_received_line_count)
                        FILTER (WHERE NOT is_order_finalized),0)::bigint AS outstanding_open_lines,
                    min(expected_delivery_date)
                        FILTER (WHERE NOT is_order_finalized) AS nearest_open_due,
                    count(DISTINCT supplier_id)
                        FILTER (WHERE NOT is_order_finalized)::int AS open_supplier_count,
                    max(last_edited_when) AS latest_state_edit
                FROM scope
                """,
                {"as_of": as_of},
            )
            summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    p.supplier_id,
                    s.supplier_name,
                    count(*)::int AS open_po_count,
                    coalesce(sum(p.ordered_outers),0)::bigint AS ordered_outers,
                    coalesce(sum(p.received_outers),0)::bigint AS received_outers,
                    coalesce(sum(greatest(p.ordered_outers-p.received_outers,0)),0)::bigint
                        AS outstanding_outers,
                    min(p.expected_delivery_date) AS nearest_due
                FROM realtime.current_procurement_state p
                LEFT JOIN core.dim_supplier s
                  ON s.supplier_id=p.supplier_id
                 AND s.is_current
                WHERE p.order_date >= %(as_of)s::date - interval '29 days'
                  AND p.order_date <= %(as_of)s::date
                  AND NOT p.is_order_finalized
                GROUP BY p.supplier_id,s.supplier_name
                ORDER BY outstanding_outers DESC,p.supplier_id
                """,
                {"as_of": as_of},
            )
            open_suppliers = [dict(row) for row in cur.fetchall()]
            supplier_performance = fetch_supplier_performance(cur)
            supplier_inbound_risk = fetch_supplier_inbound_risk(cur)

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
                WHERE r.domain='procurement'
                """
            )
            alert_summary = dict(cur.fetchone())

    ordered = int(summary["ordered_outers"])
    received = int(summary["received_outers"])
    nearest_due = summary["nearest_open_due"]

    performance_by_supplier = {
        int(row["supplier_id"]): row for row in supplier_performance
    }
    risk_by_supplier = {
        int(row["supplier_id"]): row for row in supplier_inbound_risk
    }
    enriched_suppliers = []
    for row in open_suppliers:
        supplier_id = int(row["supplier_id"])
        perf = performance_by_supplier.get(supplier_id, {})
        risk = risk_by_supplier.get(supplier_id, {})
        enriched_suppliers.append({
            **row,
            "otif_pct": perf.get("otif_pct"),
            "avg_delay_days": perf.get("avg_delay_days"),
            "historical_finalized_po_count": int(perf.get("finalized_po_count") or 0),
            "historical_late_po_count": int(perf.get("late_po_count") or 0),
            "at_risk_sku_count": int(risk.get("at_risk_sku_count") or 0),
            "at_risk_units": int(risk.get("at_risk_units") or 0),
            "affected_order_links": int(risk.get("affected_order_links") or 0),
        })

    result = {
        "generated_at": datetime.now(timezone.utc),
        "as_of_date": as_of,
        "lookback_days": 30,
        "kpis": {
            "po_30d": int(summary["po_30d"]),
            "open_po": int(summary["open_po"]),
            "due_today": int(summary["due_today"]),
            "overdue": int(summary["overdue"]),
        },
        "operational_context": {
            "finalized_po": int(summary["finalized_po"]),
            "upcoming_open": int(summary["upcoming_open"]),
            "ordered_outers": ordered,
            "received_outers": received,
            "receipt_rate_pct": round(received / ordered * 100.0, 1) if ordered else 0.0,
            "outstanding_open_outers": int(summary["outstanding_open_outers"]),
            "outstanding_open_lines": int(summary["outstanding_open_lines"]),
            "nearest_open_due": nearest_due,
            "days_to_nearest_due": (
                (nearest_due - as_of).days if nearest_due is not None else None
            ),
            "open_supplier_count": int(summary["open_supplier_count"]),
        },
        "open_suppliers": enriched_suppliers,
        "supplier_performance": supplier_performance,
        "supplier_risk_scope": {
            "performance_window_days": 180,
            "operational_window_days": 30,
            "otif_basis": "finalized PO is on-time when latest positive receipt movement is on/before expected delivery and in-full when received outers >= ordered outers",
            "inbound_risk_basis": "open PO units linked to inventory SKUs with current supply coverage exposure",
        },
        "alert_summary": alert_summary,
        "latest_state_edit": summary["latest_state_edit"],
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/list")
def procurement_list(
    status: str = Query(
        "open",
        pattern="^(all|open|upcoming|finalized|overdue|due_today)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    search: str = Query("", max_length=120),
) -> JSONResponse:
    filters = {
        "all": "TRUE",
        "open": "NOT p.is_order_finalized",
        "upcoming": (
            "NOT p.is_order_finalized "
            "AND p.expected_delivery_date > %(as_of)s::date"
        ),
        "finalized": "p.is_order_finalized",
        "overdue": (
            "NOT p.is_order_finalized "
            "AND p.expected_delivery_date < %(as_of)s::date"
        ),
        "due_today": (
            "NOT p.is_order_finalized "
            "AND p.expected_delivery_date = %(as_of)s::date"
        ),
    }

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)
            params: dict[str, Any] = {
                "as_of": as_of,
                "page_size": page_size,
                "offset": (page - 1) * page_size,
            }
            conditions = [
                filters[status],
                "p.order_date >= %(as_of)s::date - interval '29 days'",
                "p.order_date <= %(as_of)s::date",
            ]

            if search.strip():
                params["search"] = f"%{search.strip()}%"
                conditions.append(
                    "(p.purchase_order_id::text ILIKE %(search)s "
                    "OR p.supplier_id::text ILIKE %(search)s "
                    "OR coalesce(s.supplier_name,'') ILIKE %(search)s)"
                )

            where_sql = " AND ".join(conditions)

            cur.execute(
                f"""
                SELECT count(*)::int AS total
                FROM realtime.current_procurement_state p
                LEFT JOIN core.dim_supplier s
                  ON s.supplier_id=p.supplier_id
                 AND s.is_current
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()["total"])

            cur.execute(
                PROCUREMENT_SELECT
                + f"""
                WHERE {where_sql}
                ORDER BY
                    CASE
                        WHEN NOT p.is_order_finalized
                         AND p.expected_delivery_date < %(as_of)s::date THEN 0
                        WHEN NOT p.is_order_finalized
                         AND p.expected_delivery_date = %(as_of)s::date THEN 1
                        WHEN NOT p.is_order_finalized THEN 2
                        ELSE 3
                    END,
                    CASE
                        WHEN NOT p.is_order_finalized THEN p.expected_delivery_date
                    END ASC NULLS LAST,
                    p.order_date DESC,
                    p.purchase_order_id DESC
                LIMIT %(page_size)s OFFSET %(offset)s
                """,
                params,
            )
            rows = [dict(row) for row in cur.fetchall()]
            po_risks = fetch_po_risks(
                cur,
                [int(row["purchase_order_id"]) for row in rows],
            )
            supplier_perf_rows = fetch_supplier_performance(cur)
            supplier_perf_map = {
                int(item["supplier_id"]): item
                for item in supplier_perf_rows
            }
            for row in rows:
                risk = po_risks.get(int(row["purchase_order_id"]), {})
                perf = supplier_perf_map.get(int(row["supplier_id"]), {})
                row["at_risk_sku_count"] = int(risk.get("at_risk_sku_count") or 0)
                row["at_risk_units"] = int(risk.get("at_risk_units") or 0)
                row["affected_order_links"] = int(risk.get("affected_order_links") or 0)
                row["supplier_otif_pct"] = perf.get("otif_pct")
                row["supplier_avg_delay_days"] = perf.get("avg_delay_days")

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


@router.get("/{purchase_order_id}")
def procurement_detail(purchase_order_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)

            cur.execute(
                PROCUREMENT_SELECT
                + " WHERE p.purchase_order_id=%(purchase_order_id)s",
                {"as_of": as_of, "purchase_order_id": purchase_order_id},
            )
            row = cur.fetchone()

            if row is None:
                raise HTTPException(status_code=404, detail="Purchase order not found")

            cur.execute(
                """
                SELECT
                    f.purchase_order_line_key,
                    f.stock_item_id,
                    coalesce(prod.stock_item_name,'Stock item '||f.stock_item_id::text)
                        AS stock_item_name,
                    f.package_name,
                    f.ordered_outers,
                    f.ordered_quantity,
                    f.received_outers,
                    greatest(f.ordered_outers-f.received_outers,0)::bigint
                        AS outstanding_outers,
                    f.is_order_finalized,
                    f.last_modified_when
                FROM core.fact_purchase_order_line f
                LEFT JOIN core.dim_product prod
                  ON prod.stock_item_id=f.stock_item_id
                 AND prod.is_current
                WHERE f.purchase_order_id=%s
                ORDER BY
                    greatest(f.ordered_outers-f.received_outers,0) DESC,
                    f.stock_item_id
                """,
                (purchase_order_id,),
            )
            lines = [dict(item) for item in cur.fetchall()]
            po_risk = fetch_po_risks(cur, [purchase_order_id]).get(
                purchase_order_id,
                {},
            )
            supplier_perf_rows = fetch_supplier_performance(
                cur,
                supplier_id=int(row["supplier_id"]),
            )
            supplier_performance = (
                supplier_perf_rows[0] if supplier_perf_rows else None
            )

    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "as_of_date": as_of,
                "purchase_order": {
                    **dict(row),
                    "at_risk_sku_count": int(po_risk.get("at_risk_sku_count") or 0),
                    "at_risk_units": int(po_risk.get("at_risk_units") or 0),
                    "affected_order_links": int(po_risk.get("affected_order_links") or 0),
                    "supplier_otif_pct": (
                        supplier_performance.get("otif_pct")
                        if supplier_performance else None
                    ),
                    "supplier_avg_delay_days": (
                        supplier_performance.get("avg_delay_days")
                        if supplier_performance else None
                    ),
                },
                "lines": lines,
                "supplier_performance": supplier_performance,
            }
        )
    )
