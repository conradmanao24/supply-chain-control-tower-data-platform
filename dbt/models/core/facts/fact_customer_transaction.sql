{{ config(materialized='incremental', unique_key='customer_transaction_key', incremental_strategy='delete+insert') }}
with src as (
    select
        f.*,
        (f.date_key::timestamp + interval '1 day' - interval '1 microsecond') as business_asof_ts
    from {{ source('staging', 'financial_transaction') }} f
    where wwi_customer_transaction_id is not null
    {% if is_incremental() %}
      and {{ incremental_fact_filter('customer_transaction','f') }}
    {% endif %}
), enriched as (
    select
        s.*,
        c.customer_key,
        bc.customer_key as bill_to_customer_key,
        tt.transaction_type_key,
        pm.payment_method_name
    from src s
    left join {{ ref('dim_customer') }} c
      on c.customer_id = s.wwi_customer_id
     and s.business_asof_ts >= c.valid_from and s.business_asof_ts < c.valid_to
    left join {{ ref('dim_customer') }} bc
      on bc.customer_id = s.wwi_bill_to_customer_id
     and s.business_asof_ts >= bc.valid_from and s.business_asof_ts < bc.valid_to
    left join {{ ref('dim_transaction_type') }} tt on tt.transaction_type_id = s.wwi_transaction_type_id
    left join {{ source('staging', 'payment_method_current') }} pm on pm.payment_method_id = s.wwi_payment_method_id
)
select
    {{ surrogate_key(["'customer_transaction'", 'wwi_customer_transaction_id']) }} as customer_transaction_key,
    wwi_customer_transaction_id as customer_transaction_id,
    to_char(date_key, 'YYYYMMDD')::integer as date_key,
    customer_key,
    bill_to_customer_key,
    transaction_type_key,
    wwi_customer_id as customer_id,
    wwi_bill_to_customer_id as bill_to_customer_id,
    wwi_transaction_type_id as transaction_type_id,
    wwi_payment_method_id as payment_method_id,
    payment_method_name,
    wwi_invoice_id as invoice_id,
    total_excluding_tax,
    tax_amount,
    total_including_tax,
    outstanding_balance,
    is_finalized,
    last_modified_when
from enriched