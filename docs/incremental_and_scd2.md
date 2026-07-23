# Incremental Facts & Real SCD2 — Production dbt Patterns

This note documents two dbt-layer upgrades against Snowflake (`RETAIL_DB`):

1. The two fact tables (`fct_sales`, `fct_inventory_movements`) were converted from
   full `table` rebuilds (`CREATE TABLE AS`) to **incremental `merge`** models.
2. `dim_customer` was rewired onto a **real dbt snapshot** (`scd_customers`) so that
   segment / ticket drift is captured as proper Slowly Changing Dimension Type 2 history.

The numbers below were captured against the live warehouse. Row counts reflect the current
two-year dataset (≈3.58M sale lines / 4.56M stock movements); the timings and bytes-scanned
are representative of an XS warehouse — the ~8.5× ratio is the durable result, not the exact ms.

---

## 1. Incremental fact tables

### What changed

| Model | Before | After |
|-------|--------|-------|
| `fct_sales` | `materialized='table'` | `materialized='incremental'`, `incremental_strategy='merge'`, `unique_key='sale_line_key'`, `on_schema_change='sync_all_columns'` |
| `fct_inventory_movements` | `materialized='table'` | `materialized='incremental'`, `incremental_strategy='merge'`, `unique_key='movement_id'`, `on_schema_change='sync_all_columns'` |

- `fct_sales` has a **composite grain** (`sale_id` + `line_number`) with no single
  natural key, so a surrogate key was added:
  `dbt_utils.generate_surrogate_key(['s.sale_id', 'l.line_number']) as sale_line_key`,
  which is the merge `unique_key`. A `unique` + `not_null` test guards it.
- `fct_inventory_movements` uses the existing natural key `movement_id`
  (already covered by `unique` + `not_null`).
- Each model has an incremental predicate on its date grain so re-runs only scan
  new partitions:
  - `fct_sales`: `where order_date > (select coalesce(max(date_id), '1900-01-01') from {{ this }})`
  - `fct_inventory_movements`: `where movement_date > (select coalesce(max(date_id), '1900-01-01') from {{ this }})`

### Measured gain

| Run | fct_inventory_movements | fct_sales | Rows touched |
|-----|------------------------:|----------:|--------------|
| Full refresh (`--full-refresh`) | **5.89s** | **6.68s** | 4,556,186 / 3,580,300 (full rebuild) |
| Incremental no-op | **2.82s** | **3.33s** | 0 / 0 (only newest partition scanned) |

Snowflake query history for the two `fct_sales` builds confirms the I/O reduction:

| Operation | Bytes scanned | Rows produced |
|-----------|--------------:|--------------:|
| `CREATE OR REPLACE TABLE` (full) | ~73 MB | 3,580,300 |
| `MERGE` (incremental no-op) | ~8.6 MB | 0 |

That is roughly an **8.5x reduction in bytes scanned** even on a no-op run, and it
grows with table size: the full `CREATE TABLE AS` re-reads **all 3.58M sale lines /
4.56M stock movements on every build**, whereas the incremental `MERGE` reads only
the rows whose `order_date` / `movement_date` are newer than the current `max(date_id)`
already in the target.

### Credit implication

Snowflake bills compute by warehouse-seconds (credits). The full rebuild scans the
entire history each run, so cost is O(total rows) and constant-per-run regardless of
how little new data arrived. The incremental `MERGE` makes cost O(new rows): a daily
load that adds one day of sales scans ~1/N of the table instead of 100%. As the fact
tables keep growing, the full-refresh cost grows linearly while the incremental cost
stays flat per increment — the credit savings compound over time. (Use a periodic
`--full-refresh` only when backfilling history or after a schema change that
`on_schema_change` cannot reconcile.)

---

## 2. Real SCD2 on `dim_customer`

### What changed

- New snapshot **`dbt/snapshots/scd_customers.sql`** (`strategy='check'`,
  `check_cols=['segment','avg_ticket','ticket_trend']`, `unique_key='customer_id'`,
  `invalidate_hard_deletes=true`, `target_schema='MARTS'`). It lands at
  `RETAIL_DB.MARTS.SCD_CUSTOMERS` and tracks segment/ticket drift over time.
- `dim_customer` was rewritten to source the **versioned** tracked attributes
  (`segment`, `avg_ticket`, `ticket_trend`) from `ref('scd_customers')`, joined back
  to `stg_customers` for the current-state descriptive attributes (name, contact, geo,
  birth_year, etc.). The hardcoded sentinel stub was removed.
- It now exposes the real SCD2 columns: `dbt_scd_id`, `dbt_valid_from`,
  `dbt_valid_to`, and a derived `is_current = (dbt_valid_to is null)`.

### Test changes (`dbt/models/marts/core/_core.yml` + `dbt/tests/`)

With SCD2 there can be multiple rows per `customer_id`, so:

- `unique` moved from `customer_id` to **`dbt_scd_id`** (one per versioned row).
- `not_null` added on both `customer_id` and `dbt_scd_id`.
- New **singular test** `dbt/tests/assert_one_current_row_per_customer.sql` enforces
  exactly one `is_current = true` row per `customer_id`.

### Demonstrating real versioning (segment-drift event)

To show SCD2 versioning we need the source to *change* between two snapshot runs.
A key design principle drove how we did this: **the RAW layer is immutable** — it is
only ever populated by `COPY INTO` from a source extract, never by an in-place `UPDATE`.
In production, a customer's segment changing is not a `RAW` mutation; it arrives as a
**new full extract** from the source system (e.g. the CRM re-segments customers at
period end based on YTD behaviour). We model exactly that.

**The drift is generated by the simulator, deterministically, from a seed** — not by
hand-written `UPDATE`s. The simulator already assigns each customer a `ticket_trend`
(`growing` / `declining` / `stable`); the drift event promotes a seeded sample of
`growing` customers one tier up and demotes `declining` customers one tier down
(tier order `Bronze < Silver < Gold < Platinum`), recomputing `avg_ticket` with the new
tier multiplier. Everything else is preserved byte-for-byte.

Two reusable pieces (single source of truth = one pure function
`apply_segment_drift(customers, seed, fraction)` in `erp/generators/customers.py`):

- `erp/run_simulation.py --segment-drift-event` — during a `--target csv` run, after
  writing `customers.csv` (v1) it also writes `customers_drift.csv` (v2).
- `scripts/segment_drift.py --seed 42` — standalone: reads the existing
  `source/customers.csv` (the v1 currently in RAW) and writes `source/customers_drift.csv`
  (v2) **without re-simulating**, so v1 stays exactly consistent with what is loaded.

**Reproducible workflow (no `UPDATE`, no rollback script):**

```bash
# 1. First snapshot — capture v1 (1 version per customer)
cd dbt && dbt snapshot --target snowflake

# 2. Generate the v2 extract from the real v1 (seeded → reproducible)
python scripts/segment_drift.py --seed 42          # → source/customers_drift.csv (seeded subset of movers)

# 3. Load v2 as a NEW extract — TRUNCATE + COPY INTO, never UPDATE
python scripts/load_snowflake_raw.py --table CUSTOMERS --file source/customers_drift.csv

# 4. Second snapshot — movers get a 2nd version
cd dbt && dbt snapshot --target snowflake
```

Verified result:

```sql
SELECT COUNT(*) AS movers
FROM (SELECT customer_id FROM RETAIL_DB.MARTS.SCD_CUSTOMERS
      GROUP BY customer_id HAVING COUNT(*) > 1);
-- a seeded subset of the 10,000 customers carries a 2nd version; every other
-- customer has exactly one current row (snapshot total = base + one row per mover)
```

Example two-version history (a `declining`-trend demotion):

| customer_id | segment | valid_from | valid_to |
|-------------|---------|------------|----------|
| CUST_000073C73F36 | Silver | 2026-06-10 14:50:08 | 2026-06-10 14:52:56 |
| CUST_000073C73F36 | Bronze | 2026-06-10 14:52:56 | (current) |

The old row's `valid_to` equals the new row's `valid_from` exactly — non-overlapping,
gap-free windows (verified globally with a `LEAD()` check: 0 violations). Final
`dbt build` is green on **both** adapters: `--target snowflake` and `--target ci`
(DuckDB) → `PASS=174 WARN=0 ERROR=0`.

> **Production vs. demo — a conscious decision.** In production the snapshot would run
> over each successive source load and the RAW layer would never be touched in place.
> Here the simulator produces a single extract, so we generate the second extract with a
> **seeded drift event** (`--segment-drift-event` / `scripts/segment_drift.py`). This
> keeps RAW immutable (only `COPY INTO` ever writes it), makes the whole scenario
> reproducible from a seed, and removes any need for a rollback script — the drift is a
> deterministic function of `(customers, seed)`, not an irreversible hand-edit.

> **Loader idempotency fix (found while validating this):** `load_snowflake_raw.py` PUTs
> each CSV into `@RETAIL_STAGE/<table>/` and `COPY INTO` reads the *whole* directory with
> `FORCE=TRUE`. A stale staged file (e.g. `customers.csv.gz` left from the v1 load) plus
> the new `customers_drift.csv.gz` caused a **double-load** (twice the row count). Fixed by purging
> the stage path (`REMOVE @RETAIL_STAGE/<table>/`) at the start of each `load_table()`
> before the `PUT`, so `COPY` only ever sees the single file just uploaded. Verified
> idempotent (re-running the v2 load yields exactly 10,000 rows; the follow-up snapshot
> is a clean no-op).
