{{
    config(
        materialized='table',
        tags=['dim']
    )
}}

with stores as (
    select * from {{ ref('stg_stores') }}
),

dcs as (
    select * from {{ ref('stg_distribution_centers') }}
)

select
    s.store_id,
    s.name                                      as store_name,
    s.postal_code,
    s.municipality,
    s.province,
    s.ccaa                                      as autonomous_community,
    s.dc_id,
    d.name                                      as dc_name,
    d.city                                      as dc_city,
    d.region                                    as dc_region,
    s.opening_date,
    s.sqm,
    s.latitude,
    s.longitude,
    s.active
from stores s
left join dcs d on s.dc_id = d.dc_id
