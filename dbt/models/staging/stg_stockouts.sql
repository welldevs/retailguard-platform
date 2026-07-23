with source as (
    select * from {{ csv_source('stockouts') }}
),

renamed as (
    select
        stockout_id,
        -- Source column is literally named `date` (reserved word). The Snowflake RAW
        -- DDL renames it to event_date on ingest; DuckDB keeps the raw CSV header.
        -- Staging normalizes both paths to `event_date`.
        {% if target.type == 'duckdb' %}
        cast("date" as date)                        as event_date,
        {% else %}
        cast(event_date as date)                    as event_date,
        {% endif %}
        customer_id,
        product_id,
        location_type,
        location_id,
        cast(quantity_requested as integer)         as quantity_requested,
        cast(quantity_available as integer)         as quantity_available
    from source
)

select * from renamed
