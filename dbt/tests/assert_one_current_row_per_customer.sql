-- SCD2 invariant: each customer_id must have exactly one current row
-- (dbt_valid_to is null  <=>  is_current = true).
-- The test passes when this query returns zero rows.

select
    customer_id,
    count(*) as current_rows
from {{ ref('dim_customer') }}
where is_current
group by customer_id
having count(*) <> 1
