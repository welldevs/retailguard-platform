-- ============================================================================
-- FinOps — Warehouse Credit & Cost Observability
-- Project: RetailGuard · Spain · RETAIL_DB
-- Author : welldevs
-- Updated: 2026-06-10
--
-- PURPOSE
--   Provide a suite of ready-to-run queries for tracking Snowflake credit
--   consumption, estimating costs, and attributing spend to workloads.
--
-- DATA SOURCES
--   1. SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
--        - Full history, up to 365 days.
--        - LATENCY: data can lag UP TO 3 HOURS behind real time.
--          Do NOT use for live dashboards or same-day alerts.
--        - Requires ACCOUNTADMIN or SNOWFLAKE database privilege.
--
--   2. INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY (table function)
--        - Near real-time (seconds of latency). Good for live demos.
--        - Window limited to the last 14 days.
--        - Available to any role with MONITOR privilege on a warehouse.
--
-- CREDIT PRICE NOTE
--   $credit_price is set to $2.00 USD throughout this file.
--   This is a representative Enterprise On-Demand rate for illustrative
--   purposes only. Your actual contract rate will differ.  Replace every
--   occurrence of "* 2.00" with your negotiated price before using in a
--   business report.
-- ============================================================================


-- ============================================================================
-- QUERY 1 — Credits per warehouse, last 30 days
--           Source: ACCOUNT_USAGE (may lag up to 3 hours)
-- ============================================================================
-- Run as ACCOUNTADMIN (or a role with IMPORTED PRIVILEGES on SNOWFLAKE db).

USE ROLE ACCOUNTADMIN;

SELECT
    WAREHOUSE_NAME,
    ROUND(SUM(CREDITS_USED),              6)  AS CREDITS_USED_TOTAL,
    ROUND(SUM(CREDITS_USED_COMPUTE),      6)  AS CREDITS_COMPUTE,
    ROUND(SUM(CREDITS_USED_CLOUD_SERVICES),6) AS CREDITS_CLOUD_SERVICES,
    -- Illustrative cost at $2.00/credit (Enterprise tier example — see header note)
    ROUND(SUM(CREDITS_USED) * 2.00, 4)        AS EST_COST_USD
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY WAREHOUSE_NAME
ORDER BY CREDITS_USED_TOTAL DESC;

-- ACTUAL OUTPUT (captured 2026-06-10, account: SnowFlake project):
-- ┌─────────────────────────┬──────────────┬─────────────────┬────────────────────────┬───────────────┐
-- │ WAREHOUSE_NAME          │ CREDITS_USED │ CREDITS_COMPUTE │ CREDITS_CLOUD_SERVICES │ EST_COST_USD  │
-- ├─────────────────────────┼──────────────┼─────────────────┼────────────────────────┼───────────────┤
-- │ COMPUTE_WH              │ 16.570051    │ 16.431000       │ 0.139051               │ 33.1401       │
-- │ SYSTEM$STREAMLIT_NB_WH  │  0.053250    │  0.053250       │ 0.000000               │  0.1065       │
-- │ CLOUD_SERVICES_ONLY     │  0.000548    │  0.000000       │ 0.000548               │  0.0011       │
-- └─────────────────────────┴──────────────┴─────────────────┴────────────────────────┴───────────────┘


-- ============================================================================
-- QUERY 2 — Low-latency recent usage, last 7 days grouped by warehouse + day
--           Source: INFORMATION_SCHEMA table function (no significant latency)
--           Good for live demos and same-day monitoring.
-- ============================================================================

SELECT
    WAREHOUSE_NAME,
    DATE_TRUNC('day', START_TIME)              AS USAGE_DAY,
    ROUND(SUM(CREDITS_USED),              6)   AS CREDITS_USED_TOTAL,
    ROUND(SUM(CREDITS_USED_COMPUTE),      6)   AS CREDITS_COMPUTE,
    ROUND(SUM(CREDITS_USED_CLOUD_SERVICES),6)  AS CREDITS_CLOUD_SERVICES,
    ROUND(SUM(CREDITS_USED) * 2.00, 4)         AS EST_COST_USD
FROM TABLE(
    INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
        DATE_RANGE_START => DATEADD('day', -7, CURRENT_DATE())
    )
)
GROUP BY WAREHOUSE_NAME, USAGE_DAY
ORDER BY USAGE_DAY DESC, CREDITS_USED_TOTAL DESC;

-- ACTUAL OUTPUT (captured 2026-06-10, near real-time):
-- ┌────────────────────────────┬────────────┬──────────────┬─────────────────┬────────────────────────┬──────────────┐
-- │ WAREHOUSE_NAME             │ USAGE_DAY  │ CREDITS_USED │ CREDITS_COMPUTE │ CREDITS_CLOUD_SERVICES │ EST_COST_USD │
-- ├────────────────────────────┼────────────┼──────────────┼─────────────────┼────────────────────────┼──────────────┤
-- │ COMPUTE_WH                 │ 2026-06-10 │ 0.000008     │ 0.000000        │ 0.000008               │ 0.0000       │
-- │ COMPUTE_WH                 │ 2026-06-05 │ 6.944352     │ 6.894271        │ 0.050081               │ 13.8887      │
-- │ COMPUTE_WH                 │ 2026-06-03 │ 6.893868     │ 6.834236        │ 0.059632               │ 13.7877      │
-- │ SYSTEM$STREAMLIT_NOTEBOOK_ │ 2026-06-03 │ 0.053229     │ 0.053229        │ 0.000000               │  0.1065      │
-- │ CLOUD_SERVICES_ONLY        │ 2026-06-03 │ 0.000126     │ 0.000000        │ 0.000126               │  0.0003      │
-- └────────────────────────────┴────────────┴──────────────┴─────────────────┴────────────────────────┴──────────────┘


-- ============================================================================
-- QUERY 3 — Credits per workload heuristic (last 30 days)
--           Assigns a human-readable workload label per warehouse.
--           Extend the CASE statement as you add new warehouses.
-- ============================================================================

SELECT
    WAREHOUSE_NAME,
    CASE WAREHOUSE_NAME
        WHEN 'RETAIL_WH_XS' THEN 'dbt transform + dashboard'
        WHEN 'COMPUTE_WH'   THEN 'ad-hoc / load / ELT'
        ELSE                     'system / other'
    END                                            AS WORKLOAD_LABEL,
    ROUND(SUM(CREDITS_USED),        6)             AS CREDITS_USED_TOTAL,
    -- Cost at $2.00/credit — replace with your contracted rate
    ROUND(SUM(CREDITS_USED) * 2.00, 4)            AS EST_COST_USD,
    -- Share of total account spend
    ROUND(
        SUM(CREDITS_USED) * 100.0
        / NULLIF(SUM(SUM(CREDITS_USED)) OVER (), 0),
        2
    )                                              AS PCT_OF_ACCOUNT_CREDITS
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY WAREHOUSE_NAME
ORDER BY CREDITS_USED_TOTAL DESC;

-- ACTUAL OUTPUT (captured 2026-06-10):
-- ┌─────────────────────────┬────────────────────────────┬──────────────┬──────────────┬───────────────────────┐
-- │ WAREHOUSE_NAME          │ WORKLOAD_LABEL             │ CREDITS_USED │ EST_COST_USD │ PCT_OF_ACCOUNT_CREDITS│
-- ├─────────────────────────┼────────────────────────────┼──────────────┼──────────────┼───────────────────────┤
-- │ COMPUTE_WH              │ ad-hoc / load / ELT        │ 16.570051    │ 33.1401      │ 99.62 %               │
-- │ SYSTEM$STREAMLIT_NB_WH  │ system / other             │  0.053250    │  0.1065      │  0.32 %               │
-- │ CLOUD_SERVICES_ONLY     │ system / other             │  0.000548    │  0.0011      │  0.00 %               │
-- └─────────────────────────┴────────────────────────────┴──────────────┴──────────────┴───────────────────────┘
-- NOTE: RETAIL_WH_XS does not appear — it had no activity in the last 30 days
--       (this account uses COMPUTE_WH as the general-purpose warehouse).


-- ============================================================================
-- QUERY 4 — Daily cost trend, last 14 days (INFORMATION_SCHEMA, no latency)
--           Useful for anomaly detection: did a job run longer than expected?
-- ============================================================================

SELECT
    DATE_TRUNC('day', START_TIME)              AS USAGE_DAY,
    ROUND(SUM(CREDITS_USED),        4)         AS CREDITS_USED_TOTAL,
    ROUND(SUM(CREDITS_USED) * 2.00, 2)         AS EST_COST_USD,
    COUNT(DISTINCT WAREHOUSE_NAME)             AS WAREHOUSES_ACTIVE
FROM TABLE(
    INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
        DATE_RANGE_START => DATEADD('day', -14, CURRENT_DATE())
    )
)
GROUP BY USAGE_DAY
ORDER BY USAGE_DAY DESC;


-- ============================================================================
-- QUERY 5 — Query-level attribution: top 10 most expensive statements
--           Source: SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY (up to 3h latency)
--
--           Use this to answer: "which specific query or job is burning credits?"
--           ELAPSED_TIME correlates strongly with credits for compute-bound work.
--           BYTES_SCANNED is the key cost driver for storage-bound queries.
-- ============================================================================

SELECT
    QUERY_ID,
    QUERY_TYPE,
    WAREHOUSE_NAME,
    DATABASE_NAME,
    SCHEMA_NAME,
    ROUND(TOTAL_ELAPSED_TIME / 1000.0, 2)   AS ELAPSED_SEC,
    BYTES_SCANNED,
    ROWS_PRODUCED,
    -- Truncate long query text for readability; use QUERY_ID to look up full text
    LEFT(QUERY_TEXT, 120)                   AS QUERY_TEXT_PREVIEW
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE
    START_TIME     >= DATEADD('day', -7, CURRENT_TIMESTAMP())
    AND WAREHOUSE_NAME IS NOT NULL
ORDER BY TOTAL_ELAPSED_TIME DESC
LIMIT 10;

-- ACTUAL OUTPUT (captured 2026-06-10, top 3 shown for brevity):
-- All top-10 entries are EXECUTE_STREAMLIT calls against RETAIL_DB.PUBLIC.RETAIL_DASHBOARD
-- on COMPUTE_WH, ranging from 909 s to 1615 s elapsed. BYTES_SCANNED = 0
-- (Streamlit execution overhead, not data-scan cost).
-- BYTES_SCANNED = 0 confirms the dashboard load cost is in compute time
-- (warehouse spin-up + session overhead), not in data scan volume.


-- ============================================================================
-- QUERY 6 — Cloud-services credit check
--           Cloud services credits > 10 % of compute credits trigger billing.
--           This query surfaces that ratio so you can act before it costs money.
-- ============================================================================

SELECT
    WAREHOUSE_NAME,
    ROUND(SUM(CREDITS_USED_COMPUTE),       4) AS CREDITS_COMPUTE,
    ROUND(SUM(CREDITS_USED_CLOUD_SERVICES),4) AS CREDITS_CLOUD_SERVICES,
    ROUND(
        SUM(CREDITS_USED_CLOUD_SERVICES) * 100.0
        / NULLIF(SUM(CREDITS_USED_COMPUTE), 0),
        2
    )                                          AS CLOUD_SVC_PCT_OF_COMPUTE,
    CASE
        WHEN SUM(CREDITS_USED_CLOUD_SERVICES) * 100.0
             / NULLIF(SUM(CREDITS_USED_COMPUTE), 0) > 10
        THEN '⚠️  ABOVE 10% THRESHOLD — billed'
        ELSE '✅  Within free tier'
    END                                        AS BILLING_STATUS
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND WAREHOUSE_NAME NOT IN ('CLOUD_SERVICES_ONLY')
GROUP BY WAREHOUSE_NAME
ORDER BY CREDITS_COMPUTE DESC;
