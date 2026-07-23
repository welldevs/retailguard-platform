{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- Cohort retention: quantos clientes de cada coorte (mês de registro) ainda compraram
-- em cada mês de atividade subsequente.
-- Grão: cohort_month × activity_month (uma linha por par).
-- Métricas: cohort_size, active_customers, retention_rate (active / cohort_size).

with customers as (
    select
        customer_id,
        -- coorte = mês em que o cliente foi registrado (adquirido)
        left(cast(registration_date as varchar), 7) as cohort_month
    from {{ ref('stg_customers') }}
),

sales as (
    select * from {{ ref('fct_sales') }}
),

dates as (
    select date_id, year_month as activity_month
    from {{ ref('dim_date') }}
),

-- unique customer × activity_month combinations
customer_activity as (
    select distinct
        s.customer_id,
        d.activity_month
    from sales s
    inner join dates d on s.date_id = d.date_id
),

cohort_activity as (
    select
        c.cohort_month,
        ca.activity_month,
        count(distinct ca.customer_id) as active_customers
    from customer_activity ca
    inner join customers c on ca.customer_id = c.customer_id
    group by c.cohort_month, ca.activity_month
),

cohort_sizes as (
    select
        cohort_month,
        count(customer_id) as cohort_size
    from customers
    group by cohort_month
)

select
    ca.cohort_month,
    ca.activity_month,
    cs.cohort_size,
    ca.active_customers,
    cast(
        ca.active_customers * 1.0 / nullif(cs.cohort_size, 0)
        as numeric(8, 4)
    )                                                   as retention_rate,
    cast(
        ca.active_customers * 100.0 / nullif(cs.cohort_size, 0)
        as numeric(8, 2)
    )                                                   as retention_pct
from cohort_activity ca
inner join cohort_sizes cs on ca.cohort_month = cs.cohort_month
order by ca.cohort_month, ca.activity_month
