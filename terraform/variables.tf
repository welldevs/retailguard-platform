# ── Service account ───────────────────────────────────────────────────────────
variable "dbt_user_password" {
  description = <<-DESC
    Password for the DBT_USER service account. PREFER key-pair auth
    (dbt_user_rsa_public_key) and leave this "" so DBT_USER is key-pair-only —
    the service-account standard. Set a value only if you need password fallback.
  DESC
  type        = string
  sensitive   = true
  default     = ""
}

variable "dbt_user_rsa_public_key" {
  description = <<-DESC
    PUBLIC key body (no PEM header/footer, no newlines) for DBT_USER key-pair (JWT)
    auth — the production standard for service accounts. Generate with
    scripts/gen_dbt_keypair.sh. Leave "" to keep password-only auth.
  DESC
  type        = string
  default     = ""
  # Not sensitive: a PUBLIC key is safe to store/commit. The PRIVATE key never
  # leaves the client and is gitignored (see .gitignore + ~/.dbt/keys/).
}

# ── Virtual warehouse ─────────────────────────────────────────────────────────
variable "warehouse_size" {
  description = "Snowflake virtual warehouse size for the dedicated RETAIL_WH_XS."
  type        = string
  default     = "X-SMALL"

  validation {
    condition     = contains(["X-SMALL", "SMALL", "MEDIUM", "LARGE", "X-LARGE"], var.warehouse_size)
    error_message = "Must be X-SMALL, SMALL, MEDIUM, LARGE, or X-LARGE."
  }
}

# ── MinIO / S3-compatible data lake ───────────────────────────────────────────
# Set minio_endpoint to a non-empty value to create the external stage and pipes.
# For local dev: use an ngrok HTTPS URL (e.g. "https://abc123.ngrok.io").
# For AWS S3 in production: adapt storage.tf to use a STORAGE INTEGRATION instead.
variable "minio_endpoint" {
  description = "Public HTTPS endpoint for the MinIO server (ngrok URL or empty string to skip)."
  type        = string
  default     = ""
}

variable "minio_access_key" {
  description = "MinIO / S3 access key used in the external stage credentials."
  type        = string
  sensitive   = true
  default     = "minioadmin"
}

variable "minio_secret_key" {
  description = "MinIO / S3 secret key."
  type        = string
  sensitive   = true
  default     = ""
}

variable "minio_bucket" {
  description = "MinIO bucket that holds the retail-datalake Parquet partitions."
  type        = string
  default     = "retail-datalake"
}

# ── Streamlit deploy ──────────────────────────────────────────────────────────
variable "deploy_streamlit" {
  description = "Run 'snow streamlit deploy' via local-exec after infra is ready."
  type        = bool
  default     = true
}

variable "snow_connection" {
  description = "Snowflake CLI connection name (from ~/.snowflake/config.toml or snowflake.yml)."
  type        = string
  default     = "retail"
}
