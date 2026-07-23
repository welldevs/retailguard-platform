with source as (
    select * from {{ csv_source('supplier_payments') }}
),

renamed as (
    select
        payment_id,
        po_id,
        supplier_id,
        dc_id,
        cast(obligation_date as date)           as obligation_date,
        cast(due_date as date)                  as due_date,
        cast(payment_date as date)              as payment_date,
        cast(amount_net as numeric(14,2))       as amount_net,
        cast(amount_gross as numeric(14,2))     as amount_gross,
        status,
        cast(days_late as integer)              as days_late
    from source
)

select * from renamed
