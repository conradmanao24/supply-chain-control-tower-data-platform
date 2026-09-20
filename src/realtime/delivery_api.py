from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor

from realtime.operational_semantics import DELIVERY_LIFECYCLE_MAX_DAYS

router = APIRouter(prefix="/api/delivery", tags=["delivery"])


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
    frontier = row["safe_through_cutoff"]
    return (frontier - timedelta(days=1)).date()


LATEST_EVENT_SQL = """
    CASE
        WHEN jsonb_typeof(d.returned_delivery_data->'Events')='array'
         AND jsonb_array_length(d.returned_delivery_data->'Events') > 0
        THEN d.returned_delivery_data->'Events'->(
            jsonb_array_length(d.returned_delivery_data->'Events') - 1
        )->>'Event'
        ELSE NULL
    END
"""

LATEST_COMMENT_SQL = """
    CASE
        WHEN jsonb_typeof(d.returned_delivery_data->'Events')='array'
         AND jsonb_array_length(d.returned_delivery_data->'Events') > 0
        THEN d.returned_delivery_data->'Events'->(
            jsonb_array_length(d.returned_delivery_data->'Events') - 1
        )->>'Comment'
        ELSE NULL
    END
"""

DELIVERY_SELECT = f"""
    SELECT
        d.invoice_id,
        d.order_id,
        d.customer_id,
        coalesce(c.customer_name,'Customer '||d.customer_id::text) AS customer_name,
        d.invoice_date,
        o.order_date,
        o.expected_delivery_date,
        o.picking_completed_when,
        d.confirmed_delivery_time,
        d.confirmed_received_by,
        d.delivery_run,
        d.run_position,
        d.last_edited_when,
        d.refreshed_at,
        d.returned_delivery_data,
        {LATEST_EVENT_SQL} AS latest_event,
        {LATEST_COMMENT_SQL} AS latest_event_comment,
        coalesce(d.returned_delivery_data::text,'') ILIKE '%%Receiver not present%%'
            AS had_receiver_not_present,
        (d.invoice_date-o.order_date)::int AS lifecycle_gap_days,
        (
            o.order_date IS NOT NULL
            AND d.invoice_date >= o.order_date
            AND (d.invoice_date-o.order_date) <= %(lifecycle_max_days)s
        ) AS lifecycle_coherent,
        CASE
            WHEN d.confirmed_delivery_time IS NOT NULL THEN 'confirmed'
            WHEN o.expected_delivery_date < %(as_of)s::date THEN 'overdue'
            WHEN o.expected_delivery_date = %(as_of)s::date THEN 'due_today'
            ELSE 'pending'
        END AS delivery_state,
        CASE
            WHEN d.confirmed_delivery_time IS NULL
             AND o.expected_delivery_date < %(as_of)s::date
            THEN (%(as_of)s::date-o.expected_delivery_date)::int
            ELSE 0
        END AS days_overdue,
        CASE
            WHEN d.confirmed_delivery_time IS NULL
             AND o.expected_delivery_date > %(as_of)s::date
            THEN (o.expected_delivery_date-%(as_of)s::date)::int
            ELSE 0
        END AS days_until_due,
        CASE
            WHEN d.confirmed_delivery_time IS NULL
            THEN greatest((%(as_of)s::date-d.invoice_date),0)::int
            ELSE 0
        END AS days_since_invoice
    FROM realtime.current_delivery_state d
    LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
    LEFT JOIN core.dim_customer c
      ON c.customer_id=d.customer_id
     AND c.is_current=true
"""


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)

            cur.execute(
                """
                WITH scope AS (
                    SELECT
                        d.*,
                        o.order_date,
                        o.expected_delivery_date,
                        (
                            o.order_date IS NOT NULL
                            AND d.invoice_date >= o.order_date
                            AND (d.invoice_date-o.order_date) <= %(lifecycle_max_days)s
                        ) AS lifecycle_coherent
                    FROM realtime.current_delivery_state d
                    LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
                    WHERE d.invoice_date >= %(as_of)s::date - interval '29 days'
                      AND d.invoice_date <= %(as_of)s::date
                )
                SELECT
                    count(*)::int AS deliveries_30d,
                    count(*) FILTER (WHERE NOT lifecycle_coherent)::int AS lifecycle_anomalies,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NULL
                    )::int AS pending,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NULL
                          AND expected_delivery_date < %(as_of)s::date
                    )::int AS overdue,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NULL
                          AND expected_delivery_date = %(as_of)s::date
                    )::int AS due_today,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NULL
                          AND expected_delivery_date > %(as_of)s::date
                    )::int AS upcoming_pending,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NOT NULL
                    )::int AS confirmed,
                    count(*) FILTER (
                        WHERE coalesce(returned_delivery_data::text,'') ILIKE '%%Receiver not present%%'
                    )::int AS receiver_not_present_events,
                    count(*) FILTER (
                        WHERE confirmed_delivery_time IS NULL
                          AND coalesce(returned_delivery_data::text,'') ILIKE '%%Receiver not present%%'
                    )::int AS receiver_not_present_pending
                FROM scope
                """,
                {"as_of": as_of, "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS},
            )
            kpis = dict(cur.fetchone())

            cur.execute(
                """
                WITH overdue AS (
                    SELECT (%(as_of)s::date-o.expected_delivery_date)::int AS days_overdue
                    FROM realtime.current_delivery_state d
                    JOIN realtime.current_order_state o ON o.order_id=d.order_id
                    WHERE d.invoice_date >= %(as_of)s::date - interval '30 days'
                      AND d.invoice_date <= %(as_of)s::date
                      AND d.confirmed_delivery_time IS NULL
                      AND o.expected_delivery_date < %(as_of)s::date
                )
                SELECT
                    coalesce(max(days_overdue),0)::int AS oldest_days_overdue,
                    coalesce(
                        percentile_disc(0.5) WITHIN GROUP (ORDER BY days_overdue),
                        0
                    )::int AS median_days_overdue
                FROM overdue
                """,
                {"as_of": as_of, "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS},
            )
            exposure = dict(cur.fetchone())

            cur.execute(
                """
                WITH buckets(bucket, sort_order) AS (
                    VALUES ('1-2 days',1),('3-5 days',2),('6-10 days',3),('10+ days',4)
                ),
                overdue AS (
                    SELECT (%(as_of)s::date-o.expected_delivery_date)::int AS days_overdue
                    FROM realtime.current_delivery_state d
                    JOIN realtime.current_order_state o ON o.order_id=d.order_id
                    WHERE d.invoice_date >= %(as_of)s::date - interval '29 days'
                      AND d.invoice_date <= %(as_of)s::date
                      AND d.confirmed_delivery_time IS NULL
                      AND o.expected_delivery_date < %(as_of)s::date
                ),
                counts AS (
                    SELECT CASE
                        WHEN days_overdue <= 2 THEN '1-2 days'
                        WHEN days_overdue <= 5 THEN '3-5 days'
                        WHEN days_overdue <= 10 THEN '6-10 days'
                        ELSE '10+ days'
                    END AS bucket,
                    count(*)::int AS value
                    FROM overdue
                    GROUP BY 1
                )
                SELECT b.bucket,coalesce(c.value,0)::int AS value
                FROM buckets b
                LEFT JOIN counts c USING(bucket)
                ORDER BY b.sort_order
                """,
                {"as_of": as_of},
            )
            aging = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                WITH source_rows AS (
                    SELECT DISTINCT
                        d.invoice_id,d.order_id,d.invoice_date,d.confirmed_delivery_time,
                        o.order_date,o.picking_completed_when
                    FROM realtime.current_delivery_state d
                    JOIN realtime.current_order_state o ON o.order_id=d.order_id
                    WHERE d.invoice_date BETWEEN %(as_of)s::date-interval '29 days'
                                             AND %(as_of)s::date
                ),
                order_cycle AS (
                    SELECT DISTINCT order_id,order_date,picking_completed_when
                    FROM source_rows
                    WHERE picking_completed_when IS NOT NULL
                )
                SELECT
                    round(
                        percentile_disc(0.5) WITHIN GROUP (
                            ORDER BY extract(epoch FROM (
                                picking_completed_when-order_date::timestamp
                            )) / 86400.0
                        )::numeric,
                        2
                    ) AS median_order_to_pick_days,
                    round(
                        percentile_disc(0.9) WITHIN GROUP (
                            ORDER BY extract(epoch FROM (
                                picking_completed_when-order_date::timestamp
                            )) / 86400.0
                        )::numeric,
                        2
                    ) AS p90_order_to_pick_days,
                    (
                        SELECT round(
                            percentile_disc(0.5) WITHIN GROUP (
                                ORDER BY extract(epoch FROM (
                                    confirmed_delivery_time-invoice_date::timestamp
                                )) / 86400.0
                            )::numeric,
                            2
                        )
                        FROM source_rows
                        WHERE confirmed_delivery_time IS NOT NULL
                    ) AS median_invoice_to_confirm_days
                FROM order_cycle
                """,
                {"as_of": as_of, "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS},
            )
            cycle_time = dict(cur.fetchone())

            cur.execute(
                """
                SELECT r.severity,count(*)::int AS count
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE r.domain='delivery'
                  AND a.status IN ('open','acknowledged')
                GROUP BY r.severity
                """
            )
            sev = {row["severity"]: row["count"] for row in cur.fetchall()}

    deliveries = int(kpis["deliveries_30d"])
    pending = int(kpis["pending"])
    confirmed = int(kpis["confirmed"])

    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "as_of_date": as_of,
                "lookback_days": 30,
                "kpis": kpis,
                "operational_context": {
                    "confirmation_rate": round(
                        confirmed / deliveries * 100.0, 1
                    ) if deliveries else 0.0,
                    "overdue_rate_pending": round(
                        int(kpis["overdue"]) / pending * 100.0, 1
                    ) if pending else 0.0,
                    "median_days_overdue": int(exposure["median_days_overdue"]),
                    "oldest_days_overdue": int(exposure["oldest_days_overdue"]),
                    "median_order_to_pick_days": (
                        float(cycle_time["median_order_to_pick_days"])
                        if cycle_time["median_order_to_pick_days"] is not None else None
                    ),
                    "p90_order_to_pick_days": (
                        float(cycle_time["p90_order_to_pick_days"])
                        if cycle_time["p90_order_to_pick_days"] is not None else None
                    ),
                    "median_invoice_to_confirm_days": (
                        float(cycle_time["median_invoice_to_confirm_days"])
                        if cycle_time["median_invoice_to_confirm_days"] is not None else None
                    ),
                    "lifecycle_anomalies": int(kpis["lifecycle_anomalies"]),
                    "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS,
                },
                "aging": aging,
                "alert_summary": {
                    "active": sum(sev.values()),
                    "critical": sev.get("critical", 0),
                    "warning": sev.get("warning", 0),
                    "info": sev.get("info", 0),
                },
            }
        )
    )


@router.get("/list")
def delivery_list(
    status: str = Query(
        "pending",
        pattern="^(all|pending|upcoming|confirmed|receiver_not_present|overdue|overdue_1_2|overdue_3_5|overdue_6_10|overdue_10_plus|due_today)$",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    search: str = Query("", max_length=120),
) -> JSONResponse:
    filters = {
        "all": "TRUE",
        "pending": "d.confirmed_delivery_time IS NULL",
        "upcoming": (
            "d.confirmed_delivery_time IS NULL "
            "AND o.expected_delivery_date > %(as_of)s::date"
        ),
        "confirmed": "d.confirmed_delivery_time IS NOT NULL",
        "receiver_not_present": (
            "coalesce(d.returned_delivery_data::text,'') "
            "ILIKE '%%Receiver not present%%'"
        ),
        "overdue": (
            "d.confirmed_delivery_time IS NULL "
            "AND o.expected_delivery_date < %(as_of)s::date"
        ),
        "overdue_1_2": (
            "d.confirmed_delivery_time IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 1 AND 2"
        ),
        "overdue_3_5": (
            "d.confirmed_delivery_time IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 3 AND 5"
        ),
        "overdue_6_10": (
            "d.confirmed_delivery_time IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) BETWEEN 6 AND 10"
        ),
        "overdue_10_plus": (
            "d.confirmed_delivery_time IS NULL "
            "AND (%(as_of)s::date-o.expected_delivery_date) > 10"
        ),
        "due_today": (
            "d.confirmed_delivery_time IS NULL "
            "AND o.expected_delivery_date = %(as_of)s::date"
        ),
    }

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)
            params: dict[str, Any] = {
                "as_of": as_of,
                "page_size": page_size,
                "offset": (page - 1) * page_size,
                "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS,
            }
            conditions = [
                filters[status],
                "d.invoice_date >= %(as_of)s::date - interval '29 days'",
                "d.invoice_date <= %(as_of)s::date",
            ]

            if search.strip():
                params["search"] = f"%{search.strip()}%"
                conditions.append(
                    "(d.invoice_id::text ILIKE %(search)s "
                    "OR d.order_id::text ILIKE %(search)s "
                    "OR d.customer_id::text ILIKE %(search)s "
                    "OR coalesce(c.customer_name,'') ILIKE %(search)s)"
                )

            where_sql = " AND ".join(conditions)

            cur.execute(
                f"""
                SELECT count(*)::int AS total
                FROM realtime.current_delivery_state d
                LEFT JOIN realtime.current_order_state o ON o.order_id=d.order_id
                LEFT JOIN core.dim_customer c
                  ON c.customer_id=d.customer_id
                 AND c.is_current=true
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()["total"])

            cur.execute(
                DELIVERY_SELECT
                + f"""
                WHERE {where_sql}
                ORDER BY
                    CASE
                        WHEN d.confirmed_delivery_time IS NULL
                         AND o.expected_delivery_date < %(as_of)s::date THEN 0
                        WHEN d.confirmed_delivery_time IS NULL
                         AND o.expected_delivery_date = %(as_of)s::date THEN 1
                        WHEN d.confirmed_delivery_time IS NULL THEN 2
                        ELSE 3
                    END,
                    CASE
                        WHEN d.confirmed_delivery_time IS NULL
                         AND o.expected_delivery_date < %(as_of)s::date
                        THEN o.expected_delivery_date
                    END ASC NULLS LAST,
                    d.invoice_date DESC,
                    d.invoice_id DESC
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


@router.get("/{invoice_id}")
def delivery_detail(invoice_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            as_of = get_business_date(cur)
            cur.execute(
                DELIVERY_SELECT + " WHERE d.invoice_id=%(invoice_id)s",
                {
                    "as_of": as_of,
                    "invoice_id": invoice_id,
                    "lifecycle_max_days": DELIVERY_LIFECYCLE_MAX_DAYS,
                },
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Delivery not found")

    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "as_of_date": as_of,
                "delivery": dict(row),
            }
        )
    )
