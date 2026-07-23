# Airflow + astronomer-cosmos image for the RetailGuard dbt pipeline.
#
# Pattern: dbt lives in an ISOLATED virtualenv (/opt/dbt_venv), separate from the
# Airflow Python environment. This is the Astronomer-recommended layout — it avoids
# the dependency conflicts (jinja2, pydantic, etc.) that arise when dbt and Airflow
# share one environment. Cosmos points at the venv's dbt binary via ExecutionConfig.
FROM apache/airflow:2.10.3-python3.12

# Cosmos in the Airflow environment (it only orchestrates; it does not run dbt itself)
RUN pip install --no-cache-dir "astronomer-cosmos==1.7.1"

# dbt in its own venv — same pins as CI (dbt-core 1.11.11 / dbt-duckdb 1.10.1).
# Built as root (the airflow user can't write to /opt), then handed back to airflow.
USER root
RUN python -m venv /opt/dbt_venv && \
    /opt/dbt_venv/bin/pip install --no-cache-dir --upgrade pip && \
    /opt/dbt_venv/bin/pip install --no-cache-dir \
        "dbt-core==1.11.11" "dbt-duckdb==1.10.1" && \
    chown -R airflow:root /opt/dbt_venv
USER airflow

# Bake the project into the image: ERP simulator, dbt models, RAW loader, and
# the versioned seed sample. Airflow generates fresh batch CSVs with the ERP
# simulator before loading DuckDB.
COPY --chown=airflow:root erp/                       /opt/airflow/project/erp/
COPY --chown=airflow:root dbt/                       /opt/airflow/project/dbt/
COPY --chown=airflow:root scripts/                   /opt/airflow/project/scripts/
COPY --chown=airflow:root seed_sample/               /opt/airflow/project/seed_sample/
COPY --chown=airflow:root airflow/config/profiles.yml /opt/airflow/project/dbt/profiles.yml

# Install dbt packages (dbt_utils, dbt_date) so Cosmos can parse the project at render time
RUN cd /opt/airflow/project/dbt && \
    DBT_PROFILES_DIR=/opt/airflow/project/dbt /opt/dbt_venv/bin/dbt deps

# Demo entrypoint with FIXED admin credentials (replaces `airflow standalone`)
COPY --chmod=0755 --chown=airflow:root airflow/entrypoint.sh /opt/airflow/entrypoint-demo.sh
