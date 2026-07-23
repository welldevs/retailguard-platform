"""Inventory & Stock — disponibilidade na ponta e perdas.

Público: Gestão de Estoque / Categoria.
MARTS: mart_fill_rate_mensal, mart_stockouts_mensal, mart_stockouts_por_categoria,
mart_stock_movements_mensal, mart_mermas.
"""
from __future__ import annotations

import streamlit as st

from charts.charts import bar_chart, line_chart
from components.kpi import kpi_row
from components.notices import safe
from components.tables import table
from layout.theme import page_header
from services.data import load_mart
from utils.format import eur, num, pct
from utils.periods import filter_period


def render() -> None:
    page_header(
        "📦 Inventory & Stock",
        "Disponibilidade na ponta e perdas. Fonte: fill rate, rupturas, movimentos, mermas.",
    )

    fill = filter_period(load_mart("mart_fill_rate_mensal"))
    so_m = filter_period(load_mart("mart_stockouts_mensal"))
    so_c = load_mart("mart_stockouts_por_categoria")          # grão categoria
    mov = filter_period(load_mart("mart_stock_movements_mensal"))
    mermas = filter_period(load_mart("mart_mermas"))

    def _tiles() -> None:
        latest = fill.sort_values("year_month").tail(1)
        kpi_row([
            {"label": "Fill rate (último mês)",
             "value": pct(latest["fill_rate_stockout_pct"].iloc[0]) if not latest.empty else "—"},
            {"label": "Unid. não atendidas", "value": num(so_m["qty_unmet"].sum()) if not so_m.empty else "—"},
            {"label": "Rupturas (período)", "value": num(so_m["num_stockouts"].sum()) if not so_m.empty else "—"},
            {"label": "Custo de mermas", "value": eur(mermas["lost_cost"].sum()) if not mermas.empty else "—"},
        ])

    safe(_tiles)

    st.subheader("Disponibilidade mensal")
    safe(lambda: line_chart(
        fill.sort_values("year_month"), "year_month",
        ["fill_rate_stockout_pct", "perfect_order_pct"],
    ))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Ruptura por categoria (Pareto)")

        def _pareto() -> None:
            bar_chart(so_c.sort_values("qty_unmet", ascending=False).head(15), "product_category", "qty_unmet")
            table(so_c.sort_values("qty_unmet", ascending=False))

        safe(_pareto)
    with c2:
        st.subheader("Mermas por categoria")

        def _mermas() -> None:
            agg = (
                mermas.groupby("product_category", as_index=False)["lost_cost"].sum()
                .sort_values("lost_cost", ascending=False)
            )
            bar_chart(agg, "product_category", "lost_cost")
            table(agg)

        safe(_mermas)

    st.subheader("Movimentos de estoque por tipo")
    safe(lambda: table(mov.sort_values(["year_month", "movement_type"]) if not mov.empty else mov))
