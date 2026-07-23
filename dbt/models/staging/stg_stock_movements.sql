with source as (
    select * from {{ csv_source('stock_movements') }}
),

renamed as (
    select
        movement_id,
        -- Source column is literally named `date` (reserved word). The Snowflake RAW
        -- DDL renames it to movement_date on ingest; DuckDB keeps the raw CSV header.
        -- Staging normalizes both paths to `movement_date`.
        {% if target.type == 'duckdb' %}
        cast("date" as date)                    as movement_date,
        {% else %}
        cast(movement_date as date)             as movement_date,
        {% endif %}
        product_id,
        location_type,
        location_id,
        movement_type,
        reason,
        reference_id,
        cast(quantity_delta as integer)         as quantity_delta,
        cast(quantity_after as integer)         as quantity_after
    from source
)

select * from renamed
