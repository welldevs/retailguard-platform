# ─────────────────────────────────────────────────────────────────────────────
# Storage — File Formats + Stages
#
# Uses snowflake_execute (raw SQL) to match the exact DDL already in
# snowflake/sql/ddl_raw.sql and snowflake/sql/minio_external_stage.sql.
# ─────────────────────────────────────────────────────────────────────────────

# ── CSV File Format ───────────────────────────────────────────────────────────
resource "snowflake_execute" "csv_format" {
  execute = <<-SQL
    CREATE OR REPLACE FILE FORMAT RETAIL_DB.RAW.CSV_FORMAT
      TYPE                         = 'CSV'
      FIELD_DELIMITER              = ','
      RECORD_DELIMITER             = '\n'
      SKIP_HEADER                  = 1
      FIELD_OPTIONALLY_ENCLOSED_BY = '"'
      NULL_IF                      = ('', 'NULL', 'None')
      EMPTY_FIELD_AS_NULL          = TRUE
      DATE_FORMAT                  = 'YYYY-MM-DD'
      TIMESTAMP_FORMAT             = 'YYYY-MM-DD HH24:MI:SS'
      COMMENT                      = 'Standard CSV format for ERP simulation output (PUT + COPY path).'
  SQL
  revert  = "DROP FILE FORMAT IF EXISTS RETAIL_DB.RAW.CSV_FORMAT"

  depends_on = [snowflake_schema.raw]
}

# ── Parquet File Format (Kafka → MinIO → Snowflake path) ─────────────────────
resource "snowflake_execute" "parquet_format" {
  execute = <<-SQL
    CREATE OR REPLACE FILE FORMAT RETAIL_DB.RAW.RETAIL_PARQUET_FMT
      TYPE               = PARQUET
      SNAPPY_COMPRESSION = TRUE
      BINARY_AS_TEXT     = FALSE
      NULL_IF            = ('NULL', 'null', '')
      COMMENT            = 'Snappy-compressed Parquet written by parquet_consumer.py from Kafka topics.'
  SQL
  revert  = "DROP FILE FORMAT IF EXISTS RETAIL_DB.RAW.RETAIL_PARQUET_FMT"

  depends_on = [snowflake_schema.raw]
}

# ── Internal Stage (CSV bulk load) ────────────────────────────────────────────
resource "snowflake_execute" "internal_stage" {
  execute = <<-SQL
    CREATE OR REPLACE STAGE RETAIL_DB.RAW.RETAIL_STAGE
      FILE_FORMAT = RETAIL_DB.RAW.CSV_FORMAT
      COMMENT     = 'Internal stage: PUT CSV files here, then COPY INTO raw tables. Used by load_snowflake_raw.py.'
  SQL
  revert  = "DROP STAGE IF EXISTS RETAIL_DB.RAW.RETAIL_STAGE"

  depends_on = [snowflake_execute.csv_format]
}

# ── External Stage (MinIO / S3 — Kafka → Parquet streaming path) ─────────────
# Only created when minio_endpoint is provided (streaming architecture).
#
# SECURITY NOTE: credentials are stored in Snowflake state and the stage object.
# In production, replace inline credentials with a named STORAGE INTEGRATION
# backed by an IAM role (no long-lived keys exposed).
resource "snowflake_execute" "minio_stage" {
  count = var.minio_endpoint != "" ? 1 : 0

  execute = <<-SQL
    CREATE OR REPLACE STAGE RETAIL_DB.RAW.RETAIL_STAGE_MINIO
      URL         = 's3://${var.minio_bucket}/raw/'
      ENDPOINT    = '${var.minio_endpoint}'
      CREDENTIALS = (
        AWS_KEY_ID     = '${var.minio_access_key}'
        AWS_SECRET_KEY = '${var.minio_secret_key}'
      )
      FILE_FORMAT = RETAIL_DB.RAW.RETAIL_PARQUET_FMT
      COMMENT     = 'MinIO data lake — Parquet files written by parquet_consumer.py.'
  SQL
  revert  = "DROP STAGE IF EXISTS RETAIL_DB.RAW.RETAIL_STAGE_MINIO"

  depends_on = [snowflake_execute.parquet_format]
}
