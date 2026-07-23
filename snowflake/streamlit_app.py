"""
RetailGuard — Executive Dashboard (Streamlit in Snowflake)
Executive storytelling: GMV, margin, fill rate, RFM, churn, P&L.
Primary charts visible by default; granular detail in expanders.
Source: RETAIL_DB.MARTS (dbt Medallion on Snowflake RAW).
"""

import html

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from snowflake.snowpark.context import get_active_session

COMPANY_NAME = "RetailGuard"  # dashboard / brand title

ACCENT_COLOR = "#0e5563"          # primary brand teal — KPIs, legend, primary chart series
ACCENT_RGBA = "14, 85, 99"        # rgb of ACCENT_COLOR, for translucent fills
WARN_COLOR = "#f59e0b"            # amber — secondary / transfer series
BAD_COLOR = "#ef4444"             # red — budget line, churn, targets
MUTED_COLOR = "#64748b"           # slate — neutral series

st.set_page_config(
    page_title=COMPANY_NAME,
    page_icon="🛒",
    layout="wide",
)

# ── Session ───────────────────────────────────────────────────────────────────
session = get_active_session()


def safe_load(fn, label):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"⚠️ Could not load **{label}**: {type(exc).__name__}")
        return pd.DataFrame()


def status_callout(text: str, tone: str = "info", icon: str = "i"):
    st.markdown(f"""
    <div class="insight insight-{tone}">
      <span class="insight-chip">{html.escape(icon)}</span>
      <div>{text}</div>
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, caption: str = "", legend: str = ""):
    caption_html = f'<div class="chart-caption">{html.escape(caption)}</div>' if caption else ""
    legend_html = f'<div class="chart-legend">{legend}</div>' if legend else ""
    st.markdown(f"""
    <div class="chart-head">
      <div>
        <div class="chart-title">{html.escape(title)}</div>
        {caption_html}
      </div>
      {legend_html}
    </div>
    """, unsafe_allow_html=True)


def chart_layout(fig, height=None, showlegend=None, hovermode="x unified"):
    layout = dict(
        title=None,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(l=4, r=4, t=8, b=8),
        hovermode=hovermode,
        font=dict(family="Public Sans, sans-serif", color="#334155"),
        xaxis=dict(showgrid=False, zeroline=False),
        yaxis=dict(showgrid=True, gridcolor="#edf2f7", zeroline=False),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="left",
            x=0,
            font=dict(size=12),
        ),
    )
    if height:
        layout["height"] = height
    if showlegend is not None:
        layout["showlegend"] = showlegend
    fig.update_layout(**layout)
    return fig


def fmt_compact(value: float, prefix: str = "", suffix: str = "") -> str:
    value = float(value or 0)
    abs_value = abs(value)
    if abs_value >= 1_000_000:
        return f"{prefix}{value / 1_000_000:,.1f}M{suffix}"
    if abs_value >= 1_000:
        return f"{prefix}{value / 1_000:,.1f}k{suffix}"
    return f"{prefix}{value:,.0f}{suffix}"


def sparkline(points, color=ACCENT_COLOR) -> str:
    vals = [float(v) for v in points if pd.notna(v)]
    width, height = 120, 26
    if len(set(vals)) <= 1:
        # No real series or a single snapshot (e.g. churn is one accumulated
        # figure) — draw a flat mid-line instead of fabricating a trend.
        mid = height / 2
        coords = [f"0,{mid:.1f}", f"{width:.1f},{mid:.1f}"]
    else:
        lo, hi = min(vals), max(vals)
        span = hi - lo
        recent = vals[-12:]
        coords = [
            f"{i * width / max(len(recent) - 1, 1):.1f},"
            f"{height - 4 - ((v - lo) / span * (height - 8)):.1f}"
            for i, v in enumerate(recent)
        ]
    return (
        f'<svg width="100%" height="26" viewBox="0 0 120 26" preserveAspectRatio="none">'
        f'<polyline points="{" ".join(coords)}" fill="none" stroke="{html.escape(color)}" '
        'stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline></svg>'
    )


def kpi_card(label: str, value: str, note: str, points, icon: str, accent: str, tone: str = "neutral"):
    tone_class = f"kpi-note-{tone}"
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-top">
        <span>{html.escape(label)}</span>
        <span class="kpi-icon">{html.escape(icon)}</span>
      </div>
      <div class="kpi-value">{html.escape(value)}</div>
      <div class="kpi-note {tone_class}">{html.escape(note)}</div>
      {sparkline(points, accent if tone in ("good", "neutral") else "#b45309")}
    </div>
    """, unsafe_allow_html=True)


# ── RFM helpers ───────────────────────────────────────────────────────────────
_RFM_ORDER = [
    "Champions", "Loyal Customers", "Potential Loyalists",
    "At Risk", "Hibernating", "Lost",
]


# ── Queries (cached 10 min) ───────────────────────────────────────────────────
@st.cache_data(ttl=600)
def load_gmv():
    return session.sql("""
        SELECT year_month, gmv_gross, gmv_net, num_pedidos, ticket_medio
        FROM RETAIL_DB.MARTS.MART_GMV_MENSAL
        ORDER BY year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_margem():
    return session.sql("""
        SELECT year_month, product_category,
            SUM(revenue)                                               AS revenue,
            SUM(cost)                                                  AS cost,
            ROUND((SUM(revenue)-SUM(cost))*100.0/NULLIF(SUM(revenue),0),2) AS margin_pct
        FROM RETAIL_DB.MARTS.MART_MARGEM_POR_CATEGORIA
        GROUP BY year_month, product_category
        ORDER BY year_month, revenue DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_fill():
    return session.sql("""
        SELECT year_month, fill_rate_stockout_pct AS fill_rate_pct,
               total_pedidos, pedidos_com_ruptura, pedidos_sem_ruptura
        FROM RETAIL_DB.MARTS.MART_FILL_RATE_MENSAL
        ORDER BY year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_top_produtos():
    return session.sql("""
        SELECT year_month, product_id, product_name, category,
               revenue, units, cost, margin_pct
        FROM RETAIL_DB.MARTS.MART_TOP_PRODUTOS
        ORDER BY year_month, revenue DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_budget():
    return session.sql("""
        SELECT year_month, gmv_meta
        FROM RETAIL_DB.MARTS.BUDGET_MENSAL
        ORDER BY year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_stockouts_mensal():
    return session.sql("""
        SELECT year_month, num_stockouts, qty_requested, qty_unmet, unmet_pct
        FROM RETAIL_DB.MARTS.MART_STOCKOUTS_MENSAL
        ORDER BY year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_stockouts_categoria():
    return session.sql("""
        SELECT product_category, num_stockouts, qty_unmet
        FROM RETAIL_DB.MARTS.MART_STOCKOUTS_POR_CATEGORIA
        ORDER BY qty_unmet DESC
        LIMIT 10
    """).to_pandas()


@st.cache_data(ttl=600)
def load_movimentacoes():
    return session.sql("""
        SELECT year_month, movement_type, num_movements, total_delta
        FROM RETAIL_DB.MARTS.MART_STOCK_MOVEMENTS_MENSAL
        ORDER BY year_month, movement_type
    """).to_pandas()


@st.cache_data(ttl=600)
def load_rfm():
    return session.sql("""
        SELECT rfm_label,
               COUNT(*)                 AS num_customers,
               ROUND(AVG(monetary),2)   AS avg_monetary,
               ROUND(AVG(recency),1)    AS avg_recency,
               ROUND(AVG(frequency),2)  AS avg_frequency
        FROM RETAIL_DB.MARTS.MART_RFM
        GROUP BY rfm_label
        ORDER BY avg_monetary DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_churn():
    return session.sql("""
        SELECT
            SUM(CASE WHEN is_churned THEN 1 ELSE 0 END)                         AS churned,
            COUNT(*)                                                             AS total,
            ROUND(SUM(CASE WHEN is_churned THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS churn_rate
        FROM RETAIL_DB.MARTS.MART_CHURN_60D
    """).to_pandas()


@st.cache_data(ttl=600)
def load_churn_detail():
    return session.sql("""
        SELECT
            segment,
            COUNT(*)                                                             AS total,
            SUM(CASE WHEN is_churned THEN 1 ELSE 0 END)                         AS churned,
            ROUND(SUM(CASE WHEN is_churned THEN 1 ELSE 0 END)*100.0/COUNT(*),1) AS churn_rate,
            ROUND(AVG(stockout_count),2)                                        AS avg_stockouts,
            ROUND(AVG(avg_delay_days),2)                                        AS avg_delay_days
        FROM RETAIL_DB.MARTS.MART_CHURN_60D
        WHERE segment IS NOT NULL
        GROUP BY segment
        ORDER BY churn_rate DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_supplier_perf():
    return session.sql("""
        SELECT supplier_id, supplier_name, category_specialization,
               otif_rate, on_time_rate, in_full_rate, fill_rate,
               avg_lead_time_actual, avg_lead_time_promised, avg_lead_time_variance,
               total_pos
        FROM RETAIL_DB.MARTS.MART_SUPPLIER_PERFORMANCE
        ORDER BY otif_rate DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_dc_sla():
    return session.sql("""
        SELECT dc_id, total_entregas, on_time_rate,
               avg_delay_days_when_late, avg_transit_days,
               delivered_count, total_packages
        FROM RETAIL_DB.MARTS.MART_DC_SLA
        ORDER BY on_time_rate DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_cohort():
    return session.sql("""
        SELECT cohort_month, activity_month, cohort_size,
               active_customers, retention_pct
        FROM RETAIL_DB.MARTS.MART_CUSTOMER_COHORT
        ORDER BY cohort_month, activity_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_ltv_segments():
    return session.sql("""
        SELECT segment,
               COUNT(*)                              AS num_customers,
               ROUND(AVG(total_revenue_gross),2)     AS avg_ltv,
               ROUND(MEDIAN(total_revenue_gross),2)  AS median_ltv,
               ROUND(AVG(total_orders),2)            AS avg_orders,
               ROUND(AVG(aov_gross),2)               AS avg_aov
        FROM RETAIL_DB.MARTS.MART_CUSTOMER_LTV
        GROUP BY segment
        ORDER BY avg_ltv DESC
    """).to_pandas()


@st.cache_data(ttl=600)
def load_iva():
    return session.sql("""
        SELECT iva_type, year_month, base_imponible, cuota_iva, total_com_iva
        FROM RETAIL_DB.MARTS.MART_IVA_RESUMO
        ORDER BY year_month, iva_type
    """).to_pandas()


@st.cache_data(ttl=600)
def load_hora():
    return session.sql("""
        SELECT order_hour, num_pedidos, gmv_gross, ticket_medio, pct_pedidos
        FROM RETAIL_DB.MARTS.MART_VENTAS_HORA
        ORDER BY order_hour
    """).to_pandas()


@st.cache_data(ttl=600)
def load_store_day():
    # Aggregate to store × month so the sidebar period filter applies
    # (the raw mart is store × day ≈ 61k rows).
    return session.sql("""
        SELECT store_id, year_month,
               SUM(num_pedidos)   AS num_pedidos,
               SUM(gmv_gross)     AS gmv_gross,
               SUM(units_sold)    AS units_sold,
               SUM(num_stockouts) AS num_stockouts,
               SUM(unmet_units)   AS unmet_units,
               COUNT(*)           AS dias,
               SUM(CASE WHEN num_stockouts > 0 THEN 1 ELSE 0 END) AS ruptura_dias
        FROM RETAIL_DB.MARTS.MART_STORE_DAY
        GROUP BY store_id, year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_mermas():
    return session.sql("""
        SELECT year_month, location_type, product_category,
               num_eventos, units_wasted, lost_cost
        FROM RETAIL_DB.MARTS.MART_MERMAS
        ORDER BY year_month
    """).to_pandas()


@st.cache_data(ttl=600)
def load_finops():
    """
    Query INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY for the last 14 days.
    Uses the table-function variant (no ACCOUNT_USAGE latency, works with
    MONITOR privilege on the warehouse — no ACCOUNTADMIN required at runtime).
    Falls back to an empty DataFrame so the tab degrades gracefully.
    """
    return session.sql("""
        SELECT
            WAREHOUSE_NAME,
            DATE_TRUNC('day', START_TIME)               AS USAGE_DAY,
            ROUND(SUM(CREDITS_USED),              6)    AS CREDITS_USED,
            ROUND(SUM(CREDITS_USED_COMPUTE),      6)    AS CREDITS_COMPUTE,
            ROUND(SUM(CREDITS_USED_CLOUD_SERVICES),6)   AS CREDITS_CLOUD_SERVICES,
            -- Illustrative cost at $2.00/credit (Enterprise On-Demand example)
            ROUND(SUM(CREDITS_USED) * 2.00, 4)          AS EST_COST_USD
        FROM TABLE(
            INFORMATION_SCHEMA.WAREHOUSE_METERING_HISTORY(
                DATE_RANGE_START => DATEADD('day', -14, CURRENT_DATE())
            )
        )
        GROUP BY WAREHOUSE_NAME, USAGE_DAY
        ORDER BY USAGE_DAY DESC, CREDITS_USED DESC
    """).to_pandas()


# ── Load ──────────────────────────────────────────────────────────────────────
with st.spinner("Loading data…"):
    gmv          = safe_load(load_gmv,                 "Monthly GMV")
    margem       = safe_load(load_margem,              "Category margin")
    fill         = safe_load(load_fill,                "Fill rate")
    top_prod     = safe_load(load_top_produtos,        "Top products")
    budget       = safe_load(load_budget,              "Monthly budget")
    stk_mes      = safe_load(load_stockouts_mensal,    "Monthly stockouts")
    stk_cat      = safe_load(load_stockouts_categoria, "Stockouts by category")
    movs         = safe_load(load_movimentacoes,       "Stock movements")
    rfm          = safe_load(load_rfm,                 "RFM segmentation")
    churn        = safe_load(load_churn,               "Churn 60d")
    churn_detail = safe_load(load_churn_detail,        "Churn by segment")
    iva          = safe_load(load_iva,                 "IVA summary")
    hora         = safe_load(load_hora,                "Hourly sales")
    store_day    = safe_load(load_store_day,           "Store × day")
    mermas       = safe_load(load_mermas,              "Waste / mermas")
    supplier_perf = safe_load(load_supplier_perf,      "Supplier scorecard")
    dc_sla       = safe_load(load_dc_sla,              "DC SLA")
    cohort       = safe_load(load_cohort,              "Customer cohort")
    ltv_segs     = safe_load(load_ltv_segments,        "LTV by segment")
    finops       = safe_load(load_finops,              "FinOps metering")


def filter_period(df, low, high):
    if df is None or df.empty or "YEAR_MONTH" not in df.columns:
        return df
    return df[(df["YEAR_MONTH"] >= low) & (df["YEAR_MONTH"] <= high)]


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"## {COMPANY_NAME}")
    st.markdown("**Snowflake · dbt**")
    st.divider()

    months = sorted(gmv["YEAR_MONTH"].unique().tolist()) if not gmv.empty else []
    if months:
        selected = st.select_slider("Period", options=months, value=(months[0], months[-1]))
        gmv_f      = filter_period(gmv,      selected[0], selected[1])
        fill_f     = filter_period(fill,     selected[0], selected[1])
        iva_f      = filter_period(iva,      selected[0], selected[1])
        margem_f   = filter_period(margem,   selected[0], selected[1])
        top_prod_f = filter_period(top_prod, selected[0], selected[1])
        budget_f   = filter_period(budget,   selected[0], selected[1])
        stk_mes_f  = filter_period(stk_mes,  selected[0], selected[1])
        movs_f     = filter_period(movs,     selected[0], selected[1])
        store_day_f = filter_period(store_day, selected[0], selected[1])
        mermas_f    = filter_period(mermas,    selected[0], selected[1])
    else:
        selected = ("", "")
        gmv_f, fill_f, iva_f = gmv, fill, iva
        margem_f, top_prod_f, budget_f = margem, top_prod, budget
        stk_mes_f, movs_f = stk_mes, movs
        store_day_f, mermas_f = store_day, mermas

    st.divider()
    if not gmv.empty:
        data_through = str(gmv["YEAR_MONTH"].max())
        st.caption(f"Data through {data_through} · {int(gmv['NUM_PEDIDOS'].sum()):,} total orders")
    else:
        data_through = "—"
    st.divider()
    st.caption("Source: RETAIL_DB.MARTS\ndbt Medallion · Snowflake\nCache: 10 min")


# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700;800&family=Public+Sans:wght@400;500;600;700&display=swap');

:root {{
    --accent: {ACCENT_COLOR};
    --ink: #0b2b33;
    --text: #0f172a;
    --muted: #64748b;
    --canvas: #eaeef3;
    --line: #e3e9ef;
    --ok: #15803d;
    --warn: #b45309;
    --bad: #b91c1c;
}}

html, body, [data-testid="stAppViewContainer"] {{
    background: var(--canvas);
    color: var(--text);
    font-family: "Public Sans", system-ui, sans-serif;
}}

h1, h2, h3, .chart-title, .kpi-value {{
    font-family: "Archivo", system-ui, sans-serif !important;
    letter-spacing: 0;
}}

.block-container {{
    padding-top: 2rem;
    padding-bottom: 2.5rem;
    max-width: 1380px;
}}

[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, #0b2b33, #0c3a45 55%, #0e4351);
}}
[data-testid="stSidebar"] * {{ color: #cfe2e9 !important; }}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{ color: #ffffff !important; }}
[data-testid="stSidebar"] input {{
    color: #0f172a !important;
}}

.page-head {{
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 22px;
}}
.page-title {{
    margin: 0;
    color: var(--ink);
    font-size: 29px;
    font-weight: 800;
}}
.page-subtitle {{
    margin-top: 7px;
    color: #5b6b7c;
    font-size: 14px;
}}
.period-pill {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    background: #fff;
    border: 1px solid #dbe3ea;
    border-radius: 999px;
    padding: 7px 14px;
    font-size: 12.5px;
    color: #475569;
    font-weight: 700;
    white-space: nowrap;
}}
.period-pill::before {{
    content: "";
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: #16a34a;
    box-shadow: 0 0 0 3px rgba(22, 163, 74, .16);
}}

.kpi-card {{
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(15,23,42,.05);
    padding: 18px 18px 15px;
    min-height: 156px;
}}
.kpi-top {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    font-size: 11px;
    letter-spacing: .07em;
    text-transform: uppercase;
    color: #7c8a9c;
    font-weight: 800;
}}
.kpi-icon {{ color: #94a3b8; font-size: 16px; letter-spacing: 0; }}
.kpi-value {{
    margin-top: 12px;
    color: var(--ink);
    font-size: clamp(22px, 2.1vw, 29px);
    line-height: 1;
    font-weight: 800;
    white-space: nowrap;
}}
.kpi-note {{
    display: inline-flex;
    width: fit-content;
    margin: 12px 0 8px;
    border-radius: 6px;
    padding: 3px 7px;
    font-size: 12px;
    font-weight: 700;
    color: #64748b;
    background: #f1f5f9;
}}
.kpi-note-good {{ color: var(--ok); background: #e9f6ee; }}
.kpi-note-warn {{ color: var(--warn); background: #fff7ed; }}
.kpi-note-bad {{ color: var(--bad); background: #fef2f2; }}

[data-testid="stVerticalBlockBorderWrapper"] {{
    background: #fff;
    border: 1px solid var(--line);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(15,23,42,.05);
}}

.chart-head {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
    margin-bottom: 14px;
}}
.chart-title {{
    font-weight: 800;
    font-size: 16px;
    color: #0f172a;
}}
.chart-caption {{
    margin-top: 3px;
    font-size: 12.5px;
    color: var(--muted);
    line-height: 1.45;
}}
.chart-legend {{
    display: flex;
    align-items: center;
    gap: 15px;
    flex-wrap: wrap;
    font-size: 12.5px;
    color: #475569;
    font-weight: 700;
    padding-top: 2px;
}}
.legend-swatch {{
    display: inline-flex;
    align-items: center;
    gap: 7px;
}}
.legend-box {{
    width: 12px;
    height: 12px;
    border-radius: 3px;
    background: var(--accent);
}}
.legend-line {{
    width: 18px;
    border-top: 2px dashed #ef4444;
}}

.insight {{
    display: flex;
    align-items: flex-start;
    gap: 12px;
    border-radius: 8px;
    padding: 13px 15px;
    margin: 10px 0 4px;
    font-size: 13.5px;
    line-height: 1.5;
}}
.insight-chip {{
    flex-shrink: 0;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    color: #fff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 800;
}}
.insight-info {{ background: #eef5fb; border: 1px solid #d4e6f5; color: #1e3a5f; }}
.insight-info .insight-chip {{ background: #1d4ed8; }}
.insight-info strong {{ color: #1d4ed8; }}
.insight-good {{ background: #f1f8f4; border: 1px solid #d7ecdf; color: #1e3a2b; }}
.insight-good .insight-chip {{ background: var(--ok); }}
.insight-good strong {{ color: var(--ok); }}
.insight-warn {{ background: #fffaf0; border: 1px solid #f4e3c1; color: #5a3a0c; }}
.insight-warn .insight-chip {{ background: var(--warn); }}
.insight-warn strong {{ color: var(--warn); }}
.insight-bad {{ background: #fff5f3; border: 1px solid #f6d9cf; color: #5a2310; }}
.insight-bad .insight-chip {{ background: var(--bad); }}
.insight-bad strong {{ color: var(--bad); }}

button[data-baseweb="tab"] {{
    font-family: "Public Sans", system-ui, sans-serif;
    font-weight: 700;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    border-bottom: 3px solid var(--accent) !important;
    color: var(--ink) !important;
}}
</style>
""", unsafe_allow_html=True)


# ── Hero ──────────────────────────────────────────────────────────────────────
period_label = (
    f"{gmv_f['YEAR_MONTH'].min()} → {gmv_f['YEAR_MONTH'].max()}"
    if not gmv_f.empty else "—"
)
st.markdown(f"""
<div class="page-head">
  <div>
    <h1 class="page-title">{COMPANY_NAME}</h1>
    <div class="page-subtitle">Executive view — GMV, margin, availability, customers and fiscal P&amp;L.</div>
  </div>
  <div class="period-pill">{html.escape(period_label)} · {len(gmv_f) if not gmv_f.empty else 0} months · data through {html.escape(data_through)}</div>
</div>
""", unsafe_allow_html=True)


# ── Top KPIs ──────────────────────────────────────────────────────────────────
gmv_total    = gmv_f["GMV_GROSS"].sum()       if not gmv_f.empty else 0
orders_total = gmv_f["NUM_PEDIDOS"].sum()     if not gmv_f.empty else 0
ticket_avg   = (gmv_total / orders_total)     if orders_total else 0  # weighted AOV = GMV ÷ orders
fill_avg     = fill_f["FILL_RATE_PCT"].mean() if not fill_f.empty else 0
churn_rate   = float(churn["CHURN_RATE"][0]) if not churn.empty else 0.0
budget_tot   = budget_f["GMV_META"].sum()     if not budget_f.empty else 0
gap_pct      = ((gmv_total - budget_tot) / budget_tot * 100) if budget_tot else 0

kpi_cols = st.columns(5, gap="medium")
with kpi_cols[0]:
    kpi_card(
        "GMV",
        fmt_compact(gmv_total, "€"),
        f"{gap_pct:+.1f}% vs target" if budget_tot else "no target",
        gmv_f["GMV_GROSS"].tolist() if not gmv_f.empty else [],
        "€",
        ACCENT_COLOR,
        "good" if gap_pct >= 0 else "bad",
    )
with kpi_cols[1]:
    kpi_card(
        "Orders",
        f"{orders_total:,.0f}",
        f"~{orders_total / max(len(gmv_f), 1):,.0f} / mo" if not gmv_f.empty else "no data",
        gmv_f["NUM_PEDIDOS"].tolist() if not gmv_f.empty else [],
        "#",
        MUTED_COLOR,
    )
with kpi_cols[2]:
    kpi_card(
        "Avg ticket",
        f"€{ticket_avg:,.2f}",
        "GMV ÷ orders",
        gmv_f["TICKET_MEDIO"].tolist() if not gmv_f.empty and "TICKET_MEDIO" in gmv_f.columns else [],
        "Ø",
        MUTED_COLOR,
    )
with kpi_cols[3]:
    kpi_card(
        "Fill rate",
        f"{fill_avg:.1f}%",
        "above 95% target" if fill_avg >= 95 else "below 95% target",
        fill_f["FILL_RATE_PCT"].tolist() if not fill_f.empty else [],
        "%",
        ACCENT_COLOR,
        "good" if fill_avg >= 95 else "bad",
    )
with kpi_cols[4]:
    kpi_card(
        "Churn 60d",
        f"{churn_rate:.1f}%",
        "healthy (≤20%)" if churn_rate <= 20 else "watch",
        [],
        "↘",
        MUTED_COLOR,
        "good" if churn_rate <= 20 else "warn",
    )

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Overview",
    "🛍️ Products",
    "📦 Operations",
    "🏪 Store ops",
    "👥 Customers",
    "💳 Finance",
    "💵 FinOps",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    if gmv_f.empty:
        st.info("No data for selected period.")
    else:
        gmv_b = gmv_f.copy()
        if not budget_f.empty:
            gmv_b = gmv_b.merge(budget_f, on="YEAR_MONTH", how="left")
        if "GMV_META" not in gmv_b.columns:
            gmv_b["GMV_META"] = float("nan")

        # Partial months (simulation start/end) are flagged so they render in a
        # lighter colour and are tagged in the hover. Bars are anchored at zero
        # (full bars), so the seasonal swing — incl. the December peak — reads
        # directly without a misleading truncated baseline.
        gmv_median = gmv_b["GMV_GROSS"].median()
        gmv_b["IS_PARTIAL"] = gmv_b["GMV_GROSS"] < gmv_median * 0.65

        full_months = gmv_b[~gmv_b["IS_PARTIAL"]]
        all_vals = list(gmv_b["GMV_GROSS"])
        if gmv_b["GMV_META"].notna().any():
            all_vals += list(gmv_b["GMV_META"].dropna())
        y_max = max(all_vals) * 1.14

        bar_colors = [
            f"rgba({ACCENT_RGBA}, 0.35)" if p else ACCENT_COLOR
            for p in gmv_b["IS_PARTIAL"]
        ]
        gmv_b["BAR_LABEL"] = ""
        if not full_months.empty:
            peak_idx = full_months["GMV_GROSS"].idxmax()
            trough_idx = full_months["GMV_GROSS"].idxmin()
            gmv_b.loc[peak_idx, "BAR_LABEL"] = f"Peak · €{gmv_b.loc[peak_idx, 'GMV_GROSS']/1e6:.1f}M"
            gmv_b.loc[trough_idx, "BAR_LABEL"] = f"Low · €{gmv_b.loc[trough_idx, 'GMV_GROSS']/1e6:.1f}M"

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=gmv_b["YEAR_MONTH"], y=gmv_b["GMV_GROSS"],
            name="GMV",
            marker_color=bar_colors,
            text=gmv_b["BAR_LABEL"],
            textposition="outside",
            cliponaxis=False,
            textfont=dict(color="#334155", size=11, family="Public Sans"),
            customdata=gmv_b["IS_PARTIAL"],
            hovertemplate=(
                "<b>%{x}</b><br>GMV: €%{y:,.0f}"
                "<extra>%{customdata}</extra>"
            ),
        ))
        if gmv_b["GMV_META"].notna().any():
            fig.add_trace(go.Scatter(
                x=gmv_b["YEAR_MONTH"], y=gmv_b["GMV_META"],
                name="Budget", mode="lines+markers",
                line=dict(color=BAD_COLOR, width=2, dash="dash"),
                marker=dict(size=6, symbol="diamond"),
            ))

        chart_layout(fig, height=420)
        fig.update_yaxes(title="GMV (€)", range=[0, y_max])
        with st.container():
            section_header(
                "Monthly GMV vs. budget",
                "Faded bars = partial months (simulation start/end). Dashed line = monthly budget.",
                """
                <span class="legend-swatch"><span class="legend-box"></span>GMV</span>
                <span class="legend-swatch"><span class="legend-line"></span>Budget</span>
                """,
            )
            st.plotly_chart(fig, use_container_width=True)

            if budget_tot:
                if gap_pct >= 0:
                    status_callout(
                        f"<strong>On track:</strong> GMV is <strong>{gap_pct:+.1f}%</strong> above budget "
                        f"for the period (€{gmv_total:,.0f} actual vs €{budget_tot:,.0f} target).",
                        "good",
                        "✓",
                    )
                else:
                    status_callout(
                        f"<strong>Gap detected:</strong> GMV is <strong>{gap_pct:+.1f}%</strong> below budget "
                        f"(€{gmv_total:,.0f} vs €{budget_tot:,.0f} target).",
                        "warn",
                        "!",
                    )

        # Secondary — Fill Rate (compact, right-aligned metrics)
        if not fill_f.empty:
            col_chart, col_stats = st.columns([3, 1])
            with col_chart:
                fig_fill = go.Figure()
                fig_fill.add_trace(go.Scatter(
                    x=fill_f["YEAR_MONTH"], y=fill_f["FILL_RATE_PCT"],
                    mode="lines+markers+text", name="Fill Rate",
                    line=dict(color=ACCENT_COLOR, width=2.5),
                    marker=dict(size=7),
                    text=[f"{v:.1f}%" for v in fill_f["FILL_RATE_PCT"]],
                    textposition="top center",
                    textfont=dict(size=10, color="#475569"),
                    hovertemplate="<b>%{x}</b><br>Fill rate: %{y:.2f}%<extra></extra>",
                ))
                fig_fill.add_hline(y=95, line_dash="dash", line_color=BAD_COLOR,
                                   annotation_text="95% target",
                                   annotation_position="bottom right")
                fmin = float(fill_f["FILL_RATE_PCT"].min())
                chart_layout(fig_fill, height=300)
                fig_fill.update_yaxes(
                    title="Fill Rate (%)",
                    range=[min(94, fmin - 1), 100.5],
                )
                with st.container():
                    section_header(
                        "Fill rate — on-shelf availability",
                        "Units delivered ÷ demanded. Target ≥ 95%.",
                    )
                    st.plotly_chart(fig_fill, use_container_width=True)

            with col_stats:
                months_below = int((fill_f["FILL_RATE_PCT"] < 95).sum())
                ruptures     = int(stk_mes_f["NUM_STOCKOUTS"].sum()) if not stk_mes_f.empty else 0
                with st.container():
                    st.metric("Avg fill rate", f"{fill_avg:.1f}%")
                    st.metric("Months < 95%", str(months_below),
                              delta="Issue" if months_below > 0 else "OK",
                              delta_color="inverse" if months_below > 0 else "normal")
                    st.metric("Total stockouts", f"{ruptures:,}")


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Products
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    if margem_f.empty:
        st.info("No data for selected period.")
    else:
        margem_cat = (
            margem_f.groupby("PRODUCT_CATEGORY", as_index=False)
            .agg(REVENUE=("REVENUE", "sum"), COST=("COST", "sum"))
        )
        margem_cat["MARGIN_PCT"] = (
            (margem_cat["REVENUE"] - margem_cat["COST"]) * 100.0
            / margem_cat["REVENUE"].replace(0, float("nan"))
        ).round(2)
        margem_cat = margem_cat.sort_values("REVENUE", ascending=False).head(15)

        col_a, col_b = st.columns(2)

        # Colour scale anchored to actual data range so variation is visible
        _m_lo = max(0.0, float(margem_cat["MARGIN_PCT"].min()) - 3)
        _m_hi = min(60.0, float(margem_cat["MARGIN_PCT"].max()) + 3)

        with col_a:
            fig = px.bar(
                margem_cat.sort_values("REVENUE"),
                x="REVENUE", y="PRODUCT_CATEGORY",
                orientation="h",
                color="MARGIN_PCT",
                color_continuous_scale="RdYlGn",
                range_color=[_m_lo, _m_hi],
                labels={"REVENUE": "Revenue (€)", "PRODUCT_CATEGORY": "",
                        "MARGIN_PCT": "Margin %"},
                text_auto=".2s",
            )
            chart_layout(fig, height=430, hovermode="closest")
            with st.container():
                section_header(
                    "Revenue by category",
                    "Length = revenue. Colour = margin, to flag margin-destroying categories.",
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_b:
            fig_tm = px.treemap(
                margem_cat,
                path=["PRODUCT_CATEGORY"],
                values="REVENUE",
                color="MARGIN_PCT",
                color_continuous_scale="RdYlGn",
                range_color=[_m_lo, _m_hi],
                labels={"MARGIN_PCT": "Margin %"},
            )
            fig_tm.update_traces(
                texttemplate="<b>%{label}</b><br>%{percentRoot:.0%}",
                textfont_size=12,
            )
            chart_layout(fig_tm, height=430, hovermode="closest")
            with st.container():
                section_header(
                    "Revenue share × margin",
                    "Treemap of the top categories for the selected period.",
                )
                st.plotly_chart(fig_tm, use_container_width=True)

        # Narrative callouts
        best  = margem_cat.loc[margem_cat["MARGIN_PCT"].idxmax()]
        worst = margem_cat.loc[margem_cat["MARGIN_PCT"].idxmin()]
        top_r = margem_cat.loc[margem_cat["REVENUE"].idxmax()]
        c1, c2 = st.columns(2)
        with c1:
            status_callout(f"<strong>Best margin:</strong> {html.escape(str(best['PRODUCT_CATEGORY']))} — "
                           f"<strong>{best['MARGIN_PCT']:.1f}%</strong>", "good", "★")
        with c2:
            status_callout(f"<strong>Top revenue:</strong> {html.escape(str(top_r['PRODUCT_CATEGORY']))} — "
                           f"<strong>€{top_r['REVENUE']:,.0f}</strong> ({top_r['MARGIN_PCT']:.1f}% margin)",
                           "warn" if float(top_r["MARGIN_PCT"]) < 15 else "info", "!")

        # SKU detail — collapsed by default
        if not top_prod_f.empty:
            with st.expander("🔍 SKU Detail — top products by revenue & margin"):
                top_agg = (
                    top_prod_f.groupby(["PRODUCT_ID", "PRODUCT_NAME", "CATEGORY"], as_index=False)
                    .agg(REVENUE=("REVENUE", "sum"), UNITS=("UNITS", "sum"), COST=("COST", "sum"))
                )
                top_agg["MARGIN_PCT"] = (
                    (top_agg["REVENUE"] - top_agg["COST"]) * 100.0
                    / top_agg["REVENUE"].replace(0, float("nan"))
                ).round(2)

                d1, d2 = st.columns(2)
                with d1:
                    st.markdown("**By Revenue**")
                    top_rev = top_agg.sort_values("REVENUE", ascending=False).head(10)
                    figr = px.bar(
                        top_rev.sort_values("REVENUE"),
                        x="REVENUE", y="PRODUCT_NAME", orientation="h",
                        color="MARGIN_PCT", color_continuous_scale="RdYlGn",
                        labels={"REVENUE": "Revenue (€)", "PRODUCT_NAME": "",
                                "MARGIN_PCT": "Margin %"},
                        text_auto=".2s",
                    )
                    chart_layout(figr, height=360, hovermode="closest")
                    figr.update_layout(coloraxis_showscale=False, showlegend=False)
                    st.plotly_chart(figr, use_container_width=True)

                with d2:
                    st.markdown("**By Margin % (above median revenue SKUs)**")
                    rev_floor = top_agg["REVENUE"].median()
                    top_marg  = (top_agg[top_agg["REVENUE"] >= rev_floor]
                                 .sort_values("MARGIN_PCT", ascending=False).head(10))
                    figm = px.bar(
                        top_marg.sort_values("MARGIN_PCT"),
                        x="MARGIN_PCT", y="PRODUCT_NAME", orientation="h",
                        color="MARGIN_PCT", color_continuous_scale="RdYlGn",
                        labels={"MARGIN_PCT": "Margin %", "PRODUCT_NAME": ""},
                        text_auto=".1f",
                    )
                    chart_layout(figm, height=360, hovermode="closest")
                    figm.update_layout(coloraxis_showscale=False, showlegend=False)
                    st.plotly_chart(figm, use_container_width=True)

                st.divider()
                cats = sorted(top_agg["CATEGORY"].dropna().unique().tolist())
                if cats:
                    cat_sel = st.selectbox("Drill-down by category", options=cats)
                    drill = (top_agg[top_agg["CATEGORY"] == cat_sel]
                             .sort_values("REVENUE", ascending=False).head(20))
                    if not drill.empty:
                        st.dataframe(
                            drill[["PRODUCT_NAME", "REVENUE", "UNITS", "MARGIN_PCT"]].rename(columns={
                                "PRODUCT_NAME": "Product", "REVENUE": "Revenue (€)",
                                "UNITS": "Units",          "MARGIN_PCT": "Margin %",
                            }),
                            use_container_width=True,
                        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Operations
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    col_a, col_b = st.columns([3, 2])

    with col_a:
        if fill_f.empty:
            st.info("No data for selected period.")
        else:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=fill_f["YEAR_MONTH"], y=fill_f["FILL_RATE_PCT"],
                mode="lines+markers+text", name="Fill Rate",
                line=dict(color=ACCENT_COLOR, width=2.5),
                marker=dict(size=7),
                text=[f"{v:.1f}%" for v in fill_f["FILL_RATE_PCT"]],
                textposition="top center",
                textfont=dict(size=10, color="#475569"),
                hovertemplate="<b>%{x}</b><br>Fill rate: %{y:.2f}%<extra></extra>",
            ))
            fig.add_hline(y=95, line_dash="dash", line_color=BAD_COLOR,
                          annotation_text="95% target",
                          annotation_position="bottom right")
            fmin = float(fill_f["FILL_RATE_PCT"].min())
            chart_layout(fig, height=380)
            fig.update_yaxes(
                title="Fill Rate (%)",
                range=[min(94, fmin - 1), 100.5],
            )
            with st.container():
                section_header(
                    "Fill rate — availability",
                    "Units delivered ÷ demanded, incl. stockout demand. Target ≥ 95%.",
                )
                st.plotly_chart(fig, use_container_width=True)

    with col_b:
        if stk_cat.empty:
            st.info("No data.")
        else:
            figc = px.bar(
                stk_cat.sort_values("QTY_UNMET"),
                x="QTY_UNMET", y="PRODUCT_CATEGORY",
                orientation="h", color="QTY_UNMET",
                color_continuous_scale="Reds",
                labels={"QTY_UNMET": "Units unmet", "PRODUCT_CATEGORY": ""},
                text_auto=".2s",
            )
            chart_layout(figc, height=380, hovermode="closest")
            figc.update_layout(coloraxis_showscale=False, showlegend=False)
            with st.container():
                section_header(
                    "Stockouts by category",
                    "Units unmet for the selected period.",
                )
                st.plotly_chart(figc, use_container_width=True)

    # Detail sections — collapsed
    if not stk_mes_f.empty:
        with st.expander("📋 Stockouts — monthly breakdown"):
            figs = go.Figure()
            figs.add_trace(go.Bar(
                x=stk_mes_f["YEAR_MONTH"], y=stk_mes_f["NUM_STOCKOUTS"],
                name="# Stockouts", marker_color=ACCENT_COLOR,
            ))
            figs.add_trace(go.Scatter(
                x=stk_mes_f["YEAR_MONTH"], y=stk_mes_f["QTY_UNMET"],
                name="Units unmet", yaxis="y2",
                mode="lines+markers", line=dict(color=WARN_COLOR, width=2),
            ))
            figs.update_layout(
                yaxis=dict(title="# Stockouts"),
                yaxis2=dict(title="Units unmet", overlaying="y", side="right", showgrid=False),
            )
            chart_layout(figs, height=360)
            st.plotly_chart(figs, use_container_width=True)

    if not movs_f.empty:
        with st.expander("📋 Stock Movements — IN / OUT / TRANSFER by month"):
            figm = px.bar(
                movs_f, x="YEAR_MONTH", y="NUM_MOVEMENTS",
                color="MOVEMENT_TYPE", barmode="group",
                color_discrete_map={"IN": ACCENT_COLOR, "OUT": BAD_COLOR, "TRANSFER": WARN_COLOR},
                labels={"NUM_MOVEMENTS": "Movements", "YEAR_MONTH": "",
                        "MOVEMENT_TYPE": "Type"},
            )
            chart_layout(figm, height=360)
            st.plotly_chart(figm, use_container_width=True)

    # ── Supplier Scorecard ────────────────────────────────────────────────────
    if not supplier_perf.empty:
        with st.expander("🏭 Supplier Scorecard — OTIF, lead time, fill rate"):
            sup = supplier_perf.copy()
            sup.columns = [c.upper() for c in sup.columns]

            sc1, sc2 = st.columns(2)
            with sc1:
                fig_otif = px.bar(
                    sup.sort_values("OTIF_RATE"),
                    x="OTIF_RATE", y="SUPPLIER_NAME", orientation="h",
                    color="OTIF_RATE",
                    color_continuous_scale="RdYlGn",
                    range_color=[0.5, 1.0],
                    labels={"OTIF_RATE": "OTIF rate", "SUPPLIER_NAME": ""},
                    text_auto=".1%",
                )
                chart_layout(fig_otif, height=420, hovermode="closest")
                fig_otif.update_layout(coloraxis_showscale=False)
                with st.container():
                    section_header("OTIF by supplier", "On-Time In-Full: delivered ≤ promised date AND ≥95% units.")
                    st.plotly_chart(fig_otif, use_container_width=True)

            with sc2:
                fig_lead = px.scatter(
                    sup,
                    x="AVG_LEAD_TIME_PROMISED", y="AVG_LEAD_TIME_ACTUAL",
                    size="TOTAL_POS", color="OTIF_RATE",
                    color_continuous_scale="RdYlGn",
                    range_color=[0.5, 1.0],
                    hover_name="SUPPLIER_NAME",
                    labels={
                        "AVG_LEAD_TIME_PROMISED": "Promised lead time (days)",
                        "AVG_LEAD_TIME_ACTUAL":   "Actual lead time (days)",
                        "OTIF_RATE": "OTIF",
                        "TOTAL_POS": "# POs",
                    },
                    text="SUPPLIER_NAME",
                )
                fig_lead.update_traces(textposition="top center", textfont_size=9)
                # diagonal reference line
                if not sup.empty:
                    max_lt = max(sup["AVG_LEAD_TIME_PROMISED"].max(), sup["AVG_LEAD_TIME_ACTUAL"].max())
                    fig_lead.add_trace(go.Scatter(
                        x=[0, max_lt], y=[0, max_lt],
                        mode="lines", line=dict(dash="dash", color="#94a3b8", width=1),
                        showlegend=False,
                    ))
                chart_layout(fig_lead, height=420, hovermode="closest")
                fig_lead.update_layout(coloraxis_showscale=False)
                with st.container():
                    section_header(
                        "Promised vs. actual lead time",
                        "Points above the diagonal arrive late. Size = number of POs.",
                    )
                    st.plotly_chart(fig_lead, use_container_width=True)

    # ── DC SLA ────────────────────────────────────────────────────────────────
    if not dc_sla.empty:
        with st.expander("🏗️ Distribution Center SLA — on-time delivery by DC"):
            dc = dc_sla.copy()
            dc.columns = [c.upper() for c in dc.columns]

            d1, d2 = st.columns(2)
            with d1:
                fig_dc = px.bar(
                    dc.sort_values("ON_TIME_RATE"),
                    x="ON_TIME_RATE", y="DC_ID", orientation="h",
                    color="ON_TIME_RATE",
                    color_continuous_scale="RdYlGn",
                    range_color=[0.7, 1.0],
                    labels={"ON_TIME_RATE": "On-time rate", "DC_ID": ""},
                    text_auto=".1%",
                )
                chart_layout(fig_dc, height=300, hovermode="closest")
                fig_dc.update_layout(coloraxis_showscale=False)
                with st.container():
                    section_header("On-time rate by DC", "Deliveries where actual ≤ estimated delivery date.")
                    st.plotly_chart(fig_dc, use_container_width=True)

            with d2:
                dc["PCT_ON_TIME"] = (dc["ON_TIME_RATE"] * 100).round(1)
                st.dataframe(
                    dc[["DC_ID", "TOTAL_ENTREGAS", "PCT_ON_TIME",
                        "AVG_DELAY_DAYS_WHEN_LATE", "AVG_TRANSIT_DAYS"]].rename(columns={
                        "DC_ID": "DC", "TOTAL_ENTREGAS": "Deliveries",
                        "PCT_ON_TIME": "On-time %",
                        "AVG_DELAY_DAYS_WHEN_LATE": "Avg delay (days)",
                        "AVG_TRANSIT_DAYS": "Avg transit (days)",
                    }),
                    use_container_width=True,
                )


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Store ops (store-manager cockpit)
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    # ── KPI row ──────────────────────────────────────────────────────────────
    peak_hour, peak_pct = "—", 0.0
    if not hora.empty:
        ph = hora.loc[hora["NUM_PEDIDOS"].idxmax()]
        peak_hour = f"{int(ph['ORDER_HOUR']):02d}:00"
        peak_pct = float(ph["PCT_PEDIDOS"])

    merm_cost  = mermas_f["LOST_COST"].sum()    if not mermas_f.empty else 0
    merm_units = mermas_f["UNITS_WASTED"].sum() if not mermas_f.empty else 0

    if not store_day_f.empty:
        _u  = store_day_f["UNITS_SOLD"].sum()
        _um = store_day_f["UNMET_UNITS"].sum()
        store_fill   = _u / (_u + _um) * 100 if (_u + _um) else 0
        ruptura_dias = int(store_day_f["RUPTURA_DIAS"].sum())
    else:
        store_fill, ruptura_dias = 0, 0

    sk = st.columns(4, gap="medium")
    sk[0].metric("Peak hour", peak_hour,
                 delta=f"{peak_pct:.1f}% of orders", delta_color="off")
    sk[1].metric("Waste (period)", fmt_compact(merm_cost, "€"),
                 delta=f"{merm_units:,.0f} units lost", delta_color="off")
    sk[2].metric("Store fill rate", f"{store_fill:.2f}%")
    sk[3].metric("Store-days w/ stockout", f"{ruptura_dias:,}")

    st.divider()

    # ── Hora punta — sales by hour of day ────────────────────────────────────
    if not hora.empty:
        hora_s = hora.sort_values("ORDER_HOUR")
        hmax = float(hora_s["NUM_PEDIDOS"].max())
        bar_cols = [
            ACCENT_COLOR if v >= hmax * 0.9 else f"rgba({ACCENT_RGBA}, 0.45)"
            for v in hora_s["NUM_PEDIDOS"]
        ]
        figh = go.Figure(go.Bar(
            x=[f"{int(h):02d}h" for h in hora_s["ORDER_HOUR"]],
            y=hora_s["NUM_PEDIDOS"],
            marker_color=bar_cols,
            hovertemplate="<b>%{x}</b><br>Orders: %{y:,}<extra></extra>",
        ))
        chart_layout(figh, height=330, showlegend=False)
        figh.update_yaxes(title="Orders", range=[0, hmax * 1.12])
        with st.container():
            section_header(
                "Sales by hour — peak hours (hora punta)",
                "All-period order distribution by hour. Darker bars = peak demand → checkout & staffing sizing.",
            )
            st.plotly_chart(figh, use_container_width=True)

    # ── Waste by category  +  lowest-availability stores ─────────────────────
    col_a, col_b = st.columns(2)

    with col_a:
        if mermas_f.empty:
            st.info("No waste data for selected period.")
        else:
            merm_cat = (
                mermas_f.groupby("PRODUCT_CATEGORY", as_index=False)
                .agg(LOST_COST=("LOST_COST", "sum"), UNITS=("UNITS_WASTED", "sum"))
                .sort_values("LOST_COST", ascending=False).head(12)
            )
            figw = px.bar(
                merm_cat.sort_values("LOST_COST"),
                x="LOST_COST", y="PRODUCT_CATEGORY", orientation="h",
                color="LOST_COST", color_continuous_scale="Reds",
                labels={"LOST_COST": "Lost cost (€)", "PRODUCT_CATEGORY": ""},
                text_auto=".2s",
            )
            chart_layout(figw, height=400, hovermode="closest")
            figw.update_layout(coloraxis_showscale=False)
            with st.container():
                section_header(
                    "Waste by category (mermas / caducidad)",
                    "Perishable shrink — expired stock booked as a real inventory write-off.",
                )
                st.plotly_chart(figw, use_container_width=True)

    with col_b:
        if store_day_f.empty:
            st.info("No store data for selected period.")
        else:
            st_agg = (
                store_day_f.groupby("STORE_ID", as_index=False)
                .agg(UNITS=("UNITS_SOLD", "sum"), UNMET=("UNMET_UNITS", "sum"),
                     RUPT=("RUPTURA_DIAS", "sum"), GMV=("GMV_GROSS", "sum"))
            )
            st_agg["FILL"] = (
                st_agg["UNITS"] * 100.0
                / (st_agg["UNITS"] + st_agg["UNMET"]).replace(0, float("nan"))
            ).round(2)
            worst = st_agg.sort_values("FILL").head(12)
            figs = px.bar(
                worst.sort_values("FILL", ascending=False),
                x="FILL", y="STORE_ID", orientation="h",
                color="FILL", color_continuous_scale="RdYlGn",
                range_color=[float(worst["FILL"].min()) - 0.5, 100],
                labels={"FILL": "Fill rate %", "STORE_ID": ""},
            )
            chart_layout(figs, height=400, hovermode="closest")
            figs.update_layout(coloraxis_showscale=False)
            with st.container():
                section_header(
                    "Lowest-availability stores",
                    "Bottom stores by fill rate (units sold ÷ demanded) — replenishment focus.",
                )
                st.plotly_chart(figs, use_container_width=True)

    # ── Waste trend + insight ────────────────────────────────────────────────
    if not mermas_f.empty:
        with st.expander("📋 Waste trend — store vs DC by month"):
            merm_trend = (
                mermas_f.groupby(["YEAR_MONTH", "LOCATION_TYPE"], as_index=False)
                .agg(LOST_COST=("LOST_COST", "sum"))
            )
            figmt = px.bar(
                merm_trend, x="YEAR_MONTH", y="LOST_COST",
                color="LOCATION_TYPE", barmode="stack",
                color_discrete_map={"STORE": ACCENT_COLOR, "DC": WARN_COLOR},
                labels={"LOST_COST": "Lost cost (€)", "YEAR_MONTH": "",
                        "LOCATION_TYPE": "Location"},
            )
            chart_layout(figmt, height=340)
            st.plotly_chart(figmt, use_container_width=True)

        top_cat = merm_cat.iloc[0]
        status_callout(
            f"<strong>{html.escape(str(top_cat['PRODUCT_CATEGORY']))}</strong> is the largest source of "
            f"waste — <strong>€{top_cat['LOST_COST']:,.0f}</strong> ({top_cat['UNITS']:,.0f} units). "
            "Tighten ordering and rotation on short-shelf-life lines.",
            "warn", "!",
        )


# ════════════════════════════════════════════════════════════════════════════
# TAB 5 — Customers
# ════════════════════════════════════════════════════════════════════════════
with tab5:
    st.caption("Accumulated view — period filter does not apply to RFM / churn / cohort models.")
    col_a, col_b = st.columns(2)

    with col_a:
        if rfm.empty:
            st.info("No data.")
        else:
            rfm_disp = rfm.copy()
            rfm_disp.columns = [c.upper() for c in rfm_disp.columns]
            _ord_map = {lbl: i for i, lbl in enumerate(_RFM_ORDER)}
            rfm_disp["_ord"] = rfm_disp["RFM_LABEL"].map(lambda x: _ord_map.get(x, 99))
            rfm_disp = rfm_disp.sort_values("_ord", ascending=False)

            fig = px.bar(
                rfm_disp,
                x="NUM_CUSTOMERS", y="RFM_LABEL",
                orientation="h",
                color="AVG_MONETARY",
                color_continuous_scale="Blues",
                labels={"RFM_LABEL": "", "NUM_CUSTOMERS": "Customers",
                        "AVG_MONETARY": "Avg Spend (€)"},
                text_auto=True,
            )
            chart_layout(fig, height=380, hovermode="closest")
            with st.container():
                section_header(
                    "RFM segmentation",
                    "Customers per segment. Colour = avg historical spend.",
                )
                st.plotly_chart(fig, use_container_width=True)

            high_value = rfm_disp[rfm_disp["RFM_LABEL"].isin(["Champions", "Loyal Customers"])]["NUM_CUSTOMERS"].sum()
            total_cust = rfm_disp["NUM_CUSTOMERS"].sum()
            pct_hv = high_value / total_cust * 100 if total_cust else 0
            status_callout(f"<strong>{pct_hv:.0f}%</strong> of customers are Champions or Loyal — "
                           "the highest-LTV segments.", "info", "★")

    with col_b:
        if churn.empty:
            st.info("No data.")
        else:
            churned = int(churn["CHURNED"][0])
            active  = int(churn["TOTAL"][0]) - churned

            fig2 = go.Figure(go.Pie(
                labels=["Active", "Churned (>60d)"],
                values=[active, churned],
                hole=0.55,
                marker_colors=[ACCENT_COLOR, BAD_COLOR],
                textinfo="percent+label",
                hovertemplate="%{label}: %{value:,}<extra></extra>",
            ))
            fig2.add_annotation(
                text=(f"{churn_rate:.1f}%<br>"
                      "<span style='font-size:11px;color:#64748b'>churn</span>"),
                x=0.5, y=0.5, showarrow=False, font_size=22, align="center",
            )
            fig2.update_layout(showlegend=True)
            chart_layout(fig2, height=380, hovermode="closest")
            with st.container():
                section_header(
                    "Churn — 60-day inactivity",
                    "Customers with no purchase in the last 60 days.",
                )
                st.plotly_chart(fig2, use_container_width=True)

            status_callout(f"<strong>{churned:,}</strong> customers inactive >60 days "
                           f"({churn_rate:.1f}% churn). "
                           f"<strong>{active:,}</strong> remain active.",
                           "good" if churn_rate <= 20 else "warn", "✓" if churn_rate <= 20 else "!")

    # ── Churn by segment + LTV by segment ────────────────────────────────────
    row2a, row2b = st.columns(2)

    with row2a:
        if not churn_detail.empty:
            cd = churn_detail.copy()
            cd.columns = [c.upper() for c in cd.columns]
            seg_order = ["Bronze", "Silver", "Gold", "Platinum"]
            cd["_ord"] = cd["SEGMENT"].map({s: i for i, s in enumerate(seg_order)})
            cd = cd.sort_values("_ord")

            fig_cd = px.bar(
                cd, x="SEGMENT", y="CHURN_RATE",
                color="CHURN_RATE",
                color_continuous_scale="RdYlGn_r",
                range_color=[0, 30],
                labels={"CHURN_RATE": "Churn rate (%)", "SEGMENT": ""},
                text_auto=".1f",
            )
            fig_cd.update_traces(texttemplate="%{y:.1f}%", textposition="outside")
            chart_layout(fig_cd, height=340, hovermode="closest")
            fig_cd.update_layout(coloraxis_showscale=False)
            with st.container():
                section_header(
                    "Churn rate by segment",
                    "Higher churn in lower-value segments is the expected pattern.",
                )
                st.plotly_chart(fig_cd, use_container_width=True)

    with row2b:
        if not ltv_segs.empty:
            lt = ltv_segs.copy()
            lt.columns = [c.upper() for c in lt.columns]
            lt["_ord"] = lt["SEGMENT"].map({s: i for i, s in enumerate(seg_order)})
            lt = lt.sort_values("_ord")

            fig_ltv = px.bar(
                lt, x="SEGMENT", y="AVG_LTV",
                color="AVG_LTV",
                color_continuous_scale="Blues",
                labels={"AVG_LTV": "Avg LTV (€)", "SEGMENT": ""},
                text_auto=".0f",
            )
            fig_ltv.update_traces(texttemplate="€%{y:,.0f}", textposition="outside")
            chart_layout(fig_ltv, height=340, hovermode="closest")
            fig_ltv.update_layout(coloraxis_showscale=False)
            with st.container():
                section_header(
                    "Avg lifetime revenue by segment",
                    "Historical revenue per customer (LTV = total gross spend over 2 years).",
                )
                st.plotly_chart(fig_ltv, use_container_width=True)

    # ── Cohort retention heatmap ──────────────────────────────────────────────
    if not cohort.empty:
        with st.expander("📋 Cohort retention — monthly reactivation by acquisition cohort"):
            coh = cohort.copy()
            coh.columns = [c.upper() for c in coh.columns]

            cohort_pivot = coh.pivot(
                index="COHORT_MONTH", columns="ACTIVITY_MONTH", values="RETENTION_PCT"
            )
            fig_hm = px.imshow(
                cohort_pivot,
                color_continuous_scale="Blues",
                labels={"x": "Activity month", "y": "Cohort", "color": "Retention %"},
                aspect="auto",
                text_auto=".0f",
            )
            fig_hm.update_traces(textfont_size=9)
            chart_layout(fig_hm, height=500, hovermode="closest")
            with st.container():
                section_header(
                    "Cohort retention heatmap",
                    "Rows = acquisition cohort (registration month). "
                    "Columns = activity month. Cell = % of cohort still active.",
                )
                st.plotly_chart(fig_hm, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 6 — Finance
# ════════════════════════════════════════════════════════════════════════════
with tab6:
    receita_bruta = gmv_f["GMV_GROSS"].sum() if (not gmv_f.empty and "GMV_GROSS" in gmv_f.columns) else 0
    iva_tot       = iva_f["CUOTA_IVA"].sum() if not iva_f.empty else 0
    cogs          = margem_f["COST"].sum()   if not margem_f.empty else 0
    margem_bruta  = receita_bruta - iva_tot - cogs

    if receita_bruta == 0 and cogs == 0:
        st.info("No data for selected period.")
    else:
        figw = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute", "relative", "relative", "total"],
            x=["Gross Revenue", "− IVA", "− COGS", "Gross Margin"],
            y=[receita_bruta, -iva_tot, -cogs, margem_bruta],
            connector={"line": {"color": "#cbd5e1"}},
            increasing={"marker": {"color": ACCENT_COLOR}},
            decreasing={"marker": {"color": BAD_COLOR}},
            totals={"marker":    {"color": WARN_COLOR}},
            text=[f"€{receita_bruta:,.0f}", f"−€{iva_tot:,.0f}",
                  f"−€{cogs:,.0f}", f"€{margem_bruta:,.0f}"],
            textposition="outside",
        ))
        chart_layout(figw, height=420, showlegend=False, hovermode="closest")
        figw.update_yaxes(title="€")
        with st.container():
            section_header(
                "P&L — selected period",
                "Gross revenue − IVA − COGS = gross margin.",
            )
            st.plotly_chart(figw, use_container_width=True)

        margem_pct = (margem_bruta / (receita_bruta - iva_tot) * 100) if (receita_bruta - iva_tot) else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Gross Revenue", f"€{receita_bruta:,.0f}")
        m2.metric("IVA collected",  f"€{iva_tot:,.0f}", delta="remitted to state", delta_color="off")
        m3.metric("Gross Margin",   f"€{margem_bruta:,.0f}",
                  delta=f"{margem_pct:.0f}% of net revenue")

        st.caption("IVA rates: S1 21% (general) · S2 10% (food) · S4 4% (essentials). "
                   "OPEX (payroll, marketing, logistics) is out of scope.")

    with st.expander("📋 IVA detail — monthly breakdown by type"):
        if iva_f.empty:
            st.info("No data for selected period.")
        else:
            fig2 = px.bar(
                iva_f, x="YEAR_MONTH", y="CUOTA_IVA",
                color="IVA_TYPE", barmode="stack",
                color_discrete_sequence=px.colors.qualitative.Set2,
                labels={"CUOTA_IVA": "IVA collected (€)", "YEAR_MONTH": "",
                        "IVA_TYPE": "IVA type"},
            )
            chart_layout(fig2, height=360)
            st.plotly_chart(fig2, use_container_width=True)

            iva_display = iva_f[
                ["IVA_TYPE", "YEAR_MONTH", "BASE_IMPONIBLE", "CUOTA_IVA", "TOTAL_COM_IVA"]
            ].rename(columns={
                "IVA_TYPE": "Type", "YEAR_MONTH": "Month",
                "BASE_IMPONIBLE": "Base imponible (€)", "CUOTA_IVA": "Cuota IVA (€)",
                "TOTAL_COM_IVA": "Total con IVA (€)",
            })
            st.dataframe(iva_display, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 7 — FinOps
# ════════════════════════════════════════════════════════════════════════════
with tab7:
    if finops.empty:
        st.info(
            "No metering data available for the last 14 days. "
            "This can happen if the runtime role lacks MONITOR privilege on the warehouse, "
            "or if no warehouse activity occurred in this window."
        )
    else:
        # Normalise column names (Snowpark returns uppercase)
        fo = finops.copy()
        fo.columns = [c.upper() for c in fo.columns]

        # ── KPI row ──────────────────────────────────────────────────────────
        total_credits  = float(fo["CREDITS_USED"].sum())
        total_cost_usd = float(fo["EST_COST_USD"].sum())
        warehouses     = fo["WAREHOUSE_NAME"].nunique()
        active_days    = fo["USAGE_DAY"].nunique()

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Credits (14d)",    f"{total_credits:.4f}")
        k2.metric("Est. Cost USD (14d)",    f"${total_cost_usd:.2f}",
                  delta="@ $2.00/credit (illustrative)", delta_color="off")
        k3.metric("Warehouses Active",      str(warehouses))
        k4.metric("Days with Activity",     str(active_days))

        st.divider()

        # ── Daily credits bar chart ───────────────────────────────────────────
        # Aggregate across warehouses per day for a total-cost view,
        # then break out by warehouse as colour series.
        col_chart, col_table = st.columns([3, 2])

        with col_chart:
            # Ensure USAGE_DAY is string-sortable (cast to date string)
            fo["USAGE_DAY_STR"] = fo["USAGE_DAY"].astype(str).str[:10]

            fig_fo = px.bar(
                fo.sort_values("USAGE_DAY_STR"),
                x="USAGE_DAY_STR",
                y="CREDITS_USED",
                color="WAREHOUSE_NAME",
                barmode="stack",
                labels={
                    "USAGE_DAY_STR":   "Day",
                    "CREDITS_USED":    "Credits used",
                    "WAREHOUSE_NAME":  "Warehouse",
                },
                color_discrete_sequence=[ACCENT_COLOR, WARN_COLOR, BAD_COLOR, MUTED_COLOR],
                text_auto=".4f",
            )
            chart_layout(fig_fo, height=420)
            fig_fo.update_xaxes(title="Date")
            fig_fo.update_yaxes(title="Credits")
            with st.container():
                section_header(
                    "Credits consumed per day",
                    (
                        "Last 14 days, stacked by warehouse. "
                        "Cost estimate uses $2.00 USD/credit."
                    ),
                )
                st.plotly_chart(fig_fo, use_container_width=True)

        with col_table:
            # Summary table: one row per warehouse
            wh_summary = (
                fo.groupby("WAREHOUSE_NAME", as_index=False)
                .agg(
                    CREDITS_USED=("CREDITS_USED", "sum"),
                    CREDITS_COMPUTE=("CREDITS_COMPUTE", "sum"),
                    CREDITS_CLOUD_SERVICES=("CREDITS_CLOUD_SERVICES", "sum"),
                    EST_COST_USD=("EST_COST_USD", "sum"),
                )
                .sort_values("CREDITS_USED", ascending=False)
            )
            wh_summary["CREDITS_USED"]    = wh_summary["CREDITS_USED"].round(4)
            wh_summary["CREDITS_COMPUTE"] = wh_summary["CREDITS_COMPUTE"].round(4)
            wh_summary["EST_COST_USD"]    = wh_summary["EST_COST_USD"].round(2)
            wh_summary["PCT"] = (
                wh_summary["CREDITS_USED"] * 100.0
                / max(float(wh_summary["CREDITS_USED"].sum()), 1e-9)
            ).round(1).astype(str) + " %"

            display_cols = {
                "WAREHOUSE_NAME":   "Warehouse",
                "CREDITS_USED":     "Credits",
                "CREDITS_COMPUTE":  "Compute Cr.",
                "EST_COST_USD":     "Est. USD",
                "PCT":              "% of total",
            }
            # Use plain st.dataframe — legacy Streamlit-in-Snowflake does not
            # support st.column_config
            with st.container():
                section_header(
                    "Credits & cost per warehouse",
                    "CLOUD_SERVICES_ONLY represents serverless cloud-services usage.",
                )
                st.dataframe(
                    wh_summary[list(display_cols.keys())].rename(columns=display_cols),
                    use_container_width=True,
                )

        # ── Insight callout ──────────────────────────────────────────────────
        top_wh = wh_summary.iloc[0]
        status_callout(
            f"<strong>{html.escape(str(top_wh['WAREHOUSE_NAME']))}</strong> accounts for "
            f"<strong>{top_wh['PCT']}</strong> of credits consumed in the last 14 days "
            f"({top_wh['CREDITS_USED']:.4f} credits ≈ "
            f"<strong>${top_wh['EST_COST_USD']:.2f}</strong> at $2.00/credit). "
            "Enable auto-suspend (60–120 s) and right-size the warehouse to cut idle spend.",
            "warn",
            "!",
        )

        # ── Raw detail — collapsed ────────────────────────────────────────────
        with st.expander("📋 Raw daily metering detail"):
            raw_disp = fo[["WAREHOUSE_NAME", "USAGE_DAY_STR", "CREDITS_USED",
                           "CREDITS_COMPUTE", "CREDITS_CLOUD_SERVICES", "EST_COST_USD"]].rename(columns={
                "WAREHOUSE_NAME":         "Warehouse",
                "USAGE_DAY_STR":          "Day",
                "CREDITS_USED":           "Credits total",
                "CREDITS_COMPUTE":        "Credits compute",
                "CREDITS_CLOUD_SERVICES": "Credits cloud svc",
                "EST_COST_USD":           "Est. USD",
            })
            st.dataframe(raw_disp, use_container_width=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "RetailGuard · Data Engineering Portfolio · Snowflake + dbt + Streamlit"
)
