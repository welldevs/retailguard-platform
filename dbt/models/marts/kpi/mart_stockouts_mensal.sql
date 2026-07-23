{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Rupturas de estoque por mês. Grão: year_month.
-- Modelo dbt canônico: `dbt build` produz TODAS as marts do dashboard a partir
-- da mesma fonte RAW/staging, seja a ingestão batch (CSV) ou streaming (Kafka).
-- quantity_available é sempre 0 (registramos apenas rupturas totais), então
-- qty_unmet = qty_requested.

with stockouts as (
    select * from {{ ref('stg_stockouts') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

joined as (
    select
        d.year_month,
        d.year,
        d.month,
        so.quantity_requested,
        so.quantity_available,
        so.quantity_requested - so.quantity_available as qty_unmet
    from stockouts so
    inner join dates d on so.event_date = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        count(*)                                                        as num_stockouts,
        cast(sum(quantity_requested) as integer)                        as qty_requested,
        cast(sum(quantity_available) as integer)                        as qty_available,
        cast(sum(qty_unmet)          as integer)                        as qty_unmet,
        cast(
            sum(qty_unmet) * 100.0 / nullif(sum(quantity_requested), 0)
            as numeric(8, 2)
        )                                                               as unmet_pct
    from joined
    group by year_month, year, month
)

select * from aggregated
order by year_month
