{{ config(materialized='table') }}
with src as (
    select s.* from {{ source('staging', 'product_stock_group') }} s
)
select {{ surrogate_key(["'product_stock_group'", 'p.product_key', 's.stock_group_id']) }} as product_stock_group_key,
       p.product_key,s.stock_item_id,s.stock_group_id,s.stock_group_name,s.last_edited_when
from src s join {{ ref('dim_product') }} p on p.stock_item_id=s.stock_item_id and p.is_current
