with checks as (
    select 'order_total_including_tax' as check_name,
           (select sum(total_including_tax) from {{ source('staging','order_line') }})::numeric as source_value,
           (select sum(total_including_tax) from {{ ref('fact_order_line') }})::numeric as target_value
    union all select 'sales_total_including_tax',
           (select sum(total_including_tax) from {{ source('staging','sale_line') }}),
           (select sum(total_including_tax) from {{ ref('fact_sales_line') }})
    union all select 'sales_profit',
           (select sum(profit) from {{ source('staging','sale_line') }}),
           (select sum(profit) from {{ ref('fact_sales_line') }})
    union all select 'inventory_quantity',
           (select sum(quantity)::numeric from {{ source('staging','inventory_movement') }}),
           (select sum(quantity)::numeric from {{ ref('fact_inventory_movement') }})
    union all select 'customer_transaction_total',
           (select sum(total_including_tax) from {{ source('staging','financial_transaction') }} where wwi_customer_transaction_id is not null),
           (select sum(total_including_tax) from {{ ref('fact_customer_transaction') }})
    union all select 'supplier_transaction_total',
           (select sum(total_including_tax) from {{ source('staging','financial_transaction') }} where wwi_supplier_transaction_id is not null),
           (select sum(total_including_tax) from {{ ref('fact_supplier_transaction') }})
)
select * from checks where source_value is distinct from target_value