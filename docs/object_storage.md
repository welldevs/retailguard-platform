# Object Storage — swapping MinIO for S3 / GCS / Azure

**MinIO is the default** (local, free, S3-compatible) and stays the default. The platform is built so
that the object-storage provider can be swapped **without changing the architecture** — the RAW → dbt →
marts → serving layers are untouched. This document explains exactly what changes and what does not.

> Scope note: this is **documentation only**. No cloud provider is implemented here — MinIO remains the
> reference implementation. Moving to a paid cloud is a roadmap step (see the ADR baseline).

## The abstraction

The streaming/ingestion lane follows one provider-agnostic pattern:

```
producer → object store (S3-compatible)  →  Snowflake EXTERNAL STAGE  →  COPY INTO RAW  →  dbt
                     ▲                                  ▲
          provider-specific here                provider-specific here
          (endpoint + credentials + client)     (STAGE url + storage integration)
```

Everything downstream of `COPY INTO RAW` (staging, marts, snapshots, tests, dashboard) is **100%
provider-independent**. Only **two** touch points are provider-specific:

1. **The object-storage client** in the loader/consumer — `snowflake/load_parquet.py` and
   `extensions/streaming/consumers/parquet_consumer.py` (both read `MINIO_HOST` / `MINIO_ACCESS_KEY` /
   `MINIO_SECRET_KEY` / `MINIO_ENDPOINT` from the environment).
2. **The Snowflake external stage** — `snowflake/sql/minio_external_stage.sql` and
   `terraform/storage.tf` (`var.minio_endpoint` / `var.minio_access_key` / `var.minio_secret_key` /
   `var.minio_bucket`).

## What to change per provider

| Provider | Object-storage client (loader) | Snowflake stage | Auth (recommended) |
|---|---|---|---|
| **MinIO** (default) | `minio` client, `endpoint=localhost:9000`, `secure=False` | `URL='s3://<bucket>/raw/'` + `ENDPOINT=<minio>` | inline demo keys (local only) |
| **AWS S3** | same `minio`/`boto3` client, AWS endpoint (or none), `secure=True` | `URL='s3://<bucket>/raw/'` | **STORAGE INTEGRATION** (IAM role) — no inline keys |
| **Google Cloud Storage** | swap to a GCS client (`google-cloud-storage`) | `URL='gcs://<bucket>/raw/'` | **STORAGE INTEGRATION** (GCS) |
| **Azure Blob** | swap to an Azure client (`azure-storage-blob`) | `URL='azure://<acct>.blob.core.windows.net/<container>/raw/'` | **STORAGE INTEGRATION** (Azure tenant) |

Key points:

- **AWS S3 is the smallest change:** the `minio` Python client is already S3-compatible, so only the
  endpoint + credentials change (prefer a Snowflake **storage integration** over inline keys). No new
  library, no pipeline change.
- **GCS / Azure** require swapping the storage *client library* in the two loader files, and using the
  provider's stage `URL` scheme + storage integration. The Parquet layout
  (`raw/<entity>/dt=YYYY-MM-DD/*.parquet`), the `COPY INTO`, and every dbt model stay identical.
- **Credentials never become literals.** In production use a Snowflake **storage integration**
  (`CREATE STORAGE INTEGRATION`) so no access key lives in SQL or state — this also removes the demo
  `minioadmin123` default entirely.

## Why the architecture does not change

The contract between object storage and the warehouse is the **external stage + `COPY INTO`** pattern,
which Snowflake supports natively for S3, GCS, and Azure. Because the pipeline depends only on *"Parquet
files land in a stage"* — not on *which* object store — the provider is a swappable adapter, not an
architectural decision. That is the definition of being "object-storage compatible."
