{{ config(materialized='incremental', unique_key='purchase_order_line_key', incremental_strategy='delete+insert') }}
with src as (
    select
        p.*,
        (p.date_key::timestamp + interval '1 day' - interval '1 microsecond') as business_asof_ts
    from {{ source('staging', 'purchase_line') }} p
    {% if is_incremental() %}
    where {{ incremental_fact_filter('purchase_line','p') }}
    {% endif %}
), enriched as (
    select
        s.*,
        po.expected_delivery_date,
        po.delivery_method_id,
        p.product_key,
        sup.supplier_key,
        dm.delivery_method_key,
        pt.package_type_key
    from src s
    left join {{ source('staging', 'purchase_order_state') }} po on po.purchase_order_id = s.wwi_purchase_order_id
    left join {{ ref('dim_product') }} p
      on p.stock_item_id = s.wwi_stock_item_id
     and s.business_asof_ts >= p.valid_from and s.business_asof_ts < p.valid_to
    left join {{ ref('dim_supplier') }} sup
      on sup.supplier_id = s.wwi_supplier_id
     and s.business_asof_ts >= sup.valid_from and s.business_asof_ts < sup.valid_to
    left join {{ ref('dim_delivery_method') }} dm on dm.delivery_method_id = po.delivery_method_id
    left join {{ ref('dim_package_type') }} pt on pt.package_type_name = s.package
)
select
    {{ surrogate_key(["'purchase_order_line'", 'wwi_purchase_order_id', 'wwi_stock_item_id']) }} as purchase_order_line_key,
    wwi_purchase_order_id as purchase_order_id,
    to_char(date_key, 'YYYYMMDD')::integer as order_date_key,
    case when expected_delivery_date is not null then to_char(expected_delivery_date, 'YYYYMMDD')::integer end as expected_delivery_date_key,
    product_key,
    supplier_key,
    delivery_method_key,
    package_type_key,
    wwi_stock_item_id as stock_item_id,
    wwi_supplier_id as supplier_id,
    ordered_outers,
    ordered_quantity,
    received_outers,
    package as package_name,
    is_order_finalized,
    last_modified_when
from enriched