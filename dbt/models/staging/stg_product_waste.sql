with source as (
    select * from {{ csv_source('product_waste') }}
),

renamed as (
    select
        waste_id,
        -- Source column is literally `date` (reserved word). Snowflake RAW DDL
        -- renames it to waste_date on ingest; DuckDB keeps the raw CSV header.
        -- Staging normalizes both paths to `waste_date`.
        {% if target.type == 'duckdb' %}
        cast("date" as date)                        as waste_date,
        {% else %}
        cast(waste_date as date)                    as waste_date,
        {% endif %}
        product_id,
        category,
        location_type,
        location_id,
        cast(quantity as integer)                   as quantity,
        cast(unit_cost as numeric(12, 4))           as unit_cost,
        cast(lost_cost as numeric(14, 2))           as lost_cost,
        reason
    from source
)

select * from renamed
