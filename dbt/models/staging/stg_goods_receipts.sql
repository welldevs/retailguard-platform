with source as (
    select * from {{ csv_source('goods_receipts') }}
),

renamed as (
    select
        receipt_id,
        po_id,
        cast(po_line_number as integer)         as po_line_number,
        dc_id,
        product_id,
        supplier_id,
        cast(quantity_received as integer)      as quantity_received,
        cast(receipt_date as date)              as receipt_date,
        cast(unit_cost as numeric(12,4))        as unit_cost
    from source
)

select * from renamed
