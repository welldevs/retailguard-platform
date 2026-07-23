{{
    config(
        materialized='table',
        tags=['kpi']
    )
}}

-- stg_deliveries: delivery_id, sale_id, dc_id, carrier, tracking_number,
--                 dispatch_date, estimated_delivery_date, actual_delivery_date,
--                 delivery_status, weight_kg, packages, signature_required, total_amount

with deliveries as (
    select * from {{ ref('stg_deliveries') }}
),

carrier_stats as (
    select
        carrier,
        count(delivery_id)                                          as total_entregas,
        -- on_time: actual_delivery_date <= estimated_delivery_date
        cast(
            sum(
                case
                    when actual_delivery_date is not null
                     and actual_delivery_date <= estimated_delivery_date
                    then 1 else 0
                end
            ) * 1.0 / nullif(
                count(case when actual_delivery_date is not null then 1 end), 0
            )
            as numeric(8,4)
        )                                                           as on_time_rate,
        cast(
            avg(
                case
                    when actual_delivery_date is not null
                     and actual_delivery_date > estimated_delivery_date
                    then (actual_delivery_date - estimated_delivery_date)
                    else null
                end
            )
            as numeric(8,2)
        )                                                           as avg_delay_days,
        cast(sum(packages) as integer)                             as total_packages,
        cast(sum(weight_kg) as numeric(14,2))                      as total_weight_kg,
        cast(avg(weight_kg) as numeric(8,2))                       as avg_weight_kg,
        cast(sum(total_amount) as numeric(18,2))                   as total_amount,
        count(case when delivery_status = 'delivered' then 1 end)  as delivered_count,
        count(case when delivery_status = 'in_transit' then 1 end) as in_transit_count
    from deliveries
    group by carrier
)

select * from carrier_stats
order by total_entregas desc
