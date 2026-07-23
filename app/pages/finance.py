"""Finance — P&L (valores absolutos), IVA e contas a pagar.

Público: CFO / Controladoria / Fiscal.
MARTS: mart_margem_por_categoria, mart_iva_resumo, mart_ap_aging.
Nota: as parcelas do P&L (receita, COGS, gross profit) são medidas ADITIVAS de um
único mart — soma direta, não recomputação. Apenas a margem % consolidada
(ratio de agregados) fica como limitação.
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
from utils.periods import filter_period


def render() -> None:
    page_header(
        "💳 Finance",
        "P&L (valores absolutos), IVA e contas a pagar. Fonte: margem, IVA, AP.",
    )

    margem = filter_period(load_mart("mart_margem_por_categoria"))
    iva = filter_period(load_mart("mart_iva_resumo"))
    ap = load_mart("mart_ap_aging")

    def _pnl() -> None:
        revenue = margem["revenue"].sum() if "revenue" in margem.columns else None
        cogs = margem["cost"].sum() if "cost" in margem.columns else None
        gp = margem["gross_profit"].sum() if "gross_profit" in margem.columns else None
        overdue = (
            ap[ap["aging_bucket"] != "0-current"]["total_amount_gross"].sum()
            if not ap.empty else 0
        )
        kpi_row([
            {"label": "Receita (revenue)", "value": eur(revenue) if revenue is not None else "—"},
            {"label": "COGS (custo)", "value": eur(cogs) if cogs is not None else "—"},
            {"label": "Gross profit", "value": eur(gp) if gp is not None else "—"},
            {"label": "AP em atraso", "value": eur(overdue)},
        ])
        kpi_row([
            {"label": "IVA base imponible", "value": eur(iva["base_imponible"].sum()) if not iva.empty else "—"},
            {"label": "IVA cuota", "value": eur(iva["cuota_iva"].sum()) if not iva.empty else "—"},
            {"label": "Total c/ IVA", "value": eur(iva["total_com_iva"].sum()) if not iva.empty else "—"},
            {"label": "Linhas faturadas",
             "value": num(iva["num_linhas"].sum()) if "num_linhas" in iva.columns else "—"},
        ])

    safe(_pnl)

    st.subheader("IVA por alíquota")

    def _iva() -> None:
        agg = iva.groupby("iva_type", as_index=False)["cuota_iva"].sum()
        bar_chart(agg, "iva_type", "cuota_iva")
        table(iva.sort_values(["year_month", "iva_type"]))

    safe(_iva)

    st.subheader("Accounts Payable por bucket de aging")

    def _ap() -> None:
        agg = (
            ap.groupby("aging_bucket", as_index=False)["total_amount_gross"].sum()
            .sort_values("aging_bucket")
        )
        bar_chart(agg, "aging_bucket", "total_amount_gross")
        table(ap.sort_values(["supplier_id", "aging_bucket"]))

    safe(_ap)

    limitations([
        "**Margem bruta (%)** — `gross_profit/revenue` consolidado é ratio de agregados; os "
        "valores absolutos (receita, COGS, gross profit) são somas diretas e estão acima.",
        "**P&L canônico mês a mês** — hoje montado a partir de `mart_margem_por_categoria`; "
        "um P&L consolidado por mês seria o caso de uso do futuro `mart_executive_mensal`.",
    ])
