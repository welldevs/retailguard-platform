# FinOps — Snowflake Cost Observability

This document explains the cost-observability capability added to the RetailGuard Platform,
covering the SQL queries in `snowflake/sql/finops_warehouse_metering.sql` and the
**FinOps** tab in the Streamlit dashboard.

---

## 1. What each query answers

| Query | Question answered |
|---|---|
| **Q1 — Credits per warehouse (30d, ACCOUNT_USAGE)** | How many credits did each warehouse burn in the last 30 days? Split by compute vs. cloud-services credit types. |
| **Q2 — Low-latency daily usage (7d, INFORMATION_SCHEMA)** | Same breakdown but with near-zero latency — suitable for live dashboards and same-day alerts. |
| **Q3 — Workload heuristic (30d, ACCOUNT_USAGE)** | Which logical workload (dbt/transform, ad-hoc/load, system) is driving credit spend? Shows share of total account credits. |
| **Q4 — Daily cost trend (14d, INFORMATION_SCHEMA)** | How does credit consumption vary day-to-day? Use for anomaly detection (unexpected spikes = runaway job). |
| **Q5 — Query-level attribution (7d, ACCOUNT_USAGE)** | Which specific SQL statements cost the most, ranked by elapsed time and bytes scanned? |
| **Q6 — Cloud-services ratio check** | Is cloud-services credit consumption above the 10% threshold where Snowflake starts billing for it? |

---

## 2. ACCOUNT_USAGE vs. INFORMATION_SCHEMA

| Dimension | ACCOUNT_USAGE | INFORMATION_SCHEMA |
|---|---|---|
| Latency | Up to **3 hours** | **Near real-time** (seconds) |
| History window | Up to **365 days** | **14 days** |
| Minimum privilege | `ACCOUNTADMIN` or `IMPORTED PRIVILEGES` on the SNOWFLAKE database | `MONITOR` privilege on the warehouse |
| Use case | Historical trend analysis, month-end reporting, cost allocation | Live dashboard, same-day monitoring, CI/CD cost gates |
| Used in Streamlit tab | No (too much privilege for app runtime) | **Yes** — `load_finops()` uses the table function |

**Rule of thumb:** use INFORMATION_SCHEMA for anything that needs to be fresh;
use ACCOUNT_USAGE for anything that needs full history or cross-account analysis.

---

## 3. Credit to USD model

Snowflake bills in **credits**. The cost in USD depends on your contract:

```
USD cost = credits_used × credit_price_per_unit
```

| Edition | Typical on-demand price |
|---|---|
| Standard | ~$2.00 / credit |
| Enterprise | ~$3.00 / credit (on-demand) |
| Business Critical | ~$4.00 / credit (on-demand) |

All queries and the dashboard use **$2.00/credit** as a conservative illustrative
baseline. This is clearly marked as "illustrative" throughout the code and UI.
Replace every `* 2.00` with your actual negotiated rate before using in a business report.

1 XS warehouse = 1 credit/hour. Auto-suspend at 60 s of idle time effectively
means you pay only for the seconds the warehouse is active.

---

## 4. FinOps conversation guide

### Cost per workload
Query 3 maps each warehouse to a workload label.
In this project `COMPUTE_WH` (ad-hoc / load / ELT) consumed **16.57 credits (~$33.14)**
over 30 days. That is 99.6 % of account spend. The dashboard/dbt workload
(`RETAIL_WH_XS`) is either auto-suspended or was not active in the observation window —
a positive sign.

### Identifying expensive queries
Query 5 revealed the top-10 costliest statements are all `EXECUTE_STREAMLIT` calls
on `RETAIL_DB.PUBLIC.RETAIL_DASHBOARD`, ranging 909–1615 s elapsed with
**0 bytes scanned**. This confirms the cost is warehouse spin-up and session overhead,
not data scan volume. Fix: enable `st.cache_data` on all loaders (already done)
and use a smaller warehouse size for the dashboard.

### Right-sizing the warehouse
- `COMPUTE_WH` is used for both ELT bulk loads (which need size M or L for a short
  burst) and for the Streamlit dashboard (which needs only XS).
- Recommendation: route the dashboard to `RETAIL_WH_XS` (XS), keep `COMPUTE_WH`
  at M only for dbt full-refresh runs, and auto-suspend both at 60 s.

### Auto-suspend savings estimate
If `COMPUTE_WH` is XS and runs 1 hour/day for ELT:
- With auto-suspend off (24 h): 24 credits/day × 30 days = 720 credits = $1,440/month.
- With auto-suspend at 60 s and 1 h of actual work: 1 credit/day × 30 = 30 credits = $60/month.
- **Savings: ~$1,380/month on a single XS warehouse.**

### Cloud-services threshold (Query 6)
Cloud-services credits are free up to 10% of compute credits. Query 6 surfaces the
ratio per warehouse so you can detect metadata-heavy workloads (heavy SHOW TABLES,
COPY INTO metadata, Python connector overhead) before they generate a surprise bill.

---

## 5. Dashboard tab

The **💵 FinOps** tab (tab 6 in the Streamlit app) exposes:
- Four KPI metrics: total credits, estimated USD cost, warehouses active, days with activity.
- A stacked bar chart of credits per day per warehouse.
- A per-warehouse summary table with credits, compute vs. cloud-services split, and estimated cost.
- A graceful `st.info` fallback if the runtime role cannot access metering data.

All data comes from `INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY` (14-day window,
no ACCOUNT_USAGE latency, available to warehouse-monitor roles).
