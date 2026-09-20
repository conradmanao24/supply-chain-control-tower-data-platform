{{ config(materialized='table') }}
select
    {{ surrogate_key(["'delivery_method'", 'delivery_method_id']) }} as delivery_method_key,
    delivery_method_id,
    delivery_method_name
from {{ source('staging', 'delivery_method_current') }}