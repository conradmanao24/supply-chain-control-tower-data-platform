with expected as (
    select count(*)::bigint as row_count
    from (
        select customer_id, valid_from, credit_limit,
               lag(credit_limit) over (partition by customer_id order by valid_from) as previous_credit_limit,
               row_number() over (partition by customer_id order by valid_from) as rn
        from {{ source('staging','customer_history') }}
    ) x
    where rn=1 or credit_limit is distinct from previous_credit_limit
), actual as (
    select count(*)::bigint as row_count from {{ ref('dim_customer') }}
)
select expected.row_count as expected_count, actual.row_count as actual_count
from expected cross join actual
where expected.row_count <> actual.row_count