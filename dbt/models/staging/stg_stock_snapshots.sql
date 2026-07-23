with source as (
    select * from {{ csv_source('stock_snapshots') }}
),

renamed as (
    select
        cast(snapshot_date as date)                 as snapshot_date,
        product_id,
        location_type,
        location_id,
        cast(quantity_on_hand as integer)           as quantity_on_hand,
        cast(quantity_reserved as integer)          as quantity_reserved,
        cast(quantity_in_transit as integer)        as quantity_in_transit,
        cast(reorder_point as integer)              as reorder_point,
        cast(max_stock as integer)                  as max_stock,
        cast(unit_cost as numeric(12,4))            as unit_cost
    from source
)

select * from renamed
