"""Read-only mart loading. The ONLY SQL in the whole app lives here — plain
`SELECT * FROM <schema>.<mart>`. No joins, no aggregations, no business logic.
Every result is cached so a mart read once is reused across all pages.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from services.connection import MARTS_SCHEMA, get_connection

# Canonical serving surface: the 19 KPI marts + the budget seed. Nothing else.
KPI_MARTS = [
    "mart_gmv_mensal",
    "mart_margem_por_categoria",
    "mart_top_produtos",
    "mart_iva_resumo",
    "mart_fill_rate_mensal",
    "mart_stockouts_mensal",
    "mart_stockouts_por_categoria",
    "mart_stock_movements_mensal",
    "mart_mermas",
    "mart_ventas_hora",
    "mart_store_day",
    "mart_rfm",
    "mart_churn_60d",
    "mart_customer_ltv",
    "mart_customer_cohort",
    "mart_supplier_performance",
    "mart_ap_aging",
    "mart_carrier_performance",
    "mart_dc_sla",
]


@st.cache_data(show_spinner=False)
def load_mart(name: str) -> pd.DataFrame:
    """`SELECT * FROM <schema>.<name>` — read-only, cached, no transformation."""
    con = get_connection()
    if con is None:
        return pd.DataFrame()
    return con.execute(f'select * from {MARTS_SCHEMA}."{name}"').df()


@st.cache_data(show_spinner=False)
def materialized_marts() -> pd.DataFrame:
    """Catalog check for Platform Health: which expected marts exist and their row counts."""
    con = get_connection()
    if con is None:
        return pd.DataFrame(columns=["mart", "rows", "status"])
    rows = []
    for name in KPI_MARTS:
        try:
            n = con.execute(f'select count(*) from {MARTS_SCHEMA}."{name}"').fetchone()[0]
            rows.append({"mart": name, "rows": int(n), "status": "ok" if n > 0 else "vazio"})
        except Exception:  # noqa: BLE001 — a missing mart is a health finding, not a crash
            rows.append({"mart": name, "rows": 0, "status": "ausente"})
    return pd.DataFrame(rows)
