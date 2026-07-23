"""Executive Decision Platform — Streamlit multipage entrypoint (router).

Serving layer only. Reads the dbt MARTS read-only (DuckDB local / Snowflake prod).
Navigation is defined explicitly with st.navigation, so the `pages/` directory is
a normal Python package (each module exposes `render()`), not Streamlit auto-pages.

Run:  make platform      (or)  streamlit run app/main.py
Data: DUCKDB_PATH (default /tmp/retail_analytics_dev.duckdb), MARTS_SCHEMA (main_marts).
"""
from __future__ import annotations

import streamlit as st

from layout.theme import APP_TITLE, configure_page, inject_css
from pages import (
    cockpit,
    customers,
    finance,
    inventory,
    platform_health,
    revenue,
    store_ops,
    supply_chain,
)
from services.connection import DUCKDB_PATH, has_warehouse
from services.data import load_mart
from utils.periods import set_period

configure_page()
inject_css()

# ── guard: warehouse construído? ────────────────────────────────────────────────
if not has_warehouse():
    st.title(APP_TITLE)
    st.error(f"Warehouse não encontrado em `{DUCKDB_PATH}`.")
    st.markdown(
        "Construa o pipeline local primeiro:\n\n"
        "```bash\nmake setup\nmake simulate    # ou um run menor de homologação\n"
        "make load\nmake build\n```\n\n"
        "Ou aponte `DUCKDB_PATH` para o arquivo `.duckdb` correto."
    )
    st.stop()

# ── navegação multipage (definida explicitamente) ───────────────────────────────
# url_path é explícito porque todas as páginas expõem um callable chamado `render`;
# sem isso, st.navigation infere o mesmo pathname para todas e colide.
nav = st.navigation({
    "Strategy": [
        st.Page(cockpit.render, title="Executive Cockpit", icon="🎯", url_path="cockpit", default=True),
    ],
    "Growth": [
        st.Page(revenue.render, title="Revenue & Profit", icon="📈", url_path="revenue"),
        st.Page(customers.render, title="Customer Intelligence", icon="👥", url_path="customers"),
    ],
    "Operations": [
        st.Page(supply_chain.render, title="Supply Chain", icon="🔗", url_path="supply-chain"),
        st.Page(inventory.render, title="Inventory & Stock", icon="📦", url_path="inventory"),
        st.Page(store_ops.render, title="Store Operations", icon="🏪", url_path="store-ops"),
    ],
    "Governance": [
        st.Page(finance.render, title="Finance", icon="💳", url_path="finance"),
        st.Page(platform_health.render, title="Platform Health", icon="🛡️", url_path="platform-health"),
    ],
})


# ── filtro global: período (year_month) ─────────────────────────────────────────
def _global_period_filter() -> None:
    st.sidebar.markdown("### Filtro global")
    gmv = load_mart("mart_gmv_mensal")
    if not gmv.empty and "year_month" in gmv.columns:
        months = sorted(gmv["year_month"].unique())
        if months:
            lo, hi = st.sidebar.select_slider(
                "Período (year_month)",
                options=months,
                value=(months[0], months[-1]),
            )
            set_period((lo, hi))
    st.sidebar.caption(
        "Aplica-se às páginas de grão mensal. Marts por entidade "
        "(clientes, fornecedores, DCs) usam a base completa."
    )


_global_period_filter()
nav.run()
