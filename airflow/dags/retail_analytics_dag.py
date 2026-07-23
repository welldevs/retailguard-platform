"""
RetailGuard — batch pipeline orchestrated with Airflow + astronomer-cosmos.

This DAG is the batch counterpart to the Kafka/event path:
  1. Generate a fresh ERP batch as CSVs with erp/run_simulation.py.
  2. Load those CSVs into DuckDB RAW tables.
  3. Build/test the dbt Medallion pipeline with Cosmos.

Cosmos parses the dbt project and renders each dbt model as its own Airflow task
(run + test), so the Airflow graph mirrors the dbt DAG one-to-one.
"""

import logging
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.models.param import Param
from cosmos import (
    DbtTaskGroup,
    ExecutionConfig,
    ProfileConfig,
    ProjectConfig,
    RenderConfig,
)
from cosmos.constants import LoadMode

# ── Paths inside the container (baked by the Dockerfile) ───────────────────────
REPO_DIR = "/opt/airflow/project"
PROJECT_DIR = "/opt/airflow/project/dbt"
SCRIPTS_DIR = "/opt/airflow/project/scripts"
SOURCE_DIR = "/opt/airflow/project/source"
SEED_DIR = "/opt/airflow/project/seed_sample"
PROFILES_YML = "/opt/airflow/project/dbt/profiles.yml"
DUCKDB_PATH = "/opt/airflow/duckdb/retail.duckdb"
DBT_BIN = "/opt/dbt_venv/bin/dbt"
PY_BIN = "/opt/dbt_venv/bin/python"  # has duckdb (via dbt-duckdb)

# ── Cosmos configuration ───────────────────────────────────────────────────────
project_config = ProjectConfig(dbt_project_path=PROJECT_DIR)

profile_config = ProfileConfig(
    profile_name="retail_analytics",
    target_name="dev_raw",
    profiles_yml_filepath=PROFILES_YML,
)

execution_config = ExecutionConfig(dbt_executable_path=DBT_BIN)

# DBT_LS: Cosmos runs `dbt ls` at render time to discover models from the live project.
render_config = RenderConfig(load_method=LoadMode.DBT_LS, dbt_executable_path=DBT_BIN)


# ── Production defaults: retries, timeouts, failure logging ─────────────────────
log = logging.getLogger("airflow.task")


def log_task_failure(context):
    """on_failure_callback — emits a structured failure log line (no external service).

    In a real deployment this is where a Slack/PagerDuty/email hook would go; kept
    log-only here to avoid coupling the pipeline to an alerting provider.
    """
    ti = context.get("task_instance")
    dag_obj = context.get("dag")
    log.error(
        "TASK FAILED dag=%s task=%s run=%s try=%s exception=%s",
        dag_obj.dag_id if dag_obj else "?",
        getattr(ti, "task_id", "?"),
        context.get("run_id"),
        getattr(ti, "try_number", "?"),
        context.get("exception"),
    )


default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(hours=2),
    "on_failure_callback": log_task_failure,
}

with DAG(
    dag_id="retail_analytics_pipeline",
    description="Generate batch CSVs, load RAW into DuckDB, then build the dbt Medallion pipeline.",
    schedule="@daily",        # batch refresh cadence (catchup=False → no backfill storm)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    dagrun_timeout=timedelta(hours=3),
    max_active_tasks=1,       # DuckDB has a single write lock → serialize tasks
    tags=["batch", "dbt", "duckdb", "cosmos", "retail"],
    params={
        "period": Param("365d", type="string", description="Simulation shortcut: 30d, 90d, 180d, 365d, ytd"),
        "customers": Param(100000, type="integer", minimum=1, description="Number of customers to simulate"),
        "stores": Param(0, type="integer", minimum=0, description="Number of stores; 0 uses all 1597 real Mercadona store rows"),
        "suppliers": Param(20, type="integer", minimum=1, description="Number of suppliers to simulate"),
        "seed": Param(42, type="integer", description="Deterministic seed"),
    },
) as dag:

    # Step 1 — create a fresh batch in Airflow-managed storage.
    simulate_batch_csv = BashOperator(
        task_id="simulate_batch_csv",
        cwd=REPO_DIR,
        bash_command=(
            f"mkdir -p {SOURCE_DIR} && "
            f"SOURCE_DIR={SOURCE_DIR} {PY_BIN} erp/run_simulation.py "
            "--target csv "
            "--period '{{ params.period }}' "
            "--customers {{ params.customers }} "
            "--stores {{ params.stores }} "
            "--suppliers {{ params.suppliers }} "
            "--seed {{ params.seed }}"
        ),
    )

    # Step 2 — mirror Snowflake's COPY INTO: load batch CSVs as physical main.* tables
    load_raw_layer = BashOperator(
        task_id="load_raw_layer",
        bash_command=(
            f"CSV_DIR={SOURCE_DIR} SCHEMA_CSV_DIR={SEED_DIR} DUCKDB_PATH={DUCKDB_PATH} "
            f"{PY_BIN} {SCRIPTS_DIR}/load_raw_layer.py"
        ),
    )

    # Step 3 — Freshness gate: verify RAW sources are not stale before transforming.
    # Uses the same proxy loaded_at_field (business-date cast to timestamp_ntz) defined
    # in dbt/models/staging/_staging.yml. A WARN (e.g. sales > 3 days old) is logged
    # but does NOT block the pipeline. An ERROR (stale beyond error_after threshold)
    # returns a non-zero exit code and blocks dbt_transform — closing the observability
    # loop. In production, wire on_failure_callback to a Slack/email alert here.
    dbt_source_freshness = BashOperator(
        task_id="dbt_source_freshness",
        bash_command=(
            f"{DBT_BIN} source freshness "
            f"--project-dir {PROJECT_DIR} "
            f"--profiles-dir $(dirname {PROFILES_YML}) "
            "--target dev_raw"
        ),
    )

    # Step 4 — Cosmos renders staging → core → kpi as individual run/test tasks
    dbt_transform = DbtTaskGroup(
        group_id="dbt_transform",
        project_config=project_config,
        profile_config=profile_config,
        execution_config=execution_config,
        render_config=render_config,
    )

    simulate_batch_csv >> load_raw_layer >> dbt_source_freshness >> dbt_transform
