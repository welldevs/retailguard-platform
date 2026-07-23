resource "snowflake_database" "retail_db" {
  name    = "RETAIL_DB"
  comment = "RetailGuard — Spain simulation. Schemas: RAW (OLTP), STAGING, MARTS, PUBLIC (Streamlit)."
}

resource "snowflake_schema" "raw" {
  database = snowflake_database.retail_db.name
  name     = "RAW"
  comment  = "Landing zone — 17 tables loaded from ERP simulation CSVs + 4 stream tables from Kafka/Parquet."
}

resource "snowflake_schema" "staging" {
  database = snowflake_database.retail_db.name
  name     = "STAGING"
  comment  = "dbt staging models: light casting, renaming, and deduplication."
}

resource "snowflake_schema" "marts" {
  database = snowflake_database.retail_db.name
  name     = "MARTS"
  comment  = "dbt mart models: business-ready aggregations consumed by Streamlit and ad-hoc queries."
}

resource "snowflake_schema" "public" {
  database = snowflake_database.retail_db.name
  name     = "PUBLIC"
  comment  = "Streamlit in Snowflake app (RETAIL_DASHBOARD). Required by snowflake.yml."
}
