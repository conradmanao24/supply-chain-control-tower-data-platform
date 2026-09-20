with checks as (
    select 'product' as entity,
           (select count(distinct stock_item_id) from {{ source('staging','product_current') }})::bigint as expected_current,
           (select count(*) from {{ ref('dim_product') }} where is_current)::bigint as actual_current
    union all select 'customer',
           (select count(distinct customer_id) from {{ source('staging','customer_current') }}),
           (select count(*) from {{ ref('dim_customer') }} where is_current)
    union all select 'supplier',
           (select count(distinct supplier_id) from {{ source('staging','supplier_current') }}),
           (select count(*) from {{ ref('dim_supplier') }} where is_current)
    union all select 'employee',
           (select count(distinct person_id) from {{ source('staging','employee_current') }}),
           (select count(*) from {{ ref('dim_employee') }} where is_current)
)
select * from checks where expected_current <> actual_current