# ─────────────────────────────────────────────────────────────────────────────
# Snowpipes — vitrine de auto-ingest (MinIO → Parquet → Snowflake RAW canônico)
#
# Só provisionados quando minio_endpoint é definido (off por default).
# Análogo de PRODUÇÃO do `make load-parquet`: em produção o Snowpipe auto-anexa
# os Parquets normalizados às MESMAS tabelas RAW.* que o dbt lê; em dev/CI usa-se
# load_parquet.py (full refresh). O streaming publica eventos JÁ normalizados
# (erp/simulator/normalize.py), então o COPY destas pipes espelha o schema
# canônico de ddl_raw.sql (mesmo mapeamento de snowflake/load_parquet.py).
# Renomeio: parquet `date` → movement_date / event_date.
# ─────────────────────────────────────────────────────────────────────────────

resource "snowflake_pipe" "sales" {
  count    = var.minio_endpoint != "" ? 1 : 0
  name     = "PIPE_SALES"
  database = snowflake_database.retail_db.name
  schema   = snowflake_schema.raw.name
  comment  = "Snowpipe: auto-load sales Parquet partitions from MinIO → RAW.SALES."

  auto_ingest = true

  copy_statement = <<-SQL
    COPY INTO RETAIL_DB.RAW.SALES (
      sale_id, order_date, order_ts, customer_id, store_id, dc_id, region,
      payment_method, payment_status, payment_days, channel,
      subtotal_net, tax_amount, total_gross, status, has_partial_stockout,
      num_items, ticket_trend
    )
    FROM (
      SELECT
        $1:sale_id::VARCHAR(25),
        $1:order_date::VARCHAR(10),
        $1:order_ts::VARCHAR(25),
        $1:customer_id::VARCHAR(30),
        $1:store_id::VARCHAR(10),
        $1:dc_id::VARCHAR(10),
        $1:region::VARCHAR(60),
        $1:payment_method::VARCHAR(20),
        $1:payment_status::VARCHAR(20),
        $1:payment_days::NUMBER(3),
        $1:channel::VARCHAR(10),
        $1:subtotal_net::NUMBER(14,2),
        $1:tax_amount::NUMBER(14,2),
        $1:total_gross::NUMBER(14,2),
        $1:status::VARCHAR(20),
        $1:has_partial_stockout::VARCHAR(5),
        $1:num_items::NUMBER(5),
        $1:ticket_trend::VARCHAR(20)
      FROM @RETAIL_DB.RAW.RETAIL_STAGE_MINIO/sales/
    )
    PATTERN = '.*\.parquet'
  SQL

  depends_on = [
    snowflake_execute.tbl_sales,
    snowflake_execute.minio_stage,
  ]
}

resource "snowflake_pipe" "sale_lines" {
  count    = var.minio_endpoint != "" ? 1 : 0
  name     = "PIPE_SALE_LINES"
  database = snowflake_database.retail_db.name
  schema   = snowflake_schema.raw.name
  comment  = "Snowpipe: auto-load sale_lines Parquet partitions from MinIO → RAW.SALE_LINES."

  auto_ingest = true

  copy_statement = <<-SQL
    COPY INTO RETAIL_DB.RAW.SALE_LINES (
      sale_id, line_number, product_id, quantity_ordered, quantity_delivered,
      unit_price_net, discount_pct, tax_rate, line_total_net
    )
    FROM (
      SELECT
        $1:sale_id::VARCHAR(25),
        $1:line_number::NUMBER(5),
        $1:product_id::VARCHAR(30),
        $1:quantity_ordered::NUMBER(10),
        $1:quantity_delivered::NUMBER(10),
        $1:unit_price_net::NUMBER(12,4),
        $1:discount_pct::NUMBER(6,4),
        $1:tax_rate::NUMBER(4,2),
        $1:line_total_net::NUMBER(14,2)
      FROM @RETAIL_DB.RAW.RETAIL_STAGE_MINIO/sale_lines/
    )
    PATTERN = '.*\.parquet'
  SQL

  depends_on = [
    snowflake_execute.tbl_sale_lines,
    snowflake_execute.minio_stage,
  ]
}

resource "snowflake_pipe" "stock_movements" {
  count    = var.minio_endpoint != "" ? 1 : 0
  name     = "PIPE_STOCK_MOVEMENTS"
  database = snowflake_database.retail_db.name
  schema   = snowflake_schema.raw.name
  comment  = "Snowpipe: auto-load stock_movements Parquet partitions from MinIO → RAW.STOCK_MOVEMENTS."

  auto_ingest = true

  copy_statement = <<-SQL
    COPY INTO RETAIL_DB.RAW.STOCK_MOVEMENTS (
      movement_id, movement_date, product_id, location_type, location_id,
      movement_type, reason, reference_id, quantity_delta, quantity_after
    )
    FROM (
      SELECT
        $1:movement_id::VARCHAR(30),
        $1:date::VARCHAR(10),
        $1:product_id::VARCHAR(30),
        $1:location_type::VARCHAR(10),
        $1:location_id::VARCHAR(10),
        $1:movement_type::VARCHAR(10),
        $1:reason::VARCHAR(50),
        $1:reference_id::VARCHAR(30),
        $1:quantity_delta::NUMBER(12),
        $1:quantity_after::NUMBER(12)
      FROM @RETAIL_DB.RAW.RETAIL_STAGE_MINIO/stock_movements/
    )
    PATTERN = '.*\.parquet'
  SQL

  depends_on = [
    snowflake_execute.tbl_stock_movements,
    snowflake_execute.minio_stage,
  ]
}

resource "snowflake_pipe" "stockouts" {
  count    = var.minio_endpoint != "" ? 1 : 0
  name     = "PIPE_STOCKOUTS"
  database = snowflake_database.retail_db.name
  schema   = snowflake_schema.raw.name
  comment  = "Snowpipe: auto-load stockouts Parquet partitions from MinIO → RAW.STOCKOUTS."

  auto_ingest = true

  copy_statement = <<-SQL
    COPY INTO RETAIL_DB.RAW.STOCKOUTS (
      stockout_id, event_date, customer_id, product_id,
      location_type, location_id, quantity_requested, quantity_available
    )
    FROM (
      SELECT
        $1:stockout_id::VARCHAR(30),
        $1:date::VARCHAR(10),
        $1:customer_id::VARCHAR(30),
        $1:product_id::VARCHAR(30),
        $1:location_type::VARCHAR(10),
        $1:location_id::VARCHAR(10),
        $1:quantity_requested::NUMBER(10),
        $1:quantity_available::NUMBER(10)
      FROM @RETAIL_DB.RAW.RETAIL_STAGE_MINIO/stockouts/
    )
    PATTERN = '.*\.parquet'
  SQL

  depends_on = [
    snowflake_execute.tbl_stockouts,
    snowflake_execute.minio_stage,
  ]
}
