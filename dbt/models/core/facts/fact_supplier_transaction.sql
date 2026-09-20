{{ config(materialized='incremental', unique_key='supplier_transaction_key', incremental_strategy='delete+insert') }}
with src as (
    select
        f.*,
        (f.date_key::timestamp + interval '1 day' - interval '1 microsecond') as business_asof_ts
    from {{ source('staging', 'financial_transaction') }} f
    where wwi_supplier_transaction_id is not null
    {% if is_incremental() %}
      and {{ incremental_fact_filter('supplier_transaction','f') }}
    {% endif %}
), enriched as (
    select
        s.*,
        sup.supplier_key,
        tt.transaction_type_key,
        pm.payment_method_name
    from src s
    left join {{ ref('dim_supplier') }} sup
      on sup.supplier_id = s.wwi_supplier_id
     and s.business_asof_ts >= sup.valid_from and s.business_asof_ts < sup.valid_to
    left join {{ ref('dim_transaction_type') }} tt on tt.transaction_type_id = s.wwi_transaction_type_id
    left join {{ source('staging', 'payment_method_current') }} pm on pm.payment_method_id = s.wwi_payment_method_id
)
select
    {{ surrogate_key(["'supplier_transaction'", 'wwi_supplier_transaction_id']) }} as supplier_transaction_key,
    wwi_supplier_transaction_id as supplier_transaction_id,
    to_char(date_key, 'YYYYMMDD')::integer as date_key,
    supplier_key,
    transaction_type_key,
    wwi_supplier_id as supplier_id,
    wwi_transaction_type_id as transaction_type_id,
    wwi_payment_method_id as payment_method_id,
    payment_method_name,
    wwi_purchase_order_id as purchase_order_id,
    supplier_invoice_number,
    total_excluding_tax,
    tax_amount,
    total_including_tax,
    outstanding_balance,
    is_finalized,
    last_modified_when
from enriched