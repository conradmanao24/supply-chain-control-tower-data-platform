-- serving layer serving-layer indexes
-- Supports interactive drill-down without scanning the full analytical fact table.

CREATE INDEX IF NOT EXISTS ix_fact_order_line_order_id
    ON core.fact_order_line(order_id);
