with source as (
    select * from {{ csv_source('distribution_centers') }}
),

renamed as (
    select
        dc_id,
        name,
        city,
        region,
        cast(latitude as double)                as latitude,
        cast(longitude as double)               as longitude,
        cast(stock_weight as numeric(10,4))     as stock_weight
    from source
)

select * from renamed
