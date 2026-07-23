-- Cross-check: MART_GMV_MENSAL.gmv_gross must equal an INDEPENDENT GMV recompute
-- straight from the staging layer (stg_sales x stg_sale_lines), bypassing
-- fct_sales / dim_date. This validates that the incremental fact build, the
-- dimensional join and the monthly aggregation all CONSERVE GMV — and catches
-- incremental drift (stale fct_sales rows) that a mart-only view would hide.
--
-- Migrated from snowflake/sql/oltp_queries.sql (#24 "cross-check mart vs raw").
-- Passes when the query returns ZERO rows. Tolerance 0.10 absorbs the mart's
-- numeric(18,2) rounding; a real divergence is orders of magnitude larger.

with recomputed as (
    select
        substr(cast(s.order_date as varchar), 1, 7)                     as year_month,
        sum(sl.line_total_net * (1 + sl.tax_rate))                      as gmv_gross_src
    from {{ ref('stg_sale_lines') }} sl
    inner join {{ ref('stg_sales') }} s on s.sale_id = sl.sale_id
    group by 1
),

mart as (
    select year_month, gmv_gross as gmv_gross_mart
    from {{ ref('mart_gmv_mensal') }}
)

select
    coalesce(r.year_month, m.year_month)                                as year_month,
    r.gmv_gross_src,
    m.gmv_gross_mart,
    abs(coalesce(r.gmv_gross_src, 0) - coalesce(m.gmv_gross_mart, 0))    as abs_diff
from recomputed r
full outer join mart m on m.year_month = r.year_month
where abs(coalesce(r.gmv_gross_src, 0) - coalesce(m.gmv_gross_mart, 0)) > 0.10
