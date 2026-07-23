{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Customer Lifetime Value (LTV) simplificado: receita histórica total por cliente.
-- LTV = soma de line_total_net ao longo de toda a vida do cliente no dataset.
-- Inclui métricas de lifecycle (dias ativo, frequência, ticket médio, coorte).
-- Grão: customer_id (uma linha por cliente com ao menos 1 compra).

with sales as (
    select * from {{ ref('fct_sales') }}
),

customers as (
    select
        customer_id,
        segment,
        left(cast(registration_date as varchar), 7) as cohort_month,
        registration_date
    from {{ ref('stg_customers') }}
),

dates as (
    select date_id, year_month
    from {{ ref('dim_date') }}
),

customer_sales as (
    select
        s.customer_id,
        count(distinct s.sale_id)                                               as total_orders,
        count(s.sale_id)                                                        as total_lines,
        cast(sum(s.line_total_net * (1 + s.line_tax_rate)) as numeric(18, 2))  as total_revenue_gross,
        cast(sum(s.line_total_net) as numeric(18, 2))                          as total_revenue_net,
        cast(sum(s.quantity_ordered) as integer)                               as total_units,
        min(s.date_id)                                                          as first_order_date,
        max(s.date_id)                                                          as last_order_date
    from sales s
    group by s.customer_id
),

customer_ltv as (
    select
        cs.customer_id,
        c.segment,
        c.cohort_month,
        c.registration_date,
        cs.total_orders,
        cs.total_lines,
        cs.total_revenue_gross,
        cs.total_revenue_net,
        cs.total_units,
        cs.first_order_date,
        cs.last_order_date,
        -- avg order value (gross)
        cast(
            cs.total_revenue_gross / nullif(cs.total_orders, 0)
            as numeric(12, 2)
        )                                                                       as aov_gross,
        -- avg units per order
        cast(
            cs.total_units * 1.0 / nullif(cs.total_orders, 0)
            as numeric(8, 2)
        )                                                                       as avg_units_per_order,
        -- active span (days between first and last order)
        cast(cs.last_order_date - cs.first_order_date as integer)              as active_span_days
    from customer_sales cs
    inner join customers c on cs.customer_id = c.customer_id
)

select * from customer_ltv
order by total_revenue_gross desc
