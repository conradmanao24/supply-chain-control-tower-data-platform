select 'inventory_customer' as orphan_type, inventory_movement_key as row_key
from {{ ref('fact_inventory_movement') }}
where customer_id is not null and customer_key is null
union all
select 'inventory_supplier', inventory_movement_key
from {{ ref('fact_inventory_movement') }}
where supplier_id is not null and supplier_key is null
union all
select 'delivery_driver', delivery_event_key
from {{ ref('fact_delivery_event') }}
where driver_person_id is not null and driver_key is null
union all
select 'order_picker', order_line_key
from {{ ref('fact_order_line') }}
where picker_person_id is not null and picker_key is null