with source as (
    select * from {{ csv_source('invoices') }}
),

renamed as (
    select
        invoice_id,
        sale_id,
        delivery_id,
        customer_id,
        cast(invoice_date as date)              as invoice_date,
        cast(subtotal_net as numeric(12,2))     as subtotal_net,
        -- tax_breakdown excluded: Python dict string, not portable SQL
        cast(tax_amount as numeric(12,2))       as tax_amount,
        cast(total_gross as numeric(12,2))      as total_gross,
        cast(due_date as date)                  as due_date,
        cast(payment_days as integer)           as payment_days,
        payment_status,
        cast(payment_date as date)              as payment_date
    from source
)

select * from renamed
