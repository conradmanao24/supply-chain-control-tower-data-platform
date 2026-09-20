{{ config(materialized='incremental', unique_key='customer_key', incremental_strategy='delete+insert') }}
with history as (
    select
        h.*,
        lag(credit_limit) over (partition by customer_id order by valid_from) as previous_credit_limit,
        row_number() over (partition by customer_id order by valid_from) as source_version_number
    from {{ source('staging', 'customer_history') }} h
    {% if is_incremental() %}
    where h.customer_id in ({{ incremental_affected_ids('customer') }})
    {% endif %}
), semantic as (
    select *
    from history
    where source_version_number = 1
       or credit_limit is distinct from previous_credit_limit
), versioned as (
    select
        s.*,
        lead(valid_from) over (partition by customer_id order by valid_from) as next_semantic_valid_from,
        row_number() over (partition by customer_id order by valid_from) as semantic_version_number
    from semantic s
), current_descriptor as (
    select
        customer_id,
        customer_name,
        buying_group_name,
        delivery_latitude,
        delivery_longitude
    from {{ source('staging', 'customer_current') }}
)
select
    {{ surrogate_key(["'customer'", 'v.customer_id', 'v.valid_from']) }} as customer_key,
    v.customer_id,
    c.customer_name,
    v.bill_to_customer_id,
    v.customer_category_id,
    v.buying_group_id,
    c.buying_group_name,
    v.delivery_method_id,
    v.delivery_city_id,
    v.postal_city_id,
    v.credit_limit,
    v.account_opened_date,
    v.standard_discount_percentage,
    v.is_statement_sent,
    v.is_on_credit_hold,
    v.payment_days,
    v.delivery_run,
    v.run_position,
    v.delivery_postal_code,
    c.delivery_latitude,
    c.delivery_longitude,
    v.semantic_version_number,
    v.valid_from,
    coalesce(v.next_semantic_valid_from, timestamp '9999-12-31 23:59:59.999999') as valid_to,
    v.next_semantic_valid_from is null as is_current
from versioned v
join current_descriptor c using (customer_id)