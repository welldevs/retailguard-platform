{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Mermas / caducidad — perdas de perecíveis por validade. Grão:
-- year_month × location_type × category. Responde "quanto perdi por caducidad,
-- por categoria, ao longo do tempo, em loja vs CD?". A merma é uma saída real
-- de estoque (reason='waste'), então reconcilia com stock_movements.

with waste as (
    select * from {{ ref('stg_product_waste') }}
),

dates as (
    select * from {{ ref('dim_date') }}
),

joined as (
    select
        d.year_month,
        d.year,
        d.month,
        w.location_type,
        w.category                                          as product_category,
        w.quantity,
        w.lost_cost
    from waste w
    inner join dates d on w.waste_date = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        location_type,
        product_category,
        count(*)                                            as num_eventos,
        cast(sum(quantity) as integer)                      as units_wasted,
        cast(sum(lost_cost) as numeric(16, 2))              as lost_cost
    from joined
    group by year_month, year, month, location_type, product_category
)

select * from aggregated
order by year_month, lost_cost desc
