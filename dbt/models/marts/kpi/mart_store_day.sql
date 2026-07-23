{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Cockpit operacional do gerente de LOJA: vendas, ticket, unidades, rupturas e
-- disponibilidade (fill rate) por loja × dia. Apenas canal tienda — o ecommerce
-- é atendido pelo CD, não pela prateleira da loja. Grão: store_id × date_id.

with sales as (
    select * from {{ ref('fct_sales') }}
    where store_id is not null
),

dates as (
    select * from {{ ref('dim_date') }}
),

stockouts as (
    select * from {{ ref('stg_stockouts') }}
    where location_type = 'STORE'
),

sales_agg as (
    select
        s.store_id,
        s.date_id,
        count(distinct s.sale_id)                                            as num_pedidos,
        cast(sum(s.line_total_net * (1 + s.line_tax_rate)) as numeric(16, 2)) as gmv_gross,
        cast(sum(s.quantity_delivered) as integer)                           as units_sold
    from sales s
    group by s.store_id, s.date_id
),

so_agg as (
    select
        location_id                              as store_id,
        event_date                               as date_id,
        count(*)                                 as num_stockouts,
        cast(sum(quantity_requested) as integer) as unmet_units
    from stockouts
    group by location_id, event_date
)

select
    sa.store_id,
    sa.date_id,
    d.year_month,
    sa.num_pedidos,
    sa.gmv_gross,
    cast(sa.gmv_gross / nullif(sa.num_pedidos, 0) as numeric(12, 2)) as ticket_medio,
    sa.units_sold,
    coalesce(so.num_stockouts, 0)                                   as num_stockouts,
    coalesce(so.unmet_units, 0)                                     as unmet_units,
    cast(
        sa.units_sold * 100.0
        / nullif(sa.units_sold + coalesce(so.unmet_units, 0), 0)
        as numeric(8, 2)
    )                                                               as fill_rate_pct
from sales_agg sa
left join so_agg so on sa.store_id = so.store_id and sa.date_id = so.date_id
left join dates d   on sa.date_id = d.date_id
order by sa.date_id, sa.store_id
