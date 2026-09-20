{{ config(materialized='incremental', unique_key='date_key', incremental_strategy='delete+insert') }}
with bounds as (
    select min(d)::date as min_date, max(d)::date as max_date
    from (
        select order_date_key as d from {{ source('staging', 'order_line') }}
        union all select invoice_date_key from {{ source('staging', 'sale_line') }}
        union all select date_key from {{ source('staging', 'inventory_movement') }}
        union all select date_key from {{ source('staging', 'purchase_line') }}
        union all select date_key from {{ source('staging', 'financial_transaction') }}
        union all select expected_delivery_date from {{ source('staging', 'order_state') }}
        union all select expected_delivery_date from {{ source('staging', 'purchase_order_state') }} where expected_delivery_date is not null
        union all select confirmed_delivery_time::date from {{ source('staging', 'invoice_delivery') }} where confirmed_delivery_time is not null
        union all select bucket_start::date from {{ source('staging', 'coldroom_5m') }}
        union all select bucket_start::date from {{ source('staging', 'vehicle_5m') }}
    ) x
), dates as (
    select generate_series(min_date, max_date, interval '1 day')::date as calendar_date
    from bounds
)
select
    to_char(calendar_date, 'YYYYMMDD')::integer as date_key,
    calendar_date,
    extract(year from calendar_date)::integer as year,
    extract(quarter from calendar_date)::integer as quarter,
    extract(month from calendar_date)::integer as month_number,
    to_char(calendar_date, 'FMMonth') as month_name,
    extract(day from calendar_date)::integer as day_of_month,
    extract(isodow from calendar_date)::integer as iso_day_of_week,
    to_char(calendar_date, 'FMDay') as day_name,
    extract(week from calendar_date)::integer as iso_week_of_year,
    date_trunc('month', calendar_date)::date as month_start_date,
    (date_trunc('month', calendar_date) + interval '1 month - 1 day')::date as month_end_date,
    (extract(isodow from calendar_date) in (6,7)) as is_weekend
from dates
{% if is_incremental() %}
where not exists (select 1 from {{ this }} t where t.calendar_date = dates.calendar_date)
{% endif %}
