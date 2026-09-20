{{ config(materialized='table') }}
select
    {{ surrogate_key(["'geography'", 'city_id']) }} as geography_key,
    city_id,
    city_name,
    state_province_id,
    state_province_code,
    state_province_name,
    sales_territory,
    country_id,
    country_name,
    continent,
    region,
    subregion,
    latest_recorded_population,
    latitude,
    longitude
from {{ source('staging', 'geography_current') }}