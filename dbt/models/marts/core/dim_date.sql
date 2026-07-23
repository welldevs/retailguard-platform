{{
    config(
        materialized='table',
        tags=['dim']
    )
}}

{#
  Conformed date dimension. The spine spans 2024-01-01 .. 2028-12-31 (1827 days)
  on purpose: the simulator can generate data anchored either to fixed dates
  (--start/--end, default 2024) or to a trailing window relative to run date
  (`make simulate` uses --period 365d). A 5-year spine guarantees every fact
  date_id resolves regardless of when the data was generated.
#}
{% if target.type == 'duckdb' %}

with date_spine as (
    select
        (date '2024-01-01' + interval (n) day)::date as date_day
    from generate_series(0, 1826) as t(n)
),

enriched as (
    select
        date_day                                                                    as date_id,
        extract('year'    from date_day)::integer                                   as year,
        extract('quarter' from date_day)::integer                                   as quarter,
        extract('month'   from date_day)::integer                                   as month,
        strftime(date_day, '%B')                                                    as month_name,
        extract('week'    from date_day)::integer                                   as week_of_year,
        extract('day'     from date_day)::integer                                   as day_of_month,
        extract('dow'     from date_day)::integer                                   as day_of_week,
        strftime(date_day, '%A')                                                    as day_name,
        case when extract('dow' from date_day) in (0, 6) then true else false end  as is_weekend,
        concat(
            extract('year' from date_day)::varchar, '-Q',
            extract('quarter' from date_day)::varchar
        )                                                                           as year_quarter,
        strftime(date_day, '%Y-%m')                                                as year_month
    from date_spine
)

select * from enriched

{% else %}

with date_spine as (
    select
        DATEADD(day, SEQ4(), '2024-01-01'::date) as date_day
    from TABLE(GENERATOR(ROWCOUNT => 1827))
),

enriched as (
    select
        date_day                                                                                as date_id,
        EXTRACT(year    FROM date_day)::integer                                                 as year,
        EXTRACT(quarter FROM date_day)::integer                                                 as quarter,
        EXTRACT(month   FROM date_day)::integer                                                 as month,
        TO_CHAR(date_day, 'MMMM')                                                              as month_name,
        EXTRACT(week    FROM date_day)::integer                                                 as week_of_year,
        EXTRACT(day     FROM date_day)::integer                                                 as day_of_month,
        DAYOFWEEK(date_day)                                                                     as day_of_week,
        DAYNAME(date_day)                                                                       as day_name,
        CASE WHEN DAYOFWEEK(date_day) IN (0, 6) THEN TRUE ELSE FALSE END                       as is_weekend,
        CONCAT(EXTRACT(year FROM date_day)::varchar, '-Q', EXTRACT(quarter FROM date_day)::varchar) as year_quarter,
        TO_CHAR(date_day, 'YYYY-MM')                                                           as year_month
    from date_spine
)

select * from enriched

{% endif %}
