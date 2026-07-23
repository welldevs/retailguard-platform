-- ============================================================
-- snowflake/ddl_raw.sql
-- RetailGuard — Snowflake RAW Schema Setup
-- Run once to initialise the Snowflake environment.
-- Usage: execute via SnowSQL or Snowflake Web UI Worksheets
-- ============================================================

-- SECTION 1: Database + schemas
USE ROLE ACCOUNTADMIN;  -- ou SYSADMIN se não tiver ACCOUNTADMIN

CREATE DATABASE IF NOT EXISTS RETAIL_DB;
USE DATABASE RETAIL_DB;

CREATE SCHEMA IF NOT EXISTS RAW;
CREATE SCHEMA IF NOT EXISTS STAGING;
CREATE SCHEMA IF NOT EXISTS MARTS;

-- SECTION 2: Warehouse
-- Trial já tem COMPUTE_WH criado — usamos ele diretamente.
-- RETAIL_WH_XS comentado para não criar warehouse extra no trial.
--
-- CREATE WAREHOUSE IF NOT EXISTS RETAIL_WH_XS
--   WAREHOUSE_SIZE = 'X-SMALL'
--   AUTO_SUSPEND = 60
--   AUTO_RESUME = TRUE
--   INITIALLY_SUSPENDED = TRUE;

USE WAREHOUSE COMPUTE_WH;

-- SECTION 3: Role + user setup (opcional — roda como ACCOUNTADMIN)
-- Descomenta e ajusta se quiser separar permissões por role.
--
-- CREATE ROLE IF NOT EXISTS RETAIL_ENGINEER;
-- GRANT USAGE ON DATABASE RETAIL_DB TO ROLE RETAIL_ENGINEER;
-- GRANT USAGE ON SCHEMA RETAIL_DB.RAW TO ROLE RETAIL_ENGINEER;
-- GRANT ALL ON SCHEMA RETAIL_DB.RAW TO ROLE RETAIL_ENGINEER;
-- GRANT USAGE ON SCHEMA RETAIL_DB.STAGING TO ROLE RETAIL_ENGINEER;
-- GRANT ALL ON SCHEMA RETAIL_DB.STAGING TO ROLE RETAIL_ENGINEER;
-- GRANT USAGE ON SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_ENGINEER;
-- GRANT ALL ON SCHEMA RETAIL_DB.MARTS TO ROLE RETAIL_ENGINEER;
-- GRANT USAGE ON WAREHOUSE RETAIL_WH_XS TO ROLE RETAIL_ENGINEER;
-- GRANT OPERATE ON WAREHOUSE RETAIL_WH_XS TO ROLE RETAIL_ENGINEER;
-- CREATE USER IF NOT EXISTS DBT_USER
--   PASSWORD = '***'
--   DEFAULT_ROLE = RETAIL_ENGINEER
--   DEFAULT_WAREHOUSE = RETAIL_WH_XS;
-- GRANT ROLE RETAIL_ENGINEER TO USER DBT_USER;

-- SECTION 4: File format para CSV
CREATE OR REPLACE FILE FORMAT RETAIL_DB.RAW.CSV_FORMAT
  TYPE = 'CSV'
  FIELD_DELIMITER = ','
  RECORD_DELIMITER = '\n'
  SKIP_HEADER = 1
  FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  NULL_IF = ('', 'NULL', 'None')
  EMPTY_FIELD_AS_NULL = TRUE
  DATE_FORMAT = 'YYYY-MM-DD'
  TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS';

-- SECTION 5: Internal stage
CREATE OR REPLACE STAGE RETAIL_DB.RAW.RETAIL_STAGE
  FILE_FORMAT = RETAIL_DB.RAW.CSV_FORMAT
  COMMENT = 'Internal stage for retail CSV uploads';

-- SECTION 6: RAW tables (17 tables)
USE SCHEMA RAW;

-- ============================================================
-- MASTER DATA (5 tables)
-- ============================================================

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.DISTRIBUTION_CENTERS (
  dc_id         VARCHAR(10)   NOT NULL,
  name          VARCHAR(100)  NOT NULL,
  city          VARCHAR(100),
  region        VARCHAR(60),
  latitude      NUMBER(9,6),
  longitude     NUMBER(9,6),
  stock_weight  NUMBER(6,4),
  PRIMARY KEY (dc_id)
)
COMMENT = 'Distribution centres that supply stores in the network.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STORES (
  store_id      VARCHAR(10)   NOT NULL,
  name          VARCHAR(100)  NOT NULL,
  postal_code   VARCHAR(5),
  municipality  VARCHAR(100),
  province      VARCHAR(60),
  ccaa          VARCHAR(60),
  dc_id         VARCHAR(10),
  opening_date  VARCHAR(10),
  sqm           NUMBER(6),
  latitude      NUMBER(9,6),
  longitude     NUMBER(9,6),
  active        VARCHAR(5),   -- '0'/'1' no CSV; cast para BOOLEAN no staging
  PRIMARY KEY (store_id)
)
COMMENT = 'Physical retail stores, each linked to a distribution centre.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCTS (
  product_id       VARCHAR(30)   NOT NULL,
  sku              VARCHAR(50),
  name             VARCHAR(300)  NOT NULL,
  brand            VARCHAR(100),
  category         VARCHAR(100),
  category_path    VARCHAR(300),
  price            NUMBER(10,2),
  unit             VARCHAR(200),
  image_url        VARCHAR(500),
  active           VARCHAR(5),
  barcode          VARCHAR(13),
  sale_price       NUMBER(10,2),
  cost_price       NUMBER(10,4),
  tax_rate         NUMBER(4,2),
  iva_type         VARCHAR(5),
  unit_of_measure  VARCHAR(5),
  supplier_code    VARCHAR(15),
  active_since     VARCHAR(10),
  shelf_life_days  NUMBER(6),       -- vida útil (frescos); NULL = não-perecível
  is_perishable    NUMBER(1),       -- 1 = perecível (gera merma/caducidad)
  PRIMARY KEY (product_id)
)
COMMENT = '3,727 real Mercadona SKUs with pricing, tax and perishability.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.CUSTOMERS (
  customer_id          VARCHAR(30)   NOT NULL,
  first_name           VARCHAR(100),
  last_name            VARCHAR(100),
  email                VARCHAR(150),
  phone                VARCHAR(20),
  nif                  VARCHAR(10),
  address_street       VARCHAR(200),
  postal_code          VARCHAR(5),
  municipality         VARCHAR(100),
  province             VARCHAR(60),
  ccaa                 VARCHAR(60),
  registration_date    VARCHAR(10),
  segment              VARCHAR(10),
  profile              VARCHAR(30),
  birth_year           NUMBER(4),
  age                  NUMBER(3),
  payment_method       VARCHAR(30),
  avg_ticket           NUMBER(10,2),
  ticket_trend         VARCHAR(20),
  behavior_variance    NUMBER(5,2),
  channel_probability  NUMBER(5,4),
  nearest_store_id     VARCHAR(10),
  payment_days         NUMBER(3),
  PRIMARY KEY (customer_id)
)
COMMENT = '20.000 synthetic customers with behavioural attributes.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SUPPLIERS (
  supplier_id             VARCHAR(30)   NOT NULL,
  name                    VARCHAR(200)  NOT NULL,
  country                 VARCHAR(50),
  city                    VARCHAR(100),
  lead_time_days          NUMBER(3),
  reliability_score       NUMBER(5,2),
  payment_terms_days      NUMBER(3),
  contact_email           VARCHAR(150),
  phone                   VARCHAR(20),
  active                  VARCHAR(5),
  category_specialization VARCHAR(500),
  cif                     VARCHAR(10),
  payment_terms           VARCHAR(5),
  incoterm                VARCHAR(5),
  currency                VARCHAR(3),
  iban                    VARCHAR(30),
  PRIMARY KEY (supplier_id)
)
COMMENT = 'Product suppliers with payment and logistics terms.';

-- ============================================================
-- TRANSACTIONAL (8 tables)
-- ============================================================

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SALES (
  sale_id              VARCHAR(25)   NOT NULL,
  order_date           VARCHAR(10),
  order_ts             VARCHAR(25),  -- timestamp intradía ISO (hora-punta); cast no staging
  customer_id          VARCHAR(30),
  store_id             VARCHAR(10),
  dc_id                VARCHAR(10),
  region               VARCHAR(60),
  payment_method       VARCHAR(20),
  payment_status       VARCHAR(20),
  payment_days         NUMBER(3),
  channel              VARCHAR(10),
  subtotal_net         NUMBER(14,2),
  tax_amount           NUMBER(14,2),
  total_gross          NUMBER(14,2),
  status               VARCHAR(20),
  has_partial_stockout VARCHAR(5),   -- '0'/'1' no CSV; cast para BOOLEAN no staging
  num_items            NUMBER(5),
  ticket_trend         VARCHAR(20),
  PRIMARY KEY (sale_id)
)
COMMENT = 'Sale order headers — ~368,000 orders over the simulation period.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SALE_LINES (
  -- Note: no identity column; line_id generated by dbt or omitted in CSV
  sale_id            VARCHAR(25)   NOT NULL,
  line_number        NUMBER(5),
  product_id         VARCHAR(30),
  quantity_ordered   NUMBER(10),
  quantity_delivered NUMBER(10),
  unit_price_net     NUMBER(12,4),
  discount_pct       NUMBER(6,4),
  tax_rate           NUMBER(4,2),
  line_total_net     NUMBER(14,2)
)
COMMENT = 'Individual line items per sales order.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PURCHASE_ORDERS (
  -- Columns _lines (JSON blob) excluded — not loaded into RAW
  po_id                  VARCHAR(25)   NOT NULL,
  supplier_id            VARCHAR(30),
  dc_id                  VARCHAR(10),
  order_date             VARCHAR(10),
  expected_receipt_date  VARCHAR(10),
  actual_receipt_date    VARCHAR(10),
  status                 VARCHAR(25),
  incoterm               VARCHAR(5),
  payment_terms          VARCHAR(5),
  currency               VARCHAR(3),
  total_cost_net         NUMBER(14,2),
  tax_amount             NUMBER(14,2),
  total_cost_gross       NUMBER(14,2),
  PRIMARY KEY (po_id)
)
COMMENT = 'Supplier purchase order headers. Column _lines (JSON blob) excluded.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PURCHASE_ORDER_LINES (
  po_id             VARCHAR(25)   NOT NULL,
  line_number       NUMBER(5),
  product_id        VARCHAR(30),
  quantity_ordered  NUMBER(10),
  unit_cost         NUMBER(12,4),
  tax_rate          NUMBER(4,2),
  line_total_net    NUMBER(14,2)
)
COMMENT = 'Line items per purchase order.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.GOODS_RECEIPTS (
  receipt_id        VARCHAR(30)   NOT NULL,
  po_id             VARCHAR(25),
  po_line_number    NUMBER(5),
  product_id        VARCHAR(30),
  dc_id             VARCHAR(10),
  supplier_id       VARCHAR(30),
  quantity_received NUMBER(10),
  receipt_date      VARCHAR(10),
  unit_cost         NUMBER(12,4),
  PRIMARY KEY (receipt_id)
)
COMMENT = 'Physical goods received at distribution centres.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.DELIVERIES (
  delivery_id              VARCHAR(25)   NOT NULL,
  sale_id                  VARCHAR(25),
  dc_id                    VARCHAR(10),
  carrier                  VARCHAR(30),
  tracking_number          VARCHAR(20),
  dispatch_date            VARCHAR(10),
  estimated_delivery_date  VARCHAR(10),
  actual_delivery_date     VARCHAR(10),
  delivery_status          VARCHAR(20),
  weight_kg                NUMBER(8,2),
  packages                 NUMBER(3),
  signature_required       VARCHAR(5),   -- '0'/'1' no CSV; cast para BOOLEAN no staging
  total_amount             NUMBER(14,2),
  PRIMARY KEY (delivery_id)
)
COMMENT = 'Ecommerce deliveries — one row per sale with ecommerce channel.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.INVOICES (
  invoice_id      VARCHAR(25)   NOT NULL,
  sale_id         VARCHAR(25),
  delivery_id     VARCHAR(25),
  customer_id     VARCHAR(30),
  invoice_date    VARCHAR(10),
  subtotal_net    NUMBER(14,2),
  tax_breakdown   VARCHAR(200),
  tax_amount      NUMBER(14,2),
  total_gross     NUMBER(14,2),
  due_date        VARCHAR(10),
  payment_days    NUMBER(3),
  payment_status  VARCHAR(20),
  payment_date    VARCHAR(10),
  PRIMARY KEY (invoice_id)
)
COMMENT = 'Customer invoices with IVA breakdown per tax bracket (S1=4%, S2=10%, S4=21%).';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SUPPLIER_PAYMENTS (
  payment_id       VARCHAR(25)   NOT NULL,
  po_id            VARCHAR(25),
  supplier_id      VARCHAR(30),
  dc_id            VARCHAR(10),
  obligation_date  VARCHAR(10),
  due_date         VARCHAR(10),
  payment_date     VARCHAR(10),
  amount_net       NUMBER(14,2),
  amount_gross     NUMBER(14,2),
  status           VARCHAR(20),
  days_late        NUMBER(5),
  PRIMARY KEY (payment_id)
)
COMMENT = 'Supplier payment obligations and their settlement status.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCT_RETURNS (
  return_id          VARCHAR(25)   NOT NULL,
  sale_id            VARCHAR(25),
  order_id           VARCHAR(25),
  product_id         VARCHAR(30),
  customer_id        VARCHAR(30),
  location_type      VARCHAR(10),
  location_id        VARCHAR(10),
  return_date        VARCHAR(10),
  quantity_returned  NUMBER(10),
  unit_price_net     NUMBER(12,4),
  refund_amount      NUMBER(14,2),
  reason             VARCHAR(20),
  restocked          VARCHAR(5),
  PRIMARY KEY (return_id)
)
COMMENT = 'Customer product returns with reason and restocking flag.';

-- ============================================================
-- OPERATIONAL (4 tables)
-- ============================================================

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCK_SNAPSHOTS (
  -- No snapshot_id in CSV — composite PK: snapshot_date + product_id + location_type + location_id
  snapshot_date        VARCHAR(10)   NOT NULL,
  product_id           VARCHAR(30)   NOT NULL,
  location_type        VARCHAR(10)   NOT NULL,
  location_id          VARCHAR(10)   NOT NULL,
  quantity_on_hand     NUMBER(12),
  quantity_reserved    NUMBER(12),
  quantity_in_transit  NUMBER(12),
  reorder_point        NUMBER(12),
  max_stock            NUMBER(12),
  unit_cost            NUMBER(12,4)
)
COMMENT = 'Daily stock position snapshots per product and location.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCKOUTS (
  stockout_id        VARCHAR(30)   NOT NULL,
  event_date         VARCHAR(10),
  customer_id        VARCHAR(30),
  product_id         VARCHAR(30),
  location_type      VARCHAR(10),
  location_id        VARCHAR(10),
  quantity_requested NUMBER(10),
  quantity_available NUMBER(10),
  PRIMARY KEY (stockout_id)
)
COMMENT = 'Stockout events: demand that could not be fulfilled.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCK_MOVEMENTS (
  movement_id    VARCHAR(30)   NOT NULL,
  movement_date  VARCHAR(10),
  product_id     VARCHAR(30),
  location_type  VARCHAR(10),
  location_id    VARCHAR(10),
  movement_type  VARCHAR(10),
  reason         VARCHAR(50),
  reference_id   VARCHAR(30),
  quantity_delta NUMBER(12),
  quantity_after NUMBER(12),
  PRIMARY KEY (movement_id)
)
COMMENT = 'All inventory movements (IN/OUT/TRANSFER/RETURN/WASTE) with delta and running balance.';

CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCT_WASTE (
  waste_id       VARCHAR(30)   NOT NULL,
  waste_date     VARCHAR(10),
  product_id     VARCHAR(30),
  category       VARCHAR(60),
  location_type  VARCHAR(10),
  location_id    VARCHAR(10),
  quantity       NUMBER(10),
  unit_cost      NUMBER(12,4),
  lost_cost      NUMBER(14,2),
  reason         VARCHAR(20),
  PRIMARY KEY (waste_id)
)
COMMENT = 'Perishable waste / merma (caducidad) events — units lost and cost, by location and category.';

-- ============================================================
-- SECTION 7: COPY INTO templates (execute after PUT)
-- Run load_snowflake.py to perform PUT + COPY automatically, or
-- execute the statements below manually in a Worksheet after
-- uploading the files with: PUT file:///path/to/source/*.csv @RETAIL_DB.RAW.RETAIL_STAGE AUTO_COMPRESS=TRUE
-- ============================================================

/*

COPY INTO RETAIL_DB.RAW.DISTRIBUTION_CENTERS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/distribution_centers/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.STORES
FROM @RETAIL_DB.RAW.RETAIL_STAGE/stores/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.PRODUCTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/products/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.CUSTOMERS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/customers/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.SUPPLIERS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/suppliers/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.SALES
FROM @RETAIL_DB.RAW.RETAIL_STAGE/sales/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.SALE_LINES
FROM @RETAIL_DB.RAW.RETAIL_STAGE/sale_lines/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

-- NOTE: The CSV contains columns _lines (JSON blob) that must be excluded.
-- Use a SELECT transformation to load only the mapped columns:
COPY INTO RETAIL_DB.RAW.PURCHASE_ORDERS (
  po_id, supplier_id, dc_id, order_date, expected_receipt_date,
  actual_receipt_date, status, incoterm, payment_terms, currency,
  total_cost_net, tax_amount, total_cost_gross
)
FROM (
  SELECT
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
  FROM @RETAIL_DB.RAW.RETAIL_STAGE/purchase_orders/
)
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.PURCHASE_ORDER_LINES
FROM @RETAIL_DB.RAW.RETAIL_STAGE/purchase_order_lines/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.GOODS_RECEIPTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/goods_receipts/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.DELIVERIES
FROM @RETAIL_DB.RAW.RETAIL_STAGE/deliveries/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

-- NOTE: The CSV contains column tax_breakdown (JSON blob) that must be excluded.
-- Column order in CSV: invoice_id, sale_id, delivery_id, customer_id, invoice_date,
--                      subtotal_net, tax_breakdown, tax_amount, total_gross,
--                      due_date, payment_days, payment_status, payment_date
-- tax_breakdown is $7 — skip it with positional SELECT:
COPY INTO RETAIL_DB.RAW.INVOICES (
  invoice_id, sale_id, delivery_id, customer_id, invoice_date,
  subtotal_net, tax_amount, total_gross, due_date, payment_days,
  payment_status, payment_date
)
FROM (
  SELECT $1, $2, $3, $4, $5, $6, $8, $9, $10, $11, $12, $13
  FROM @RETAIL_DB.RAW.RETAIL_STAGE/invoices/
)
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.SUPPLIER_PAYMENTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/supplier_payments/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.PRODUCT_RETURNS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/product_returns/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.STOCK_SNAPSHOTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/stock_snapshots/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.STOCKOUTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/stockouts/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

COPY INTO RETAIL_DB.RAW.STOCK_MOVEMENTS
FROM @RETAIL_DB.RAW.RETAIL_STAGE/stock_movements/
FILE_FORMAT = (FORMAT_NAME = 'RETAIL_DB.RAW.CSV_FORMAT')
ON_ERROR = 'CONTINUE';

*/
