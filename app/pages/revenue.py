"""Revenue & Profit — onde receita e margem crescem ou vazam.

Público: Diretor Comercial / Head de Categoria.
MARTS: mart_gmv_mensal, budget_mensal, mart_margem_por_categoria, mart_top_produtos.
"""
from __future__ import annotations

import streamlit as st

from charts.charts import bar_chart, line_chart
from components.kpi import kpi_row
from components.notices import limitations, safe
from components.tables import table
from layout.theme import page_header
from services.data import load_mart
from utils.format import eur, num
from utils.periods import filter_period


def render() -> None:
    page_header(
        "📈 Revenue & Profit",
        "Onde a receita e a margem crescem — ou vazam. Fonte: MARTS de vendas.",
    )

    gmv = filter_period(load_mart("mart_gmv_mensal"))
    budget = filter_period(load_mart("budget_mensal"))
    margem = filter_period(load_mart("mart_margem_por_categoria"))
    top = filter_period(load_mart("mart_top_produtos"))

    cats = sorted(margem["product_category"].dropna().unique()) if not margem.empty else []
    sel = st.multiselect("Categoria", cats, default=cats)
    margem_f = margem[margem["product_category"].isin(sel)] if sel else margem

    def _tiles() -> None:
        latest = gmv.sort_values("year_month").tail(1)
        kpi_row([
            {"label": "GMV bruto (período)", "value": eur(gmv["gmv_gross"].sum())},
            {"label": "GMV líquido (período)", "value": eur(gmv["gmv_net"].sum())},
            {"label": "Pedidos (período)", "value": num(gmv["num_pedidos"].sum())},
            {"label": "Ticket médio (último mês)",
             "value": eur(latest["ticket_medio"].iloc[0], 2) if not latest.empty else "—"},
        ])

    safe(_tiles)

    st.subheader("GMV realizado vs meta")

    def _line() -> None:
        g = gmv.sort_values("year_month")
        if not budget.empty:
            g = g.merge(budget, on="year_month", how="left")
        line_chart(g, "year_month", [c for c in ["gmv_gross", "gmv_meta"] if c in g.columns])

    safe(_line)

    st.subheader("Receita por categoria")

    def _cat() -> None:
        agg = (
            margem_f.groupby("product_category", as_index=False)["revenue"].sum()
            .sort_values("revenue", ascending=False)
        )
        bar_chart(agg, "product_category", "revenue")
        table(margem_f.sort_values(["year_month", "revenue"], ascending=[True, False]))

    safe(_cat)

    st.subheader("Top produtos por receita")

    def _top() -> None:
        rev = "revenue" if "revenue" in top.columns else top.select_dtypes("number").columns[0]
        table(top.sort_values(rev, ascending=False).head(20))

    safe(_top)

    limitations([
        "**Margem % agregada no período** — o mart expõe `margin_pct` no grão categoria×mês; "
        "consolidá-lo exigiria `sum(gross_profit)/sum(revenue)`. Mostramos receita (soma direta) "
        "por categoria e a tabela no grão original.",
    ])
