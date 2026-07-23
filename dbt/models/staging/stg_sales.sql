with source as (
    select * from {{ csv_source('sales') }}
),

renamed as (
    select
        sale_id,
        cast(order_date as date)                        as order_date,
        -- timestamp intradía (hora-punta). order_hour extraído para análise
        -- de afluência por hora (portável DuckDB/Snowflake).
        cast(order_ts as timestamp)                     as order_ts,
        cast(extract(hour from cast(order_ts as timestamp)) as integer) as order_hour,
        customer_id,
        store_id,
        dc_id,
        region,
        payment_method,
        payment_status,
        cast(payment_days as integer)                   as payment_days,
        channel,
        cast(subtotal_net as numeric(12, 2))            as subtotal_net,
        cast(tax_amount as numeric(12, 2))              as tax_amount,
        cast(total_gross as numeric(12, 2))             as total_gross,
        status,
        cast(has_partial_stockout as boolean)           as has_partial_stockout,
        cast(num_items as integer)                      as num_items,
        ticket_trend
    from source
)

select * from renamed
