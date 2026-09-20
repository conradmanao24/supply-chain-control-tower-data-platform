with overlap_rows as (
    select 'product' as entity, a.stock_item_id::text as business_key
    from {{ ref('dim_product') }} a
    join {{ ref('dim_product') }} b
      on a.stock_item_id=b.stock_item_id and a.product_key<>b.product_key
     and a.valid_from < b.valid_to and b.valid_from < a.valid_to
    union all
    select 'customer', a.customer_id::text
    from {{ ref('dim_customer') }} a
    join {{ ref('dim_customer') }} b
      on a.customer_id=b.customer_id and a.customer_key<>b.customer_key
     and a.valid_from < b.valid_to and b.valid_from < a.valid_to
    union all
    select 'supplier', a.supplier_id::text
    from {{ ref('dim_supplier') }} a
    join {{ ref('dim_supplier') }} b
      on a.supplier_id=b.supplier_id and a.supplier_key<>b.supplier_key
     and a.valid_from < b.valid_to and b.valid_from < a.valid_to
    union all
    select 'employee', a.person_id::text
    from {{ ref('dim_employee') }} a
    join {{ ref('dim_employee') }} b
      on a.person_id=b.person_id and a.employee_key<>b.employee_key
     and a.valid_from < b.valid_to and b.valid_from < a.valid_to
)
select distinct * from overlap_rows