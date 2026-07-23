{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- dim_product.iva_type: S1=21% (general), S2=10% (reducido), S4=4% (superreducido)
-- fct_sales.line_tax_rate: alíquota da linha
-- fct_sales.line_total_net: base imponible da linha
-- cuota_iva da linha = line_total_net * line_tax_rate

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
        p.iva_type,
        p.iva_rate,
        s.line_total_net                                                        as base_imponible,
        cast(s.line_total_net * s.line_tax_rate as numeric(14,2))              as cuota_iva,
        cast(s.line_total_net + s.line_total_net * s.line_tax_rate
            as numeric(14,2))                                                   as total_com_iva
    from sales s
    inner join products p on s.product_id = p.product_id
    inner join dates d    on s.date_id    = d.date_id
),

aggregated as (
    select
        year_month,
        year,
        month,
        iva_type,
        iva_rate,
        cast(sum(base_imponible)    as numeric(18,2))   as base_imponible,
        cast(sum(cuota_iva)         as numeric(18,2))   as cuota_iva,
        cast(sum(total_com_iva)     as numeric(18,2))   as total_com_iva,
        count(*)                                        as num_linhas
    from joined
    group by year_month, year, month, iva_type, iva_rate
)

select * from aggregated
order by year_month, iva_type
