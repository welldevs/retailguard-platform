{{
    config(
        materialized='incremental',
        unique_key='movement_id',
        incremental_strategy='merge',
        on_schema_change='sync_all_columns',
        tags=['fct'],
        indexes=[{'columns': ['date_id', 'product_id']}]
    )
}}

with movements as (
    select * from {{ ref('stg_stock_movements') }}
    {% if is_incremental() %}
    where movement_date > (select coalesce(max(date_id), cast('1900-01-01' as date)) from {{ this }})
    {% endif %}
)

select
    movement_id,
    product_id,
    movement_date                               as date_id,
    location_type,
    location_id,
    movement_type,
    reason,
    reference_id,
    cast(quantity_delta as integer)             as quantity_delta,
    cast(quantity_after as integer)             as quantity_after
from movements
