{{ config(materialized='incremental', unique_key='inventory_movement_key', incremental_strategy='delete+insert') }}
with src as (
    select * from {{ source('staging', 'inventory_movement') }} s
    {% if is_incremental() %}
    where {{ incremental_fact_filter('inventory_movement','s') }}
    {% endif %}
), enriched as (
    select
        s.*,
        p.product_key,
        c.customer_key,
        sup.supplier_key,
        tt.transaction_type_key
    from src s
    left join {{ ref('dim_product') }} p
      on p.stock_item_id = s.wwi_stock_item_id
     and s.transaction_occurred_when >= p.valid_from and s.transaction_occurred_when < p.valid_to
    left join {{ ref('dim_customer') }} c
      on c.customer_id = s.wwi_customer_id
     and s.transaction_occurred_when >= c.valid_from and s.transaction_occurred_when < c.valid_to
    left join {{ ref('dim_supplier') }} sup
      on sup.supplier_id = s.wwi_supplier_id
     and s.transaction_occurred_when >= sup.valid_from and s.transaction_occurred_when < sup.valid_to
    left join {{ ref('dim_transaction_type') }} tt on tt.transaction_type_id = s.wwi_transaction_type_id
)
select
    {{ surrogate_key(["'inventory_movement'", 'wwi_stock_item_transaction_id']) }} as inventory_movement_key,
    wwi_stock_item_transaction_id as stock_item_transaction_id,
    to_char(date_key, 'YYYYMMDD')::integer as date_key,
    transaction_occurred_when,
    product_key,
    customer_key,
    supplier_key,
    transaction_type_key,
    wwi_stock_item_id as stock_item_id,
    wwi_customer_id as customer_id,
    wwi_supplier_id as supplier_id,
    wwi_transaction_type_id as transaction_type_id,
    wwi_invoice_id as invoice_id,
    wwi_purchase_order_id as purchase_order_id,
    quantity
from enriched