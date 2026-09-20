-- data quality/reconciliation explicit preservation test for an audited WideWorldImporters source behavior.
-- DeliveryAttempt events with an absent/null Status must remain NULL in core and
-- must be represented only by is_unconfirmed_attempt=true, never normalized.

with source_behavior as (
    select count(*)::bigint as source_null_status_count
    from {{ source('staging','invoice_delivery') }} i
    cross join lateral jsonb_array_elements(i.returned_delivery_data::jsonb -> 'Events') e
    where i.returned_delivery_data is not null
      and e->>'Event' = 'DeliveryAttempt'
      and e->>'Status' is null
), core_behavior as (
    select
        count(*) filter (where event_type='DeliveryAttempt' and event_status is null)::bigint as core_null_status_count,
        count(*) filter (where is_unconfirmed_attempt)::bigint as flag_count,
        count(*) filter (
            where is_unconfirmed_attempt
              and not (event_type='DeliveryAttempt' and event_status is null)
        )::bigint as invalid_flag_count
    from {{ ref('fact_delivery_event') }}
)
select *
from source_behavior s
cross join core_behavior c
where s.source_null_status_count <> c.core_null_status_count
   or s.source_null_status_count <> c.flag_count
   or c.invalid_flag_count <> 0
