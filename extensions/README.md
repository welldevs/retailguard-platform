# Extensions

Everything here is **outside the platform's core narrative** (see
[docs/adr/0001-architecture-baseline.md](../docs/adr/0001-architecture-baseline.md), §3).

Extensions exist to demonstrate breadth and preserve keywords for job screening — **without**
contaminating the core with features that are broken or only "look" complete. Nothing in the core
pipeline depends on anything in this directory.

| Extension | Location | Status | Purpose |
|---|---|---|---|
| **Streaming** | `extensions/streaming/` | 🧪 **Experimental Extension** — covers **16 of 18** canonical tables (`suppliers` and `stock_snapshots` are not streamed yet) | Event path: simulator → Kafka (KRaft) → Parquet consumer → MinIO. Demonstrates **streaming ingestion** only; **not Core** and **does not feed the Executive Decision Platform**. |
| **Intelligence Layer** | `extensions/ai/` | 🚧 Planned · **vendor-neutral** | Read-only decision layer over `MARTS` (MCP · RAG · NL→SQL · multi-LLM · agents). See its README. |
| **Dynamic Tables** | `terraform/dynamic_tables.tf`, `snowflake/sql/dynamic_tables.sql` *(in place)* | Showcase | Snowflake-native declarative refresh (`TARGET_LAG`). Showcase only — dbt marts are the source of truth. |

> Dynamic Tables stay physically inside `terraform/` and `snowflake/` because moving them would break
> the Terraform deploy — but they are **classified as an extension**, not core.

## The core does not import from here

The streaming producer (`erp/simulator/kafka_bus.py`) lives with the simulator, but the batch pipeline
(loaders → dbt → marts) runs end-to-end with zero dependency on Kafka/MinIO. If this whole directory
were deleted, the platform would still build and pass CI.
