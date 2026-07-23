-- ============================================================
-- snowflake/validate_raw.sql
-- RetailGuard — Post-Load Validation Queries
-- Run after load_snowflake_raw.py to verify row counts and data quality.
-- Usage: paste into Snowflake Web UI Worksheets (run section by section)
-- ============================================================

USE DATABASE RETAIL_DB;
USE SCHEMA RAW;
USE WAREHOUSE COMPUTE_WH;

-- ============================================================
-- SECTION 1: Row counts (all 18 tables)
-- Expected counts are approximate — exact values depend on the
-- simulation seed and period used when generating the CSVs.
-- Reference run: python erp/run_simulation.py --period 730d --customers 10000 --stores 150 --seed 42
-- ============================================================

SELECT 'distribution_centers' AS table_name, COUNT(*) AS row_count FROM RAW.DISTRIBUTION_CENTERS  -- expected: ~5
UNION ALL
SELECT 'stores',               COUNT(*) FROM RAW.STORES                                             -- expected: ~150
UNION ALL
SELECT 'products',             COUNT(*) FROM RAW.PRODUCTS                                           -- expected: ~3,727
UNION ALL
SELECT 'customers',            COUNT(*) FROM RAW.CUSTOMERS                                          -- expected: ~10,000
UNION ALL
SELECT 'suppliers',            COUNT(*) FROM RAW.SUPPLIERS                                          -- expected: ~20
UNION ALL
SELECT 'sales',                COUNT(*) FROM RAW.SALES                                              -- expected: ~374,000
UNION ALL
SELECT 'sale_lines',           COUNT(*) FROM RAW.SALE_LINES                                        -- expected: ~3,580,000
UNION ALL
SELECT 'purchase_orders',      COUNT(*) FROM RAW.PURCHASE_ORDERS                                   -- expected: ~3,488
UNION ALL
SELECT 'purchase_order_lines', COUNT(*) FROM RAW.PURCHASE_ORDER_LINES                              -- expected: ~20,788
UNION ALL
SELECT 'goods_receipts',       COUNT(*) FROM RAW.GOODS_RECEIPTS                                    -- expected: ~20,684
UNION ALL
SELECT 'deliveries',           COUNT(*) FROM RAW.DELIVERIES                                        -- expected: ~201,000
UNION ALL
SELECT 'invoices',             COUNT(*) FROM RAW.INVOICES                                          -- expected: ~374,000 (all channels)
UNION ALL
SELECT 'supplier_payments',    COUNT(*) FROM RAW.SUPPLIER_PAYMENTS                                 -- expected: ~3,488
UNION ALL
SELECT 'product_returns',      COUNT(*) FROM RAW.PRODUCT_RETURNS                                   -- expected: ~6,000
UNION ALL
SELECT 'product_waste',        COUNT(*) FROM RAW.PRODUCT_WASTE                                     -- expected: ~11,000
UNION ALL
SELECT 'stock_snapshots',      COUNT(*) FROM RAW.STOCK_SNAPSHOTS                                   -- expected: ~298,000
UNION ALL
SELECT 'stockouts',            COUNT(*) FROM RAW.STOCKOUTS                                         -- expected: ~7,000
UNION ALL
SELECT 'stock_movements',      COUNT(*) FROM RAW.STOCK_MOVEMENTS                                   -- expected: ~4,556,000
ORDER BY table_name;

-- ============================================================
-- SECTION 2: Primary-key NULL checks
-- All queries below should return 0 rows.
-- ============================================================

-- Master data PKs
SELECT 'distribution_centers.dc_id NULL' AS check_name, COUNT(*) AS null_count FROM RAW.DISTRIBUTION_CENTERS WHERE dc_id IS NULL
UNION ALL
SELECT 'stores.store_id NULL',       COUNT(*) FROM RAW.STORES       WHERE store_id IS NULL
UNION ALL
SELECT 'products.product_id NULL',   COUNT(*) FROM RAW.PRODUCTS     WHERE product_id IS NULL
UNION ALL
SELECT 'customers.customer_id NULL', COUNT(*) FROM RAW.CUSTOMERS    WHERE customer_id IS NULL
UNION ALL
SELECT 'suppliers.supplier_id NULL', COUNT(*) FROM RAW.SUPPLIERS    WHERE supplier_id IS NULL
-- Transactional PKs
UNION ALL
SELECT 'sales.sale_id NULL',              COUNT(*) FROM RAW.SALES               WHERE sale_id IS NULL
UNION ALL
SELECT 'purchase_orders.po_id NULL',      COUNT(*) FROM RAW.PURCHASE_ORDERS     WHERE po_id IS NULL
UNION ALL
SELECT 'goods_receipts.receipt_id NULL',  COUNT(*) FROM RAW.GOODS_RECEIPTS      WHERE receipt_id IS NULL
UNION ALL
SELECT 'deliveries.delivery_id NULL',     COUNT(*) FROM RAW.DELIVERIES          WHERE delivery_id IS NULL
UNION ALL
SELECT 'invoices.invoice_id NULL',        COUNT(*) FROM RAW.INVOICES            WHERE invoice_id IS NULL
UNION ALL
SELECT 'supplier_payments.payment_id NULL', COUNT(*) FROM RAW.SUPPLIER_PAYMENTS WHERE payment_id IS NULL
UNION ALL
SELECT 'product_returns.return_id NULL',  COUNT(*) FROM RAW.PRODUCT_RETURNS     WHERE return_id IS NULL
-- Operational PKs
UNION ALL
SELECT 'stockouts.stockout_id NULL',      COUNT(*) FROM RAW.STOCKOUTS           WHERE stockout_id IS NULL
UNION ALL
SELECT 'stock_movements.movement_id NULL',COUNT(*) FROM RAW.STOCK_MOVEMENTS     WHERE movement_id IS NULL
-- Composite PK components for stock_snapshots
UNION ALL
SELECT 'stock_snapshots.snapshot_date NULL', COUNT(*) FROM RAW.STOCK_SNAPSHOTS  WHERE snapshot_date IS NULL
UNION ALL
SELECT 'stock_snapshots.product_id NULL',    COUNT(*) FROM RAW.STOCK_SNAPSHOTS  WHERE product_id IS NULL
UNION ALL
SELECT 'stock_snapshots.location_type NULL', COUNT(*) FROM RAW.STOCK_SNAPSHOTS  WHERE location_type IS NULL
UNION ALL
SELECT 'stock_snapshots.location_id NULL',   COUNT(*) FROM RAW.STOCK_SNAPSHOTS  WHERE location_id IS NULL
ORDER BY null_count DESC, check_name;

-- ============================================================
-- SECTION 3: Date range check — sales
-- Expect a full ~730-day window from the simulation start date.
-- ============================================================

SELECT
    MIN(order_date)                                          AS first_order_date,
    MAX(order_date)                                          AS last_order_date,
    DATEDIFF('day', MIN(order_date), MAX(order_date))        AS span_days,
    COUNT(*)                                                 AS total_orders,
    COUNT(DISTINCT order_date)                               AS distinct_dates
FROM RAW.SALES;

-- ============================================================
-- SECTION 4: Channel distribution — sales
-- Expected values: 'tienda', 'ecommerce'
-- Any unexpected value here would fail the dbt accepted_values test.
-- ============================================================

SELECT
    channel,
    COUNT(*)                                    AS orders,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM RAW.SALES
GROUP BY channel
ORDER BY orders DESC;

-- ============================================================
-- SECTION 5: IVA type distribution — products
-- Expected values: 'S1' (21% general), 'S2' (10% reducido), 'S4' (4% superreducido)
-- ============================================================

SELECT
    iva_type,
    COUNT(*)                                      AS products,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM RAW.PRODUCTS
GROUP BY iva_type
ORDER BY iva_type;

-- ============================================================
-- SECTION 6: Additional spot-checks
-- ============================================================

-- Delivery status distribution (expected: pending, dispatched, in_transit, delivered, failed)
SELECT
    delivery_status,
    COUNT(*) AS deliveries
FROM RAW.DELIVERIES
GROUP BY delivery_status
ORDER BY deliveries DESC;

-- Invoice payment status (expected: paid, pending, overdue, refunded)
SELECT
    payment_status,
    COUNT(*) AS invoices
FROM RAW.INVOICES
GROUP BY payment_status
ORDER BY invoices DESC;

-- Purchase order status (expected: open, pending, confirmed, received, cancelled)
SELECT
    status,
    COUNT(*) AS purchase_orders
FROM RAW.PURCHASE_ORDERS
GROUP BY status
ORDER BY purchase_orders DESC;

-- Stock movement types (expected: IN, OUT, TRANSFER, RETURN)
SELECT
    movement_type,
    COUNT(*) AS movements
FROM RAW.STOCK_MOVEMENTS
GROUP BY movement_type
ORDER BY movements DESC;

-- Customer segment distribution (expected: Bronze, Silver, Gold, Platinum)
SELECT
    segment,
    COUNT(*) AS customers
FROM RAW.CUSTOMERS
GROUP BY segment
ORDER BY customers DESC;

-- Stock snapshot location types (expected: DC, STORE)
SELECT
    location_type,
    COUNT(*) AS snapshots
FROM RAW.STOCK_SNAPSHOTS
GROUP BY location_type
ORDER BY snapshots DESC;

-- ============================================================
-- SECTION 7: Financial sanity checks
-- ============================================================

-- Sales: verify total_gross ≈ subtotal_net + tax_amount (tolerance ±0.02)
SELECT
    COUNT(*) AS mismatched_rows
FROM RAW.SALES
WHERE ABS(total_gross - (subtotal_net + tax_amount)) > 0.02;

-- Sales: average order value and tax rate check
SELECT
    ROUND(AVG(total_gross), 2)           AS avg_order_value_eur,
    ROUND(AVG(tax_amount / NULLIF(subtotal_net, 0)) * 100, 2) AS avg_effective_tax_pct,
    MIN(total_gross)                     AS min_order_value,
    MAX(total_gross)                     AS max_order_value
FROM RAW.SALES;

-- Supplier payments: count by status (expected: pending, paid, overdue)
SELECT
    status,
    COUNT(*)                     AS payments,
    ROUND(SUM(amount_gross), 2)  AS total_gross_eur
FROM RAW.SUPPLIER_PAYMENTS
GROUP BY status
ORDER BY total_gross_eur DESC;

-- ============================================================
-- SECTION 8: Stage contents (verify files were uploaded)
-- ============================================================

LIST @RETAIL_DB.RAW.RETAIL_STAGE;
