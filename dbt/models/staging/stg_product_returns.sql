with source as (
    select * from {{ csv_source('product_returns') }}
),

renamed as (
    select
        return_id,
        sale_id,
        order_id,
        product_id,
        customer_id,
        location_type,
        location_id,
        cast(return_date as date)               as return_date,
        cast(quantity_returned as integer)      as quantity_returned,
        cast(unit_price_net as numeric(10,4))   as unit_price_net,
        cast(refund_amount as numeric(12,2))    as refund_amount,
        reason,
        cast(restocked as boolean)              as restocked
    from source
)

select * from renamed
