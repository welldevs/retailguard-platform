{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Top categorias por demanda não atendida (ruptura). Grão: product_category.
-- Modelo dbt equivalente ao antigo script de streaming, lendo de staging + dim_product.

with stockouts as (
    select * from {{ ref('stg_stockouts') }}
),

products as (
    select product_id, category from {{ ref('dim_product') }}
),

joined as (
    select
        p.category                                          as product_category,
        so.quantity_requested - so.quantity_available       as qty_unmet
    from stockouts so
    inner join products p on so.product_id = p.product_id
),

aggregated as (
    select
        product_category,
        count(*)                                            as num_stockouts,
        cast(sum(qty_unmet) as integer)                     as qty_unmet
    from joined
    group by product_category
)

select * from aggregated
order by qty_unmet desc
