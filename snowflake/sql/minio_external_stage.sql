-- =============================================================================
-- MinIO External Stage — caminho de auto-ingest (showcase / referência)
--
-- Arquitetura:
--   ERP Simulator --kafka--> Kafka --parquet_consumer--> MinIO (Parquet/Hive)
--   MinIO --[external stage]--> Snowflake RAW.* (CANÔNICO) --dbt--> Marts
--
-- O streaming publica eventos JÁ NORMALIZADOS (erp/simulator/normalize.py), então
-- caem nas MESMAS tabelas RAW.* canônicas que o batch (CSV) usa e que o dbt lê —
-- fonte única de verdade, zero drift. Não há mais tabelas *_STREAM.
--
-- Este arquivo define APENAS o file format + external stage (referência para o
-- caminho external-stage manual). Os mapeamentos COPY canônicos vivem em um único
-- lugar para evitar duplicação/drift:
--   • snowflake/load_parquet.py      → loader internal-stage (dev/CI, full refresh)
--   • terraform/pipes.tf             → Snowpipes auto-ingest (produção, append)
--
-- MinIO é S3-compatível. O mesmo SQL roda contra AWS S3 / Cloudflare R2 / Azure.
-- Demo local: exponha o MinIO via `ngrok http 9000` e use a URL HTTPS abaixo.
-- Em produção: use STORAGE INTEGRATION — nunca hardcode credenciais.
-- =============================================================================

USE DATABASE RETAIL_DB;
USE SCHEMA   RAW;
USE WAREHOUSE COMPUTE_WH;


-- ── 1. Parquet file format ─────────────────────────────────────────────────────
CREATE OR REPLACE FILE FORMAT RETAIL_PARQUET_FMT
    TYPE               = PARQUET
    SNAPPY_COMPRESSION = TRUE
    BINARY_AS_TEXT     = FALSE
    NULL_IF            = ('NULL', 'null', '');


-- ── 2. External stage apontando para o MinIO ────────────────────────────────────
-- Troque <MINIO_PUBLIC_ENDPOINT> pela sua URL ngrok (ex.: abc123.ngrok.io).
CREATE OR REPLACE STAGE RETAIL_STAGE_MINIO
    URL         = 's3://retail-datalake/raw/'
    ENDPOINT    = '<MINIO_PUBLIC_ENDPOINT>'
    -- DEMO DEFAULTS (MinIO local): troque por credenciais reais em QUALQUER deploy não-local.
    -- A via IaC (terraform/storage.tf) já parametriza isto via var.minio_secret_key.
    CREDENTIALS = (
        AWS_KEY_ID     = 'minioadmin'
        AWS_SECRET_KEY = 'minioadmin123'
    )
    FILE_FORMAT = RETAIL_PARQUET_FMT
    COMMENT     = 'MinIO data lake — Parquet escrito por parquet_consumer.py';


-- Verificar conectividade e listar os Parquets disponíveis
LIST @RETAIL_STAGE_MINIO;

-- Introspeccionar o schema de um Parquet (sem carregar dados)
SELECT $1 FROM @RETAIL_STAGE_MINIO/sales/ LIMIT 3;


-- ── 3. COPY INTO canônico — exemplo (manual / agendado) ──────────────────────────
-- As tabelas RAW.* já existem (ddl_raw.sql / terraform/tables.tf). O streaming
-- publica o schema canônico, então o COPY mapeia direto. Exemplo p/ SALES; os
-- demais (sale_lines, stock_movements [date→movement_date], stockouts
-- [date→event_date], deliveries, invoices, …) seguem o mesmo padrão — veja a
-- lista completa de colunas em snowflake/load_parquet.py (ENTITY_MAP).
--
-- FORCE = TRUE + TRUNCATE → full refresh idempotente (re-simulação completa).
TRUNCATE TABLE RAW.SALES;
COPY INTO RAW.SALES (
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
    FROM @RETAIL_STAGE_MINIO/sales/
)
PATTERN = '.*\.parquet'
FORCE   = TRUE;


-- ── 4. Snowpipe (auto-ingest) ────────────────────────────────────────────────────
-- O padrão de produção (AUTO_INGEST via notificação SQS/bucket) está definido como
-- IaC em terraform/pipes.tf — provisionado quando `minio_endpoint` é setado.
-- Após o apply: configure a notificação do bucket MinIO para o ARN retornado por
--   terraform output snowpipes_notification_channel
