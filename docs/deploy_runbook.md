# Deploy Runbook — RetailGuard Platform on Snowflake

The exact, ordered command sequence to stand up the platform from zero, with the **reason** for
each step. Mirrors how the live environment was built and hardened.

> **Auth model:** the human account (`SNOWFLAKE_USER`) authenticates with a password from `.env`;
> the `DBT_USER` service account authenticates with an **RSA key pair** (no password). Secrets live
> only in `.env`, `terraform/terraform.tfvars`, and `~/.dbt/` — all gitignored.

---

## 0. Prerequisites (once per machine)

```bash
# Terraform >= 1.5 (binary → ~/.local/bin if no sudo)
cd /tmp && curl -sLO https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip \
  && unzip -q terraform_1.9.8_linux_amd64.zip && mv terraform ~/.local/bin/terraform

pip install -r requirements.txt          # dbt-snowflake, snowflake-connector, streamlit, etc.
# snow CLI connection 'retail' in ~/.snowflake/config.toml (account/user/password/role)
```
**Why:** Terraform provisions all Snowflake objects; `snow` CLI deploys Streamlit and runs ad-hoc SQL;
the Python deps run the simulator + dbt.

```bash
# create .env at the repo root with your Snowflake creds (gitignored, never committed):
printf 'SNOWFLAKE_ACCOUNT=\nSNOWFLAKE_USER=\nSNOWFLAKE_PASSWORD=\n' > .env   # + MINIO_* if streaming
```
**Why:** every script and the Terraform wrapper read credentials from `.env` — never hardcoded, never committed.

---

## 1. Infrastructure as Code — Terraform (the "deploy")

```bash
make tf-init     # scripts/tf_deploy.sh init — download provider snowflakedb/snowflake ~> 0.100
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
#   edit: dbt_user_rsa_public_key (step 2), leave dbt_user_password="" → key-pair-only
make tf-plan     # preview ~50 resources
make tf-apply    # create DB + 4 schemas + warehouse + RETAIL_ENGINEER role + DBT_USER
                 #   + 22 tables + file formats + internal stage + 3 Dynamic Tables + Streamlit
```
**Why:** one idempotent `apply` reproduces the entire environment in any account — no manual UI clicks.
The wrapper parses `SNOWFLAKE_ACCOUNT` into the provider's `ORGANIZATION_NAME`/`ACCOUNT_NAME` and loads `.env`.

---

## 2. Key-pair auth for the DBT_USER service account

```bash
DBT_PRIVATE_KEY_PASSPHRASE='<strong-passphrase>' scripts/gen_dbt_keypair.sh
#   → ~/.dbt/keys/dbt_user_key.p8 (private, gitignored) + prints the PUBLIC key body
#   paste the public key into terraform/terraform.tfvars: dbt_user_rsa_public_key = "MIIB..."
#   add to .env: DBT_PRIVATE_KEY_PATH + DBT_PRIVATE_KEY_PASSPHRASE
make tf-apply    # registers RSA_PUBLIC_KEY on DBT_USER
```
**Why:** service accounts should never use passwords (the production standard). The private key never
leaves the machine; only the public key is stored (it is not a secret).

---

## 3. Generate the synthetic dataset

```bash
make simulate    # python erp/run_simulation.py --period 730d --customers 10000 --stores 150 --seed 42 --export-csv  → source/*.csv
```
**Why:** deterministic (seed 42) OLTP output — 350,648 sales, 3.46M sale lines, 10,000 customers, etc.
Same seed → byte-identical data, so the numbers are reproducible.

---

## 4. Load RAW into Snowflake

```bash
python scripts/load_snowflake_raw.py     # PUT source/*.csv → @RETAIL_STAGE → COPY INTO RAW.*
```
**Why:** mirrors a production COPY-INTO ingestion. The loader purges the stage path before each PUT
(`REMOVE @stage/<table>/`) so `COPY ... FORCE=TRUE` only ever sees the file just uploaded — idempotent,
no double-loads.

---

## 5. Build the Medallion (staging → star schema → KPI marts)

```bash
cd dbt && set -a && source ../.env && set +a
dbt deps
dbt build --full-refresh --target snowflake   # 187 nodes: 18 staging views + 5 dims + 2 incremental fcts
                                               #   + 1 SCD2 snapshot + 19 KPI marts + 1 seed + 141 tests
```
**Why:** dbt builds and TESTS every layer in dependency order. `fct_sales`/`fct_inventory_movements`
are incremental (`MERGE`); `dim_customer` is backed by the `scd_customers` snapshot.
> **`--full-refresh` is required here** because `load_snowflake_raw.py` (step 4) TRUNCATE+reloads
> the RAW tables. Without it, the incremental facts keep rows from a prior simulation (different
> dates/values), silently diluting fill rate, perfect-order and churn. The `make build-snowflake`
> target wraps this exact command. (A pure incremental `dbt build` is correct only when RAW grows
> append-only, as in real production — not after a full re-simulation.)

> CI / local check (DuckDB, no Snowflake, ephemeral): `DBT_CSV_DIR=../seed_sample dbt build --target ci`
> → same 187 nodes green (the CI DuckDB is fresh each run, so incrementals build full anyway).
> Proves the pipeline is portable + reproducible.

---

## 6. Governance — RBAC + Dynamic Data Masking (post-bootstrap, on demand)

```bash
snow sql -f snowflake/sql/rbac_and_masking.sql --connection retail
```
**Why:** creates `RETAIL_DASHBOARD_ROLE` (least-privilege) + `RETAIL_GOVERNANCE_ROLE` and masks PII on
`RAW.CUSTOMERS` (email/nif/phone/names). Exempt roles: `ACCOUNTADMIN` + `RETAIL_GOVERNANCE_ROLE`.
> **Run dbt as an exempt role** (the default target is ACCOUNTADMIN) so the transformation layer keeps
> clear PII; non-exempt roles see masked values.

---

## 7. (Optional) SCD2 segment-drift demo

```bash
python scripts/segment_drift.py --seed 42                                   # → source/customers_drift.csv (v2)
cd dbt && dbt snapshot --target snowflake                                    # capture v1
python scripts/load_snowflake_raw.py --table CUSTOMERS --file source/customers_drift.csv  # load v2 (new extract)
cd dbt && dbt snapshot --target snowflake                                    # → versions a seeded subset of customers
```
**Why:** demonstrates real SCD Type 2 — a re-segmentation arrives as a **new source extract** (COPY INTO),
RAW is never `UPDATE`-d, and the snapshot records gap-free history. Reproducible from the seed.

---

## 8. Dashboard (Streamlit in Snowflake)

Deployed automatically by `make tf-apply` (step 1) whenever `snowflake/streamlit_app.py` changes
(Terraform triggers `snow streamlit deploy --replace --prune`). Manual redeploy:
```bash
make deploy-streamlit
```
**Why:** the dashboard reads only `RETAIL_DB.MARTS` (dbt output). Open in Snowsight → Apps → Streamlit → RETAIL_DASHBOARD.

---

## 9. Validate everything

```bash
make lint                                   # ruff
make test                                   # pytest (34 tests)
(cd dbt && DBT_CSV_DIR=../seed_sample dbt build --target ci)   # full pipeline, DuckDB, 187 green
make tf-plan                                # → "No changes" (infra matches code)
```
**Why:** proves the platform builds from scratch (CI), unit logic holds, and the live infra has zero drift.

---

## 10. Security one-time hardening (operator actions)

- **Rotate** the human Snowflake password if it ever touched git history; update `.env` + `~/.snowflake/config.toml`.
- The `DBT_USER` password is unset (key-pair-only) — nothing to rotate there.
- `terraform/*.tfstate*` and `terraform.tfvars` are gitignored; if they were ever committed, untrack with
  `git rm --cached` and scrub history.

---

### One-shot (environment already bootstrapped)

```bash
make tf-apply                                   # converge infra (idempotent)
make simulate && python scripts/load_snowflake_raw.py
(cd dbt && set -a && source ../.env && set +a && dbt build --full-refresh --target snowflake)  # full-refresh: RAW was reloaded
make deploy-streamlit
```
