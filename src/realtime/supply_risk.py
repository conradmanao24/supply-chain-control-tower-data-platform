from __future__ import annotations

from typing import Any

from psycopg2.extras import RealDictCursor


INVENTORY_PROJECTION_CTES = """
WITH params AS (
    SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
    FROM control.source_frontier
    WHERE source_name='WideWorldImporters'
),
inbound_lines AS (
    SELECT
        f.stock_item_id,
        f.purchase_order_id,
        f.supplier_id,
        ed.calendar_date AS expected_delivery_date,
        greatest(f.ordered_outers-f.received_outers,0)::bigint AS outstanding_outers,
        (
            greatest(f.ordered_outers-f.received_outers,0)
            * CASE
                WHEN f.ordered_outers > 0
                THEN f.ordered_quantity::numeric / f.ordered_outers
                ELSE 0
              END
        )::bigint AS outstanding_units
    FROM core.fact_purchase_order_line f
    JOIN realtime.current_procurement_state cps
      ON cps.purchase_order_id=f.purchase_order_id
    JOIN core.dim_date od ON od.date_key=f.order_date_key
    LEFT JOIN core.dim_date ed ON ed.date_key=f.expected_delivery_date_key
    CROSS JOIN params p
    WHERE od.calendar_date BETWEEN p.as_of - interval '29 days' AND p.as_of
      AND NOT cps.is_order_finalized
      AND greatest(f.ordered_outers-f.received_outers,0) > 0
),
inbound AS (
    SELECT
        stock_item_id,
        coalesce(sum(outstanding_units),0)::bigint AS incoming_units,
        min(expected_delivery_date) AS next_inbound_date,
        count(DISTINCT purchase_order_id)::int AS inbound_po_count
    FROM inbound_lines
    GROUP BY stock_item_id
),
open_demand_base AS (
    SELECT
        f.stock_item_id,
        f.order_id,
        f.quantity::bigint AS quantity,
        o.expected_delivery_date
    FROM core.fact_order_line f
    JOIN realtime.current_order_state o ON o.order_id=f.order_id
    CROSS JOIN params p
    WHERE o.order_date BETWEEN p.as_of - interval '29 days' AND p.as_of
      AND o.picking_completed_when IS NULL
      AND f.picking_completed_when IS NULL
),
open_demand AS (
    SELECT
        d.stock_item_id,
        coalesce(sum(d.quantity),0)::bigint AS open_demand_units,
        coalesce(
            sum(d.quantity) FILTER (
                WHERE d.expected_delivery_date < coalesce(
                    i.next_inbound_date,
                    p.as_of + interval '100 years'
                )
            ),
            0
        )::bigint AS demand_before_inbound_units,
        count(DISTINCT d.order_id)::int AS affected_orders,
        min(d.expected_delivery_date) AS earliest_demand_due
    FROM open_demand_base d
    CROSS JOIN params p
    LEFT JOIN inbound i ON i.stock_item_id=d.stock_item_id
    GROUP BY d.stock_item_id
),
velocity AS (
    SELECT
        m.stock_item_id,
        abs(
            coalesce(
                sum(m.quantity) FILTER (
                    WHERE m.quantity < 0 AND m.customer_id IS NOT NULL
                ),
                0
            )
        )::numeric AS outbound_units_30d
    FROM core.fact_inventory_movement m
    JOIN core.dim_date d ON d.date_key=m.date_key
    CROSS JOIN params p
    WHERE d.calendar_date BETWEEN p.as_of - interval '29 days' AND p.as_of
    GROUP BY m.stock_item_id
),
projection AS (
    SELECT
        p.as_of,
        i.stock_item_id,
        i.stock_item_name,
        i.quantity_on_hand,
        i.last_stocktake_quantity,
        i.reorder_level,
        i.target_stock_level AS typical_order_quantity,
        i.last_edited_when,
        i.refreshed_at,
        coalesce(d.open_demand_units,0)::bigint AS open_demand_units,
        coalesce(d.demand_before_inbound_units,0)::bigint AS demand_before_inbound_units,
        coalesce(b.incoming_units,0)::bigint AS incoming_units,
        coalesce(d.affected_orders,0)::int AS affected_orders,
        d.earliest_demand_due,
        b.next_inbound_date,
        coalesce(b.inbound_po_count,0)::int AS inbound_po_count,
        coalesce(v.outbound_units_30d,0)::numeric AS outbound_units_30d,
        CASE
            WHEN coalesce(v.outbound_units_30d,0) > 0
            THEN round(
                i.quantity_on_hand
                / nullif(v.outbound_units_30d / 30.0, 0),
                2
            )
            ELSE NULL
        END AS days_of_cover,
        CASE
            WHEN b.next_inbound_date IS NOT NULL
            THEN (b.next_inbound_date-p.as_of)::int
            ELSE NULL
        END AS days_to_next_inbound,
        (
            i.quantity_on_hand
            - coalesce(d.demand_before_inbound_units,0)
        )::bigint AS pre_inbound_balance,
        (
            i.quantity_on_hand
            + coalesce(b.incoming_units,0)
            - coalesce(d.open_demand_units,0)
        )::bigint AS projected_available,
        greatest(
            coalesce(d.demand_before_inbound_units,0)-i.quantity_on_hand,
            0
        )::bigint AS pre_inbound_shortfall_units,
        greatest(
            coalesce(d.open_demand_units,0)
            - i.quantity_on_hand
            - coalesce(b.incoming_units,0),
            0
        )::bigint AS projected_shortfall_units
    FROM realtime.current_inventory_state i
    CROSS JOIN params p
    LEFT JOIN open_demand d ON d.stock_item_id=i.stock_item_id
    LEFT JOIN inbound b ON b.stock_item_id=i.stock_item_id
    LEFT JOIN velocity v ON v.stock_item_id=i.stock_item_id
),
scored AS (
    SELECT
        projection.*,
        CASE
            WHEN quantity_on_hand < 0 THEN 'negative_stock'
            WHEN projected_available < 0 THEN 'projected_shortfall'
            WHEN pre_inbound_balance < 0 THEN 'stockout_before_inbound'
            WHEN days_of_cover IS NOT NULL
             AND days_to_next_inbound IS NOT NULL
             AND days_to_next_inbound > 0
             AND days_of_cover < days_to_next_inbound
            THEN 'coverage_gap'
            WHEN quantity_on_hand <= reorder_level THEN 'reorder'
            ELSE 'healthy'
        END AS coverage_state,
        CASE
            WHEN quantity_on_hand < 0 OR projected_available < 0 THEN 'critical'
            WHEN pre_inbound_balance < 0 THEN 'critical'
            WHEN days_of_cover IS NOT NULL
             AND days_to_next_inbound IS NOT NULL
             AND days_to_next_inbound > 0
             AND days_of_cover < days_to_next_inbound
            THEN 'warning'
            WHEN quantity_on_hand <= reorder_level THEN 'warning'
            ELSE 'healthy'
        END AS coverage_severity
    FROM projection
)
"""


SUPPLIER_PERFORMANCE_CTES = """
WITH params AS (
    SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
    FROM control.source_frontier
    WHERE source_name='WideWorldImporters'
),
receipts AS (
    SELECT
        purchase_order_id,
        max(transaction_occurred_when::date) AS last_receipt_date
    FROM core.fact_inventory_movement
    WHERE purchase_order_id IS NOT NULL
      AND quantity > 0
    GROUP BY purchase_order_id
),
historical_po AS (
    SELECT
        f.purchase_order_id,
        f.supplier_id,
        min(od.calendar_date) AS order_date,
        max(ed.calendar_date) AS expected_delivery_date,
        bool_and(f.is_order_finalized) AS finalized,
        sum(f.ordered_outers)::bigint AS ordered_outers,
        sum(f.received_outers)::bigint AS received_outers
    FROM core.fact_purchase_order_line f
    JOIN core.dim_date od ON od.date_key=f.order_date_key
    LEFT JOIN core.dim_date ed ON ed.date_key=f.expected_delivery_date_key
    CROSS JOIN params p
    WHERE od.calendar_date BETWEEN p.as_of - interval '179 days' AND p.as_of
    GROUP BY f.purchase_order_id,f.supplier_id
),
po_performance AS (
    SELECT
        po.*,
        r.last_receipt_date,
        (po.received_outers >= po.ordered_outers) AS in_full,
        (
            r.last_receipt_date IS NOT NULL
            AND po.expected_delivery_date IS NOT NULL
            AND r.last_receipt_date <= po.expected_delivery_date
        ) AS on_time,
        greatest(
            coalesce(r.last_receipt_date-po.expected_delivery_date,0),
            0
        )::int AS delay_days
    FROM historical_po po
    LEFT JOIN receipts r USING(purchase_order_id)
    WHERE po.finalized
),
supplier_performance AS (
    SELECT
        p.supplier_id,
        coalesce(s.supplier_name,'Supplier '||p.supplier_id::text) AS supplier_name,
        count(*)::int AS finalized_po_count,
        round(
            100.0 * avg((p.on_time AND p.in_full)::int),
            1
        ) AS otif_pct,
        round(avg(p.delay_days)::numeric,1) AS avg_delay_days,
        count(*) FILTER (WHERE NOT p.on_time)::int AS late_po_count,
        count(*) FILTER (WHERE NOT p.in_full)::int AS incomplete_po_count
    FROM po_performance p
    LEFT JOIN core.dim_supplier s
      ON s.supplier_id=p.supplier_id
     AND s.is_current
    GROUP BY p.supplier_id,s.supplier_name
)
"""


def fetch_inventory_projection(
    cur: RealDictCursor,
    stock_item_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if stock_item_id is not None:
        conditions.append("stock_item_id=%s")
        params.append(stock_item_id)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT %s"
        params.append(limit)

    cur.execute(
        INVENTORY_PROJECTION_CTES
        + f"""
        SELECT *
        FROM scored
        {where_sql}
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
        {limit_sql}
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_supplier_performance(
    cur: RealDictCursor,
    supplier_id: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if supplier_id is not None:
        conditions.append("supplier_id=%s")
        params.append(supplier_id)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT %s"
        params.append(limit)

    cur.execute(
        SUPPLIER_PERFORMANCE_CTES
        + f"""
        SELECT *
        FROM supplier_performance
        {where_sql}
        ORDER BY otif_pct ASC, late_po_count DESC, finalized_po_count DESC
        {limit_sql}
        """,
        params,
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_open_orders_for_sku(
    cur: RealDictCursor,
    stock_item_id: int,
    limit: int = 8,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        WITH p AS (
            SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
            FROM control.source_frontier
            WHERE source_name='WideWorldImporters'
        )
        SELECT
            o.order_id,
            o.customer_id,
            coalesce(c.customer_name,'Customer '||o.customer_id::text)
                AS customer_name,
            o.order_date,
            o.expected_delivery_date,
            f.quantity::bigint AS demand_units,
            greatest((p.as_of-o.expected_delivery_date),0)::int AS days_overdue
        FROM core.fact_order_line f
        JOIN realtime.current_order_state o ON o.order_id=f.order_id
        CROSS JOIN p
        LEFT JOIN core.dim_customer c
          ON c.customer_id=o.customer_id
         AND c.is_current
        WHERE f.stock_item_id=%s
          AND f.picking_completed_when IS NULL
          AND o.picking_completed_when IS NULL
          AND o.order_date BETWEEN p.as_of - interval '29 days' AND p.as_of
        ORDER BY
            o.expected_delivery_date ASC,
            o.order_id
        LIMIT %s
        """,
        (stock_item_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_open_pos_for_sku(
    cur: RealDictCursor,
    stock_item_id: int,
    limit: int = 8,
) -> list[dict[str, Any]]:
    cur.execute(
        """
        WITH p AS (
            SELECT (safe_through_cutoff - interval '1 day')::date AS as_of
            FROM control.source_frontier
            WHERE source_name='WideWorldImporters'
        )
        SELECT
            f.purchase_order_id,
            f.supplier_id,
            coalesce(s.supplier_name,'Supplier '||f.supplier_id::text)
                AS supplier_name,
            od.calendar_date AS order_date,
            ed.calendar_date AS expected_delivery_date,
            greatest(f.ordered_outers-f.received_outers,0)::bigint
                AS outstanding_outers,
            (
                greatest(f.ordered_outers-f.received_outers,0)
                * CASE
                    WHEN f.ordered_outers > 0
                    THEN f.ordered_quantity::numeric/f.ordered_outers
                    ELSE 0
                  END
            )::bigint AS outstanding_units
        FROM core.fact_purchase_order_line f
        JOIN realtime.current_procurement_state cps
          ON cps.purchase_order_id=f.purchase_order_id
        JOIN core.dim_date od ON od.date_key=f.order_date_key
        LEFT JOIN core.dim_date ed ON ed.date_key=f.expected_delivery_date_key
        CROSS JOIN p
        LEFT JOIN core.dim_supplier s
          ON s.supplier_id=f.supplier_id
         AND s.is_current
        WHERE f.stock_item_id=%s
          AND NOT cps.is_order_finalized
          AND od.calendar_date BETWEEN p.as_of - interval '29 days' AND p.as_of
          AND greatest(f.ordered_outers-f.received_outers,0) > 0
        ORDER BY ed.calendar_date ASC NULLS LAST,f.purchase_order_id
        LIMIT %s
        """,
        (stock_item_id, limit),
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_supplier_inbound_risk(cur: RealDictCursor) -> list[dict[str, Any]]:
    cur.execute(
        INVENTORY_PROJECTION_CTES
        + """
        SELECT
            f.supplier_id,
            coalesce(sup.supplier_name,'Supplier '||f.supplier_id::text)
                AS supplier_name,
            count(DISTINCT f.purchase_order_id)::int AS open_po_count,
            count(DISTINCT f.stock_item_id)::int AS inbound_sku_count,
            count(DISTINCT f.stock_item_id) FILTER (
                WHERE s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            )::int AS at_risk_sku_count,
            coalesce(sum(
                greatest(f.ordered_outers-f.received_outers,0)
                * CASE
                    WHEN f.ordered_outers>0
                    THEN f.ordered_quantity::numeric/f.ordered_outers
                    ELSE 0
                  END
            ),0)::bigint AS outstanding_units,
            coalesce(sum(
                greatest(f.ordered_outers-f.received_outers,0)
                * CASE
                    WHEN f.ordered_outers>0
                    THEN f.ordered_quantity::numeric/f.ordered_outers
                    ELSE 0
                  END
            ) FILTER (
                WHERE s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS at_risk_units,
            coalesce(sum(s.affected_orders) FILTER (
                WHERE s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS affected_order_links,
            min(ed.calendar_date) AS nearest_due
        FROM core.fact_purchase_order_line f
        JOIN realtime.current_procurement_state cps
          ON cps.purchase_order_id=f.purchase_order_id
        JOIN core.dim_date od ON od.date_key=f.order_date_key
        LEFT JOIN core.dim_date ed ON ed.date_key=f.expected_delivery_date_key
        CROSS JOIN params p
        LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
        LEFT JOIN core.dim_supplier sup
          ON sup.supplier_id=f.supplier_id
         AND sup.is_current
        WHERE od.calendar_date BETWEEN p.as_of-interval '29 days' AND p.as_of
          AND NOT cps.is_order_finalized
          AND greatest(f.ordered_outers-f.received_outers,0) > 0
        GROUP BY f.supplier_id,sup.supplier_name
        ORDER BY at_risk_units DESC,outstanding_units DESC,f.supplier_id
        """
    )
    return [dict(row) for row in cur.fetchall()]


def fetch_po_risk(cur: RealDictCursor, purchase_order_id: int) -> dict[str, Any]:
    cur.execute(
        INVENTORY_PROJECTION_CTES
        + """
        SELECT
            f.purchase_order_id,
            count(DISTINCT f.stock_item_id)::int AS sku_count,
            count(DISTINCT f.stock_item_id) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            )::int AS at_risk_sku_count,
            coalesce(sum(
                greatest(f.ordered_outers-f.received_outers,0)
                * CASE
                    WHEN f.ordered_outers>0
                    THEN f.ordered_quantity::numeric/f.ordered_outers
                    ELSE 0
                  END
            ) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS at_risk_units,
            coalesce(sum(s.affected_orders) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS affected_order_links
        FROM core.fact_purchase_order_line f
        JOIN realtime.current_procurement_state p
          ON p.purchase_order_id=f.purchase_order_id
        LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
        WHERE f.purchase_order_id=%s
        GROUP BY f.purchase_order_id
        """,
        (purchase_order_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else {
        "purchase_order_id": purchase_order_id,
        "sku_count": 0,
        "at_risk_sku_count": 0,
        "at_risk_units": 0,
        "affected_order_links": 0,
    }


def fetch_po_risks(
    cur: RealDictCursor,
    purchase_order_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not purchase_order_ids:
        return {}
    cur.execute(
        INVENTORY_PROJECTION_CTES
        + """
        SELECT
            f.purchase_order_id,
            count(DISTINCT f.stock_item_id)::int AS sku_count,
            count(DISTINCT f.stock_item_id) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            )::int AS at_risk_sku_count,
            coalesce(sum(
                greatest(f.ordered_outers-f.received_outers,0)
                * CASE
                    WHEN f.ordered_outers>0
                    THEN f.ordered_quantity::numeric/f.ordered_outers
                    ELSE 0
                  END
            ) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS at_risk_units,
            coalesce(sum(s.affected_orders) FILTER (
                WHERE NOT p.is_order_finalized
                  AND greatest(f.ordered_outers-f.received_outers,0) > 0
                  AND s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ),0)::bigint AS affected_order_links
        FROM core.fact_purchase_order_line f
        JOIN realtime.current_procurement_state p
          ON p.purchase_order_id=f.purchase_order_id
        LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
        WHERE f.purchase_order_id=ANY(%s)
        GROUP BY f.purchase_order_id
        """,
        (purchase_order_ids,),
    )
    return {
        int(row["purchase_order_id"]): dict(row)
        for row in cur.fetchall()
    }


def fetch_order_supply_risks(
    cur: RealDictCursor,
    order_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not order_ids:
        return {}
    cur.execute(
        INVENTORY_PROJECTION_CTES
        + """
        SELECT
            f.order_id,
            count(DISTINCT f.stock_item_id) FILTER (
                WHERE s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            )::int AS supply_exposed_sku_count,
            count(DISTINCT f.stock_item_id) FILTER (
                WHERE s.coverage_severity='critical'
            )::int AS critical_supply_sku_count,
            coalesce(sum(s.pre_inbound_shortfall_units) FILTER (
                WHERE s.coverage_severity='critical'
            ),0)::bigint AS linked_pre_inbound_shortfall_units,
            min(s.days_of_cover) FILTER (
                WHERE s.coverage_state IN (
                    'negative_stock',
                    'projected_shortfall',
                    'stockout_before_inbound',
                    'coverage_gap'
                )
            ) AS minimum_days_of_cover
        FROM core.fact_order_line f
        LEFT JOIN scored s ON s.stock_item_id=f.stock_item_id
        WHERE f.order_id=ANY(%s)
          AND f.picking_completed_when IS NULL
        GROUP BY f.order_id
        """,
        (order_ids,),
    )
    return {int(row["order_id"]): dict(row) for row in cur.fetchall()}
