{{ config(materialized='incremental', unique_key='product_key', incremental_strategy='delete+insert') }}
with history as (
    select
        h.*,
        md5(concat_ws('|',
            stock_item_name, supplier_id, color_id, unit_package_id, outer_package_id,
            brand, size, lead_time_days, quantity_per_outer, is_chiller_stock, barcode,
            tax_rate, unit_price, recommended_retail_price, typical_weight_per_unit
        )) as business_hash
    from {{ source('staging', 'product_history') }} h
    {% if is_incremental() %}
    where h.stock_item_id in ({{ incremental_affected_ids('product') }})
    {% endif %}
), marked as (
    select
        *,
        lag(business_hash) over (partition by stock_item_id order by valid_from) as previous_business_hash,
        row_number() over (partition by stock_item_id order by valid_from) as source_version_number
    from history
), semantic as (
    select *
    from marked
    where source_version_number = 1
       or business_hash is distinct from previous_business_hash
), versioned as (
    select
        *,
        lead(valid_from) over (partition by stock_item_id order by valid_from) as next_semantic_valid_from,
        row_number() over (partition by stock_item_id order by valid_from) as semantic_version_number
    from semantic
)
select
    {{ surrogate_key(["'product'", 'stock_item_id', 'valid_from']) }} as product_key,
    stock_item_id,
    stock_item_name,
    supplier_id,
    color_id,
    unit_package_id,
    outer_package_id,
    brand,
    size,
    lead_time_days,
    quantity_per_outer,
    is_chiller_stock,
    barcode,
    tax_rate,
    unit_price,
    recommended_retail_price,
    typical_weight_per_unit,
    semantic_version_number,
    valid_from,
    coalesce(next_semantic_valid_from, timestamp '9999-12-31 23:59:59.999999') as valid_to,
    next_semantic_valid_from is null as is_current
from versioned