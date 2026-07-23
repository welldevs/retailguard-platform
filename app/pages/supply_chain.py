"""Supply Chain — confiabilidade de fornecedores e malha de entrega.

Público: Diretor de Supply Chain / Compras.
MARTS: mart_supplier_performance, mart_dc_sla, mart_carrier_performance, mart_ap_aging.
(Marts por entidade — o filtro global de período não se aplica.)
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
        "🔗 Supply Chain",
        "Confiabilidade de fornecedores e da malha de entrega (inbound + outbound).",
    )

    sup = load_mart("mart_supplier_performance")
    dc = load_mart("mart_dc_sla")
    carrier = load_mart("mart_carrier_performance")
    ap = load_mart("mart_ap_aging")

    def _tiles() -> None:
        overdue = (
            ap[ap["aging_bucket"] != "0-current"]["total_amount_gross"].sum()
            if not ap.empty else 0
        )
        kpi_row([
            {"label": "Fornecedores", "value": num(len(sup))},
            {"label": "Distribution Centers", "value": num(len(dc))},
            {"label": "Transportadoras", "value": num(len(carrier))},
            {"label": "AP em atraso", "value": eur(overdue)},
        ])

    safe(_tiles)

    st.subheader("OTIF por fornecedor")

    def _otif() -> None:
        if "otif_rate" in sup.columns:
            bar_chart(sup.sort_values("otif_rate", ascending=False).head(20), "supplier_id", "otif_rate")
        table(sup)

    safe(_otif)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("On-time por DC")

        def _dc() -> None:
            if "on_time_rate" in dc.columns:
                bar_chart(dc.sort_values("on_time_rate", ascending=False), "dc_id", "on_time_rate")
            table(dc)

        safe(_dc)
    with c2:
        st.subheader("On-time por transportadora")

        def _carrier() -> None:
            if "on_time_rate" in carrier.columns:
                bar_chart(carrier.sort_values("on_time_rate", ascending=False), "carrier", "on_time_rate")
            table(carrier)

        safe(_carrier)

    st.subheader("Accounts Payable — aging por fornecedor")
    safe(lambda: table(ap.sort_values(["supplier_id", "aging_bucket"])))

    limitations([
        "**OTIF / on-time consolidados** — expostos por fornecedor, DC e carrier (grão do mart). "
        "Um número único exigiria média ponderada por volume.",
    ])
