"""Warehouse connection — the ONE place the platform talks to the database.

Local/dev: read-only DuckDB (the dbt `dev_raw` target → schema `main_marts`).
Snowflake: to run as Streamlit-in-Snowflake, replace `get_connection()` with
`snowflake.snowpark.context.get_active_session()` and set MARTS_SCHEMA=MARTS.
The rest of the app never changes — it only calls `load_mart()`.
"""
from __future__ import annotations

import os

import duckdb
import streamlit as st

DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/retail_analytics_dev.duckdb")
# dbt dev_raw → generate_schema_name → main_marts (DuckDB) / MARTS (Snowflake)
MARTS_SCHEMA = os.environ.get("MARTS_SCHEMA", "main_marts")


@st.cache_resource(show_spinner=False)
def get_connection():
    """Read-only handle to the dbt-built warehouse, or None if it does not exist yet."""
    if not os.path.exists(DUCKDB_PATH):
        return None
    return duckdb.connect(DUCKDB_PATH, read_only=True)


def has_warehouse() -> bool:
    return get_connection() is not None
