"""Store Operations — cockpit operacional loja a loja + hora-punta.

Público: Diretor de Operações de Loja / Gerentes regionais.
MARTS: mart_store_day, mart_ventas_hora.
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
        "🏪 Store Operations",
        "Cockpit operacional loja a loja + hora-punta. Fonte: store_day, ventas_hora.",
    )

    store = filter_period(load_mart("mart_store_day"))
    hora = load_mart("mart_ventas_hora")             # grão hora — período não se aplica

    stores = sorted(store["store_id"].dropna().unique()) if not store.empty else []
    sel = st.multiselect("Loja", stores, default=[])
    store_f = store[store["store_id"].isin(sel)] if sel else store

    def _tiles() -> None:
        kpi_row([
            {"label": "Lojas", "value": num(store["store_id"].nunique()) if not store.empty else "—"},
            {"label": "GMV (período)", "value": eur(store_f["gmv_gross"].sum()) if not store_f.empty else "—"},
            {"label": "Unidades vendidas", "value": num(store_f["units_sold"].sum()) if not store_f.empty else "—"},
            {"label": "Rupturas em loja", "value": num(store_f["num_stockouts"].sum()) if not store_f.empty else "—"},
        ])

    safe(_tiles)

    st.subheader("Ranking de lojas por GMV")

    def _rank() -> None:
        agg = (
            store_f.groupby("store_id", as_index=False)["gmv_gross"].sum()
            .sort_values("gmv_gross", ascending=False).head(20)
        )
        bar_chart(agg, "store_id", "gmv_gross")

    safe(_rank)

    st.subheader("Vendas por hora (hora-punta)")

    def _hora() -> None:
        xcol = "order_hour" if "order_hour" in hora.columns else hora.columns[0]
        ycol = "num_pedidos" if "num_pedidos" in hora.columns else hora.select_dtypes("number").columns[0]
        bar_chart(hora.sort_values(xcol), xcol, ycol)
        table(hora)

    safe(_hora)

    st.subheader("Loja × dia (detalhe)")
    safe(lambda: table(store_f.sort_values(["date_id", "store_id"]).head(500)))

    limitations([
        "**Fill rate consolidado por loja** — `mart_store_day` expõe `fill_rate_pct` no grão "
        "loja×dia; um valor por loja no período exigiria média ponderada por unidades.",
    ])
