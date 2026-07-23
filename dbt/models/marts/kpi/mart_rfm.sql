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

rfm_base as (
    select
        s.customer_id,
        r.max_date                                                              as reference_date,
        cast((r.max_date - max(s.date_id)) as integer)                          as recency,
        count(distinct s.sale_id)                                               as frequency,
        -- monetary pelas medidas de LINHA (total_gross é do cabeçalho, repetido
        -- por linha → somar inflaria pelo nº de linhas/pedido)
        cast(sum(s.line_total_net * (1 + s.line_tax_rate)) as numeric(18,2))    as monetary
    from sales s
    cross join ref_date r
    group by s.customer_id, r.max_date
),

rfm_scored as (
    select
        customer_id,
        reference_date,
        recency,
        frequency,
        monetary,
        -- NTILE: menor recency = melhor (score 3), então invertemos
        4 - ntile(3) over (order by recency asc)    as r_score,
        ntile(3) over (order by frequency asc)      as f_score,
        ntile(3) over (order by monetary asc)       as m_score
    from rfm_base
),

rfm_final as (
    select
        customer_id,
        reference_date,
        recency,
        frequency,
        monetary,
        r_score,
        f_score,
        m_score,
        concat(r_score::varchar, f_score::varchar, m_score::varchar) as rfm_segment
    from rfm_scored
),

rfm_labeled as (
    select
        *,
        case
            when r_score = 3 and f_score = 3 and m_score = 3          then 'Champions'
            when r_score >= 2 and (f_score + m_score) >= 5            then 'Loyal Customers'
            when r_score = 3                                            then 'Potential Loyalists'
            when r_score = 1 and (f_score + m_score) >= 4             then 'At Risk'
            when r_score = 1 and (f_score + m_score) >= 2             then 'Hibernating'
            else 'Lost'
        end                                                             as rfm_label
    from rfm_final
)

select * from rfm_labeled
order by monetary desc
