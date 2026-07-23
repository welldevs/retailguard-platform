with source as (
    select * from {{ csv_source('sale_lines') }}
),

renamed as (
    select
        sale_id,
        cast(line_number as integer)                    as line_number,
        product_id,
        cast(quantity_ordered as integer)               as quantity_ordered,
        cast(quantity_delivered as integer)             as quantity_delivered,
        cast(unit_price_net as numeric(12, 4))          as unit_price_net,
        cast(discount_pct as numeric(6, 4))             as discount_pct,
        cast(tax_rate as numeric(6, 4))                 as tax_rate,
        cast(line_total_net as numeric(12, 2))          as line_total_net
    from source
)

select * from renamed
