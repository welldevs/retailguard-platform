with source as (
    select * from {{ csv_source('purchase_orders') }}
),

renamed as (
    select
        po_id,
        supplier_id,
        dc_id,
        cast(order_date as date)                as order_date,
        cast(expected_receipt_date as date)     as expected_receipt_date,
        cast(actual_receipt_date as date)       as actual_receipt_date,
        status,
        incoterm,
        payment_terms,
        currency,
        cast(total_cost_net as numeric(14,2))   as total_cost_net,
        cast(tax_amount as numeric(14,2))       as tax_amount,
        cast(total_cost_gross as numeric(14,2)) as total_cost_gross
        -- _lines column excluded: raw JSON blob, not needed in staging
    from source
)

select * from renamed
