{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- dim_product.gross_margin = sale_price - cost_price (valor absoluto, não decimal 0-1)
-- dim_product.margin_pct   = (sale_price - cost_price) / cost_price (decimal)
-- Para calcular custo da linha: unit_price_net * quantity_ordered * (1 - margin_pct_calculada)
-- Mais direto: revenue - gross_margin_unit * qty = custo

with sales as (
    select * from {{ ref('fct_sales') }}
),

products as (
    select * from {{ ref('dim_product') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

joined as (
    select
        d.year_month,
        d.year,
        d.month,
        p.category                                                              as product_category,
        p.iva_type,
        s.line_total_net                                                        as revenue,
        -- custo estimado da linha = unit_price_net * qty * (cost_price / sale_price)
        cast(
            s.unit_price_net * s.quantity_ordered
            * (p.cost_price / nullif(p.sale_price, 0))
            as numeric(14,2)
        )                                                                       as cost_estimate,
        s.quantity_ordered
    from sales s
    inner join products p on s.product_id = p.product_id
    inner join dates d    on s.date_id    = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        product_category,
        cast(sum(revenue)                                       as numeric(18,2)) as revenue,
        cast(sum(cost_estimate)                                 as numeric(18,2)) as cost,
        cast(sum(revenue) - sum(cost_estimate)                  as numeric(18,2)) as gross_profit,
        cast(
            (sum(revenue) - sum(cost_estimate)) / nullif(sum(revenue), 0)
            as numeric(8,4)
        )                                                                          as margin_pct,
        sum(quantity_ordered)                                                      as total_units
    from joined
    group by year_month, year, month, product_category
)

select * from aggregated
order by year_month, product_category
