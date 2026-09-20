{{ config(materialized='incremental', unique_key='delivery_event_key', incremental_strategy='delete+insert') }}
with events as (
    select
        i.*,
        e.ordinality::integer as event_sequence,
        e.event ->> 'Event' as event_type,
        (e.event ->> 'EventTime')::timestamp as event_time,
        e.event ->> 'ConNote' as consignment_note,
        nullif(e.event ->> 'DriverID', '')::integer as driver_person_id,
        nullif(e.event ->> 'Latitude', '')::numeric as latitude,
        nullif(e.event ->> 'Longitude', '')::numeric as longitude,
        e.event ->> 'Status' as event_status
    from {{ source('staging', 'invoice_delivery') }} i
    cross join lateral jsonb_array_elements(i.returned_delivery_data::jsonb -> 'Events')
        with ordinality as e(event, ordinality)
    where i.returned_delivery_data is not null
    {% if is_incremental() %}
      and {{ incremental_fact_filter('delivery_event','i') }}
    {% endif %}
), enriched as (
    select
        e.*,
        c.customer_key,
        bc.customer_key as bill_to_customer_key,
        drv.employee_key as driver_key,
        dm.delivery_method_key
    from events e
    left join {{ ref('dim_customer') }} c
      on c.customer_id = e.customer_id
     and e.event_time >= c.valid_from and e.event_time < c.valid_to
    left join {{ ref('dim_customer') }} bc
      on bc.customer_id = e.bill_to_customer_id
     and e.event_time >= bc.valid_from and e.event_time < bc.valid_to
    left join {{ ref('dim_employee') }} drv
      on drv.person_id = e.driver_person_id
     and e.event_time >= drv.valid_from and e.event_time < drv.valid_to
    left join {{ ref('dim_delivery_method') }} dm on dm.delivery_method_id = e.delivery_method_id
)
select
    {{ surrogate_key(["'delivery_event'", 'invoice_id', 'event_sequence']) }} as delivery_event_key,
    invoice_id,
    order_id,
    event_sequence,
    to_char(event_time::date, 'YYYYMMDD')::integer as event_date_key,
    event_time,
    event_type,
    event_status,
    consignment_note,
    customer_key,
    bill_to_customer_key,
    driver_key,
    delivery_method_key,
    customer_id,
    bill_to_customer_id,
    driver_person_id,
    delivery_method_id,
    latitude,
    longitude,
    event_type = 'DeliveryAttempt' as is_delivery_attempt,
    event_type = 'DeliveryAttempt' and event_status = 'Delivered' as is_delivered,
    event_type = 'DeliveryAttempt' and event_status is null as is_unconfirmed_attempt,
    confirmed_delivery_time,
    confirmed_received_by,
    last_edited_when
from enriched