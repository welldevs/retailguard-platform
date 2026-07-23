{{
    config(
        materialized='table',
        tags=['dim']
    )
}}

with suppliers as (
    select * from {{ ref('stg_suppliers') }}
)

select
    supplier_id,
    name                                        as supplier_name,
    country,
    city,
    category_specialization,
    lead_time_days,
    reliability_score,
    payment_terms_days,
    payment_terms,
    incoterm,
    currency,
    cif,
    iban,
    contact_email,
    phone,
    active
from suppliers
