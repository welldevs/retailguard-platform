"""Customer Intelligence — base, valor e retenção.

Público: CRM / Marketing / Head de Growth.
MARTS: mart_rfm, mart_churn_60d, mart_customer_ltv, mart_customer_cohort.
(Marts por cliente — o filtro global de período não se aplica.)
"""
from __future__ import annotations

import streamlit as st

from charts.charts import bar_chart
from components.kpi import kpi_row
from components.notices import limitations, safe
from components.tables import table
from layout.theme import page_header
from services.data import load_mart
from utils.format import eur, num


def render() -> None:
    page_header(
        "👥 Customer Intelligence",
        "Base, valor e retenção de clientes. Fonte: RFM, churn, LTV e coorte.",
    )

    rfm = load_mart("mart_rfm")
    churn = load_mart("mart_churn_60d")
    ltv = load_mart("mart_customer_ltv")
    cohort = load_mart("mart_customer_cohort")

    def _tiles() -> None:
        kpi_row([
            {"label": "Clientes (RFM)", "value": num(len(rfm))},
            {"label": "Em risco (churn 60d)",
             "value": num(int(churn["is_churned"].sum())) if not churn.empty else "—"},
            {"label": "LTV médio",
             "value": eur(ltv["total_revenue_gross"].mean(), 2) if not ltv.empty else "—"},
            {"label": "Pedidos/cliente (médio)",
             "value": f"{ltv['total_orders'].mean():.1f}"
                      if not ltv.empty and "total_orders" in ltv.columns else "—"},
        ])

    safe(_tiles)

    st.subheader("Distribuição RFM")

    def _rfm() -> None:
        label = "rfm_label" if "rfm_label" in rfm.columns else None
        if not label:
            table(rfm.head(50))
            return
        counts = rfm[label].value_counts().rename_axis(label).reset_index(name="clientes")
        bar_chart(counts, label, "clientes")
        table(counts)

    safe(_rfm)

    st.subheader("Retenção por coorte")

    def _cohort() -> None:
        need = {"cohort_month", "activity_month", "retention_rate"}
        if not need.issubset(cohort.columns):
            table(cohort)
            return
        # Matriz de coorte em % (retention_rate vem pronto do mart). Sem heatmap
        # colorido para não introduzir matplotlib como dependência nova.
        pv = cohort.pivot_table(
            index="cohort_month", columns="activity_month",
            values="retention_rate", aggfunc="first",
        )
        st.dataframe(pv.style.format("{:.0%}", na_rep="—"), use_container_width=True)

    safe(_cohort)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Clientes em risco")
        safe(lambda: table(
            churn.sort_values("stockout_count", ascending=False).head(50)
            if "stockout_count" in churn.columns else churn.head(50)
        ))
    with c2:
        st.subheader("Top clientes por LTV")
        safe(lambda: table(ltv.sort_values("total_revenue_gross", ascending=False).head(50)))

    limitations([
        "**Churn rate (%)** — `mart_churn_60d` expõe o flag `is_churned` por cliente; a taxa "
        "consolidada exigiria `count(churned)/count(*)`. Mostramos a contagem em risco.",
    ])
