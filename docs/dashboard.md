# Serving — Executive Decision Platform

The serving layer is the **Executive Decision Platform** in [`app/`](../app/) — a **Streamlit
multipage** application that reads **only** the curated `MARTS` (Gold) layer built by dbt. It is a
**presentation layer**: it never recomputes a KPI, never re-derives a metric, and never joins marts to
substitute a mart. All business logic stays in dbt. Run it locally with `make platform`
(→ http://localhost:8501).

> The Snowflake-native deployment of the same idea lives in
> [`snowflake/streamlit_app.py`](../snowflake/streamlit_app.py) (uses `get_active_session()`), deployed
> via Terraform / `snow` CLI. It is being consolidated into `app/` (a vendor-neutral Snowflake
> connector for `app/` is on the roadmap).

## Navigation (8 pages, 4 sections)

| Section | Page | Público |
|---|---|---|
| **Strategy** | 🎯 Executive Cockpit | CEO / COO / CFO |
| **Growth** | 📈 Revenue & Profit · 👥 Customer Intelligence | Comercial · CRM / Growth |
| **Operations** | 🔗 Supply Chain · 📦 Inventory & Stock · 🏪 Store Operations | Supply · Estoque · Lojas |
| **Governance** | 💳 Finance · 🛡️ Platform Health | CFO / Fiscal · Data Eng |

## Pages, KPIs and their MARTS

| Page | MARTS consumidos | KPIs / visuais |
|---|---|---|
| 🎯 **Executive Cockpit** | `mart_gmv_mensal`, `budget_mensal`, `mart_fill_rate_mensal`, `mart_stockouts_mensal`, `mart_mermas`, `mart_iva_resumo`, `mart_ap_aging`, `mart_churn_60d`, `mart_customer_ltv` | 12 tiles headline + GMV realizado vs meta |
| 📈 **Revenue & Profit** | `mart_gmv_mensal`, `budget_mensal`, `mart_margem_por_categoria`, `mart_top_produtos` | GMV/ticket, GMV vs meta, receita por categoria, top SKUs |
| 👥 **Customer Intelligence** | `mart_rfm`, `mart_churn_60d`, `mart_customer_ltv`, `mart_customer_cohort` | RFM, clientes em risco, LTV, retenção por coorte (%) |
| 🔗 **Supply Chain** | `mart_supplier_performance`, `mart_dc_sla`, `mart_carrier_performance`, `mart_ap_aging` | OTIF por fornecedor, on-time DC/carrier, AP aging |
| 📦 **Inventory & Stock** | `mart_fill_rate_mensal`, `mart_stockouts_mensal`, `mart_stockouts_por_categoria`, `mart_stock_movements_mensal`, `mart_mermas` | Fill rate, ruptura (Pareto), movimentos, mermas |
| 🏪 **Store Operations** | `mart_store_day`, `mart_ventas_hora` | Ranking de lojas por GMV, hora-punta |
| 💳 **Finance** | `mart_margem_por_categoria`, `mart_iva_resumo`, `mart_ap_aging` | P&L (valores absolutos), IVA por alíquota, AP por bucket |
| 🛡️ **Platform Health** | catálogo dos MARTS + `mart_gmv_mensal` (cobertura) | 19/19 materializados, cobertura temporal, testes dbt |

## Design notes

- **Módulos:** `services/` (conexão + `load_mart`, o único SQL), `layout/` (tema), `components/`
  (kpi tiles, tabelas, `safe()`, `limitations()`), `charts/` (nativo), `utils/` (formatação, período),
  `pages/` (uma `render()` por página). Entrypoint `main.py` (`st.navigation`).
- **Leitura only:** `load_mart(name)` executa `SELECT * FROM <schema>."<mart>"` — cacheado
  (`@st.cache_data`); a conexão é cacheada (`@st.cache_resource`) e **read-only**.
- **Resiliência:** cada seção roda dentro de `safe()` — uma falha vira aviso, a página não quebra.
- **Gráficos nativos:** `st.line_chart` / `st.bar_chart` / `st.dataframe` / `st.metric` — sem plotly,
  gauges, 3D ou animações.
- **Filtro global de período** (`year_month`) na sidebar; aplica-se às páginas de grão mensal (marts por
  entidade usam a base completa).
- **Política presentation-only:** permitido `SUM`/`COUNT`/`AVG`/último-mês/filtro/ordenação de medidas
  do mart; **proibido** dividir dois agregados para formar um ratio, rejuntar marts, ou reimplementar
  regra do dbt. KPIs de ratio consolidado que não existem no grão de um mart (margem % total, GMV vs
  meta %, OTIF/churn consolidados) são **registrados como limitação** em [`app/TODO.md`](../app/TODO.md),
  nunca calculados em Python.

## Deploy (Snowflake)

O `snowflake/streamlit_app.py` é publicado pelo Snowflake CLI (só arquivos — credenciais via conexão
`retail`):

```bash
make deploy-streamlit          # snow streamlit deploy --connection retail
```

> Nunca embuta credenciais. A conexão `retail` / env vars fornecem os segredos.
