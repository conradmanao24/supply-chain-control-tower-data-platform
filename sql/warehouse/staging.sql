CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.order_line (
    order_date_key date NOT NULL,
    picked_date_key date NULL,
    wwi_order_id integer NOT NULL,
    wwi_backorder_id integer NULL,
    description text NOT NULL,
    package text NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    tax_rate numeric(18,4) NOT NULL,
    total_excluding_tax numeric(18,4) NOT NULL,
    tax_amount numeric(18,4) NOT NULL,
    total_including_tax numeric(18,4) NOT NULL,
    wwi_city_id integer NOT NULL,
    wwi_customer_id integer NOT NULL,
    wwi_stock_item_id integer NOT NULL,
    wwi_salesperson_id integer NOT NULL,
    wwi_picker_id integer NULL,
    last_modified_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wwi_order_id, wwi_stock_item_id)
);

CREATE TABLE IF NOT EXISTS staging.sale_line (
    invoice_date_key date NOT NULL,
    delivery_date_key date NULL,
    wwi_invoice_id integer NOT NULL,
    description text NOT NULL,
    package text NOT NULL,
    quantity integer NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    tax_rate numeric(18,4) NOT NULL,
    total_excluding_tax numeric(18,4) NOT NULL,
    tax_amount numeric(18,4) NOT NULL,
    profit numeric(18,4) NOT NULL,
    total_including_tax numeric(18,4) NOT NULL,
    total_dry_items integer NOT NULL,
    total_chiller_items integer NOT NULL,
    wwi_city_id integer NOT NULL,
    wwi_customer_id integer NOT NULL,
    wwi_bill_to_customer_id integer NOT NULL,
    wwi_stock_item_id integer NOT NULL,
    wwi_salesperson_id integer NOT NULL,
    last_modified_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wwi_invoice_id, wwi_stock_item_id)
);

CREATE TABLE IF NOT EXISTS staging.inventory_movement (
    date_key date NOT NULL,
    wwi_stock_item_transaction_id bigint PRIMARY KEY,
    wwi_invoice_id integer NULL,
    wwi_purchase_order_id integer NULL,
    quantity integer NOT NULL,
    wwi_stock_item_id integer NOT NULL,
    wwi_customer_id integer NULL,
    wwi_supplier_id integer NULL,
    wwi_transaction_type_id integer NOT NULL,
    transaction_occurred_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.purchase_line (
    date_key date NOT NULL,
    wwi_purchase_order_id integer NOT NULL,
    ordered_outers integer NOT NULL,
    ordered_quantity integer NOT NULL,
    received_outers integer NOT NULL,
    package text NOT NULL,
    is_order_finalized boolean NOT NULL,
    wwi_supplier_id integer NOT NULL,
    wwi_stock_item_id integer NOT NULL,
    last_modified_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (wwi_purchase_order_id, wwi_stock_item_id)
);

CREATE TABLE IF NOT EXISTS staging.financial_transaction (
    date_key date NOT NULL,
    wwi_customer_transaction_id integer NULL,
    wwi_supplier_transaction_id integer NULL,
    wwi_invoice_id integer NULL,
    wwi_purchase_order_id integer NULL,
    supplier_invoice_number text NULL,
    total_excluding_tax numeric(18,4) NOT NULL,
    tax_amount numeric(18,4) NOT NULL,
    total_including_tax numeric(18,4) NOT NULL,
    outstanding_balance numeric(18,4) NOT NULL,
    is_finalized boolean NOT NULL,
    wwi_customer_id integer NULL,
    wwi_bill_to_customer_id integer NULL,
    wwi_supplier_id integer NULL,
    wwi_transaction_type_id integer NOT NULL,
    wwi_payment_method_id integer NULL,
    last_modified_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((wwi_customer_transaction_id IS NOT NULL) <> (wwi_supplier_transaction_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_customer_tx
    ON staging.financial_transaction (wwi_customer_transaction_id)
    WHERE wwi_customer_transaction_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_supplier_tx
    ON staging.financial_transaction (wwi_supplier_transaction_id)
    WHERE wwi_supplier_transaction_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS staging.order_state (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL,
    salesperson_person_id integer NOT NULL,
    picked_by_person_id integer NULL,
    contact_person_id integer NOT NULL,
    backorder_order_id integer NULL,
    order_date date NOT NULL,
    expected_delivery_date date NOT NULL,
    is_undersupply_backordered boolean NOT NULL,
    delivery_instructions text NULL,
    picking_completed_when timestamp NULL,
    last_edited_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.invoice_delivery (
    invoice_id integer PRIMARY KEY,
    customer_id integer NOT NULL,
    bill_to_customer_id integer NOT NULL,
    order_id integer NULL,
    delivery_method_id integer NOT NULL,
    contact_person_id integer NOT NULL,
    salesperson_person_id integer NOT NULL,
    packed_by_person_id integer NOT NULL,
    invoice_date date NOT NULL,
    is_credit_note boolean NOT NULL,
    delivery_instructions text NULL,
    total_dry_items integer NOT NULL,
    total_chiller_items integer NOT NULL,
    delivery_run text NULL,
    run_position text NULL,
    returned_delivery_data text NULL,
    confirmed_delivery_time timestamp NULL,
    confirmed_received_by text NULL,
    last_edited_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.purchase_order_state (
    purchase_order_id integer PRIMARY KEY,
    supplier_id integer NOT NULL,
    order_date date NOT NULL,
    delivery_method_id integer NOT NULL,
    contact_person_id integer NOT NULL,
    expected_delivery_date date NULL,
    supplier_reference text NULL,
    is_order_finalized boolean NOT NULL,
    last_edited_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.customer_current (
    customer_id integer PRIMARY KEY,
    customer_name text NOT NULL,
    bill_to_customer_id integer NOT NULL,
    customer_category_id integer NOT NULL,
    customer_category_name text NOT NULL,
    buying_group_id integer NULL,
    buying_group_name text NULL,
    delivery_method_id integer NOT NULL,
    delivery_city_id integer NOT NULL,
    postal_city_id integer NOT NULL,
    credit_limit numeric(18,2) NULL,
    account_opened_date date NOT NULL,
    standard_discount_percentage numeric(18,4) NOT NULL,
    is_statement_sent boolean NOT NULL,
    is_on_credit_hold boolean NOT NULL,
    payment_days integer NOT NULL,
    delivery_run text NULL,
    run_position text NULL,
    delivery_postal_code text NOT NULL,
    delivery_latitude double precision NULL,
    delivery_longitude double precision NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.customer_history (
    customer_id integer NOT NULL,
    bill_to_customer_id integer NOT NULL,
    customer_category_id integer NOT NULL,
    buying_group_id integer NULL,
    delivery_method_id integer NOT NULL,
    delivery_city_id integer NOT NULL,
    postal_city_id integer NOT NULL,
    credit_limit numeric(18,2) NULL,
    account_opened_date date NOT NULL,
    standard_discount_percentage numeric(18,4) NOT NULL,
    is_statement_sent boolean NOT NULL,
    is_on_credit_hold boolean NOT NULL,
    payment_days integer NOT NULL,
    delivery_run text NULL,
    run_position text NULL,
    delivery_postal_code text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (customer_id, valid_from)
);

CREATE TABLE IF NOT EXISTS staging.supplier_current (
    supplier_id integer PRIMARY KEY,
    supplier_name text NOT NULL,
    supplier_category_id integer NOT NULL,
    supplier_category_name text NOT NULL,
    delivery_method_id integer NULL,
    delivery_city_id integer NOT NULL,
    postal_city_id integer NOT NULL,
    supplier_reference text NULL,
    payment_days integer NOT NULL,
    delivery_postal_code text NOT NULL,
    delivery_latitude double precision NULL,
    delivery_longitude double precision NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.supplier_history (
    supplier_id integer NOT NULL,
    supplier_name text NOT NULL,
    supplier_category_id integer NOT NULL,
    delivery_method_id integer NULL,
    delivery_city_id integer NOT NULL,
    postal_city_id integer NOT NULL,
    supplier_reference text NULL,
    payment_days integer NOT NULL,
    delivery_postal_code text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (supplier_id, valid_from)
);

CREATE TABLE IF NOT EXISTS staging.product_current (
    stock_item_id integer PRIMARY KEY,
    stock_item_name text NOT NULL,
    supplier_id integer NOT NULL,
    supplier_name text NOT NULL,
    color_id integer NULL,
    color_name text NULL,
    unit_package_id integer NOT NULL,
    unit_package text NOT NULL,
    outer_package_id integer NOT NULL,
    outer_package text NOT NULL,
    brand text NULL,
    size text NULL,
    lead_time_days integer NOT NULL,
    quantity_per_outer integer NOT NULL,
    is_chiller_stock boolean NOT NULL,
    barcode text NULL,
    tax_rate numeric(18,4) NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    recommended_retail_price numeric(18,4) NULL,
    typical_weight_per_unit numeric(18,4) NOT NULL,
    custom_fields text NULL,
    tags text NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.product_history (
    stock_item_id integer NOT NULL,
    stock_item_name text NOT NULL,
    supplier_id integer NOT NULL,
    color_id integer NULL,
    unit_package_id integer NOT NULL,
    outer_package_id integer NOT NULL,
    brand text NULL,
    size text NULL,
    lead_time_days integer NOT NULL,
    quantity_per_outer integer NOT NULL,
    is_chiller_stock boolean NOT NULL,
    barcode text NULL,
    tax_rate numeric(18,4) NOT NULL,
    unit_price numeric(18,4) NOT NULL,
    recommended_retail_price numeric(18,4) NULL,
    typical_weight_per_unit numeric(18,4) NOT NULL,
    custom_fields text NULL,
    tags text NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (stock_item_id, valid_from)
);

CREATE TABLE IF NOT EXISTS staging.product_stock_group (
    stock_item_stock_group_id integer PRIMARY KEY,
    stock_item_id integer NOT NULL,
    stock_group_id integer NOT NULL,
    stock_group_name text NOT NULL,
    last_edited_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.stock_holding_current (
    stock_item_id integer PRIMARY KEY,
    quantity_on_hand integer NOT NULL,
    bin_location text NOT NULL,
    last_stocktake_quantity integer NOT NULL,
    last_cost_price numeric(18,4) NOT NULL,
    reorder_level integer NOT NULL,
    target_stock_level integer NOT NULL,
    last_edited_when timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.employee_current (
    person_id integer PRIMARY KEY,
    full_name text NOT NULL,
    preferred_name text NOT NULL,
    is_salesperson boolean NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.employee_history (
    person_id integer NOT NULL,
    full_name text NOT NULL,
    preferred_name text NOT NULL,
    is_salesperson boolean NOT NULL,
    is_employee boolean NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (person_id, valid_from)
);

CREATE TABLE IF NOT EXISTS staging.geography_current (
    city_id integer PRIMARY KEY,
    city_name text NOT NULL,
    state_province_id integer NOT NULL,
    state_province_code text NOT NULL,
    state_province_name text NOT NULL,
    sales_territory text NOT NULL,
    country_id integer NOT NULL,
    country_name text NOT NULL,
    continent text NOT NULL,
    region text NOT NULL,
    subregion text NOT NULL,
    latest_recorded_population bigint NULL,
    latitude double precision NULL,
    longitude double precision NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.delivery_method_current (
    delivery_method_id integer PRIMARY KEY,
    delivery_method_name text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.transaction_type_current (
    transaction_type_id integer PRIMARY KEY,
    transaction_type_name text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.payment_method_current (
    payment_method_id integer PRIMARY KEY,
    payment_method_name text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.package_type_current (
    package_type_id integer PRIMARY KEY,
    package_type_name text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.stock_group_current (
    stock_group_id integer PRIMARY KEY,
    stock_group_name text NOT NULL,
    valid_from timestamp NOT NULL,
    valid_to timestamp NOT NULL,
    ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.coldroom_5m (
    sensor_number integer NOT NULL,
    bucket_start timestamp NOT NULL,
    min_temperature numeric(10,4) NOT NULL,
    max_temperature numeric(10,4) NOT NULL,
    avg_temperature numeric(10,4) NOT NULL,
    reading_count bigint NOT NULL,
    first_recorded_when timestamp NOT NULL,
    last_recorded_when timestamp NOT NULL,
    max_gap_seconds numeric(18,3) NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (sensor_number, bucket_start)
);

CREATE TABLE IF NOT EXISTS staging.vehicle_5m (
    vehicle_registration text NOT NULL,
    sensor_number integer NOT NULL,
    bucket_start timestamp NOT NULL,
    min_temperature numeric(10,4) NOT NULL,
    max_temperature numeric(10,4) NOT NULL,
    avg_temperature numeric(10,4) NOT NULL,
    reading_count bigint NOT NULL,
    first_recorded_when timestamp NOT NULL,
    last_recorded_when timestamp NOT NULL,
    max_gap_seconds numeric(18,3) NULL,
    ingested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (vehicle_registration, sensor_number, bucket_start)
);