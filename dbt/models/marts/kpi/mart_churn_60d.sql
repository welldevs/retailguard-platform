{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

with sales as (
    select * from {{ ref('fct_sales') }}
),

ref_date as (
    select max(date_id) as max_date from sales
),

customer_last_purchase as (
    select
        customer_id,
        max(date_id)            as last_purchase_date,
        min(date_id)            as first_purchase_date,
        count(distinct sale_id) as total_orders
    from sales
    group by customer_id
),

churn_calc as (
    select
        c.customer_id,
        c.last_purchase_date,
        c.first_purchase_date,
        c.total_orders,
        r.max_date                                              as reference_date,
        cast((r.max_date - c.last_purchase_date) as integer)   as days_since_purchase,
        case
            when (r.max_date - c.last_purchase_date) > 60 then true
            else false
        end                                                     as is_churned
    from customer_last_purchase c
    cross join ref_date r
),

-- current segment from stg_customers (non-SCD2 snapshot, current-state)
customer_profile as (
    select customer_id, segment, registration_date
    from {{ ref('stg_customers') }}
),

-- avg delivery delay per customer (tienda customers have no deliveries → null → 0)
delivery_delays as (
    select
        s.customer_id,
        count(d.delivery_id)                                                as total_deliveries,
        cast(
            avg(
                case
                    when d.actual_delivery_date > d.estimated_delivery_date
                    then (d.actual_delivery_date - d.estimated_delivery_date)
                    else 0
                end
            ) as numeric(8, 2)
        )                                                                   as avg_delay_days,
        cast(
            sum(case when d.actual_delivery_date > d.estimated_delivery_date then 1 else 0 end)
            * 1.0 / nullif(count(d.delivery_id), 0)
            as numeric(8, 4)
        )                                                                   as late_delivery_rate
    from {{ ref('stg_deliveries') }} d
    inner join sales s on d.sale_id = s.sale_id
    group by s.customer_id
),

-- stockout events that impacted each customer directly
customer_stockouts as (
    select
        customer_id,
        count(stockout_id) as stockout_count
    from {{ ref('stg_stockouts') }}
    group by customer_id
)

select
    c.customer_id,
    c.last_purchase_date,
    c.first_purchase_date,
    c.total_orders,
    c.reference_date,
    c.days_since_purchase,
    c.is_churned,
    p.segment,
    p.registration_date,
    coalesce(dd.total_deliveries, 0)    as total_deliveries,
    coalesce(dd.avg_delay_days, 0.0)    as avg_delay_days,
    coalesce(dd.late_delivery_rate, 0.0) as late_delivery_rate,
    coalesce(so.stockout_count, 0)      as stockout_count
from churn_calc c
left join customer_profile p  on c.customer_id = p.customer_id
left join delivery_delays dd  on c.customer_id = dd.customer_id
left join customer_stockouts so on c.customer_id = so.customer_id
order by days_since_purchase desc
