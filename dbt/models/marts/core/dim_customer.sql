{{
    config(
        materialized='table',
        tags=['dim']
    )
}}

/*
  Real SCD Type 2 customer dimension.

  The tracked attributes (segment, avg_ticket, ticket_trend) are versioned by the
  dbt snapshot `scd_customers` (strategy=check). Each segment/ticket drift event
  produces a new versioned row with its own dbt_scd_id and validity window. The
  non-tracked descriptive attributes (name, contact, geo, etc.) are joined back
  from stg_customers, which is current-state only.
*/

with scd as (
    select * from {{ ref('scd_customers') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
)

select
    -- natural + surrogate keys
    scd.customer_id,
    scd.dbt_scd_id,

    -- descriptive (current-state) attributes from staging
    c.first_name,
    c.last_name,
    concat(c.first_name, ' ', c.last_name)      as full_name,
    c.email,
    c.phone,
    c.nif,
    c.address_street,
    c.postal_code,
    c.municipality,
    c.province,
    c.ccaa                                      as autonomous_community,
    c.registration_date,
    c.birth_year,
    c.age,
    c.profile,
    c.payment_method,
    c.nearest_store_id,
    c.payment_days,
    cast(c.behavior_variance as numeric(6,4))   as behavior_variance,
    cast(c.channel_probability as numeric(6,4)) as channel_probability,

    -- SCD2-tracked attributes (versioned snapshot values)
    scd.segment,
    cast(scd.avg_ticket as numeric(10,2))       as avg_ticket,
    scd.ticket_trend,

    -- real SCD2 validity columns from the snapshot
    scd.dbt_valid_from,
    scd.dbt_valid_to,
    (scd.dbt_valid_to is null)                  as is_current
from scd
left join customers c on scd.customer_id = c.customer_id
