{{ config(materialized='incremental', unique_key='order_line_key', incremental_strategy='delete+insert') }}
with src as (
    select
        o.*,
        (o.order_date_key::timestamp + interval '1 day' - interval '1 microsecond') as business_asof_ts
    from {{ source('staging', 'order_line') }} o
    {% if is_incremental() %}
    where {{ incremental_fact_filter('order_line','o') }}
    {% endif %}
), enriched as (
    select
        s.*,
        os.expected_delivery_date,
        os.is_undersupply_backordered,
        os.picking_completed_when,
        p.product_key,
        c.customer_key,
        sp.employee_key as salesperson_key,
        pk.employee_key as picker_key,
        g.geography_key,
        pt.package_type_key
    from src s
    left join {{ source('staging', 'order_state') }} os on os.order_id = s.wwi_order_id
    left join {{ ref('dim_product') }} p
      on p.stock_item_id = s.wwi_stock_item_id
     and s.business_asof_ts >= p.valid_from and s.business_asof_ts < p.valid_to
    left join {{ ref('dim_customer') }} c
      on c.customer_id = s.wwi_customer_id
     and s.business_asof_ts >= c.valid_from and s.business_asof_ts < c.valid_to
    left join {{ ref('dim_employee') }} sp
      on sp.person_id = s.wwi_salesperson_id
     and s.business_asof_ts >= sp.valid_from and s.business_asof_ts < sp.valid_to
    left join {{ ref('dim_employee') }} pk
      on pk.person_id = s.wwi_picker_id
     and s.business_asof_ts >= pk.valid_from and s.business_asof_ts < pk.valid_to
    left join {{ ref('dim_geography') }} g on g.city_id = s.wwi_city_id
    left join {{ ref('dim_package_type') }} pt on pt.package_type_name = s.package
)
select
    {{ surrogate_key(["'order_line'", 'wwi_order_id', 'wwi_stock_item_id']) }} as order_line_key,
    wwi_order_id as order_id,
    wwi_backorder_id as backorder_order_id,
    to_char(order_date_key, 'YYYYMMDD')::integer as order_date_key,
    case when picked_date_key is not null then to_char(picked_date_key, 'YYYYMMDD')::integer end as picked_date_key,
    case when expected_delivery_date is not null then to_char(expected_delivery_date, 'YYYYMMDD')::integer end as expected_delivery_date_key,
    product_key,
    customer_key,
    salesperson_key,
    picker_key,
    geography_key,
    package_type_key,
    wwi_stock_item_id as stock_item_id,
    wwi_customer_id as customer_id,
    wwi_salesperson_id as salesperson_person_id,
    wwi_picker_id as picker_person_id,
    description,
    package as package_name,
    quantity,
    unit_price,
    tax_rate,
    total_excluding_tax,
    tax_amount,
    total_including_tax,
    is_undersupply_backordered,
    picking_completed_when,
    last_modified_when
from enriched