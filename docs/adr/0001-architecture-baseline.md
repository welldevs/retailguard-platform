# ADR-0001 — Architecture Baseline (frozen reference)

**Status:** Accepted · **Date:** 2026-07 · **Owners:** project maintainer + ARB review
(Principal DE / Principal Engineer / Staff Engineer / Hiring Manager perspectives).

This document freezes the architectural identity of the project. It is the source of truth; future
decisions cite it by ADR number. Reopened only on material Data Engineering market change.

---

## Principle

The project is an **End-to-End Data Engineering Platform**, *not* a technology showcase.
No technology is "Core" because it is popular. Popularity is an **employability** criterion
(keyword/ATS), not an **architecture** criterion. The two are evaluated separately.

## 1. North Star

> *"This platform ingests retail transactional data and transforms it — with tested quality and
> governance — into reliable analytical models on a cloud data warehouse, all provisioned as code
> and validated in CI."*

- **Recruiter:** end-to-end platform on Snowflake + dbt, with Terraform and CI/CD.
- **Data engineer:** Medallion (RAW→staging→marts) in dbt, incremental MERGE + real SCD2, tests +
  source freshness, orchestration with a freshness gate, reproducible via IaC and local DuckDB.
  *(Model contracts are a roadmap item — §7 — not yet implemented.)*
- **Hiring manager:** candidate who understands the full data lifecycle and prioritizes correctness,
  governance and cost — does not accumulate tools; justifies each.
- **Principal:** separates a reliable batch core from clearly-fenced extensions (streaming/AI),
  serves decisions through a modular **Executive Decision Platform** (`app/`) with a planned
  **vendor-neutral Intelligence Layer**, models history correctly (SCD2), processes incrementally,
  treats governance/FinOps as first class.

## 2. Core

Core = solves a real pipeline problem. Everything Core lives at the repository root.

| Tech | Core | Rationale |
|---|---|---|
| Python, SQL | ✅ | Glue + warehouse language. Every JD. |
| Snowflake | ✅ | Cloud DW = the platform. Transferable to BigQuery/Databricks. |
| dbt | ✅ | Transformation + tests + lineage. De-facto standard. The heart. |
| Terraform | ✅ | IaC / reproducibility. Rare portfolio differentiator (enterprise, consultancies). |
| GitHub Actions | ✅ | CI/CD quality gate. Universal signal. |
| Docker | ✅ | Reproducible environments. Table-stakes. |
| Airflow | ✅ (orchestrator, **not protagonist**) | Highest-frequency orchestration keyword in Spanish JDs — must be *correct*. See ADR-004. |
| Governance (RBAC + Masking) | ✅ | PII / GDPR. EU differentiator. |
| FinOps | ✅ (differentiator) | Cost observability. Rare, senior signal. |
| Incremental MERGE | ✅ | Efficient processing. Proof of craft. |
| SCD2 | ✅ | Correct historical modeling. Proof of craft. |
| DuckDB | ✅ (dev/CI only) | Zero-cost local/CI parity. Engineering hygiene. |
| Streamlit | ⚠️ non-core (minimal serving) | BI/storytelling. Kept small as the serving proof. |

**Data source:** a **synthetic OLTP data generator in Python** (`erp/` — models ERP-domain entities:
sales, POs, invoices, AP, inventory). It is **not a PostgreSQL database**. Postgres appears in the
repo *only* as Airflow's metadata store. See ADR-009.

## 3. Extensions (fenced off from Core, in `extensions/`)

| Item | Why not core | When to use | Jobs it helps |
|---|---|---|---|
| Streaming (Kafka/MinIO) | Batch is the honest backbone; streaming duplicated marts and is currently a subset (16/18 tables) | Real-time / CDC case (fixed + isolated) | Flywire; real-time/IoT |
| Dynamic Tables | dbt is the transformation authority | Native near-real-time demo on Snowflake | Snowflake shops |
| BigQuery (future) | Snowflake is the current base | When targeting Mercadona/GCP | Mercadona Tech |
| Intelligence Layer (MCP/RAG/NL→SQL) | Read-only module, **vendor-neutral**, not DE core | Differentiation + currency | DE/Platform with AI bent |

Rule: extensions exist, are labelled as such, and **never contaminate the core with broken features**.

## 4. Repository taxonomy

```
/                Core at the root: README (hero), Makefile, CI, requirements
erp/             Data source — synthetic OLTP generator (Python)         [Core]
scripts/         Batch loaders: CSV → DuckDB / Snowflake RAW              [Core]
dbt/             Transformation: staging → marts, snapshots, tests        [Core]
airflow/         Orchestrator of the platform (Cosmos + freshness gate)   [Core]
app/             Serving — Executive Decision Platform (Streamlit multipage) [Core]
snowflake/       Snowflake-native deploy (streamlit_app.py) + platform SQL [Core]
terraform/       IaC — full Snowflake bootstrap                           [Core]
tests/           pytest                                                   [Core]
extensions/      Everything outside the narrative:                        [Extensions]
  streaming/       Kafka + MinIO streaming path (experimental, 16/18)
  ai/              Planned AI layer (MCP / RAG / chat) — read-only over MARTS
docs/            architecture, deep-dives, and docs/adr (this baseline)
```

Note: Dynamic Tables (`terraform/dynamic_tables.tf`, `snowflake/sql/dynamic_tables.sql`) stay physically
in place (moving them breaks Terraform/deploy) but are **classified as an extension** and documented as
such. Cortex Analyst was **removed** in the v1 public cleanup — it duplicated the planned vendor-neutral
Intelligence Layer and added Snowflake lock-in (see ADR-016).

## 5. Orchestration decision (ADR-ORCHESTRATION)

- **Decision:** Airflow is the **platform orchestrator**, made correct (scheduled, containerized, runs
  the dbt build against Snowflake, retries/SLA, source-freshness gate). GitHub Actions covers CI and the
  scheduled trigger in the no-infra lane. Dagster / Snowflake Tasks remain available as extensions.
- **Why (evidence):** the "Airflow + dbt + Snowflake/cloud DW" pairing is the most recurrent in Spanish
  DE postings; consultancies (Kyndryl/UST/SQLI/Serem/Läberit) filter for Airflow; enterprises (VW)
  expect mature orchestration. Dagster/Prefect/dbt Cloud appear far less often — betting on them as the
  base reduces role coverage.
- **Not protagonist:** the protagonist is transformation quality (dbt/Snowflake) + reliability.
- **Alternatives:** Dagster (currency, low ES adoption), Prefect (simple, low adoption), dbt Cloud Jobs
  (SaaS, little to show in-repo), GH Actions only (cheap, weak orchestration keyword), Snowflake Tasks
  (native, couples & niche).
- **Consequences:** keeps the most valuable keyword; removes the "toy Airflow"; not run 24/7 (on-demand,
  no idle cost). Requires the DAG to target Snowflake and define a real schedule.

## 6. README & documentation strategy

- **README:** inverted pyramid. Recruiter grasps it in 60–90s (title + value line + architecture image +
  ~6 capability bullets + CI badge + 4-command quickstart + 2 screenshots). Engineer reads depth below;
  all numbers/runbooks/deep-dives go to `docs/`. "README sells; `docs/` proves."
- **Docs:** KEEP architecture / incremental_and_scd2 / finops / governance / data_quality;
  MERGE dashboard + kpi → serving; MOVE dynamic_tables under extensions docs; KEEP+SIMPLIFY
  deploy_runbook; **REMOVE faq.md** (93 KB dead weight).

## 7. Technology roadmap (to Jan 2027)

- **Core (Q1–Q2 2026, High):** fix false claims; consolidate one correct batch path; dbt tests +
  contracts; Airflow correct; governance in bootstrap; FinOps consolidated.
- **Cloud (Q2–Q3 2026):** real object store (S3/GCS) replacing MinIO; external stage/Snowpipe; run on a
  real Snowflake trial. Optional BigQuery slice if targeting Mercadona.
- **Advanced DE (Q3–Q4 2026):** data observability (Elementary/freshness); lineage/exposures; streaming
  fixed as extension; optional Dagster showcase.
- **AI Layer (Q4 2026–Jan 2027):** MCP server (read-only over MARTS); RAG over dbt manifest + docs →
  chat; NL→SQL agent with guardrails (SELECT-only, MARTS-only).

## 8. Risks (impact / probability / mitigation)

- **Technical — false PostgreSQL claim** (High / addressed here): frame source as Python generator;
  Postgres = Airflow metadata only.
- **Technical — streaming sold as complete** (High / addressed here): label streaming experimental
  (16/18); it is an extension.
- **Technical — secret in git history** (High / open): rotate the credential; keep secrets in env only.
- **Technical — non-reproducible README numbers** (Medium): reduce to one strong reproducible figure.
- **Narrative — regression to "tech showcase"** (High): governance checklist as a hard gate.
- **Narrative — Airflow becomes protagonist** (Medium): ADR-004 keeps it subordinate.
- **Market — Snowflake vs. Mercadona's GCP** (Medium): transferable skill + optional BigQuery slice.
- **Architectural — dual-path drift** (Medium): core = one path; streaming isolated in extensions.

## 9. Decision list (ADRs)

| # | Decision | Status | Employability impact |
|---|---|---|---|
| 001 | Reposition as End-to-End DE Platform (not tech showcase) | Accepted | Signals judgment > accumulation |
| 002 | Snowflake as primary DW | Accepted | High in consultancies/Flywire; transferable |
| 003 | dbt as the single transformation authority | Accepted | De-facto standard; near-mandatory |
| 004 | Airflow = orchestrator, not protagonist (see §5) | Accepted | Highest-frequency ES orchestration keyword |
| 005 | Terraform for all infra | Accepted | Rare differentiator; enterprise/VW |
| 006 | CI/CD via GitHub Actions (lint→test→dbt build on DuckDB) | Accepted | Universal discipline signal |
| 007 | DuckDB as dev/CI engine | Accepted | Engineering hygiene (AE-valued) |
| 008 | Single batch ingestion path in core; streaming is extension | Accepted | Shows focus over flex |
| 009 | Source = synthetic OLTP generator (NOT PostgreSQL); remove false claim | Accepted (urgent) | Avoids interview-ending misrepresentation |
| 010 | Historical modeling via dbt SCD2 snapshots | Accepted | Classic interview topic; craft |
| 011 | Incremental fact tables (MERGE) | Accepted | Cost/scale understanding |
| 012 | Governance (RBAC + Masking) applied via IaC (in bootstrap) | Accepted | EU/GDPR differentiator |
| 013 | FinOps as a first-class differentiator | Accepted | Rare, senior signal |
| 014 | Streaming (Kafka/MinIO) → extension; correct or label experimental | Accepted | Preserves keyword w/o liability |
| 015 | Dynamic Tables → showcase, not dashboard source | Accepted | Snowflake-shop differentiator |
| 016 | Cortex Analyst → **removed** (v1 cleanup): duplicates the vendor-neutral Intelligence Layer, adds lock-in | Superseded | Removes lock-in; strengthens portable narrative |
| 017 | Intelligence Layer = separate read-only module over MARTS, **vendor-neutral** (MCP/RAG/NL→SQL/multi-LLM) | Accepted | Differentiates w/o descoping DE |
| 018 | Serving = **Executive Decision Platform** (`app/`, Streamlit multipage, 8 pages, presentation-only) | Accepted | Closes the end-to-end story |
| 019 | Real cloud object store replaces MinIO (roadmap) | Accepted | "Cloud" is must-have in JDs |
| 020 | README inverted-pyramid + docs/adr as source of truth; remove faq.md | Accepted | 90s triage decides |
| 021 | Secrets via env/key-pair only; remediate git history | Accepted | Leaked secret in portfolio = red flag |
| 022 | Serving modularized into `app/` (services/layout/components/charts/utils/pages); logic stays in dbt | Accepted | Portfolio-grade serving architecture |
| 023 | Public direction: ERP→RAW→dbt→MARTS→EDP→Intelligence Layer (planned, vendor-neutral) | Accepted | Coherent modern-platform narrative |

## 10. Decision matrix

- **KEEP:** Python, SQL, Snowflake, dbt, Terraform, GitHub Actions, Docker, Incremental MERGE, SCD2,
  Governance/Masking, FinOps, DuckDB (dev/CI), Airflow (orchestrator), the retail domain generator.
- **MOVE (`extensions/`):** Kafka, MinIO, streaming path, Dynamic Tables, Intelligence Layer, (future) Dagster.
- **SIMPLIFY:** README (inverted pyramid), docs (shrink runbook), serving = Executive Decision Platform (`app/`, 8 pages),
  Airflow (correct, not 24/7).
- **REMOVE:** false "PostgreSQL (ERP)" claim, "identical marts / single source of truth" claim while
  streaming is a subset, `docs/faq.md`, defensive over-metrics in the README TL;DR, dead code,
  any remaining secret in git history. **v1 cleanup:** Cortex Analyst (vendor lock-in, duplicates the
  Intelligence Layer), `homolog/` (superseded by `app/`), `.env.example` (Oracle remnant).

## 11. Governance checklist

See [README.md](README.md) in this directory — six mandatory questions; any NO routes the feature to
`extensions/` or rejects it.
