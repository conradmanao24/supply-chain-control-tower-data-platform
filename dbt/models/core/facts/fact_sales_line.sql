{{ config(materialized='incremental', unique_key='sales_line_key', incremental_strategy='delete+insert') }}
with src as (
    select
        s.*,
        (s.invoice_date_key::timestamp + interval '1 day' - interval '1 microsecond') as business_asof_ts
    from {{ source('staging', 'sale_line') }} s
    {% if is_incremental() %}
    where {{ incremental_fact_filter('sales_line','s') }}
    {% endif %}
), enriched as (
    select
        s.*,
        i.order_id,
        i.delivery_method_id,
        p.product_key,
        c.customer_key,
        bc.customer_key as bill_to_customer_key,
        sp.employee_key as salesperson_key,
        g.geography_key,
        dm.delivery_method_key,
        pt.package_type_key
    from src s
    left join {{ source('staging', 'invoice_delivery') }} i on i.invoice_id = s.wwi_invoice_id
    left join {{ ref('dim_product') }} p
      on p.stock_item_id = s.wwi_stock_item_id
     and s.business_asof_ts >= p.valid_from and s.business_asof_ts < p.valid_to
    left join {{ ref('dim_customer') }} c
      on c.customer_id = s.wwi_customer_id
     and s.business_asof_ts >= c.valid_from and s.business_asof_ts < c.valid_to
    left join {{ ref('dim_customer') }} bc
      on bc.customer_id = s.wwi_bill_to_customer_id
     and s.business_asof_ts >= bc.valid_from and s.business_asof_ts < bc.valid_to
    left join {{ ref('dim_employee') }} sp
      on sp.person_id = s.wwi_salesperson_id
     and s.business_asof_ts >= sp.valid_from and s.business_asof_ts < sp.valid_to
    left join {{ ref('dim_geography') }} g on g.city_id = s.wwi_city_id
    left join {{ ref('dim_delivery_method') }} dm on dm.delivery_method_id = i.delivery_method_id
    left join {{ ref('dim_package_type') }} pt on pt.package_type_name = s.package
)
select
    {{ surrogate_key(["'sales_line'", 'wwi_invoice_id', 'wwi_stock_item_id']) }} as sales_line_key,
    wwi_invoice_id as invoice_id,
    order_id,
    to_char(invoice_date_key, 'YYYYMMDD')::integer as invoice_date_key,
    case when delivery_date_key is not null then to_char(delivery_date_key, 'YYYYMMDD')::integer end as delivery_date_key,
    product_key,
    customer_key,
    bill_to_customer_key,
    salesperson_key,
    geography_key,
    delivery_method_key,
    package_type_key,
    wwi_stock_item_id as stock_item_id,
    wwi_customer_id as customer_id,
    wwi_bill_to_customer_id as bill_to_customer_id,
    wwi_salesperson_id as salesperson_person_id,
    description,
    package as package_name,
    quantity,
    unit_price,
    tax_rate,
    total_excluding_tax,
    tax_amount,
    profit,
    total_including_tax,
    total_dry_items,
    total_chiller_items,
    last_modified_when
from enriched