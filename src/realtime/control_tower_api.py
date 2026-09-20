from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from psycopg2.extras import RealDictCursor
from .alert_explanations import explain_alert
from realtime.supply_risk import INVENTORY_PROJECTION_CTES, fetch_po_risks


router = APIRouter(prefix="/api/control-tower", tags=["control-tower"])
METADATA_MAX_AGE_HOURS = max(
    1.0,
    float(os.environ.get("PLATFORM_METADATA_MAX_AGE_HOURS", "36")),
)


def pg_connect():
    return psycopg2.connect(
        host=os.environ["DWH_HOST"],
        port=int(os.environ.get("DWH_PORT", "5432")),
        dbname=os.environ["DWH_DB"],
        user=os.environ["DWH_USER"],
        password=os.environ["DWH_PASSWORD"],
    )


def domain_status(active_alerts: int, attention: int, monitoring: int = 0) -> str:
    if active_alerts > 0:
        return "exception"
    if attention > 0:
        return "attention"
    if monitoring > 0:
        return "monitoring"
    return "healthy"


@router.get("/overview")
def overview() -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT safe_through_cutoff,updated_at FROM control.source_frontier "
                "WHERE source_name='WideWorldImporters'"
            )
            frontier_row = cur.fetchone()
            source_frontier = frontier_row["safe_through_cutoff"] if frontier_row else None
            as_of_date = (source_frontier - timedelta(days=1)).date() if source_frontier else None

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status IN ('open','acknowledged'))::int AS active,
                    count(DISTINCT (entity_type, entity_id)) FILTER (
                        WHERE status IN ('open','acknowledged')
                    )::int AS affected_records,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='critical')::int AS critical,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='warning')::int AS warning,
                    count(*) FILTER (WHERE status IN ('open','acknowledged') AND severity='info')::int AS info
                FROM alert.alerts
                """
            )
            alert_summary = dict(cur.fetchone())

            cur.execute(
                """
                SELECT r.domain, count(*)::int AS active
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE a.status IN ('open','acknowledged')
                GROUP BY r.domain
                """
            )
            domain_alerts = {row["domain"]: int(row["active"]) for row in cur.fetchall()}

            cur.execute(
                """
                WITH scope AS (
                    SELECT *
                    FROM realtime.current_order_state
                    WHERE order_date >= %s::date - interval '30 days'
                      AND order_date <= %s::date
                )
                SELECT
                    count(*) FILTER (WHERE picking_completed_when IS NULL)::int AS open_window,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND expected_delivery_date < %s::date
                    )::int AS overdue,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND expected_delivery_date = %s::date
                    )::int AS due_today,
                    count(*) FILTER (
                        WHERE picking_completed_when IS NULL
                          AND backorder_order_id IS NOT NULL
                    )::int AS backorders
                FROM scope
                """,
                (as_of_date, as_of_date, as_of_date, as_of_date),
            )
            fulfillment = dict(cur.fetchone())

            cur.execute(
                "SELECT count(*) FILTER (WHERE picking_completed_when IS NULL)::int AS all_time_open "
                "FROM realtime.current_order_state"
            )
            fulfillment["all_time_open"] = int(cur.fetchone()["all_time_open"])

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE d.confirmed_delivery_time IS NULL)::int AS pending,
                    count(*) FILTER (
                        WHERE d.confirmed_delivery_time IS NULL
                          AND o.expected_delivery_date < %s::date
                    )::int AS overdue_pending,
                    count(*) FILTER (
                        WHERE d.confirmed_delivery_time IS NULL
                          AND o.expected_delivery_date = %s::date
                    )::int AS due_today_pending
                FROM realtime.current_delivery_state d
                JOIN realtime.current_order_state o ON o.order_id=d.order_id
                WHERE d.invoice_date >= %s::date - interval '29 days'
                  AND d.invoice_date <= %s::date
                """,
                (
                    as_of_date,
                    as_of_date,
                    as_of_date,
                    as_of_date,
                ),
            )
            delivery = dict(cur.fetchone())

            cur.execute(
                INVENTORY_PROJECTION_CTES
                + """
                SELECT
                    count(*)::int AS total,
                    count(*) FILTER (WHERE quantity_on_hand < 0)::int AS negative,
                    count(*) FILTER (
                        WHERE quantity_on_hand >= 0
                          AND quantity_on_hand <= reorder_level
                    )::int AS reorder_watch,
                    count(*) FILTER (
                        WHERE coverage_state IN (
                            'negative_stock',
                            'projected_shortfall',
                            'stockout_before_inbound',
                            'coverage_gap'
                        )
                    )::int AS supply_risk,
                    count(*) FILTER (
                        WHERE coverage_severity='critical'
                    )::int AS critical_supply_risk
                FROM scored
                """
            )
            inventory = dict(cur.fetchone())

            cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE NOT is_order_finalized)::int AS open_po,
                    count(*) FILTER (
                        WHERE NOT is_order_finalized
                          AND expected_delivery_date < %s::date
                    )::int AS overdue,
                    count(*) FILTER (
                        WHERE NOT is_order_finalized
                          AND expected_delivery_date = %s::date
                    )::int AS due_today,
                    coalesce(sum(greatest(ordered_outers-received_outers,0))
                        FILTER (WHERE NOT is_order_finalized),0)::bigint AS outstanding_outers
                FROM realtime.current_procurement_state
                """,
                (as_of_date, as_of_date),
            )
            procurement = dict(cur.fetchone())

            cur.execute(
                """
                SELECT purchase_order_id
                FROM realtime.current_procurement_state
                WHERE NOT is_order_finalized
                ORDER BY purchase_order_id
                """
            )
            open_po_ids = [int(row["purchase_order_id"]) for row in cur.fetchall()]
            procurement_risks = fetch_po_risks(cur, open_po_ids)
            procurement["supply_risk_po_count"] = sum(
                1
                for row in procurement_risks.values()
                if int(row.get("at_risk_sku_count") or 0) > 0
            )
            procurement["supply_risk_units"] = sum(
                int(row.get("at_risk_units") or 0)
                for row in procurement_risks.values()
            )

            cur.execute(
                """
                SELECT
                    count(*)::int AS total,
                    count(*) FILTER (WHERE sensor_type='coldroom')::int AS coldroom,
                    count(*) FILTER (WHERE sensor_type='vehicle')::int AS vehicle,
                    max(recorded_when) AS latest_recorded_when
                FROM realtime.current_sensor_state
                """
            )
            sensors = dict(cur.fetchone())

            cur.execute(
                """
                SELECT a.alert_id,a.rule_id,r.domain,a.entity_type,a.entity_id,a.severity,a.status,
                       a.opened_at,a.last_observed_at
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE a.status IN ('open','acknowledged')
                ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         a.last_observed_at DESC
                LIMIT 8
                """
            )
            recent_alerts = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT
                    event_type,
                    entity_type,
                    operation,
                    occurred_at_utc,
                    source_table,
                    processing_result,
                    payload #>> '{entity_keys,0,entity_id}' AS entity_id
                FROM realtime.event_log
                WHERE event_type IN (
                    'order.changed',
                    'delivery.changed',
                    'inventory.changed',
                    'procurement.changed'
                )
                  AND source_table IN (
                    'Sales.Orders',
                    'Sales.Invoices',
                    'Warehouse.StockItemHoldings',
                    'Purchasing.PurchaseOrders'
                )
                ORDER BY occurred_at_utc DESC
                LIMIT 8
                """
            )
            latest_activity = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT last_successful_cutoff,updated_at
                FROM control.pipeline_state
                WHERE pipeline_name='supply_chain_incremental_pipeline'
                """
            )
            pipeline_row = cur.fetchone()
            pipeline_cutoff = pipeline_row["last_successful_cutoff"] if pipeline_row else None
            pipeline_updated_at = pipeline_row["updated_at"] if pipeline_row else None

            cur.execute(
                """
                SELECT airflow_run_id,status,passed_checks,failed_checks,warning_checks,finished_at
                FROM quality.run_history
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
            quality_row = cur.fetchone()
            quality = dict(quality_row) if quality_row else None

    now = datetime.now(timezone.utc)
    frontier_updated_at = frontier_row["updated_at"] if frontier_row else None
    quality_finished_at = quality.get("finished_at") if quality else None

    def age_hours(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return round(max(0.0, (now - value).total_seconds() / 3600.0), 3)

    pipeline_age_hours = age_hours(pipeline_updated_at)
    frontier_age_hours = age_hours(frontier_updated_at)
    quality_age_hours = age_hours(quality_finished_at)
    freshness = {
        "max_age_hours": METADATA_MAX_AGE_HOURS,
        "pipeline_age_hours": pipeline_age_hours,
        "frontier_age_hours": frontier_age_hours,
        "quality_age_hours": quality_age_hours,
        "all_fresh": bool(
            pipeline_age_hours is not None
            and frontier_age_hours is not None
            and quality_age_hours is not None
            and pipeline_age_hours <= METADATA_MAX_AGE_HOURS
            and frontier_age_hours <= METADATA_MAX_AGE_HOURS
            and quality_age_hours <= METADATA_MAX_AGE_HOURS
        ),
    }

    fulfillment_alerts = domain_alerts.get("fulfillment", 0)
    delivery_alerts = domain_alerts.get("delivery", 0)
    inventory_alerts = domain_alerts.get("inventory", 0)
    procurement_alerts = domain_alerts.get("procurement", 0)
    cold_chain_alerts = domain_alerts.get("cold_chain", 0)

    fulfillment_overdue = int(fulfillment["overdue"])
    delivery_overdue = int(delivery["overdue_pending"])
    inventory_attention = int(inventory["supply_risk"])
    procurement_overdue = int(procurement["overdue"])
    procurement_supply_risk_pos = int(procurement["supply_risk_po_count"])

    domains = [
        {
            "name": "Fulfillment",
            "status": domain_status(fulfillment_alerts, fulfillment_overdue, int(fulfillment["due_today"])),
            "headline": f"{fulfillment_overdue} overdue",
            "detail": f"{int(fulfillment['open_window'])} open in 30-day window / {int(fulfillment['due_today'])} due today",
            "target": "Fulfillment",
        },
        {
            "name": "Delivery",
            "status": domain_status(delivery_alerts, delivery_overdue, int(delivery["pending"])),
            "headline": f"{int(delivery['pending'])} awaiting confirmation",
            "detail": f"{delivery_overdue} overdue / {int(delivery['due_today_pending'])} due today",
            "target": "Delivery",
        },
        {
            "name": "Inventory",
            "status": domain_status(inventory_alerts, inventory_attention),
            "headline": f"{int(inventory['supply_risk'])} supply-risk items",
            "detail": f"{int(inventory['critical_supply_risk'])} critical / {int(inventory['total'])} items tracked",
            "target": "Inventory",
        },
        {
            "name": "Procurement",
            "status": domain_status(
                procurement_alerts,
                max(procurement_overdue, procurement_supply_risk_pos),
                int(procurement["open_po"]),
            ),
            "headline": f"{int(procurement['open_po'])} open POs",
            "detail": (
                f"{procurement_supply_risk_pos} linked to supply-risk inventory / "
                f"{procurement_overdue} overdue / "
                f"{int(procurement['outstanding_outers'])} outstanding outers"
            ),
            "target": "Procurement",
        },
        {
            "name": "Cold Chain",
            "status": domain_status(cold_chain_alerts, 0),
            "headline": f"{int(sensors['coldroom']) + int(sensors['vehicle'])} sensors tracked",
            "detail": f"{int(sensors['coldroom'])} cold-room / {int(sensors['vehicle'])} vehicle / {cold_chain_alerts} active alerts",
            "target": "Cold Chain",
        },
    ]

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc),
        "as_of_date": as_of_date,
        "kpis": {
            "active_exceptions": int(alert_summary["active"]),
            "fulfillment_overdue": fulfillment_overdue,
            "delivery_pending": int(delivery["pending"]),
            "delivery_overdue": delivery_overdue,
            "inventory_watch": inventory_attention,
        },
        "workload": {
            "fulfillment_open_window": int(fulfillment["open_window"]),
            "fulfillment_all_time_open": int(fulfillment["all_time_open"]),
            "fulfillment_due_today": int(fulfillment["due_today"]),
            "fulfillment_backorders": int(fulfillment["backorders"]),
            "delivery_pending": int(delivery["pending"]),
            "delivery_due_today": int(delivery["due_today_pending"]),
            "procurement_open": int(procurement["open_po"]),
            "procurement_overdue": procurement_overdue,
            "procurement_supply_risk_pos": procurement_supply_risk_pos,
            "coldroom_sensors": int(sensors["coldroom"]),
            "vehicle_sensors": int(sensors["vehicle"]),
        },
        "alert_summary": alert_summary,
        "domains": domains,
        "recent_alerts": recent_alerts,
        "latest_activity": latest_activity,
        "platform": {
            "pipeline_cutoff": pipeline_cutoff,
            "source_frontier": source_frontier,
            "watermark_aligned": pipeline_cutoff == source_frontier and pipeline_cutoff is not None,
            "quality": quality,
            "freshness": freshness,
        },
    }
    return JSONResponse(content=jsonable_encoder(result))


@router.get("/alerts")
def alert_list(status: str = Query("active", pattern="^(active|all|open|acknowledged|resolved)$"), limit: int = Query(200, ge=1, le=500)) -> JSONResponse:
    status_sql = {
        "active": "a.status IN ('open','acknowledged')",
        "all": "TRUE",
        "open": "a.status='open'",
        "acknowledged": "a.status='acknowledged'",
        "resolved": "a.status='resolved'",
    }[status]
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"""
                SELECT a.alert_id,a.rule_id,r.domain,r.description,a.entity_type,a.entity_id,a.severity,a.status,
                       a.opened_at,a.last_observed_at,a.acknowledged_at,a.acknowledged_by,a.resolved_at,a.resolved_by,
                       a.observed_value,a.threshold_value,a.source_event_id,a.resolution_reason
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE {status_sql}
                ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         a.last_observed_at DESC,a.alert_id DESC
                LIMIT %s
            """,(limit,))
            rows=[dict(r) for r in cur.fetchall()]
    return JSONResponse(content=jsonable_encoder({'generated_at':datetime.now(timezone.utc),'status':status,'count':len(rows),'items':rows}))

@router.get("/alerts/{alert_id}")
def alert_detail(alert_id: int) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.alert_id,a.rule_id,r.domain,r.description,r.parameters,a.entity_type,a.entity_id,a.severity,a.status,
                       a.opened_at,a.last_observed_at,a.acknowledged_at,a.acknowledged_by,a.resolved_at,a.resolved_by,
                       a.observed_value,a.threshold_value,a.source_event_id,a.resolution_reason
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE a.alert_id=%s
            """,(alert_id,))
            row=cur.fetchone()
    if row is None: raise HTTPException(status_code=404,detail='Alert not found')
    return JSONResponse(content=jsonable_encoder({'generated_at':datetime.now(timezone.utc),'alert':dict(row)}))



@router.get("/exception-cases")
def exception_case_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=10, le=100),
    domain: str = Query("all", pattern="^(all|fulfillment|delivery|inventory|procurement|cold_chain)$"),
    severity: str = Query("all", pattern="^(all|critical|warning|info)$"),
    status: str = Query("active", pattern="^(active|open|acknowledged)$"),
    search: str = Query("", max_length=100),
) -> JSONResponse:
    conditions = []
    params: list[Any] = []

    if status == "active":
        conditions.append("a.status IN ('open','acknowledged')")
    elif status == "open":
        conditions.append("a.status='open'")
    else:
        conditions.append("a.status='acknowledged'")

    if domain != "all":
        conditions.append("r.domain=%s")
        params.append(domain)
    if severity != "all":
        conditions.append("a.severity=%s")
        params.append(severity)
    if search.strip():
        needle = f"%{search.strip()}%"
        conditions.append(
            "(a.entity_id ILIKE %s OR a.entity_type ILIKE %s OR a.rule_id ILIKE %s "
            "OR r.description ILIKE %s OR r.domain ILIKE %s)"
        )
        params.extend([needle] * 5)

    where_sql = " AND ".join(conditions)
    offset = (page - 1) * page_size

    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT count(*)::int AS total
                FROM (
                    SELECT a.entity_type,a.entity_id,r.domain
                    FROM alert.alerts a
                    JOIN alert.rule_config r ON r.rule_id=a.rule_id
                    WHERE {where_sql}
                    GROUP BY a.entity_type,a.entity_id,r.domain
                ) grouped
                """,
                tuple(params),
            )
            total = int(cur.fetchone()["total"])

            cur.execute(
                f"""
                SELECT
                    a.entity_type,
                    a.entity_id,
                    r.domain,
                    CASE min(CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END)
                        WHEN 0 THEN 'critical'
                        WHEN 1 THEN 'warning'
                        ELSE 'info'
                    END AS severity,
                    CASE WHEN bool_or(a.status='open') THEN 'open' ELSE 'acknowledged' END AS status,
                    min(a.opened_at) AS opened_at,
                    max(a.last_observed_at) AS last_observed_at,
                    count(*)::int AS signal_count,
                    jsonb_agg(
                        jsonb_build_object(
                            'alert_id',a.alert_id,
                            'rule_id',a.rule_id,
                            'description',r.description,
                            'severity',a.severity,
                            'status',a.status,
                            'opened_at',a.opened_at,
                            'last_observed_at',a.last_observed_at
                        )
                        ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                                 a.last_observed_at DESC,
                                 a.alert_id DESC
                    ) AS signals
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE {where_sql}
                GROUP BY a.entity_type,a.entity_id,r.domain
                ORDER BY
                    min(CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END),
                    max(a.last_observed_at) DESC,
                    a.entity_type,
                    a.entity_id
                LIMIT %s OFFSET %s
                """,
                tuple(params + [page_size, offset]),
            )
            items = [dict(row) for row in cur.fetchall()]

    total_pages = max(1, (total + page_size - 1) // page_size)
    return JSONResponse(
        content=jsonable_encoder(
            {
                "generated_at": datetime.now(timezone.utc),
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages,
                "filters": {
                    "domain": domain,
                    "severity": severity,
                    "status": status,
                    "search": search,
                },
                "items": items,
            }
        )
    )


@router.get("/exception-cases/{entity_type}/{entity_id}")
def exception_case_detail(entity_type: str, entity_id: str) -> JSONResponse:
    with pg_connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    a.alert_id,a.rule_id,r.domain,r.description,r.parameters,
                    a.entity_type,a.entity_id,a.severity,a.status,
                    a.opened_at,a.last_observed_at,a.acknowledged_at,a.acknowledged_by,
                    a.resolved_at,a.resolved_by,a.observed_value,a.threshold_value,
                    a.source_event_id,a.resolution_reason
                FROM alert.alerts a
                JOIN alert.rule_config r ON r.rule_id=a.rule_id
                WHERE a.entity_type=%s
                  AND a.entity_id=%s
                  AND a.status IN ('open','acknowledged')
                ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,
                         a.last_observed_at DESC,
                         a.alert_id DESC
                """,
                (entity_type, entity_id),
            )
            alerts = [dict(row) for row in cur.fetchall()]

    for alert in alerts:
        alert.update(
            explain_alert(
                alert["rule_id"],
                alert["description"],
                alert.get("observed_value"),
                alert.get("threshold_value"),
            )
        )

    if not alerts:
        raise HTTPException(status_code=404, detail="Active exception case not found")

    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    severity_value = min(
        (row["severity"] for row in alerts),
        key=lambda value: severity_rank.get(value, 9),
    )
    case = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "domain": alerts[0]["domain"],
        "severity": severity_value,
        "status": "open" if any(row["status"] == "open" for row in alerts) else "acknowledged",
        "opened_at": min(row["opened_at"] for row in alerts),
        "last_observed_at": max(row["last_observed_at"] for row in alerts),
        "signal_count": len(alerts),
        "alerts": alerts,
    }
    return JSONResponse(
        content=jsonable_encoder(
            {"generated_at": datetime.now(timezone.utc), "case": case}
        )
    )
