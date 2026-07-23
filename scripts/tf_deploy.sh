#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# tf_deploy.sh — Terraform wrapper that loads .env before running
#
# Usage:
#   scripts/tf_deploy.sh [init|plan|apply|destroy|output|fmt|validate]
#
# The .env file at the project root must contain:
#   SNOWFLAKE_ACCOUNT   e.g. "abc12345.eu-west-1"
#   SNOWFLAKE_USER      e.g. "WELTON"
#   SNOWFLAKE_PASSWORD  e.g. "your-password"
#
# Optional (for MinIO streaming path):
#   MINIO_ENDPOINT      e.g. "https://abc123.ngrok.io"
#   MINIO_ACCESS_KEY    e.g. "minioadmin"
#   MINIO_SECRET_KEY    e.g. "minioadmin123"
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# Ensure ~/.local/bin (where terraform binary lives after manual install) is in PATH
export PATH="${HOME}/.local/bin:${PATH}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TF_DIR="${PROJECT_ROOT}/terraform"

# ── Load .env ─────────────────────────────────────────────────────────────────
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: .env not found at ${ENV_FILE}" >&2
  echo "       Create it and add your Snowflake credentials (SNOWFLAKE_ACCOUNT/USER/PASSWORD)." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

# ── Validate required Snowflake vars ──────────────────────────────────────────
for var in SNOWFLAKE_ACCOUNT SNOWFLAKE_USER SNOWFLAKE_PASSWORD; do
  if [[ -z "${!var:-}" ]]; then
    echo "ERROR: ${var} is not set in .env" >&2
    exit 1
  fi
done

# Export for Snowflake Terraform provider (reads these automatically).
# Provider >= 0.100 uses SNOWFLAKE_ORGANIZATION_NAME + SNOWFLAKE_ACCOUNT_NAME
# instead of the legacy SNOWFLAKE_ACCOUNT (format: "ORGNAME-ACCOUNTNAME").
export SNOWFLAKE_USER SNOWFLAKE_PASSWORD
if [[ -n "${SNOWFLAKE_ACCOUNT:-}" ]]; then
  export SNOWFLAKE_ORGANIZATION_NAME="${SNOWFLAKE_ACCOUNT%%-*}"
  export SNOWFLAKE_ACCOUNT_NAME="${SNOWFLAKE_ACCOUNT#*-}"
  unset SNOWFLAKE_ACCOUNT   # remove legacy var to avoid deprecation warning in provider
fi

# ── Run Terraform ─────────────────────────────────────────────────────────────
COMMAND="${1:-plan}"
cd "${TF_DIR}"

echo "▶  terraform ${COMMAND}  (account: ${SNOWFLAKE_ORGANIZATION_NAME:-?}-${SNOWFLAKE_ACCOUNT_NAME:-?}, user: ${SNOWFLAKE_USER})"
echo ""

case "${COMMAND}" in
  init)
    terraform init
    ;;
  plan)
    terraform plan
    ;;
  apply)
    terraform apply -auto-approve
    ;;
  destroy)
    echo "⚠️  WARNING: This will destroy the entire RETAIL_DB infrastructure!"
    read -r -p "    Type 'yes' to confirm: " confirm
    if [[ "${confirm}" == "yes" ]]; then
      terraform destroy -auto-approve
    else
      echo "    Aborted."
    fi
    ;;
  output)
    terraform output
    ;;
  fmt)
    terraform fmt -recursive
    ;;
  validate)
    terraform validate
    ;;
  *)
    echo "Usage: $0 [init|plan|apply|destroy|output|fmt|validate]"
    exit 1
    ;;
esac
