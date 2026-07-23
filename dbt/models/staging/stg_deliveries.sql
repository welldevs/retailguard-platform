with source as (
    select * from {{ csv_source('deliveries') }}
),

renamed as (
    select
        delivery_id,
        sale_id,
        dc_id,
        carrier,
        tracking_number,
        cast(dispatch_date as date)                     as dispatch_date,
        cast(estimated_delivery_date as date)           as estimated_delivery_date,
        cast(actual_delivery_date as date)              as actual_delivery_date,
        delivery_status,
        cast(weight_kg as numeric(8,2))                 as weight_kg,
        cast(packages as integer)                       as packages,
        cast(signature_required as boolean)             as signature_required,
        cast(total_amount as numeric(12,2))             as total_amount
    from source
)

select * from renamed
