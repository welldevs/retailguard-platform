# ─────────────────────────────────────────────────────────────────────────────
# RAW Tables — 18 tabelas canônicas (alimentadas por batch CSV OU streaming Kafka).
#
# Não há mais tabelas *_STREAM: o streaming publica eventos NORMALIZADOS (via
# erp/simulator/normalize.py) que caem nestas MESMAS tabelas RAW, e o dbt
# transforma de forma idêntica seja qual for a ingestão (fonte única de verdade).
#
# Each snowflake_execute resource mirrors the exact DDL from ddl_raw.sql.
# CREATE TABLE IF NOT EXISTS makes every apply idempotent — tables already
# populated by a previous load are untouched.
# ─────────────────────────────────────────────────────────────────────────────

locals {
  raw_schema = "RETAIL_DB.RAW"
}

# ══════════════════════════════════════════════════════════════════════════════
# MASTER DATA (5 tables)
# ══════════════════════════════════════════════════════════════════════════════

resource "snowflake_execute" "tbl_distribution_centers" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.DISTRIBUTION_CENTERS (
      dc_id        VARCHAR(10)  NOT NULL,
      name         VARCHAR(100) NOT NULL,
      city         VARCHAR(100),
      region       VARCHAR(60),
      latitude     NUMBER(9,6),
      longitude    NUMBER(9,6),
      stock_weight NUMBER(6,4),
      PRIMARY KEY (dc_id)
    ) COMMENT = 'Distribution centres that supply stores in the network.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.DISTRIBUTION_CENTERS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_stores" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STORES (
      store_id     VARCHAR(10)  NOT NULL,
      name         VARCHAR(100) NOT NULL,
      postal_code  VARCHAR(5),
      municipality VARCHAR(100),
      province     VARCHAR(60),
      ccaa         VARCHAR(60),
      dc_id        VARCHAR(10),
      opening_date VARCHAR(10),
      sqm          NUMBER(6),
      latitude     NUMBER(9,6),
      longitude    NUMBER(9,6),
      active       VARCHAR(5),
      PRIMARY KEY (store_id)
    ) COMMENT = 'Physical retail stores, each linked to a distribution centre.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.STORES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_products" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCTS (
      product_id      VARCHAR(30)  NOT NULL,
      sku             VARCHAR(50),
      name            VARCHAR(300) NOT NULL,
      brand           VARCHAR(100),
      category        VARCHAR(100),
      category_path   VARCHAR(300),
      price           NUMBER(10,2),
      unit            VARCHAR(200),
      image_url       VARCHAR(500),
      active          VARCHAR(5),
      barcode         VARCHAR(13),
      sale_price      NUMBER(10,2),
      cost_price      NUMBER(10,4),
      tax_rate        NUMBER(4,2),
      iva_type        VARCHAR(5),
      unit_of_measure VARCHAR(5),
      supplier_code   VARCHAR(15),
      active_since    VARCHAR(10),
      shelf_life_days NUMBER(6),
      is_perishable   NUMBER(1),
      PRIMARY KEY (product_id)
    ) COMMENT = '3,727 real Mercadona SKUs with pricing, Spanish VAT classification and perishability.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.PRODUCTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_customers" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.CUSTOMERS (
      customer_id         VARCHAR(30)  NOT NULL,
      first_name          VARCHAR(100),
      last_name           VARCHAR(100),
      email               VARCHAR(150),
      phone               VARCHAR(20),
      nif                 VARCHAR(10),
      address_street      VARCHAR(200),
      postal_code         VARCHAR(5),
      municipality        VARCHAR(100),
      province            VARCHAR(60),
      ccaa                VARCHAR(60),
      registration_date   VARCHAR(10),
      segment             VARCHAR(10),
      profile             VARCHAR(30),
      birth_year          NUMBER(4),
      age                 NUMBER(3),
      payment_method      VARCHAR(30),
      avg_ticket          NUMBER(10,2),
      ticket_trend        VARCHAR(20),
      behavior_variance   NUMBER(5,2),
      channel_probability NUMBER(5,4),
      nearest_store_id    VARCHAR(10),
      payment_days        NUMBER(3),
      PRIMARY KEY (customer_id)
    ) COMMENT = '10,000 synthetic customers with behavioural and geographic attributes.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.CUSTOMERS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_suppliers" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SUPPLIERS (
      supplier_id             VARCHAR(30)  NOT NULL,
      name                    VARCHAR(200) NOT NULL,
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
    ) COMMENT = 'Product suppliers with payment terms and logistics attributes.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.SUPPLIERS"
  depends_on = [snowflake_schema.raw]
}

# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTIONAL (9 tables)
# ══════════════════════════════════════════════════════════════════════════════

resource "snowflake_execute" "tbl_sales" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SALES (
      sale_id              VARCHAR(25) NOT NULL,
      order_date           VARCHAR(10),
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
      has_partial_stockout VARCHAR(5),
      num_items            NUMBER(5),
      ticket_trend         VARCHAR(20),
      order_ts             VARCHAR(25),
      PRIMARY KEY (sale_id)
    ) COMMENT = 'Sale order headers — ~374,000 orders over the simulation period (with intradía order_ts).'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.SALES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_sale_lines" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SALE_LINES (
      sale_id            VARCHAR(25) NOT NULL,
      line_number        NUMBER(5),
      product_id         VARCHAR(30),
      quantity_ordered   NUMBER(10),
      quantity_delivered NUMBER(10),
      unit_price_net     NUMBER(12,4),
      discount_pct       NUMBER(6,4),
      tax_rate           NUMBER(4,2),
      line_total_net     NUMBER(14,2)
    ) COMMENT = 'Individual line items per sale order. GMV = SUM(line_total_net * (1 + tax_rate)).'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.SALE_LINES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_purchase_orders" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PURCHASE_ORDERS (
      po_id                 VARCHAR(25) NOT NULL,
      supplier_id           VARCHAR(30),
      dc_id                 VARCHAR(10),
      order_date            VARCHAR(10),
      expected_receipt_date VARCHAR(10),
      actual_receipt_date   VARCHAR(10),
      status                VARCHAR(25),
      incoterm              VARCHAR(5),
      payment_terms         VARCHAR(5),
      currency              VARCHAR(3),
      total_cost_net        NUMBER(14,2),
      tax_amount            NUMBER(14,2),
      total_cost_gross      NUMBER(14,2),
      PRIMARY KEY (po_id)
    ) COMMENT = 'Supplier purchase order headers. JSON column _lines excluded.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.PURCHASE_ORDERS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_purchase_order_lines" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PURCHASE_ORDER_LINES (
      po_id            VARCHAR(25) NOT NULL,
      line_number      NUMBER(5),
      product_id       VARCHAR(30),
      quantity_ordered NUMBER(10),
      unit_cost        NUMBER(12,4),
      tax_rate         NUMBER(4,2),
      line_total_net   NUMBER(14,2)
    ) COMMENT = 'Line items per purchase order.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.PURCHASE_ORDER_LINES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_goods_receipts" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.GOODS_RECEIPTS (
      receipt_id        VARCHAR(30) NOT NULL,
      po_id             VARCHAR(25),
      po_line_number    NUMBER(5),
      product_id        VARCHAR(30),
      dc_id             VARCHAR(10),
      supplier_id       VARCHAR(30),
      quantity_received NUMBER(10),
      receipt_date      VARCHAR(10),
      unit_cost         NUMBER(12,4),
      PRIMARY KEY (receipt_id)
    ) COMMENT = 'Physical goods received at distribution centres.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.GOODS_RECEIPTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_deliveries" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.DELIVERIES (
      delivery_id             VARCHAR(25) NOT NULL,
      sale_id                 VARCHAR(25),
      dc_id                   VARCHAR(10),
      carrier                 VARCHAR(30),
      tracking_number         VARCHAR(20),
      dispatch_date           VARCHAR(10),
      estimated_delivery_date VARCHAR(10),
      actual_delivery_date    VARCHAR(10),
      delivery_status         VARCHAR(20),
      weight_kg               NUMBER(8,2),
      packages                NUMBER(3),
      signature_required      VARCHAR(5),
      total_amount            NUMBER(14,2),
      PRIMARY KEY (delivery_id)
    ) COMMENT = 'Ecommerce deliveries — one row per sale with ecommerce channel.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.DELIVERIES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_invoices" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.INVOICES (
      invoice_id     VARCHAR(25) NOT NULL,
      sale_id        VARCHAR(25),
      delivery_id    VARCHAR(25),
      customer_id    VARCHAR(30),
      invoice_date   VARCHAR(10),
      subtotal_net   NUMBER(14,2),
      tax_breakdown  VARCHAR(200),
      tax_amount     NUMBER(14,2),
      total_gross    NUMBER(14,2),
      due_date       VARCHAR(10),
      payment_days   NUMBER(3),
      payment_status VARCHAR(20),
      payment_date   VARCHAR(10),
      PRIMARY KEY (invoice_id)
    ) COMMENT = 'Customer invoices with IVA breakdown per tax bracket (S1=4%, S2=10%, S4=21%).'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.INVOICES"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_supplier_payments" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.SUPPLIER_PAYMENTS (
      payment_id      VARCHAR(25) NOT NULL,
      po_id           VARCHAR(25),
      supplier_id     VARCHAR(30),
      dc_id           VARCHAR(10),
      obligation_date VARCHAR(10),
      due_date        VARCHAR(10),
      payment_date    VARCHAR(10),
      amount_net      NUMBER(14,2),
      amount_gross    NUMBER(14,2),
      status          VARCHAR(20),
      days_late       NUMBER(5),
      PRIMARY KEY (payment_id)
    ) COMMENT = 'Supplier payment obligations and their settlement status.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.SUPPLIER_PAYMENTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_product_returns" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCT_RETURNS (
      return_id         VARCHAR(25) NOT NULL,
      sale_id           VARCHAR(25),
      order_id          VARCHAR(25),
      product_id        VARCHAR(30),
      customer_id       VARCHAR(30),
      location_type     VARCHAR(10),
      location_id       VARCHAR(10),
      return_date       VARCHAR(10),
      quantity_returned NUMBER(10),
      unit_price_net    NUMBER(12,4),
      refund_amount     NUMBER(14,2),
      reason            VARCHAR(20),
      restocked         VARCHAR(5),
      PRIMARY KEY (return_id)
    ) COMMENT = 'Customer product returns with reason code and restocking flag.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.PRODUCT_RETURNS"
  depends_on = [snowflake_schema.raw]
}

# ══════════════════════════════════════════════════════════════════════════════
# OPERATIONAL / INVENTORY (3 tables)
# ══════════════════════════════════════════════════════════════════════════════

resource "snowflake_execute" "tbl_stock_snapshots" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCK_SNAPSHOTS (
      snapshot_date       VARCHAR(10) NOT NULL,
      product_id          VARCHAR(30) NOT NULL,
      location_type       VARCHAR(10) NOT NULL,
      location_id         VARCHAR(10) NOT NULL,
      quantity_on_hand    NUMBER(12),
      quantity_reserved   NUMBER(12),
      quantity_in_transit NUMBER(12),
      reorder_point       NUMBER(12),
      max_stock           NUMBER(12),
      unit_cost           NUMBER(12,4)
    ) COMMENT = 'Daily stock position snapshots per product and location.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.STOCK_SNAPSHOTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_stockouts" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCKOUTS (
      stockout_id        VARCHAR(30) NOT NULL,
      event_date         VARCHAR(10),
      customer_id        VARCHAR(30),
      product_id         VARCHAR(30),
      location_type      VARCHAR(10),
      location_id        VARCHAR(10),
      quantity_requested NUMBER(10),
      quantity_available NUMBER(10),
      PRIMARY KEY (stockout_id)
    ) COMMENT = 'Stockout events: demand that could not be fulfilled.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.STOCKOUTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_stock_movements" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.STOCK_MOVEMENTS (
      movement_id    VARCHAR(30) NOT NULL,
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
    ) COMMENT = 'All inventory movements (IN/OUT/TRANSFER/RETURN) with running balance.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.STOCK_MOVEMENTS"
  depends_on = [snowflake_schema.raw]
}

resource "snowflake_execute" "tbl_product_waste" {
  execute    = <<-SQL
    CREATE TABLE IF NOT EXISTS RETAIL_DB.RAW.PRODUCT_WASTE (
      waste_id       VARCHAR(30) NOT NULL,
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
    ) COMMENT = 'Perishable waste / merma (caducidad) events — units lost and cost, by location and category.'
  SQL
  revert     = "DROP TABLE IF EXISTS RETAIL_DB.RAW.PRODUCT_WASTE"
  depends_on = [snowflake_schema.raw]
}

