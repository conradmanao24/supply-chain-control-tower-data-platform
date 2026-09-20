from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

ALLOWED_LOOKBACKS = {30, 90, 365}


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def pct_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return round(100.0 * (current - prior) / abs(prior), 2)


def receipt_rate(received: int, ordered: int) -> float:
    if ordered <= 0:
        return 0.0
    return round(100.0 * received / ordered, 2)


@router.get("/overview")
def overview(
    lookback_days: int = Query(30, description="Analytical lookback window in days"),
) -> JSONResponse:
    if lookback_days not in ALLOWED_LOOKBACKS:
        lookback_days = 30

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT safe_through_cutoff::date AS frontier_cutoff
                FROM control.source_frontier
                WHERE source_name='WideWorldImporters'
                """
            )
            frontier = cur.fetchone()
            frontier_cutoff = frontier["frontier_cutoff"] if frontier else None
            as_of_date: date | None = (
                frontier_cutoff - timedelta(days=1)
                if frontier_cutoff is not None
                else None
            )

            cur.execute(
                """
                WITH f AS (
                    SELECT (safe_through_cutoff::date - 1) AS d
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                ),
                ranges AS (
                    SELECT
                        d,
                        d - (%s::int - 1) AS current_start,
                        d - %s::int AS prior_end,
                        d - (2 * %s::int - 1) AS prior_start
                    FROM f
                )
                SELECT
                    count(DISTINCT s.invoice_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    )::int AS invoices_current,
                    count(DISTINCT s.order_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    )::int AS orders_current,
                    coalesce(sum(s.quantity) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    ),0)::bigint AS units_current,
                    coalesce(sum(s.total_including_tax) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    ),0)::numeric(18,2) AS revenue_current,
                    coalesce(sum(s.profit) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    ),0)::numeric(18,2) AS profit_current,

                    count(DISTINCT s.invoice_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    )::int AS invoices_prior,
                    count(DISTINCT s.order_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    )::int AS orders_prior,
                    coalesce(sum(s.quantity) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    ),0)::bigint AS units_prior,
                    coalesce(sum(s.total_including_tax) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    ),0)::numeric(18,2) AS revenue_prior,
                    coalesce(sum(s.profit) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    ),0)::numeric(18,2) AS profit_prior
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                CROSS JOIN ranges r
                WHERE d.calendar_date BETWEEN r.prior_start AND r.d
                """,
                (lookback_days, lookback_days, lookback_days),
            )
            sales = dict(cur.fetchone())

            current_revenue = float(sales["revenue_current"])
            current_profit = float(sales["profit_current"])
            prior_revenue = float(sales["revenue_prior"])
            prior_profit = float(sales["profit_prior"])
            current_margin = (
                round(100.0 * current_profit / current_revenue, 2)
                if current_revenue > 0
                else 0.0
            )
            prior_margin = (
                round(100.0 * prior_profit / prior_revenue, 2)
                if prior_revenue > 0
                else 0.0
            )

            if lookback_days == 30:
                trend_granularity = "day"
                bucket_expr = "d.calendar_date"
            elif lookback_days == 90:
                trend_granularity = "week"
                bucket_expr = "date_trunc('week', d.calendar_date)::date"
            else:
                trend_granularity = "month"
                bucket_expr = "date_trunc('month', d.calendar_date)::date"

            trend_sql = f"""
                WITH f AS (
                    SELECT (safe_through_cutoff::date - 1) AS d
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                )
                SELECT
                    {bucket_expr} AS bucket_start,
                    coalesce(sum(s.total_including_tax),0)::numeric(18,2) AS revenue,
                    coalesce(sum(s.profit),0)::numeric(18,2) AS profit,
                    count(DISTINCT s.invoice_id)::int AS invoices
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                CROSS JOIN f
                WHERE d.calendar_date BETWEEN f.d - (%s::int - 1) AND f.d
                GROUP BY 1
                ORDER BY 1
            """
            cur.execute(trend_sql, (lookback_days,))
            trend = [dict(row) for row in cur.fetchall()]
            if as_of_date is not None:
                trend = _fill_trend_buckets(
                    trend,
                    trend_granularity,
                    as_of_date - timedelta(days=lookback_days - 1),
                    as_of_date,
                    {"revenue": 0, "profit": 0, "invoices": 0},
                )

            cur.execute(
                """
                WITH f AS (
                    SELECT (safe_through_cutoff::date - 1) AS d
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                )
                SELECT
                    c.customer_id,
                    c.customer_name,
                    coalesce(sum(s.total_including_tax),0)::numeric(18,2) AS revenue,
                    coalesce(sum(s.profit),0)::numeric(18,2) AS profit,
                    count(DISTINCT s.invoice_id)::int AS invoices
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                JOIN core.dim_customer c ON c.customer_key=s.customer_key
                CROSS JOIN f
                WHERE d.calendar_date BETWEEN f.d - (%s::int - 1) AND f.d
                GROUP BY c.customer_id,c.customer_name
                ORDER BY revenue DESC
                LIMIT 8
                """,
                (lookback_days,),
            )
            top_customers = [dict(row) for row in cur.fetchall()]
            for row in top_customers:
                revenue = float(row["revenue"])
                row["revenue_share_pct"] = (
                    round(100.0 * revenue / current_revenue, 2)
                    if current_revenue > 0
                    else 0.0
                )

            top5_share_pct = round(
                sum(float(row["revenue"]) for row in top_customers[:5])
                * 100.0
                / current_revenue,
                2,
            ) if current_revenue > 0 else 0.0

            cur.execute(
                """
                WITH f AS (
                    SELECT (safe_through_cutoff::date - 1) AS d
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                )
                SELECT
                    p.stock_item_id,
                    p.stock_item_name,
                    coalesce(sum(s.total_including_tax),0)::numeric(18,2) AS revenue,
                    coalesce(sum(s.profit),0)::numeric(18,2) AS profit,
                    coalesce(sum(s.quantity),0)::bigint AS units
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                JOIN core.dim_product p ON p.product_key=s.product_key
                CROSS JOIN f
                WHERE d.calendar_date BETWEEN f.d - (%s::int - 1) AND f.d
                GROUP BY p.stock_item_id,p.stock_item_name
                ORDER BY revenue DESC
                LIMIT 8
                """,
                (lookback_days,),
            )
            top_products = [dict(row) for row in cur.fetchall()]
            for row in top_products:
                revenue = float(row["revenue"])
                row["revenue_share_pct"] = (
                    round(100.0 * revenue / current_revenue, 2)
                    if current_revenue > 0
                    else 0.0
                )

            cur.execute(
                """
                WITH f AS (
                    SELECT (safe_through_cutoff::date - 1) AS d
                    FROM control.source_frontier
                    WHERE source_name='WideWorldImporters'
                ),
                ranges AS (
                    SELECT
                        d,
                        d - (%s::int - 1) AS current_start,
                        d - %s::int AS prior_end,
                        d - (2 * %s::int - 1) AS prior_start
                    FROM f
                )
                SELECT
                    coalesce(sum(p.ordered_outers) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    ),0)::bigint AS ordered_current,
                    coalesce(sum(p.received_outers) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    ),0)::bigint AS received_current,
                    count(DISTINCT p.purchase_order_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.current_start AND r.d
                    )::int AS po_current,

                    coalesce(sum(p.ordered_outers) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    ),0)::bigint AS ordered_prior,
                    coalesce(sum(p.received_outers) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    ),0)::bigint AS received_prior,
                    count(DISTINCT p.purchase_order_id) FILTER (
                        WHERE d.calendar_date BETWEEN r.prior_start AND r.prior_end
                    )::int AS po_prior
                FROM core.fact_purchase_order_line p
                JOIN core.dim_date d ON d.date_key=p.order_date_key
                CROSS JOIN ranges r
                WHERE d.calendar_date BETWEEN r.prior_start AND r.d
                """,
                (lookback_days, lookback_days, lookback_days),
            )
            procurement = dict(cur.fetchone())

    ordered_current = int(procurement["ordered_current"])
    received_current = int(procurement["received_current"])
    ordered_prior = int(procurement["ordered_prior"])
    received_prior = int(procurement["received_prior"])
    receipt_current = receipt_rate(received_current, ordered_current)
    receipt_prior = receipt_rate(received_prior, ordered_prior)

    if as_of_date is not None:
        _mark_partial(
            trend,
            trend_granularity,
            as_of_date - timedelta(days=lookback_days - 1),
            as_of_date,
        )

    top_product_share_pct = (
        round(
            100.0
            * sum(float(row["revenue"]) for row in top_products)
            / current_revenue,
            2,
        )
        if current_revenue > 0
        else 0.0
    )

    result = {
        "generated_at": datetime.now(timezone.utc),
        "frontier_cutoff": frontier_cutoff,
        "as_of_date": as_of_date,
        "lookback_days": lookback_days,
        "current_period": {
            "start_date": (
                as_of_date - timedelta(days=lookback_days - 1)
                if as_of_date
                else None
            ),
            "end_date": as_of_date,
        },
        "prior_period": {
            "start_date": (
                as_of_date - timedelta(days=(2 * lookback_days - 1))
                if as_of_date
                else None
            ),
            "end_date": (
                as_of_date - timedelta(days=lookback_days)
                if as_of_date
                else None
            ),
        },
        "kpis": {
            "invoices": int(sales["invoices_current"]),
            "orders": int(sales["orders_current"]),
            "units": int(sales["units_current"]),
            "revenue": current_revenue,
            "profit": current_profit,
            "margin_pct": current_margin,
            "prior_invoices": int(sales["invoices_prior"]),
            "prior_orders": int(sales["orders_prior"]),
            "prior_units": int(sales["units_prior"]),
            "prior_revenue": prior_revenue,
            "prior_profit": prior_profit,
            "prior_margin_pct": prior_margin,
            "revenue_change_pct": pct_change(current_revenue, prior_revenue),
            "profit_change_pct": pct_change(current_profit, prior_profit),
            "orders_change_pct": pct_change(
                float(sales["orders_current"]),
                float(sales["orders_prior"]),
            ),
            "units_change_pct": pct_change(
                float(sales["units_current"]),
                float(sales["units_prior"]),
            ),
            "margin_change_pp": round(current_margin - prior_margin, 2),
        },
        "trend_granularity": trend_granularity,
        "trend": trend,
        "customer_concentration": {
            "top5_revenue_share_pct": top5_share_pct,
            "customers": top_customers,
        },
        "top_products": top_products,
        "top_product_revenue_share_pct": top_product_share_pct,
        "procurement": {
            "ordered_outers": ordered_current,
            "received_outers": received_current,
            "po_count": int(procurement["po_current"]),
            "receipt_rate_pct": receipt_current,
            "receipt_rate_change_pp": round(receipt_current - receipt_prior, 2),
            "prior_receipt_rate_pct": receipt_prior,
            "prior_ordered_outers": ordered_prior,
            "prior_received_outers": received_prior,
            "prior_po_count": int(procurement["po_prior"]),
        },
    }
    return JSONResponse(content=jsonable_encoder(result))


def _trend_setup(lookback_days: int) -> tuple[str, str]:
    if lookback_days == 30:
        return "day", "d.calendar_date"
    if lookback_days == 90:
        return "week", "date_trunc('week', d.calendar_date)::date"
    return "month", "date_trunc('month', d.calendar_date)::date"


def _mark_partial(
    rows: list[dict],
    granularity: str,
    window_start: date | None,
    window_end: date | None,
) -> None:
    for row in rows:
        bucket_start = row["bucket_start"]
        if granularity == "day":
            bucket_end = bucket_start
        elif granularity == "week":
            bucket_end = bucket_start + timedelta(days=6)
        else:
            next_month = (bucket_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            bucket_end = next_month - timedelta(days=1)
        row["is_partial"] = bool(
            (window_start and bucket_start < window_start)
            or (window_end and bucket_end > window_end)
        )


def _bucket_floor(value: date, granularity: str) -> date:
    if granularity == "day":
        return value
    if granularity == "week":
        return value - timedelta(days=value.weekday())
    return value.replace(day=1)


def _next_bucket(value: date, granularity: str) -> date:
    if granularity == "day":
        return value + timedelta(days=1)
    if granularity == "week":
        return value + timedelta(days=7)
    return (value.replace(day=28) + timedelta(days=4)).replace(day=1)


def _fill_trend_buckets(
    rows: list[dict],
    granularity: str,
    start_date: date,
    end_date: date,
    defaults: dict[str, object],
) -> list[dict]:
    existing = {row["bucket_start"]: dict(row) for row in rows}
    cursor = _bucket_floor(start_date, granularity)
    last = _bucket_floor(end_date, granularity)
    filled: list[dict] = []
    while cursor <= last:
        row = {"bucket_start": cursor, **defaults}
        row.update(existing.get(cursor, {}))
        filled.append(row)
        cursor = _next_bucket(cursor, granularity)
    return filled


def _add_contribution_share(
    rows: list[dict],
    numerator_key: str,
    denominator: float,
    basis: str,
) -> list[dict]:
    for row in rows:
        numerator = float(row.get(numerator_key) or 0)
        row["contribution_pct"] = round(100.0 * numerator / denominator, 2) if denominator else 0.0
        row["contribution_basis"] = basis
    return rows


@router.get("/drilldown")
def drilldown(
    kind: str = Query(...),
    lookback_days: int = Query(30),
    entity_id: int | None = Query(None),
) -> JSONResponse:
    if lookback_days not in ALLOWED_LOOKBACKS:
        lookback_days = 30
    if kind not in {"revenue", "profit", "orders", "receipt", "customer", "product"}:
        raise HTTPException(status_code=400, detail="unsupported analytics drilldown kind")
    if kind in {"customer", "product"} and entity_id is None:
        raise HTTPException(status_code=400, detail="entity_id is required")

    granularity, bucket_expr = _trend_setup(lookback_days)

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT (safe_through_cutoff::date - 1) AS as_of_date
                FROM control.source_frontier
                WHERE source_name='WideWorldImporters'
                """
            )
            frontier = cur.fetchone()
            as_of_date = frontier["as_of_date"] if frontier else None
            if as_of_date is None:
                raise HTTPException(status_code=503, detail="warehouse frontier unavailable")

            current_start = as_of_date - timedelta(days=lookback_days - 1)
            prior_end = as_of_date - timedelta(days=lookback_days)
            prior_start = as_of_date - timedelta(days=2 * lookback_days - 1)

            if kind == "receipt":
                cur.execute(
                    f"""
                    SELECT
                        {bucket_expr} AS bucket_start,
                        coalesce(sum(p.ordered_outers),0)::bigint AS ordered_outers,
                        coalesce(sum(p.received_outers),0)::bigint AS received_outers,
                        count(DISTINCT p.purchase_order_id)::int AS purchase_orders
                    FROM core.fact_purchase_order_line p
                    JOIN core.dim_date d ON d.date_key=p.order_date_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                    GROUP BY 1
                    ORDER BY 1
                    """,
                    (current_start, as_of_date),
                )
                trend = [dict(row) for row in cur.fetchall()]
                trend = _fill_trend_buckets(
                    trend,
                    granularity,
                    current_start,
                    as_of_date,
                    {"ordered_outers": 0, "received_outers": 0, "purchase_orders": 0},
                )
                for row in trend:
                    ordered = int(row["ordered_outers"])
                    received = int(row["received_outers"])
                    row["receipt_rate_pct"] = receipt_rate(received, ordered)
                _mark_partial(trend, granularity, current_start, as_of_date)

                cur.execute(
                    """
                    SELECT
                        coalesce(sum(p.ordered_outers) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        ),0)::bigint AS ordered_current,
                        coalesce(sum(p.received_outers) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        ),0)::bigint AS received_current,
                        count(DISTINCT p.purchase_order_id) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        )::int AS po_current,
                        coalesce(sum(p.ordered_outers) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        ),0)::bigint AS ordered_prior,
                        coalesce(sum(p.received_outers) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        ),0)::bigint AS received_prior,
                        count(DISTINCT p.purchase_order_id) FILTER (
                            WHERE d.calendar_date BETWEEN %s AND %s
                        )::int AS po_prior
                    FROM core.fact_purchase_order_line p
                    JOIN core.dim_date d ON d.date_key=p.order_date_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                    """,
                    (
                        current_start, as_of_date,
                        current_start, as_of_date,
                        current_start, as_of_date,
                        prior_start, prior_end,
                        prior_start, prior_end,
                        prior_start, prior_end,
                        prior_start, as_of_date,
                    ),
                )
                sums = dict(cur.fetchone())
                ordered_current = int(sums["ordered_current"])
                received_current = int(sums["received_current"])
                ordered_prior = int(sums["ordered_prior"])
                received_prior = int(sums["received_prior"])
                current_rate = receipt_rate(received_current, ordered_current)
                prior_rate = receipt_rate(received_prior, ordered_prior)

                cur.execute(
                    """
                    SELECT
                        s.supplier_id,
                        s.supplier_name,
                        sum(p.ordered_outers)::bigint AS ordered_outers,
                        sum(p.received_outers)::bigint AS received_outers,
                        (sum(p.ordered_outers)-sum(p.received_outers))::bigint AS outstanding_outers,
                        count(DISTINCT p.purchase_order_id)::int AS purchase_orders
                    FROM core.fact_purchase_order_line p
                    JOIN core.dim_date d ON d.date_key=p.order_date_key
                    JOIN core.dim_supplier s ON s.supplier_key=p.supplier_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                    GROUP BY s.supplier_id,s.supplier_name
                    HAVING sum(p.ordered_outers) > 0
                    ORDER BY outstanding_outers DESC, ordered_outers DESC
                    LIMIT 6
                    """,
                    (current_start, as_of_date),
                )
                supplier_rows = [dict(row) for row in cur.fetchall()]
                for row in supplier_rows:
                    row["completion_pct"] = receipt_rate(
                        int(row["received_outers"]),
                        int(row["ordered_outers"]),
                    )
                supplier_rows = _add_contribution_share(
                    supplier_rows,
                    "outstanding_outers",
                    float(max(0, ordered_current - received_current)),
                    "outstanding receipt outers",
                )

                result = {
                    "kind": kind,
                    "title": "Receipt completion",
                    "entity_id": None,
                    "current_period": {"start_date": current_start, "end_date": as_of_date},
                    "prior_period": {"start_date": prior_start, "end_date": prior_end},
                    "trend_granularity": granularity,
                    "trend": trend,
                    "summary": {
                        "ordered_outers": ordered_current,
                        "received_outers": received_current,
                        "outstanding_outers": max(0, ordered_current - received_current),
                        "purchase_orders": int(sums["po_current"]),
                        "receipt_rate_pct": current_rate,
                        "prior_receipt_rate_pct": prior_rate,
                        "receipt_rate_change_pp": round(current_rate - prior_rate, 2),
                    },
                    "breakdowns": [
                        {
                            "title": "Suppliers with the largest outstanding receipts",
                            "entity_kind": "supplier",
                            "rows": supplier_rows,
                        }
                    ],
                }
                return JSONResponse(content=jsonable_encoder(result))

            sales_join = ""
            sales_where = ""
            entity_params: list[object] = []
            title = kind.capitalize()

            if kind == "customer":
                sales_join = "JOIN core.dim_customer entity ON entity.customer_key=s.customer_key"
                sales_where = "AND entity.customer_id=%s"
                entity_params = [entity_id]
                cur.execute(
                    """
                    SELECT customer_name
                    FROM core.dim_customer
                    WHERE customer_id=%s AND is_current=true
                    ORDER BY valid_from DESC LIMIT 1
                    """,
                    (entity_id,),
                )
                row = cur.fetchone()
                title = row["customer_name"] if row else f"Customer {entity_id}"
            elif kind == "product":
                sales_join = "JOIN core.dim_product entity ON entity.product_key=s.product_key"
                sales_where = "AND entity.stock_item_id=%s"
                entity_params = [entity_id]
                cur.execute(
                    """
                    SELECT stock_item_name
                    FROM core.dim_product
                    WHERE stock_item_id=%s AND is_current=true
                    ORDER BY valid_from DESC LIMIT 1
                    """,
                    (entity_id,),
                )
                row = cur.fetchone()
                title = row["stock_item_name"] if row else f"Product {entity_id}"

            cur.execute(
                f"""
                SELECT
                    coalesce(sum(s.total_including_tax) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::numeric(18,2) AS revenue_current,
                    coalesce(sum(s.profit) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::numeric(18,2) AS profit_current,
                    count(DISTINCT s.order_id) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    )::int AS orders_current,
                    count(DISTINCT s.invoice_id) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    )::int AS invoices_current,
                    coalesce(sum(s.quantity) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::bigint AS units_current,
                    count(DISTINCT s.customer_id) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    )::int AS customers_current,

                    coalesce(sum(s.total_including_tax) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::numeric(18,2) AS revenue_prior,
                    coalesce(sum(s.profit) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::numeric(18,2) AS profit_prior,
                    count(DISTINCT s.order_id) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    )::int AS orders_prior,
                    count(DISTINCT s.invoice_id) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    )::int AS invoices_prior,
                    coalesce(sum(s.quantity) FILTER (
                        WHERE d.calendar_date BETWEEN %s AND %s
                    ),0)::bigint AS units_prior
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                {sales_join}
                WHERE d.calendar_date BETWEEN %s AND %s
                {sales_where}
                """,
                (
                    current_start, as_of_date,
                    current_start, as_of_date,
                    current_start, as_of_date,
                    current_start, as_of_date,
                    current_start, as_of_date,
                    current_start, as_of_date,
                    prior_start, prior_end,
                    prior_start, prior_end,
                    prior_start, prior_end,
                    prior_start, prior_end,
                    prior_start, prior_end,
                    prior_start, as_of_date,
                    *entity_params,
                ),
            )
            sums = dict(cur.fetchone())

            revenue = float(sums["revenue_current"])
            profit = float(sums["profit_current"])
            orders = int(sums["orders_current"])
            units = int(sums["units_current"])
            prior_revenue = float(sums["revenue_prior"])
            prior_profit = float(sums["profit_prior"])
            prior_orders = int(sums["orders_prior"])
            prior_units = int(sums["units_prior"])

            margin = round(100.0 * profit / revenue, 2) if revenue else 0.0
            prior_margin = round(100.0 * prior_profit / prior_revenue, 2) if prior_revenue else 0.0

            cur.execute(
                f"""
                SELECT
                    {bucket_expr} AS bucket_start,
                    coalesce(sum(s.total_including_tax),0)::numeric(18,2) AS revenue,
                    coalesce(sum(s.profit),0)::numeric(18,2) AS profit,
                    count(DISTINCT s.order_id)::int AS orders,
                    coalesce(sum(s.quantity),0)::bigint AS units
                FROM core.fact_sales_line s
                JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                {sales_join}
                WHERE d.calendar_date BETWEEN %s AND %s
                {sales_where}
                GROUP BY 1
                ORDER BY 1
                """,
                (current_start, as_of_date, *entity_params),
            )
            trend = [dict(row) for row in cur.fetchall()]
            trend = _fill_trend_buckets(
                trend,
                granularity,
                current_start,
                as_of_date,
                {"revenue": 0, "profit": 0, "orders": 0, "units": 0},
            )
            _mark_partial(trend, granularity, current_start, as_of_date)

            summary = {
                "revenue": revenue,
                "profit": profit,
                "orders": orders,
                "invoices": int(sums["invoices_current"]),
                "units": units,
                "customers": int(sums["customers_current"]),
                "margin_pct": margin,
                "avg_revenue_per_order": round(revenue / orders, 2) if orders else 0.0,
                "avg_units_per_order": round(units / orders, 2) if orders else 0.0,
                "revenue_change_pct": pct_change(revenue, prior_revenue),
                "profit_change_pct": pct_change(profit, prior_profit),
                "orders_change_pct": pct_change(float(orders), float(prior_orders)),
                "units_change_pct": pct_change(float(units), float(prior_units)),
                "margin_change_pp": round(margin - prior_margin, 2),
                "prior_revenue": prior_revenue,
                "prior_profit": prior_profit,
                "prior_orders": prior_orders,
                "prior_units": prior_units,
                "prior_margin_pct": prior_margin,
            }

            breakdowns: list[dict] = []

            if kind in {"revenue", "profit", "orders"}:
                customer_metric = (
                    "sum(s.profit)" if kind == "profit"
                    else "count(DISTINCT s.order_id)" if kind == "orders"
                    else "sum(s.total_including_tax)"
                )
                customer_order = "metric_value DESC"
                cur.execute(
                    f"""
                    SELECT
                        c.customer_id AS id,
                        c.customer_name AS label,
                        {customer_metric}::numeric AS metric_value,
                        sum(s.total_including_tax)::numeric(18,2) AS revenue,
                        sum(s.profit)::numeric(18,2) AS profit,
                        count(DISTINCT s.order_id)::int AS orders
                    FROM core.fact_sales_line s
                    JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                    JOIN core.dim_customer c ON c.customer_key=s.customer_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                    GROUP BY c.customer_id,c.customer_name
                    ORDER BY {customer_order}
                    LIMIT 5
                    """,
                    (current_start, as_of_date),
                )
                customer_rows = [dict(row) for row in cur.fetchall()]
                customer_denominator = (
                    profit if kind == "profit"
                    else float(orders) if kind == "orders"
                    else revenue
                )
                customer_rows = _add_contribution_share(
                    customer_rows,
                    "metric_value",
                    customer_denominator,
                    kind,
                )
                breakdowns.append({
                    "title": f"Top customer drivers by {kind}",
                    "entity_kind": "customer",
                    "rows": customer_rows,
                })

                product_metric = (
                    "sum(s.profit)" if kind == "profit"
                    else "count(DISTINCT s.order_id)" if kind == "orders"
                    else "sum(s.total_including_tax)"
                )
                cur.execute(
                    f"""
                    SELECT
                        p.stock_item_id AS id,
                        p.stock_item_name AS label,
                        {product_metric}::numeric AS metric_value,
                        sum(s.total_including_tax)::numeric(18,2) AS revenue,
                        sum(s.profit)::numeric(18,2) AS profit,
                        sum(s.quantity)::bigint AS units
                    FROM core.fact_sales_line s
                    JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                    JOIN core.dim_product p ON p.product_key=s.product_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                    GROUP BY p.stock_item_id,p.stock_item_name
                    ORDER BY metric_value DESC
                    LIMIT 5
                    """,
                    (current_start, as_of_date),
                )
                product_rows = [dict(row) for row in cur.fetchall()]
                product_denominator = (
                    profit if kind == "profit"
                    else float(orders) if kind == "orders"
                    else revenue
                )
                product_rows = _add_contribution_share(
                    product_rows,
                    "metric_value",
                    product_denominator,
                    kind,
                )
                breakdowns.append({
                    "title": "Top product drivers",
                    "entity_kind": "product",
                    "rows": product_rows,
                })

            elif kind == "customer":
                cur.execute(
                    """
                    SELECT
                        p.stock_item_id AS id,
                        p.stock_item_name AS label,
                        sum(s.total_including_tax)::numeric(18,2) AS revenue,
                        sum(s.profit)::numeric(18,2) AS profit,
                        sum(s.quantity)::bigint AS units,
                        count(DISTINCT s.order_id)::int AS orders
                    FROM core.fact_sales_line s
                    JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                    JOIN core.dim_product p ON p.product_key=s.product_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                      AND s.customer_id=%s
                    GROUP BY p.stock_item_id,p.stock_item_name
                    ORDER BY revenue DESC
                    LIMIT 6
                    """,
                    (current_start, as_of_date, entity_id),
                )
                customer_product_rows = [dict(row) for row in cur.fetchall()]
                customer_product_rows = _add_contribution_share(
                    customer_product_rows,
                    "revenue",
                    revenue,
                    "customer revenue",
                )
                breakdowns.append({
                    "title": "Top products purchased by this customer",
                    "entity_kind": "product",
                    "rows": customer_product_rows,
                })

            elif kind == "product":
                cur.execute(
                    """
                    SELECT
                        c.customer_id AS id,
                        c.customer_name AS label,
                        sum(s.total_including_tax)::numeric(18,2) AS revenue,
                        sum(s.profit)::numeric(18,2) AS profit,
                        sum(s.quantity)::bigint AS units,
                        count(DISTINCT s.order_id)::int AS orders
                    FROM core.fact_sales_line s
                    JOIN core.dim_date d ON d.date_key=s.invoice_date_key
                    JOIN core.dim_customer c ON c.customer_key=s.customer_key
                    WHERE d.calendar_date BETWEEN %s AND %s
                      AND s.stock_item_id=%s
                    GROUP BY c.customer_id,c.customer_name
                    ORDER BY revenue DESC
                    LIMIT 6
                    """,
                    (current_start, as_of_date, entity_id),
                )
                product_customer_rows = [dict(row) for row in cur.fetchall()]
                product_customer_rows = _add_contribution_share(
                    product_customer_rows,
                    "revenue",
                    revenue,
                    "product revenue",
                )
                breakdowns.append({
                    "title": "Top customers buying this product",
                    "entity_kind": "customer",
                    "rows": product_customer_rows,
                })

            result = {
                "kind": kind,
                "title": title,
                "entity_id": entity_id,
                "current_period": {"start_date": current_start, "end_date": as_of_date},
                "prior_period": {"start_date": prior_start, "end_date": prior_end},
                "trend_granularity": granularity,
                "trend": trend,
                "summary": summary,
                "breakdowns": breakdowns,
            }
            return JSONResponse(content=jsonable_encoder(result))
