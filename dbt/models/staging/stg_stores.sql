with source as (
    select * from {{ csv_source('stores') }}
),

renamed as (
    select
        store_id,
        name,
        postal_code,
        municipality,
        province,
        ccaa,
        dc_id,
        cast(opening_date as date)              as opening_date,
        cast(sqm as integer)                    as sqm,
        cast(latitude as double)                as latitude,
        cast(longitude as double)               as longitude,
        cast(active as boolean)                 as active
    from source
)

select * from renamed
