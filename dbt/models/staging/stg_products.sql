with source as (
    select * from {{ csv_source('products') }}
),

renamed as (
    select
        product_id,
        sku,
        name,
        brand,
        category,
        category_path,
        cast(price as numeric(10, 2))                   as price,
        unit,
        cast(active as boolean)                         as active,
        barcode,
        cast(sale_price as numeric(10, 2))              as sale_price,
        cast(cost_price as numeric(10, 2))              as cost_price,
        cast(tax_rate as numeric(6, 4))                 as tax_rate,
        iva_type,
        unit_of_measure,
        supplier_code,
        cast(active_since as date)                      as active_since,
        cast(shelf_life_days as integer)                as shelf_life_days,
        cast(is_perishable as integer)                  as is_perishable
    from source
)

select * from renamed
