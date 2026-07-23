# AI Layer (planned)

**Status:** 🚧 Planned — no code yet. Design frozen in
[ADR-017](../../docs/adr/0001-architecture-baseline.md).

An **independent, read-only** module over the analytical layer. It **reads** `RETAIL_DB.MARTS` and dbt
metadata; it never writes to the pipeline. If it is removed, the data platform is unaffected.

## Planned components

```
Snowflake MARTS ─┐
                 ├─►  extensions/ai/   (isolated)
dbt manifest.json┘
   ├─ Vector store: pgvector / Qdrant  (vendor-neutral)
   │     indexes: docs/, dbt model descriptions, KPI glossary
   ├─ RAG: question → retrieval → context → LLM
   ├─ MCP server: read-only tools (query_mart, describe_model, list_kpis)
   ├─ Agent: NL → SQL over the marts (guardrails: SELECT-only, MARTS-only)
   └─ Chat: Streamlit tab or standalone app
```

## Principles

1. Reads marts + metadata; **never** writes to the pipeline.
2. If `extensions/ai/` fails, the platform stays 100% operational.
3. Start with **MCP server + RAG over dbt metadata** (the highest-signal piece for a Data Engineer).
4. This is a *data platform with a semantic interface* — not an "AI project".

## Sequencing

Belongs to the **AI Layer** phase (Q4 2026 – Jan 2027), only after the core is solid and a real cloud
object store is in place. See the roadmap in the architecture baseline.
