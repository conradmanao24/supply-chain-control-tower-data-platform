CREATE SCHEMA IF NOT EXISTS realtime;

CREATE TABLE IF NOT EXISTS realtime.event_log (
    event_id uuid PRIMARY KEY,
    schema_version integer NOT NULL,
    event_type text NOT NULL,
    entity_type text NOT NULL,
    source_table text NOT NULL,
    operation text NOT NULL,
    occurred_at_utc timestamptz NOT NULL,
    payload jsonb NOT NULL,
    processing_result text NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_realtime_event_log_processed_at ON realtime.event_log(processed_at DESC);
CREATE INDEX IF NOT EXISTS ix_realtime_event_log_type ON realtime.event_log(event_type, processed_at DESC);

CREATE TABLE IF NOT EXISTS realtime.current_order_state (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL,
    order_date date NOT NULL,
    expected_delivery_date date NOT NULL,
    is_undersupply_backordered boolean NOT NULL,
    backorder_order_id integer NULL,
    picking_completed_when timestamp NULL,
    last_edited_when timestamp NOT NULL,
    source_event_id uuid NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime.current_delivery_state (
    invoice_id integer PRIMARY KEY,
    order_id integer NULL,
    customer_id integer NOT NULL,
    delivery_method_id integer NOT NULL,
    invoice_date date NOT NULL,
    delivery_run text NULL,
    run_position text NULL,
    returned_delivery_data jsonb NULL,
    confirmed_delivery_time timestamp NULL,
    confirmed_received_by text NULL,
    last_edited_when timestamp NOT NULL,
    source_event_id uuid NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime.current_procurement_state (
    purchase_order_id integer PRIMARY KEY,
    supplier_id integer NOT NULL,
    order_date date NOT NULL,
    expected_delivery_date date NULL,
    is_order_finalized boolean NOT NULL,
    ordered_outers bigint NOT NULL,
    received_outers bigint NOT NULL,
    under_received_line_count integer NOT NULL,
    last_edited_when timestamp NOT NULL,
    source_event_id uuid NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime.current_inventory_state (
    stock_item_id integer PRIMARY KEY,
    stock_item_name text NOT NULL,
    quantity_on_hand integer NOT NULL,
    last_stocktake_quantity integer NOT NULL,
    reorder_level integer NOT NULL,
    target_stock_level integer NOT NULL,
    last_edited_when timestamp NOT NULL,
    source_event_id uuid NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime.current_sensor_state (
    sensor_key text PRIMARY KEY,
    sensor_type text NOT NULL CHECK (sensor_type IN ('coldroom','vehicle')),
    vehicle_registration text NULL,
    sensor_number integer NOT NULL,
    recorded_when timestamp NOT NULL,
    temperature numeric(18,4) NOT NULL,
    reading_count integer NULL,
    value_basis text NOT NULL,
    source_event_id uuid NULL,
    refreshed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS realtime.sensor_reading_history (
    sensor_key text NOT NULL,
    sensor_type text NOT NULL CHECK (sensor_type IN ('coldroom','vehicle')),
    vehicle_registration text NULL,
    sensor_number integer NOT NULL,
    recorded_when timestamp NOT NULL,
    temperature numeric(18,4) NOT NULL,
    source_event_id uuid NULL,
    inserted_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sensor_key, recorded_when)
);
CREATE INDEX IF NOT EXISTS ix_sensor_reading_history_sensor_time
    ON realtime.sensor_reading_history(sensor_key, recorded_when DESC);
CREATE INDEX IF NOT EXISTS ix_sensor_reading_history_inserted_at
    ON realtime.sensor_reading_history(inserted_at DESC);

INSERT INTO realtime.current_order_state
(order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,backorder_order_id,picking_completed_when,last_edited_when,source_event_id)
SELECT order_id,customer_id,order_date,expected_delivery_date,is_undersupply_backordered,backorder_order_id,picking_completed_when,last_edited_when,NULL
FROM staging.order_state
ON CONFLICT (order_id) DO NOTHING;

INSERT INTO realtime.current_delivery_state
(invoice_id,order_id,customer_id,delivery_method_id,invoice_date,delivery_run,run_position,returned_delivery_data,confirmed_delivery_time,confirmed_received_by,last_edited_when,source_event_id)
SELECT invoice_id,order_id,customer_id,delivery_method_id,invoice_date,delivery_run,run_position,
       CASE WHEN returned_delivery_data IS NULL THEN NULL ELSE returned_delivery_data::jsonb END,
       confirmed_delivery_time,confirmed_received_by,last_edited_when,NULL
FROM staging.invoice_delivery
ON CONFLICT (invoice_id) DO NOTHING;

INSERT INTO realtime.current_procurement_state
(purchase_order_id,supplier_id,order_date,expected_delivery_date,is_order_finalized,ordered_outers,received_outers,under_received_line_count,last_edited_when,source_event_id)
SELECT p.purchase_order_id,p.supplier_id,p.order_date,p.expected_delivery_date,p.is_order_finalized,
       COALESCE(a.ordered_outers,0),COALESCE(a.received_outers,0),COALESCE(a.under_received_line_count,0),p.last_edited_when,NULL
FROM staging.purchase_order_state p
LEFT JOIN (
    SELECT wwi_purchase_order_id,
           SUM(ordered_outers)::bigint AS ordered_outers,
           SUM(received_outers)::bigint AS received_outers,
           COUNT(*) FILTER (WHERE received_outers < ordered_outers)::integer AS under_received_line_count
    FROM staging.purchase_line
    GROUP BY wwi_purchase_order_id
) a ON a.wwi_purchase_order_id=p.purchase_order_id
ON CONFLICT (purchase_order_id) DO NOTHING;

INSERT INTO realtime.current_inventory_state
(stock_item_id,stock_item_name,quantity_on_hand,last_stocktake_quantity,reorder_level,target_stock_level,last_edited_when,source_event_id)
SELECT h.stock_item_id,p.stock_item_name,h.quantity_on_hand,h.last_stocktake_quantity,h.reorder_level,h.target_stock_level,h.last_edited_when,NULL
FROM staging.stock_holding_current h
JOIN staging.product_current p ON p.stock_item_id=h.stock_item_id
ON CONFLICT (stock_item_id) DO NOTHING;

INSERT INTO realtime.current_sensor_state
(sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,reading_count,value_basis,source_event_id)
SELECT 'coldroom:'||sensor_number,'coldroom',NULL,sensor_number,last_recorded_when,avg_temperature,reading_count::integer,'5m_seed',NULL
FROM (
    SELECT DISTINCT ON (sensor_number) sensor_number,last_recorded_when,avg_temperature,reading_count,bucket_start
    FROM staging.coldroom_5m
    ORDER BY sensor_number,bucket_start DESC
) x
ON CONFLICT (sensor_key) DO NOTHING;

INSERT INTO realtime.current_sensor_state
(sensor_key,sensor_type,vehicle_registration,sensor_number,recorded_when,temperature,reading_count,value_basis,source_event_id)
SELECT 'vehicle:'||vehicle_registration||':'||sensor_number,'vehicle',vehicle_registration,sensor_number,last_recorded_when,avg_temperature,reading_count::integer,'5m_seed',NULL
FROM (
    SELECT DISTINCT ON (vehicle_registration,sensor_number) vehicle_registration,sensor_number,last_recorded_when,avg_temperature,reading_count,bucket_start
    FROM staging.vehicle_5m
    ORDER BY vehicle_registration,sensor_number,bucket_start DESC
) x
ON CONFLICT (sensor_key) DO NOTHING;