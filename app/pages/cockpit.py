"""Executive Cockpit — 30-second health check for C-level.

Público: CEO / COO / CFO.
Todos os tiles são leitura direta dos MARTS: SOMA de medidas aditivas (GMV,
pedidos, mermas, IVA, AP) ou valor do ÚLTIMO MÊS (ratios que o mart já expõe no
grão mensal). Ratios consolidados (margem %, GMV vs meta %, OTIF, churn %) NÃO
são recalculados aqui — ficam como limitação (ver expander).
"""
from __future__ import annotations

import streamlit as st

from charts.charts import line_chart
from components.kpi import kpi_row
from components.notices import limitations, safe
from layout.theme import page_header
from services.data import load_mart
from utils.format import eur, num, pct
from utils.periods import filter_period


def render() -> None:
    page_header(
        "🎯 Executive Cockpit",
        "Saúde do negócio no período selecionado — leitura direta dos MARTS.",
    )

    gmv = filter_period(load_mart("mart_gmv_mensal"))
    fill = filter_period(load_mart("mart_fill_rate_mensal"))
    stockouts = filter_period(load_mart("mart_stockouts_mensal"))
    mermas = filter_period(load_mart("mart_mermas"))
    iva = filter_period(load_mart("mart_iva_resumo"))
    budget = filter_period(load_mart("budget_mensal"))
    ap = load_mart("mart_ap_aging")            # grão supplier — sem year_month
    churn = load_mart("mart_churn_60d")         # grão cliente
    ltv = load_mart("mart_customer_ltv")        # grão cliente

    def _tiles() -> None:
        latest_gmv = gmv.sort_values("year_month").tail(1)
        latest_fill = fill.sort_values("year_month").tail(1)
        overdue = (
            ap[ap["aging_bucket"] != "0-current"]["total_amount_gross"].sum()
            if not ap.empty else 0
        )
        kpi_row([
            {"label": "GMV bruto (período)", "value": eur(gmv["gmv_gross"].sum())},
            {"label": "GMV líquido (período)", "value": eur(gmv["gmv_net"].sum())},
            {"label": "Pedidos (período)", "value": num(gmv["num_pedidos"].sum())},
            {"label": "Unid. não atendidas", "value": num(stockouts["qty_unmet"].sum()) if not stockouts.empty else "—"},
        ])
        kpi_row([
            {"label": "Ticket médio (último mês)",
             "value": eur(latest_gmv["ticket_medio"].iloc[0], 2) if not latest_gmv.empty else "—"},
            {"label": "Fill rate (último mês)",
             "value": pct(latest_fill["fill_rate_stockout_pct"].iloc[0]) if not latest_fill.empty else "—"},
            {"label": "Perfect order (último mês)",
             "value": pct(latest_fill["perfect_order_pct"].iloc[0]) if not latest_fill.empty else "—"},
            {"label": "IVA cuota (período)", "value": eur(iva["cuota_iva"].sum()) if not iva.empty else "—"},
        ])
        kpi_row([
            {"label": "Custo de mermas (período)", "value": eur(mermas["lost_cost"].sum()) if not mermas.empty else "—"},
            {"label": "AP em atraso", "value": eur(overdue)},
            {"label": "Clientes em risco (churn 60d)",
             "value": num(int(churn["is_churned"].sum())) if not churn.empty else "—"},
            {"label": "LTV médio", "value": eur(ltv["total_revenue_gross"].mean(), 2) if not ltv.empty else "—"},
        ])

    safe(_tiles)

    st.subheader("GMV realizado vs meta")

    def _gmv_meta() -> None:
        g = gmv.sort_values("year_month")
        if not budget.empty:
            # Join 1:1 em chave conformada (year_month) só para o gráfico — não
            # substitui nenhum mart nem recalcula KPI.
            g = g.merge(budget, on="year_month", how="left")
        line_chart(g, "year_month", [c for c in ["gmv_gross", "gmv_meta"] if c in g.columns])

    safe(_gmv_meta)

    limitations([
        "**Margem bruta % consolidada** — `mart_margem_por_categoria` expõe margem no grão "
        "categoria×mês; um % total exigiria `sum(gross_profit)/sum(revenue)`.",
        "**GMV vs meta (%)** consolidado — exigiria `sum(gmv)/sum(meta)`; aqui mostramos "
        "realizado × meta por mês.",
        "**OTIF consolidado** — `mart_supplier_performance` expõe OTIF por fornecedor (ver Supply Chain).",
        "**Churn rate (%)** — `mart_churn_60d` traz o flag por cliente; mostramos a contagem em risco.",
    ])
