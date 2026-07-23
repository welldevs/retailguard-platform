#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# gen_dbt_keypair.sh — generate an RSA key pair for DBT_USER key-pair auth.
#
# Key-pair (JWT) auth is the production standard for Snowflake SERVICE accounts:
# no password to rotate/leak, and Snowflake is phasing out password-only auth for
# non-human users. The PRIVATE key stays on the client (dbt/Airflow); the PUBLIC
# key is registered on the Snowflake user (here via Terraform → ALTER USER ...
# SET RSA_PUBLIC_KEY).
#
# Usage:
#   DBT_PRIVATE_KEY_PASSPHRASE='choose-a-strong-passphrase' scripts/gen_dbt_keypair.sh
#
# Outputs (default $HOME/.dbt/keys, OUTSIDE the repo — never committed):
#   dbt_user_key.p8   encrypted PKCS#8 private key  → dbt private_key_path
#   dbt_user_key.pub  public key (SPKI)             → Terraform rsa_public_key
#
# It prints the single-line public-key body to paste into terraform.tfvars as
#   dbt_user_rsa_public_key = "MIIBI..."
# and the env vars to export for dbt. It NEVER prints the private key.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

KEY_DIR="${DBT_KEY_DIR:-${HOME}/.dbt/keys}"
PRIV="${KEY_DIR}/dbt_user_key.p8"
PUB="${KEY_DIR}/dbt_user_key.pub"

if [[ -z "${DBT_PRIVATE_KEY_PASSPHRASE:-}" ]]; then
  echo "ERROR: set DBT_PRIVATE_KEY_PASSPHRASE before running (used to encrypt the private key)." >&2
  exit 1
fi

mkdir -p "${KEY_DIR}"
chmod 700 "${KEY_DIR}"

# 1. Encrypted PKCS#8 private key (AES-256). Snowflake + dbt support encrypted keys.
openssl genrsa 2048 2>/dev/null \
  | openssl pkcs8 -topk8 -v2 aes-256-cbc -inform PEM \
      -out "${PRIV}" -passout env:DBT_PRIVATE_KEY_PASSPHRASE
chmod 600 "${PRIV}"

# 2. Public key (SPKI / SubjectPublicKeyInfo) — what Snowflake RSA_PUBLIC_KEY expects.
openssl rsa -in "${PRIV}" -passin env:DBT_PRIVATE_KEY_PASSPHRASE -pubout -out "${PUB}" 2>/dev/null
chmod 644 "${PUB}"

# Single-line body (strip PEM header/footer + newlines) for Terraform/Snowflake.
PUB_BODY="$(grep -v -- '-----' "${PUB}" | tr -d '\n')"

echo "✔  Key pair written to ${KEY_DIR} (private key is gitignored / outside the repo)."
echo ""
echo "── 1. Paste into terraform/terraform.tfvars (gitignored) ──────────────────────"
echo "dbt_user_rsa_public_key = \"${PUB_BODY}\""
echo ""
echo "── 2. Export for dbt (add to .env) ────────────────────────────────────────────"
echo "DBT_PRIVATE_KEY_PATH=${PRIV}"
echo "DBT_PRIVATE_KEY_PASSPHRASE=********  (the value you just used)"
echo ""
echo "── 3. Register the public key + use the key-pair dbt target ───────────────────"
echo "make tf-apply                                  # registers RSA_PUBLIC_KEY on DBT_USER"
echo "cd dbt && dbt debug --target snowflake_keypair # should authenticate as DBT_USER"
