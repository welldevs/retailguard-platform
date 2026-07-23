{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Supplier Scorecard: OTIF, lead time (real vs. prometido) e fill rate por fornecedor.
-- OTIF = On-Time In-Full: PO entregue no prazo E com ≥95% das unidades pedidas.
-- Grão: supplier_id (uma linha por fornecedor ativo com POs recebidos).

with pos as (
    select * from {{ ref('stg_purchase_orders') }}
),

pol as (
    select * from {{ ref('stg_purchase_order_lines') }}
),

gr as (
    select * from {{ ref('stg_goods_receipts') }}
),

sup as (
    select * from {{ ref('dim_supplier') }}
),

-- total quantities ordered per PO (sum across all lines)
po_qty_ordered as (
    select
        po_id,
        sum(quantity_ordered) as total_qty_ordered
    from pol
    group by po_id
),

-- total quantities received per PO (sum across all receipt lines)
po_qty_received as (
    select
        po_id,
        sum(quantity_received) as total_qty_received
    from gr
    group by po_id
),

po_with_flags as (
    select
        p.po_id,
        p.supplier_id,
        p.order_date,
        p.expected_receipt_date,
        p.actual_receipt_date,
        pq.total_qty_ordered,
        coalesce(gq.total_qty_received, 0)                              as total_qty_received,
        -- on-time: actual receipt on or before expected
        case
            when p.actual_receipt_date is not null
             and p.actual_receipt_date <= p.expected_receipt_date then 1 else 0
        end                                                             as is_on_time,
        -- in-full: received ≥95% of ordered quantity (tolerance for minor variances)
        case
            when coalesce(gq.total_qty_received, 0) >= pq.total_qty_ordered * 0.95 then 1 else 0
        end                                                             as is_in_full,
        -- actual lead time days
        case
            when p.actual_receipt_date is not null
            then cast(p.actual_receipt_date - p.order_date as integer)
            else null
        end                                                             as actual_lead_days,
        -- promised lead time days
        cast(p.expected_receipt_date - p.order_date as integer)        as promised_lead_days
    from pos p
    left join po_qty_ordered  pq on p.po_id = pq.po_id
    left join po_qty_received gq on p.po_id = gq.po_id
    where p.status != 'cancelled'
),

supplier_stats as (
    select
        supplier_id,
        count(po_id)                                                    as total_pos,
        sum(total_qty_ordered)                                          as total_qty_ordered,
        sum(total_qty_received)                                         as total_qty_received,
        -- fill rate: units received vs. ordered
        cast(
            sum(total_qty_received) * 1.0 / nullif(sum(total_qty_ordered), 0)
            as numeric(8, 4)
        )                                                               as fill_rate,
        -- on-time delivery rate
        cast(
            sum(is_on_time) * 1.0 / nullif(count(po_id), 0)
            as numeric(8, 4)
        )                                                               as on_time_rate,
        -- in-full delivery rate
        cast(
            sum(is_in_full) * 1.0 / nullif(count(po_id), 0)
            as numeric(8, 4)
        )                                                               as in_full_rate,
        -- OTIF: on-time AND in-full
        cast(
            sum(case when is_on_time = 1 and is_in_full = 1 then 1 else 0 end) * 1.0
            / nullif(count(po_id), 0)
            as numeric(8, 4)
        )                                                               as otif_rate,
        -- lead time metrics
        cast(avg(actual_lead_days)  as numeric(8, 2))                  as avg_lead_time_actual,
        cast(avg(promised_lead_days) as numeric(8, 2))                 as avg_lead_time_promised,
        cast(avg(actual_lead_days) - avg(promised_lead_days) as numeric(8, 2)) as avg_lead_time_variance
    from po_with_flags
    group by supplier_id
)

select
    ss.supplier_id,
    s.supplier_name,
    s.country,
    s.city,
    s.category_specialization,
    s.reliability_score,
    ss.total_pos,
    ss.total_qty_ordered,
    ss.total_qty_received,
    ss.fill_rate,
    ss.on_time_rate,
    ss.in_full_rate,
    ss.otif_rate,
    ss.avg_lead_time_actual,
    ss.avg_lead_time_promised,
    ss.avg_lead_time_variance
from supplier_stats ss
left join sup s on ss.supplier_id = s.supplier_id
order by otif_rate desc
