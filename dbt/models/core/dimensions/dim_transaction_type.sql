{{ config(materialized='table') }}
select
    {{ surrogate_key(["'transaction_type'", 'transaction_type_id']) }} as transaction_type_key,
    transaction_type_id,
    transaction_type_name
from {{ source('staging', 'transaction_type_current') }}