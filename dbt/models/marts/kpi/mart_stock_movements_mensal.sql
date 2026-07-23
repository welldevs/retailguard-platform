{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Movimentações de estoque por tipo e mês (IN / OUT / TRANSFER). Grão:
-- (year_month, movement_type). Modelo dbt equivalente ao antigo script de
-- streaming, lendo de stg_stock_movements + dim_date.
-- Nota: TRANSFER soma ~0 (entrada na loja compensa saída no DC — conservação).

with movements as (
    select * from {{ ref('stg_stock_movements') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

joined as (
    select
        d.year_month,
        d.year,
        d.month,
        m.movement_type,
        m.quantity_delta
    from movements m
    inner join dates d on m.movement_date = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        movement_type,
        count(*)                                            as num_movements,
        cast(sum(quantity_delta) as integer)                as total_delta
    from joined
    group by year_month, year, month, movement_type
)

select * from aggregated
order by year_month, movement_type
