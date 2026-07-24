{{
    config(
        materialized='table',
        tags=['dim']
    )
}}

with products as (
    select * from {{ ref('stg_products') }}
)

select
    product_id,
    sku,
    name                                        as product_name,
    brand,
    category,
    category_path,
    category_group,
    unit,
    unit_of_measure,
    iva_type,
    -- Mapeamento correto (schema.py): S1=21% (general), S2=10% (reducido),
    -- S4=4% (superreducido). Antes estava invertido (S1↔S4).
    case iva_type
        when 'S1' then 0.21
        when 'S2' then 0.10
        when 'S4' then 0.04
    end::numeric(4,2)                           as iva_rate,
    cast(sale_price as numeric(10,2))           as sale_price,
    cast(cost_price as numeric(10,2))           as cost_price,
    cast(sale_price - cost_price as numeric(10,2)) as gross_margin,
    case
        when cost_price > 0
        then cast((sale_price - cost_price) / cost_price as numeric(6,4))
        else null
    end                                         as margin_pct,
    cast(tax_rate as numeric(6,4))              as tax_rate,
    active,
    active_since,
    supplier_code,
    barcode
from products
