{{ config(materialized='table') }}
select
    {{ surrogate_key(["'package_type'", 'package_type_id']) }} as package_type_key,
    package_type_id,
    package_type_name
from {{ source('staging', 'package_type_current') }}