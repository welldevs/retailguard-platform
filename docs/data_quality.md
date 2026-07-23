# Data Quality — Two-Layer Strategy

This project enforces data quality at two distinct points in the pipeline:

---

## Layer 1 — BUILD-TIME tests (`dbt test`)

Defined in `dbt/models/staging/_staging.yml` and propagated to core/mart YAML files.
Cosmos executes each model's tests as a sibling Airflow task immediately after the model runs.

| Test type | Count | Examples |
|---|---|---|
| `unique` | ~20 | `sale_id`, `customer_id`, `invoice_id`, `waste_id` |
| `not_null` | ~46 | `order_date`, `product_id`, `movement_id` |
| `accepted_values` | ~12 | `channel` ∈ {tienda, ecommerce}, `segment` ∈ {Bronze…Platinum} |
| `relationships` / range | ~53 | sale_lines.sale_id → sales.sale_id; fill-rate in [0,1] |
| **Total** | **131** | |

These tests catch **structural and referential** corruption immediately after a model materialises.
They do NOT tell you whether the data arriving in RAW is stale — that is Layer 2's job.

---

## Layer 2 — RUNTIME freshness gate (`dbt source freshness`)

Defined via `config.loaded_at_field` + `config.freshness` on each source table in `_staging.yml`.
The Airflow task `dbt_source_freshness` runs **after** `load_raw_layer` and **before** `dbt_transform`,
acting as a hard gate: an ERROR-level staleness causes a non-zero exit, blocking all downstream dbt tasks.

### Proxy `loaded_at_field`

The RAW tables have no real ingestion timestamp. We use the business-date VARCHAR column cast to
`TIMESTAMP_NTZ` as a proxy:

```yaml
config:
  loaded_at_field: "cast(order_date as timestamp_ntz)"
  freshness:
    warn_after:  {count: 3,  period: day}
    error_after: {count: 60, period: day}
```

**In production this proxy would be replaced by one of:**

1. A `_loaded_at TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()` column written during `COPY INTO`.
2. Snowpipe's `COPY_HISTORY` metadata joined to each table (surfaced via an Information Schema macro).

The proxy is intentionally set to WARN on `sales` (3-day threshold) to demonstrate the check firing
on real warehouse data.

### Freshness thresholds

| Source | `loaded_at_field` proxy | `warn_after` | `error_after` | Result (2026-06-10, data ~5 days old) |
|---|---|---|---|---|
| `raw.sales` | `cast(order_date as timestamp_ntz)` | 3 days | 60 days | **WARN** |
| `raw.invoices` | `cast(invoice_date as timestamp_ntz)` | 7 days | 60 days | PASS |
| `raw.stock_movements` | `cast(movement_date as timestamp_ntz)` | 7 days | 60 days | PASS |

### `dbt source freshness --target snowflake` output (captured 2026-06-10, data ~5 days old)

> Illustrative capture from when the gate was first demonstrated. With the current two-year
> extract (data ending 2026-06-05), all three sources WARN once the data is older than their
> 3–7-day thresholds; none reach the 60-day ERROR threshold, so the gate stays open.

```
13:57:57  Found 44 models, 1 seed, 141 data tests, 1 snapshot, 18 sources, 786 macros
13:57:57  Concurrency: 4 threads (target='snowflake')
13:57:58  Pulling freshness from warehouse metadata tables for 0 sources
13:57:58  1 of 3 START freshness of raw.invoices .......... [RUN]
13:57:58  2 of 3 START freshness of raw.sales ............. [RUN]
13:57:58  3 of 3 START freshness of raw.stock_movements ... [RUN]
13:57:58  2 of 3 WARN freshness of raw.sales .............. [WARN in 0.19s]
13:57:58  1 of 3 PASS freshness of raw.invoices ........... [PASS in 0.34s]
13:57:58  3 of 3 PASS freshness of raw.stock_movements .... [PASS in 0.52s]
13:57:59  Finished running 3 sources in 1.59s.  Done.
```

---

## Airflow dependency chain

```
simulate_batch_csv
    >> load_raw_layer
        >> dbt_source_freshness   ← freshness gate (this doc's subject)
            >> dbt_transform      ← Cosmos DbtTaskGroup (44 models + 141 tests)
```

`dbt_source_freshness` uses `--target dev_raw` (DuckDB) inside the container.
On Snowflake CI it would use `--target snowflake`.

### Production alerting

Wire `on_failure_callback` on the `dbt_source_freshness` task to a Slack webhook or
`airflow.providers.slack.operators.slack.SlackAPIPostOperator` to surface stale-source alerts
immediately, before any mart materialisation occurs:

```python
from airflow.providers.slack.hooks.slack_webhook import SlackWebhookHook

def _on_freshness_failure(context):
    SlackWebhookHook(slack_webhook_conn_id="slack_alerts").send(
        text=f":warning: dbt source freshness FAILED: {context['exception']}"
    )

dbt_source_freshness = BashOperator(
    ...
    on_failure_callback=_on_freshness_failure,
)
```

This closes the observability loop: stale data never silently flows into marts.
