{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Afluência de vendas por HORA do dia (hora-punta) — habilitada pelo carimbo
-- intradía order_ts. Grão: order_hour (0-23). Responde a pergunta operacional
-- nº 1 do gerente: "qual a hora de pico?" → dimensionamento de caixas/pessoal.

with sales as (
    select order_hour, total_gross from {{ ref('stg_sales') }}
),

agg as (
    select
        order_hour,
        count(*)                                                      as num_pedidos,
        cast(sum(total_gross) as numeric(18, 2))                      as gmv_gross,
        cast(sum(total_gross) / nullif(count(*), 0) as numeric(12, 2)) as ticket_medio
    from sales
    group by order_hour
)

select
    a.order_hour,
    a.num_pedidos,
    a.gmv_gross,
    a.ticket_medio,
    cast(a.num_pedidos * 100.0 / nullif(sum(a.num_pedidos) over (), 0) as numeric(6, 2)) as pct_pedidos
from agg a
order by a.order_hour
