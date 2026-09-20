with checks as (
    select 'fact_order_line' as check_name,
           (select count(*) from {{ source('staging','order_line') }})::bigint as source_count,
           (select count(*) from {{ ref('fact_order_line') }})::bigint as target_count
    union all select 'fact_sales_line',
           (select count(*) from {{ source('staging','sale_line') }}),
           (select count(*) from {{ ref('fact_sales_line') }})
    union all select 'fact_inventory_movement',
           (select count(*) from {{ source('staging','inventory_movement') }}),
           (select count(*) from {{ ref('fact_inventory_movement') }})
    union all select 'fact_purchase_order_line',
           (select count(*) from {{ source('staging','purchase_line') }}),
           (select count(*) from {{ ref('fact_purchase_order_line') }})
    union all select 'fact_customer_transaction',
           (select count(*) from {{ source('staging','financial_transaction') }} where wwi_customer_transaction_id is not null),
           (select count(*) from {{ ref('fact_customer_transaction') }})
    union all select 'fact_supplier_transaction',
           (select count(*) from {{ source('staging','financial_transaction') }} where wwi_supplier_transaction_id is not null),
           (select count(*) from {{ ref('fact_supplier_transaction') }})
    union all select 'fact_delivery_event',
           (select coalesce(sum(jsonb_array_length(returned_delivery_data::jsonb -> 'Events')),0) from {{ source('staging','invoice_delivery') }} where returned_delivery_data is not null),
           (select count(*) from {{ ref('fact_delivery_event') }})
    union all select 'bridge_product_stock_group',
           (select count(*) from {{ source('staging','product_stock_group') }}),
           (select count(*) from {{ ref('bridge_product_stock_group') }})
)
select * from checks where source_count <> target_count