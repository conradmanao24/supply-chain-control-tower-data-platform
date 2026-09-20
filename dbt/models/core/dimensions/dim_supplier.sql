{{ config(materialized='incremental', unique_key='supplier_key', incremental_strategy='delete+insert') }}
with history as (
    select
        h.*,
        md5(concat_ws('|',supplier_name,supplier_category_id,delivery_method_id,delivery_city_id,postal_city_id,supplier_reference,payment_days,delivery_postal_code)) as business_hash
    from {{ source('staging', 'supplier_history') }} h
    {% if is_incremental() %}
    where h.supplier_id in ({{ incremental_affected_ids('supplier') }})
    {% endif %}
), marked as (
    select *,
           lag(business_hash) over (partition by supplier_id order by valid_from) as previous_business_hash,
           row_number() over (partition by supplier_id order by valid_from) as source_version_number
    from history
), semantic as (
    select * from marked
    where source_version_number = 1 or business_hash is distinct from previous_business_hash
), versioned as (
    select *,
           lead(valid_from) over (partition by supplier_id order by valid_from) as next_semantic_valid_from,
           row_number() over (partition by supplier_id order by valid_from) as semantic_version_number
    from semantic
), current_geo as (
    select supplier_id, delivery_latitude, delivery_longitude
    from {{ source('staging', 'supplier_current') }}
)
select
    {{ surrogate_key(["'supplier'", 'v.supplier_id', 'v.valid_from']) }} as supplier_key,
    v.supplier_id,
    v.supplier_name,
    v.supplier_category_id,
    v.delivery_method_id,
    v.delivery_city_id,
    v.postal_city_id,
    v.supplier_reference,
    v.payment_days,
    v.delivery_postal_code,
    c.delivery_latitude,
    c.delivery_longitude,
    v.semantic_version_number,
    v.valid_from,
    coalesce(v.next_semantic_valid_from, timestamp '9999-12-31 23:59:59.999999') as valid_to,
    v.next_semantic_valid_from is null as is_current
from versioned v
join current_geo c using (supplier_id)