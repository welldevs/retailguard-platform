#!/usr/bin/env bash
# Demo entrypoint: fixed admin credentials instead of the random password that
# `airflow standalone` generates on every container. Local development only.
set -euo pipefail

echo "→ Running database migrations..."
airflow db migrate

echo "→ Ensuring admin user '${AIRFLOW_ADMIN_USER:-admin}' has the fixed password..."
# Delete-then-create so the credentials are ALWAYS the fixed ones, even if the
# metadata volume already has an 'admin' from a previous run (Airflow 2.10 has no
# reset-password CLI). Idempotent across restarts.
airflow users delete --username "${AIRFLOW_ADMIN_USER:-admin}" >/dev/null 2>&1 || true
airflow users create \
  --role Admin \
  --username "${AIRFLOW_ADMIN_USER:-admin}" \
  --password "${AIRFLOW_ADMIN_PASSWORD:-admin}" \
  --email "admin@example.com" \
  --firstname Admin \
  --lastname User

echo "→ Starting scheduler (background) + webserver (foreground)..."
airflow scheduler &
exec airflow webserver
