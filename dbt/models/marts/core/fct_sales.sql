{{
    config(
        materialized='incremental',
        unique_key='sale_line_key',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns',
        tags=['fct']
    )
}}

with sales as (
    select * from {{ ref('stg_sales') }}
    {% if is_incremental() %}
    where order_date > (select coalesce(max(date_id), cast('1900-01-01' as date)) from {{ this }})
    {% endif %}
),

lines as (
    select * from {{ ref('stg_sale_lines') }}
),

joined as (
    select
        -- surrogate key (composite grain: sale_id + line_number)
        {{ dbt_utils.generate_surrogate_key(['s.sale_id', 'l.line_number']) }} as sale_line_key,

        -- keys
        s.sale_id,
        l.line_number,
        l.product_id,
        s.customer_id,
        s.store_id,
        s.dc_id,
        s.order_date                                        as date_id,

        -- degenerate dimensions
        s.channel,
        s.region,
        s.payment_method,
        s.payment_status,
        s.status                                            as order_status,
        s.payment_days,
        s.ticket_trend,

        -- line measures
        l.quantity_ordered,
        l.quantity_delivered,
        l.unit_price_net,
        l.discount_pct,
        l.tax_rate                                          as line_tax_rate,
        l.line_total_net,
        cast(
            l.unit_price_net * l.quantity_ordered * l.discount_pct
            as numeric(14,2)
        )                                                   as discount_amount,

        -- header measures
        s.subtotal_net,
        s.tax_amount,
        s.total_gross,
        s.num_items,
        s.has_partial_stockout
    from sales s
    inner join lines l on s.sale_id = l.sale_id
)

select * from joined
