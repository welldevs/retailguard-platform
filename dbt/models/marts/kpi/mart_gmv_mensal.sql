{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

with sales as (
    select * from {{ ref('fct_sales') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

-- fct_sales está no grão de LINHA: total_gross/subtotal_net são do CABEÇALHO
-- (repetidos em cada linha do pedido). Somá-los aqui multiplicaria o GMV pelo
-- nº de linhas/pedido. O correto é agregar pelas medidas de LINHA:
--   net   = line_total_net
--   gross = line_total_net * (1 + line_tax_rate)   (IVA real por produto)
joined as (
    select
        d.year_month,
        d.year,
        d.month,
        s.sale_id,
        s.line_total_net                                       as line_net,
        s.line_total_net * (1 + s.line_tax_rate)               as line_gross
    from sales s
    inner join dates d on s.date_id = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        cast(sum(line_gross)                            as numeric(18,2))  as gmv_gross,
        cast(sum(line_net)                              as numeric(18,2))  as gmv_net,
        count(distinct sale_id)                                            as num_pedidos,
        count(*)                                                           as num_linhas,
        cast(sum(line_gross) / nullif(count(distinct sale_id), 0)
            as numeric(14,2))                                              as ticket_medio
    from joined
    group by year_month, year, month
)

select * from aggregated
order by year_month
