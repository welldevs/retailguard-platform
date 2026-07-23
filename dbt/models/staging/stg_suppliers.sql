with source as (
    select * from {{ csv_source('suppliers') }}
),

renamed as (
    select
        supplier_id,
        name,
        country,
        city,
        cast(lead_time_days as integer)         as lead_time_days,
        cast(reliability_score as numeric(5,4)) as reliability_score,
        cast(payment_terms_days as integer)     as payment_terms_days,
        contact_email,
        phone,
        cast(active as boolean)                 as active,
        category_specialization,
        cif,
        payment_terms,
        incoterm,
        currency,
        iban
    from source
)

select * from renamed
