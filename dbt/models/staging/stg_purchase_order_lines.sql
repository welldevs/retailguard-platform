with source as (
    select * from {{ csv_source('purchase_order_lines') }}
),

renamed as (
    select
        po_id,
        cast(line_number as integer)            as line_number,
        product_id,
        cast(quantity_ordered as integer)       as quantity_ordered,
        cast(unit_cost as numeric(12,4))        as unit_cost,
        cast(tax_rate as numeric(6,4))          as tax_rate,
        cast(line_total_net as numeric(14,2))   as line_total_net
    from source
)

select * from renamed
