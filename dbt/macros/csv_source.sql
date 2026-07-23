{% macro csv_source(table_name) %}
  {#
    Returns the right source reference depending on the target:
    - dev_raw  (DuckDB, local): physical RAW tables main.* loaded by load_raw_layer.py
    - ci       (DuckDB, CI):    reads CSVs directly via read_csv_auto (DBT_CSV_DIR)
    - snowflake (prod):         the RAW schema table loaded via COPY INTO

    Usage in staging models:
      select * from {{ csv_source('sales') }}
  #}
  {% if target.type == 'duckdb' and target.name == 'dev_raw' %}
    main."{{ table_name }}"
  {% elif target.type == 'duckdb' %}
    {%- set csv_dir = env_var('DBT_CSV_DIR', '../source') -%}
    read_csv_auto('{{ csv_dir }}/{{ table_name }}.csv', header=true)
  {% else %}
    {{ source('raw', table_name) }}
  {% endif %}
{% endmacro %}
