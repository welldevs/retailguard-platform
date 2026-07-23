{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Mart de produtos para Top SKUs e drill-down por categoria.
-- Grão: (year_month, product_id). Mesmos refs do mart_margem_por_categoria.
-- Custo estimado da linha = unit_price_net * qty * (cost_price / sale_price).

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
        s.product_id,
        p.product_name,
        p.category,
        s.line_total_net                                                        as revenue,
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
        product_id,
        product_name,
        category,
        cast(sum(revenue)                                       as numeric(18,2)) as revenue,
        sum(quantity_ordered)                                                     as units,
        cast(sum(cost_estimate)                                 as numeric(18,2)) as cost,
        cast(
            (sum(revenue) - sum(cost_estimate)) / nullif(sum(revenue), 0)
            as numeric(8,4)
        )                                                                          as margin_pct
    from joined
    group by year_month, year, month, product_id, product_name, category
)

select * from aggregated
order by year_month, revenue desc
