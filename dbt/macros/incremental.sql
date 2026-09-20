{% macro incremental_run_started_at() %}
    '{{ env_var("INCREMENTAL_RUN_STARTED_AT") }}'::timestamptz
{% endmacro %}

{% macro incremental_affected_ids(entity) %}
    {% if entity == 'product' %}
        select distinct stock_item_id from {{ source('staging','product_history') }} where ingested_at >= {{ incremental_run_started_at() }}
    {% elif entity == 'customer' %}
        select distinct customer_id from {{ source('staging','customer_history') }} where ingested_at >= {{ incremental_run_started_at() }}
        union
        select distinct customer_id from {{ source('staging','customer_current') }} where ingested_at >= {{ incremental_run_started_at() }}
    {% elif entity == 'supplier' %}
        select distinct supplier_id from {{ source('staging','supplier_history') }} where ingested_at >= {{ incremental_run_started_at() }}
        union
        select distinct supplier_id from {{ source('staging','supplier_current') }} where ingested_at >= {{ incremental_run_started_at() }}
    {% elif entity == 'employee' %}
        select distinct person_id from {{ source('staging','employee_history') }} where ingested_at >= {{ incremental_run_started_at() }}
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown incremental processing entity: ' ~ entity) }}
    {% endif %}
{% endmacro %}

{% macro incremental_reference_delete_missing(staging_table, source_key, target_key) %}
    delete from {{ this }} t
    where not exists (
        select 1 from {{ source('staging', staging_table) }} s
        where s.{{ source_key }} = t.{{ target_key }}
    )
{% endmacro %}

{% macro incremental_delivery_affected_invoice_ids() %}
    select distinct i.invoice_id
    from {{ source('staging','invoice_delivery') }} i
    where i.ingested_at >= {{ incremental_run_started_at() }}
       or i.customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
       or i.bill_to_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
       or exists (
            select 1
            from jsonb_array_elements(coalesce(i.returned_delivery_data::jsonb -> 'Events','[]'::jsonb)) e(event)
            where nullif(e.event ->> 'DriverID','')::integer in (
                select person_id from ({{ incremental_affected_ids('employee') }}) p
            )
       )
{% endmacro %}

{% macro incremental_delivery_delete_affected() %}
    {% if is_incremental() %}
        delete from {{ this }} t
        where t.invoice_id in ({{ incremental_delivery_affected_invoice_ids() }})
    {% else %}
        select 1
    {% endif %}
{% endmacro %}

{% macro incremental_bridge_delete_missing() %}
    {% if is_incremental() %}
        delete from {{ this }} b
        where not exists (
            select 1 from {{ source('staging','product_stock_group') }} s
            where s.stock_item_id=b.stock_item_id and s.stock_group_id=b.stock_group_id
        )
    {% else %}
        select 1
    {% endif %}
{% endmacro %}

{% macro incremental_bridge_affected_stock_items() %}
    select distinct stock_item_id from {{ source('staging','product_stock_group') }} where ingested_at >= {{ incremental_run_started_at() }}
    union
    select stock_item_id from ({{ incremental_affected_ids('product') }}) p
{% endmacro %}

{% macro incremental_bridge_delete_affected() %}
    {% if is_incremental() %}
        delete from {{ this }} b where b.stock_item_id in ({{ incremental_bridge_affected_stock_items() }})
    {% else %}
        select 1
    {% endif %}
{% endmacro %}

{% macro incremental_fact_filter(kind, alias) %}
    (
    {% if kind == 'order_line' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or exists (select 1 from {{ source('staging','order_state') }} s where s.order_id={{ alias }}.wwi_order_id and s.ingested_at >= {{ incremental_run_started_at() }})
        or {{ alias }}.wwi_stock_item_id in (select stock_item_id from ({{ incremental_affected_ids('product') }}) p)
        or {{ alias }}.wwi_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_salesperson_id in (select person_id from ({{ incremental_affected_ids('employee') }}) e)
        or {{ alias }}.wwi_picker_id in (select person_id from ({{ incremental_affected_ids('employee') }}) e)
        or exists (select 1 from {{ source('staging','package_type_current') }} p where p.ingested_at >= {{ incremental_run_started_at() }})
    {% elif kind == 'sales_line' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or exists (select 1 from {{ source('staging','invoice_delivery') }} i where i.invoice_id={{ alias }}.wwi_invoice_id and i.ingested_at >= {{ incremental_run_started_at() }})
        or {{ alias }}.wwi_stock_item_id in (select stock_item_id from ({{ incremental_affected_ids('product') }}) p)
        or {{ alias }}.wwi_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_bill_to_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_salesperson_id in (select person_id from ({{ incremental_affected_ids('employee') }}) e)
        or exists (select 1 from {{ source('staging','package_type_current') }} p where p.ingested_at >= {{ incremental_run_started_at() }})
    {% elif kind == 'purchase_line' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or exists (select 1 from {{ source('staging','purchase_order_state') }} po_state where po_state.purchase_order_id={{ alias }}.wwi_purchase_order_id and po_state.ingested_at >= {{ incremental_run_started_at() }})
        or {{ alias }}.wwi_stock_item_id in (select stock_item_id from ({{ incremental_affected_ids('product') }}) p)
        or {{ alias }}.wwi_supplier_id in (select supplier_id from ({{ incremental_affected_ids('supplier') }}) s)
        or exists (select 1 from {{ source('staging','package_type_current') }} p where p.ingested_at >= {{ incremental_run_started_at() }})
    {% elif kind == 'inventory_movement' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or {{ alias }}.wwi_stock_item_id in (select stock_item_id from ({{ incremental_affected_ids('product') }}) p)
        or {{ alias }}.wwi_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_supplier_id in (select supplier_id from ({{ incremental_affected_ids('supplier') }}) s)
    {% elif kind == 'customer_transaction' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or {{ alias }}.wwi_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_bill_to_customer_id in (select customer_id from ({{ incremental_affected_ids('customer') }}) c)
        or {{ alias }}.wwi_payment_method_id in (select payment_method_id from {{ source('staging','payment_method_current') }} where ingested_at >= {{ incremental_run_started_at() }})
    {% elif kind == 'supplier_transaction' %}
        {{ alias }}.ingested_at >= {{ incremental_run_started_at() }}
        or {{ alias }}.wwi_supplier_id in (select supplier_id from ({{ incremental_affected_ids('supplier') }}) s)
        or {{ alias }}.wwi_payment_method_id in (select payment_method_id from {{ source('staging','payment_method_current') }} where ingested_at >= {{ incremental_run_started_at() }})
    {% elif kind == 'delivery_event' %}
        {{ alias }}.invoice_id in ({{ incremental_delivery_affected_invoice_ids() }})
    {% else %}
        {{ exceptions.raise_compiler_error('Unknown incremental processing fact kind: ' ~ kind) }}
    {% endif %}
    )
{% endmacro %}


{% macro incremental_delivery_cleanup() %}
    delete from {{ this }} t
    where not exists (
        select 1
        from {{ source('staging','invoice_delivery') }} i
        cross join lateral jsonb_array_elements(coalesce(i.returned_delivery_data::jsonb -> 'Events','[]'::jsonb))
            with ordinality as e(event, ordinality)
        where i.invoice_id=t.invoice_id and e.ordinality::integer=t.event_sequence
    )
{% endmacro %}

{% macro incremental_bridge_cleanup() %}
    delete from {{ this }} b
    where not exists (
        select 1
        from {{ source('staging','product_stock_group') }} s
        join {{ ref('dim_product') }} p on p.stock_item_id=s.stock_item_id and p.is_current
        where p.product_key=b.product_key and s.stock_group_id=b.stock_group_id
    )
{% endmacro %}
