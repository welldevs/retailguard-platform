{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- stg_purchase_orders: po_id, supplier_id, dc_id, order_date, expected_receipt_date,
--                      actual_receipt_date, status, incoterm, payment_terms, currency,
--                      total_cost_net, tax_amount, total_cost_gross
-- stg_supplier_payments: payment_id, po_id, supplier_id, dc_id, obligation_date,
--                        due_date, payment_date, amount_net, amount_gross, status, days_late

with pos as (
    select * from {{ ref('stg_purchase_orders') }}
),

payments as (
    select * from {{ ref('stg_supplier_payments') }}
),

-- Junta POs com seus pagamentos
joined as (
    select
        po.po_id,
        po.supplier_id,
        po.dc_id,
        po.order_date,
        po.status                                   as po_status,
        po.total_cost_gross,
        p.payment_id,
        p.due_date,
        p.payment_date,
        p.amount_gross,
        p.status                                    as payment_status,
        p.days_late,
        -- bucket de aging baseado em days_late
        case
            when p.days_late <= 0    then '0-current'
            when p.days_late <= 30   then '01-30d'
            when p.days_late <= 60   then '31-60d'
            when p.days_late <= 90   then '61-90d'
            else                          '91d+'
        end                                         as aging_bucket
    from pos po
    left join payments p on po.po_id = p.po_id
),

aggregated as (
    select
        supplier_id,
        aging_bucket,
        count(distinct po_id)                       as num_pos,
        count(payment_id)                           as num_payments,
        cast(sum(amount_gross) as numeric(18,2))    as total_amount_gross,
        cast(avg(days_late) as numeric(8,2))        as avg_days_late
    from joined
    where payment_id is not null
    group by supplier_id, aging_bucket
)

select * from aggregated
order by supplier_id, aging_bucket
