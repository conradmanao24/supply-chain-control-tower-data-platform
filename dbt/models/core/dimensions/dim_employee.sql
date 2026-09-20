{{ config(materialized='incremental', unique_key='employee_key', incremental_strategy='delete+insert') }}
with history as (
    select
        h.*,
        md5(concat_ws('|',full_name,preferred_name,is_salesperson,is_employee)) as business_hash
    from {{ source('staging', 'employee_history') }} h
    {% if is_incremental() %}
    where h.person_id in ({{ incremental_affected_ids('employee') }})
    {% endif %}
), marked as (
    select *,
           lag(business_hash) over (partition by person_id order by valid_from) as previous_business_hash,
           row_number() over (partition by person_id order by valid_from) as source_version_number
    from history
), semantic as (
    select * from marked
    where source_version_number = 1 or business_hash is distinct from previous_business_hash
), versioned as (
    select *,
           lead(valid_from) over (partition by person_id order by valid_from) as next_semantic_valid_from,
           row_number() over (partition by person_id order by valid_from) as semantic_version_number
    from semantic
)
select
    {{ surrogate_key(["'employee'", 'person_id', 'valid_from']) }} as employee_key,
    person_id,
    full_name,
    preferred_name,
    is_salesperson,
    is_employee,
    semantic_version_number,
    valid_from,
    coalesce(next_semantic_valid_from, timestamp '9999-12-31 23:59:59.999999') as valid_to,
    next_semantic_valid_from is null as is_current
from versioned