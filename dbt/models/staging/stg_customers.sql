with source as (
    select * from {{ csv_source('customers') }}
),

renamed as (
    select
        customer_id,
        first_name,
        last_name,
        email,
        phone,
        nif,
        address_street,
        postal_code,
        municipality,
        province,
        ccaa,
        cast(registration_date as date)                 as registration_date,
        segment,
        profile,
        cast(birth_year as integer)                     as birth_year,
        cast(age as integer)                            as age,
        payment_method,
        cast(avg_ticket as numeric(10, 2))              as avg_ticket,
        ticket_trend,
        cast(behavior_variance as numeric(6, 4))        as behavior_variance,
        cast(channel_probability as numeric(6, 4))      as channel_probability,
        nearest_store_id,
        cast(payment_days as integer)                   as payment_days
    from source
)

select * from renamed
