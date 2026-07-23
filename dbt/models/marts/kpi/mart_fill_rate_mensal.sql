{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Fill rate mensal — DISPONIBILIDADE de produto (definição padrão de varejo):
--
--   fill_rate = unidades entregues / unidades demandadas
--             = delivered_units / (delivered_units + unmet_units)
--
-- onde unmet_units = soma de quantity_requested das rupturas (STOCKOUTS).
-- É a métrica de "on-shelf availability" e fica ~96-98% num supermercado bem
-- abastecido. Substitui a antiga métrica baseada em quantity_delivered, que era
-- inútil (=0 nos dados), e a aproximação por has_partial_stockout (que media o
-- "perfect order rate", não a disponibilidade).
--
-- Mantém também o perfect_order_pct (pedidos sem nenhuma ruptura / total) como
-- métrica secundária — naturalmente mais baixa por contar o pedido inteiro.
--
-- fct_sales está no grão de LINHA: deduplicamos por sale_id para o perfect order.

with sales as (
    select * from {{ ref('fct_sales') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

stockouts as (
    select * from {{ ref('stg_stockouts') }}
),

-- unidades efetivamente entregues por mês
delivered as (
    select
        d.year_month,
        sum(s.quantity_delivered) as delivered_units
    from sales s
    inner join dates d on s.date_id = d.date_id
    group by d.year_month
),

-- unidades demandadas e não atendidas (ruptura) por mês
unmet as (
    select
        d.year_month,
        sum(so.quantity_requested) as unmet_units
    from stockouts so
    inner join dates d on so.event_date = d.date_id
    group by d.year_month
),

-- um registro por pedido, com a flag de ruptura normalizada (boolean ou texto)
orders as (
    select
        s.sale_id,
        s.date_id,
        case
            when lower(cast(s.has_partial_stockout as varchar)) in ('true', '1', 't')
                then 1
            else 0
        end as has_stockout
    from sales s
    group by s.sale_id, s.date_id, s.has_partial_stockout
),

orders_monthly as (
    select
        d.year_month,
        d.year,
        d.month,
        count(distinct o.sale_id)                    as total_pedidos,
        sum(o.has_stockout)                          as pedidos_com_ruptura,
        count(distinct o.sale_id) - sum(o.has_stockout) as pedidos_sem_ruptura
    from orders o
    inner join dates d on o.date_id = d.date_id
    group by d.year_month, d.year, d.month
),

final as (
    select
        o.year_month,
        o.year,
        o.month,
        o.total_pedidos,
        o.pedidos_com_ruptura,
        o.pedidos_sem_ruptura,
        cast(coalesce(dl.delivered_units, 0) as integer)    as delivered_units,
        cast(coalesce(u.unmet_units, 0) as integer)         as unmet_units,
        -- fill rate de disponibilidade (unidades) — decimal 0-1
        cast(
            coalesce(dl.delivered_units, 0) * 1.0
            / nullif(coalesce(dl.delivered_units, 0) + coalesce(u.unmet_units, 0), 0)
            as numeric(8, 4)
        )                                                   as fill_rate_stockout,
        -- fill rate de disponibilidade (unidades) — percentual 0-100
        cast(
            coalesce(dl.delivered_units, 0) * 100.0
            / nullif(coalesce(dl.delivered_units, 0) + coalesce(u.unmet_units, 0), 0)
            as numeric(8, 2)
        )                                                   as fill_rate_stockout_pct,
        -- perfect order rate (% de pedidos sem nenhuma ruptura)
        cast(
            o.pedidos_sem_ruptura * 100.0 / nullif(o.total_pedidos, 0)
            as numeric(8, 2)
        )                                                   as perfect_order_pct
    from orders_monthly o
    left join delivered dl on o.year_month = dl.year_month
    left join unmet u      on o.year_month = u.year_month
)

select * from final
order by year_month
