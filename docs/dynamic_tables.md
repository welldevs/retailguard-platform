# Dynamic Tables — Snowflake-Native Streaming Showcase

## Overview

This document describes the three Snowflake **Dynamic Tables** (`DT_*`) used as a **native-streaming
showcase**. They read the **same canonical `RAW.*` tables** that dbt reads and refresh themselves
within a `TARGET_LAG`, with no orchestrator.

**Scope note — dbt is the single source of truth.** The project chose **dbt** to build all canonical
`MART_*` tables (versioned, tested, portable, CI-integrated) — those are what Streamlit reads. The
`DT_*` Dynamic Tables are **not** the dashboard's source; they exist to demonstrate Snowflake's
declarative, zero-orchestration streaming maintenance over the same base data.

---

## Declarative Dynamic Tables (`dynamic_tables.sql`)

```
CREATE DYNAMIC TABLE RETAIL_DB.MARTS.DT_GMV_MENSAL
    TARGET_LAG = '1 hour'
    WAREHOUSE  = COMPUTE_WH
    REFRESH_MODE = AUTO
    INITIALIZE = ON_CREATE
AS
  SELECT ... FROM RAW.SALES JOIN RAW.SALE_LINES ...
```

| Characteristic | Value |
|---|---|
| Freshness bound | `TARGET_LAG = '1 hour'` — Snowflake guarantees data is at most 1 hour stale |
| Failure handling | Snowflake retries automatically; state visible via `DYNAMIC_TABLE_REFRESH_HISTORY()` |
| Empty data risk | None — built off the populated canonical RAW tables (373K+ sales rows) |
| Dependency ordering | Implicit — Snowflake resolves DT dependency graphs automatically |
| Idempotency | `CREATE DYNAMIC TABLE IF NOT EXISTS` — no-op if the table already exists |
| Orchestration | None — Snowflake schedules and runs each refresh within `TARGET_LAG` |

The DTs read directly from the canonical `RAW.SALES` / `RAW.SALE_LINES` / `RAW.PRODUCTS` tables — the
exact same tables dbt reads, regardless of whether the data arrived via batch CSV or Kafka streaming.

---

## Key Parameters

### `TARGET_LAG`

The maximum acceptable staleness. Snowflake determines refresh frequency from this value. Setting `TARGET_LAG = '1 hour'` means the DT content will never be more than 60 minutes behind the base tables. For near-real-time dashboards, `'1 minute'` is possible but more expensive. For overnight batch equivalents, `'1 day'` suffices.

### `REFRESH_MODE`

- `AUTO` (used here): Snowflake chooses the best mode. For simple append-only aggregations it uses **incremental** (processes only new/changed rows). For complex queries with window functions, QUALIFY, or multi-level CTEs it falls back to **FULL** (recomputes the entire result set). All three DT_ tables received `FULL` mode because of the multi-CTE + QUALIFY + aggregation pattern — this is expected and documented in the refresh history output below.
- `INCREMENTAL`: Force incremental. Only viable when the query shape allows change tracking (simple joins + aggregations on append-only sources without window functions).
- `FULL`: Force full recompute every refresh cycle.

### `INITIALIZE`

- `ON_CREATE` (used here): Snowflake runs the first full refresh immediately when the `CREATE DYNAMIC TABLE` statement executes. Data is available without a separate `ALTER DYNAMIC TABLE ... REFRESH` trigger.
- `ON_SCHEDULE`: The first refresh happens at the next scheduled interval. Table is empty until then.

---

## Why Dynamic Tables (self-maintaining freshness)

An orchestrator-driven rebuild (Airflow/cron issuing `CREATE OR REPLACE TABLE`) bounds freshness by
the schedule interval, fails if a run is missed, and needs explicit dependency ordering. Dynamic
Tables remove all of that:

1. Data lands in the canonical RAW tables (batch CSV or Kafka streaming — same tables).
2. No orchestrator action needed — Snowflake schedules and executes the refresh within `TARGET_LAG`.
3. Each DT (`DT_GMV_MENSAL`, `DT_MARGEM_POR_CATEGORIA`, `DT_TOP_PRODUTOS`) stays within 1 hour of the base tables.
4. Operational overhead: zero. Refresh health is inspectable via `DYNAMIC_TABLE_REFRESH_HISTORY()`.

This makes them a clean demonstration of Snowflake-native streaming maintenance — complementary to
the dbt-built `MART_*` tables that actually feed the dashboard.

---

## Verified Refresh Evidence (2026-06-10)

### SHOW DYNAMIC TABLES result

All three DTs created and ACTIVE:

| Name | TARGET_LAG_SEC | Scheduling State |
|---|---|---|
| DT_GMV_MENSAL | 3600 | ACTIVE |
| DT_MARGEM_POR_CATEGORIA | 3600 | ACTIVE |
| DT_TOP_PRODUTOS | 3600 | ACTIVE |

### Refresh History (DYNAMIC_TABLE_REFRESH_HISTORY)

| NAME | STATE | REFRESH_ACTION | DATA_TIMESTAMP |
|---|---|---|---|
| DT_TOP_PRODUTOS | SUCCEEDED | FULL | 2026-06-10 07:00:14.703-07:00 |
| DT_MARGEM_POR_CATEGORIA | SUCCEEDED | FULL | 2026-06-10 06:59:45.031-07:00 |
| DT_GMV_MENSAL | SUCCEEDED | FULL | 2026-06-10 06:59:19.603-07:00 |

All three succeeded with `FULL` refresh action (expected — complex multi-CTE + QUALIFY + aggregation queries; Snowflake AUTO mode selected FULL as noted in the CREATE output). Incremental would require simpler query shapes without window functions or QUALIFY clauses.

### DT_GMV_MENSAL row count: 25 rows (one per month across the two-year window)

### GMV Totals Comparison: DT vs dbt mart (at-creation validation)

When the Dynamic Tables and the dbt mart were created over the **same canonical RAW input**, their
totals reconciled exactly:

| Source | total_gmv_net | total_gmv_gross |
|---|---|---|
| DT_GMV_MENSAL (Dynamic Table) | 23,301,962 | 27,891,990 |
| MART_GMV_MENSAL (dbt), same input | 23,301,962 | 27,891,990 |

**Exact match.** Both use the same business logic: `gmv_net = SUM(line_total_net)`,
`gmv_gross = SUM(line_total_net * (1 + sl.tax_rate))`. Both the `DT_*` tables and the dbt `MART_*`
tables read the same canonical `RAW.*` tables — the reconciliation above proves the SQL is
equivalent. (The figures here are from an earlier validation snapshot; the current two-year RAW load
yields ~€19.7M net / ~€23.5M gross across both the DTs and the dbt marts, since they share the same
base data. The DT may trail the dbt mart by one refresh cycle within `TARGET_LAG`.)

---

## When to Prefer dbt Incremental vs Dynamic Tables

| Concern | Prefer dbt incremental | Prefer Dynamic Tables |
|---|---|---|
| **CI/CD lineage + tests** | Yes — dbt generates DAG, runs schema/data tests, integrates with dbt Cloud CI | No — DTs have no built-in test framework |
| **Cross-platform portability** | Yes — dbt targets Snowflake, BigQuery, Redshift, DuckDB | No — Snowflake-specific feature |
| **Zero-orchestration freshness** | No — dbt still needs an orchestrator (Airflow, dbt Cloud, cron) to trigger runs | Yes — Snowflake schedules autonomously within TARGET_LAG |
| **Bounded staleness SLA** | Hard to guarantee — depends on orchestrator reliability | Yes — Snowflake enforces TARGET_LAG as a contract |
| **Complex window functions / QUALIFY** | Fine — dbt materializes the full SQL | Fine — Dynamic Tables support FULL refresh for complex queries |
| **Incremental processing (large tables)** | Yes — dbt incremental with `is_incremental()` + merge gives fine-grained control | Yes — when REFRESH_MODE=INCREMENTAL is viable (simpler queries on append-only sources) |
| **Cost transparency** | dbt runs consume warehouse credits only at run time | DT refreshes consume warehouse credits on each refresh cycle, billed to the refresh warehouse |

**Recommendation for this project:** dbt is the single source of truth — it builds the production
`MART_*` tables (CI, tests, dashboard SLA) that Streamlit reads. The `DT_*` Dynamic Tables are a
**Snowflake-native streaming showcase** over the same canonical RAW: they demonstrate zero-orchestration
freshness for streaming-adjacent use cases (operational metrics, near-real-time monitoring). They
coexist with the `MART_*` tables but do not replace them.

> **Operational gotcha — incrementals after a full RAW reload.** The `DT_*` tables read `RAW.*`
> directly, so a full re-simulation (`load_parquet.py` / `load_snowflake_raw.py`, which TRUNCATE+reload
> RAW) is reflected automatically on the next refresh. The dbt incremental facts (`fct_sales`,
> `fct_inventory_movements`) are **not** — a plain `dbt build` keeps rows from the prior simulation
> (`where order_date > max(date_id)` never replaces existing dates), silently diluting fill rate,
> perfect-order and churn. After any full RAW reload, rebuild with `dbt build --full-refresh`
> (wrapped by `make build-snowflake`). Incremental-only is correct solely when RAW grows append-only,
> as in real production.

---

## Files

| File | Purpose |
|---|---|
| `snowflake/sql/dynamic_tables.sql` | Idempotent DDL — run once to create all three DTs over canonical RAW |
| `terraform/dynamic_tables.tf` | IaC equivalent — `terraform apply` after `snowflake/sql/dynamic_tables.sql` is a no-op (IF NOT EXISTS) |
