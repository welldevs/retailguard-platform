"""Platform Health — confiança no dado (materialização, cobertura, governança).

Público: Analytics Engineer / Data Platform.
Lê apenas MARTS + catálogo. NÃO reexecuta lógica de negócio: a reconciliação e as
invariantes são garantidas pelos testes singulares do dbt (apenas referenciados).
"""
from __future__ import annotations

import streamlit as st

from components.kpi import kpi_row
from components.notices import safe
from components.tables import table
from layout.theme import page_header
from services.data import KPI_MARTS, load_mart, materialized_marts
from utils.format import num


def render() -> None:
    page_header(
        "🛡️ Platform Health",
        "Confiança no dado: materialização, cobertura e governança (dbt tests).",
    )

    inv = materialized_marts()

    def _health() -> None:
        with_data = int((inv["rows"] > 0).sum()) if not inv.empty else 0
        empty = int((inv["rows"] <= 0).sum()) if not inv.empty else 0
        kpi_row([
            {"label": "MARTS esperados", "value": str(len(KPI_MARTS))},
            {"label": "Materializados c/ dados", "value": num(with_data)},
            {"label": "Vazios / ausentes", "value": num(empty)},
        ])
        table(inv)

    safe(_health)

    st.subheader("Cobertura temporal")

    def _coverage() -> None:
        gmv = load_mart("mart_gmv_mensal")
        if gmv.empty or "year_month" not in gmv.columns:
            st.caption("Sem dados de cobertura.")
            return
        months = sorted(gmv["year_month"].unique())
        kpi_row([
            {"label": "Meses com dados", "value": num(len(months))},
            {"label": "Primeiro mês", "value": str(months[0])},
            {"label": "Último mês", "value": str(months[-1])},
        ])

    safe(_coverage)

    st.subheader("Governança — garantida no dbt (não recalculada aqui)")
    st.markdown(
        "- **Reconciliação GMV mart × RAW** → teste dbt `assert_gmv_mart_matches_source` "
        "(recalcula o GMV a partir do staging e compara com `mart_gmv_mensal`, tolerância € 0,10).\n"
        "- **Invariante SCD2** (uma linha corrente por cliente) → teste dbt "
        "`assert_one_current_row_per_customer`.\n"
        "- **141 testes** rodam no `dbt build`. Esta página não reexecuta lógica de negócio; "
        "apenas reporta materialização e cobertura."
    )
