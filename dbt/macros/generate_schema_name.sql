{% macro generate_schema_name(custom_schema_name, node) -%}
    {#
      Snowflake: use custom_schema directly → RETAIL_DB.STAGING.* and RETAIL_DB.MARTS.*
      DuckDB:    use dbt default behavior  → main_staging, main_marts (prefix with target schema)

      NOTE: default_schema must be set from target.schema (dbt's built-in macro does
      this; a custom override must too — senão `default_schema` fica indefinido/vazio
      e os schemas viram "_staging"/"_marts"/"" em vez de main_staging/main_marts/main).
    #}
    {%- set default_schema = target.schema -%}
    {%- if target.type != 'duckdb' -%}
        {%- if custom_schema_name is none -%}
            {{ default_schema }}
        {%- else -%}
            {{ custom_schema_name | trim | upper }}
        {%- endif -%}
    {%- else -%}
        {%- if custom_schema_name is none -%}
            {{ default_schema }}
        {%- else -%}
            {{ default_schema }}_{{ custom_schema_name | trim }}
        {%- endif -%}
    {%- endif -%}
{%- endmacro %}
