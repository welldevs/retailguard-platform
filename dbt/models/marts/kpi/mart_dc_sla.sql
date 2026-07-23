{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- DC SLA: on-time delivery rate e atraso médio por Distribution Center de origem.
-- Grão: dc_id (uma linha por DC).
-- Fonte: stg_deliveries (dc_id, estimated_delivery_date, actual_delivery_date).

with deliveries as (
    select * from {{ ref('stg_deliveries') }}
),

dc_stats as (
    select
        dc_id,
        count(delivery_id)                                              as total_entregas,
        -- on-time: actual_delivery_date <= estimated_delivery_date
        cast(
            sum(
                case
                    when actual_delivery_date is not null
                     and actual_delivery_date <= estimated_delivery_date then 1 else 0
                end
            ) * 1.0 / nullif(
                count(case when actual_delivery_date is not null then 1 end), 0
            )
            as numeric(8, 4)
        )                                                               as on_time_rate,
        -- avg delay when late (days)
        cast(
            avg(
                case
                    when actual_delivery_date is not null
                     and actual_delivery_date > estimated_delivery_date
                    then cast(actual_delivery_date - estimated_delivery_date as integer)
                    else null
                end
            )
            as numeric(8, 2)
        )                                                               as avg_delay_days_when_late,
        -- avg transit time (dispatch to actual delivery)
        cast(
            avg(
                case
                    when actual_delivery_date is not null
                    then cast(actual_delivery_date - dispatch_date as integer)
                    else null
                end
            )
            as numeric(8, 2)
        )                                                               as avg_transit_days,
        count(case when delivery_status = 'delivered' then 1 end)      as delivered_count,
        count(case when delivery_status = 'in_transit' then 1 end)     as in_transit_count,
        cast(sum(packages) as integer)                                  as total_packages,
        cast(sum(weight_kg) as numeric(14, 2))                         as total_weight_kg
    from deliveries
    where dc_id is not null
    group by dc_id
)

select
    dc_id,
    total_entregas,
    on_time_rate,
    avg_delay_days_when_late,
    avg_transit_days,
    delivered_count,
    in_transit_count,
    total_packages,
    total_weight_kg
from dc_stats
order by on_time_rate desc
