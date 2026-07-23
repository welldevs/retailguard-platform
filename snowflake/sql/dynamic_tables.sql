-- ============================================================
-- snowflake/sql/dynamic_tables.sql
-- RetailGuard — Dynamic Tables (Declarative Streaming Marts)
--
-- SHOWCASE — Snowflake-native declarative streaming
-- ───────────────────────────────────────────────────────────────
-- Estas 3 Dynamic Tables (DT_*) são uma VITRINE de streaming declarativo
-- nativo do Snowflake, NÃO a fonte do dashboard (o Streamlit lê MARTS.MART_*,
-- construídas pelo dbt — fonte única de verdade).
--
-- Como funcionam: DDL declarativa apenas. O Snowflake é dono do loop de refresh
-- (sem orquestrador, sem CREATE OR REPLACE manual, sem DAG). TARGET_LAG define o
-- orçamento máximo de staleness; o Snowflake agenda refreshes incrementais
-- (REFRESH_MODE=AUTO usa change-tracking incremental quando o shape permite, ou
-- full para agregações complexas). INITIALIZE=ON_CREATE popula na criação.
--
-- As DT_ leem as tabelas base RAW.* (as MESMAS que o dbt lê e que o pipeline
-- batch/streaming popula), então demonstram "marts que se auto-atualizam" lado a
-- lado com as marts dbt, sobre exatamente a mesma fonte canônica.
-- ============================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE RETAIL_DB;
USE WAREHOUSE COMPUTE_WH;

-- ============================================================
-- DT_GMV_MENSAL
-- Grain: year_month (one row per calendar month)
-- Net revenue  = SUM(line_total_net)  — line_total_net is already
--   the net amount after discount but before IVA (verified:
--   qty * unit_price_net accounts for discount_pct, making
--   line_total_net < qty * unit_price_net in some rows).
-- Gross revenue = SUM(line_total_net * (1 + sl.tax_rate))
--   using the line-level tax rate (matches the dbt MART_GMV_MENSAL).
-- gmv_gross from SALES.total_gross aggregated per month is also
--   provided as a header-level cross-check column.
-- ticket_medio is computed on gmv_gross (gross average basket)
--   consistent with the dbt mart definition.
-- ============================================================
CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_GMV_MENSAL
    TARGET_LAG     = '1 hour'
    WAREHOUSE      = COMPUTE_WH
    REFRESH_MODE   = AUTO
    INITIALIZE     = ON_CREATE
    COMMENT        = 'Dynamic Table: monthly GMV (gross + net) from base RAW tables. Auto-refreshes within 1 hour of source changes. Replaces the orchestrator-driven CREATE OR REPLACE pattern.'
AS
WITH sale_dates AS (
    -- one row per sale_id with its year_month extracted from VARCHAR order_date
    SELECT
        sale_id,
        LEFT(order_date, 7)      AS year_month,
        total_gross              AS header_gross   -- header-level gross for cross-check
    FROM RETAIL_DB.RAW.SALES
    WHERE order_date IS NOT NULL
),
line_agg AS (
    SELECT
        sd.year_month,
        sl.sale_id,
        sl.line_total_net                                    AS line_net,
        sl.line_total_net * (1 + sl.tax_rate)               AS line_gross
    FROM RETAIL_DB.RAW.SALE_LINES sl
    JOIN sale_dates sd ON sl.sale_id = sd.sale_id
),
header_agg AS (
    -- aggregate header gross per month (one row per order, no fan-out)
    SELECT year_month, SUM(header_gross) AS sum_header_gross
    FROM sale_dates
    GROUP BY year_month
)
SELECT
    la.year_month,
    LEFT(la.year_month, 4)::NUMBER                                          AS year,
    SUBSTR(la.year_month, 6, 2)::NUMBER                                     AS month,
    CAST(ha.sum_header_gross              AS NUMBER(18,2))                  AS gmv_gross_header,
    CAST(SUM(la.line_gross)               AS NUMBER(18,2))                  AS gmv_gross,
    CAST(SUM(la.line_net)                 AS NUMBER(18,2))                  AS gmv_net,
    COUNT(DISTINCT la.sale_id)                                              AS num_pedidos,
    CAST(SUM(la.line_gross) / NULLIF(COUNT(DISTINCT la.sale_id), 0)
         AS NUMBER(14,2))                                                   AS ticket_medio
FROM line_agg la
JOIN header_agg ha ON la.year_month = ha.year_month
GROUP BY la.year_month, ha.sum_header_gross
ORDER BY la.year_month;


-- ============================================================
-- DT_MARGEM_POR_CATEGORIA
-- Grain: year_month x product_category
-- revenue   = SUM(line_total_net)   — net revenue per category/month
-- cost      = SUM(quantity_delivered * cost_price)
--   quantity_delivered is used (units actually shipped, not ordered)
--   cost_price is the net unit cost from PRODUCTS
-- PRODUCTS deduped with QUALIFY to avoid the known duplicate pk issue
-- ============================================================
CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_MARGEM_POR_CATEGORIA
    TARGET_LAG     = '1 hour'
    WAREHOUSE      = COMPUTE_WH
    REFRESH_MODE   = AUTO
    INITIALIZE     = ON_CREATE
    COMMENT        = 'Dynamic Table: monthly margin by product category. Auto-refreshes within 1 hour. Replaces orchestrator-driven CREATE OR REPLACE.'
AS
WITH prod AS (
    -- deduplicate PRODUCTS: known issue with duplicate product_id rows
    SELECT *
    FROM RETAIL_DB.RAW.PRODUCTS
    QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY 1) = 1
),
sale_dates AS (
    SELECT sale_id, LEFT(order_date, 7) AS year_month
    FROM RETAIL_DB.RAW.SALES
    WHERE order_date IS NOT NULL
),
base AS (
    SELECT
        sd.year_month,
        p.category                                      AS product_category,
        sl.line_total_net                               AS net_rev,
        sl.quantity_delivered * p.cost_price            AS cost_line,
        sl.quantity_delivered                           AS units
    FROM RETAIL_DB.RAW.SALE_LINES sl
    JOIN sale_dates sd  ON sl.sale_id    = sd.sale_id
    JOIN prod p         ON sl.product_id = p.product_id
)
SELECT
    year_month,
    LEFT(year_month, 4)::NUMBER                                             AS year,
    SUBSTR(year_month, 6, 2)::NUMBER                                        AS month,
    product_category,
    CAST(SUM(net_rev)                    AS NUMBER(18,2))                   AS revenue,
    CAST(SUM(cost_line)                  AS NUMBER(18,2))                   AS cost,
    CAST(SUM(net_rev) - SUM(cost_line)   AS NUMBER(18,2))                   AS gross_profit,
    CAST((SUM(net_rev) - SUM(cost_line)) / NULLIF(SUM(net_rev), 0)
         AS NUMBER(8,4))                                                    AS margin_pct,
    SUM(units)                                                              AS total_units
FROM base
GROUP BY year_month, product_category
ORDER BY year_month, revenue DESC;


-- ============================================================
-- DT_TOP_PRODUTOS
-- Grain: year_month x product_id
-- Same logic as DT_MARGEM_POR_CATEGORIA but at product level
-- Includes product_name and category for readability
-- ============================================================
CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_TOP_PRODUTOS
    TARGET_LAG     = '1 hour'
    WAREHOUSE      = COMPUTE_WH
    REFRESH_MODE   = AUTO
    INITIALIZE     = ON_CREATE
    COMMENT        = 'Dynamic Table: monthly revenue, units, and margin per product. Auto-refreshes within 1 hour. Replaces orchestrator-driven CREATE OR REPLACE.'
AS
WITH prod AS (
    SELECT *
    FROM RETAIL_DB.RAW.PRODUCTS
    QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY 1) = 1
),
sale_dates AS (
    SELECT sale_id, LEFT(order_date, 7) AS year_month
    FROM RETAIL_DB.RAW.SALES
    WHERE order_date IS NOT NULL
),
base AS (
    SELECT
        sd.year_month,
        sl.product_id,
        p.name                                          AS product_name,
        p.category,
        sl.line_total_net                               AS net_rev,
        sl.quantity_delivered * p.cost_price            AS cost_line,
        sl.quantity_delivered                           AS units
    FROM RETAIL_DB.RAW.SALE_LINES sl
    JOIN sale_dates sd  ON sl.sale_id    = sd.sale_id
    JOIN prod p         ON sl.product_id = p.product_id
)
SELECT
    year_month,
    LEFT(year_month, 4)::NUMBER                                             AS year,
    SUBSTR(year_month, 6, 2)::NUMBER                                        AS month,
    product_id,
    product_name,
    category,
    CAST(SUM(net_rev)                    AS NUMBER(18,2))                   AS revenue,
    SUM(units)                                                              AS units,
    CAST(SUM(cost_line)                  AS NUMBER(18,2))                   AS cost,
    CAST((SUM(net_rev) - SUM(cost_line)) / NULLIF(SUM(net_rev), 0)
         AS NUMBER(8,4))                                                    AS margin_pct
FROM base
GROUP BY year_month, product_id, product_name, category
ORDER BY year_month, revenue DESC;


-- ============================================================
-- Post-creation validation queries
-- Run after the CREATE statements to confirm data + refresh state
-- ============================================================

-- 1. Verify all three DTs exist and their scheduling state
SHOW DYNAMIC TABLES IN SCHEMA RETAIL_DB.MARTS;

-- 2. Monthly GMV sanity check (expect ~13 rows, June 2025 – June 2026)
SELECT * FROM RETAIL_DB.MARTS.DT_GMV_MENSAL ORDER BY year_month;

-- 3. DT vs dbt mart GMV comparison
SELECT 'DT_GMV_MENSAL (dynamic)'  AS source, ROUND(SUM(gmv_net), 0) AS total_gmv_net
FROM RETAIL_DB.MARTS.DT_GMV_MENSAL
UNION ALL
SELECT 'MART_GMV_MENSAL (dbt)',            ROUND(SUM(gmv_net), 0)
FROM RETAIL_DB.MARTS.MART_GMV_MENSAL;

-- 4. Refresh metadata
SELECT name, target_lag_sec, scheduling_state, last_suspended_on
FROM TABLE(RETAIL_DB.INFORMATION_SCHEMA.DYNAMIC_TABLES());

-- 5. Refresh history
SELECT name, state, refresh_action, data_timestamp
FROM TABLE(RETAIL_DB.INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY())
ORDER BY data_timestamp DESC
LIMIT 10;
