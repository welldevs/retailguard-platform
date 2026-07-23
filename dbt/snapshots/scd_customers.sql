{% snapshot scd_customers %}
{{ config(
    target_schema='MARTS',
    unique_key='customer_id',
    strategy='check',
    check_cols=['segment', 'avg_ticket', 'ticket_trend'],
    invalidate_hard_deletes=true
) }}
select
    customer_id,
    segment,
    cast(avg_ticket as numeric(10,2)) as avg_ticket,
    ticket_trend
from {{ csv_source('customers') }}
{% endsnapshot %}
