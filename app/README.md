# Executive Decision Platform (Streamlit)

Camada de **Serving** da plataforma. Multipage, modular, lê **exclusivamente os
MARTS** do dbt (read-only). O Core (ERP → RAW → dbt → MARTS) está **congelado**:
esta app **não** recalcula KPI, não repete regra de negócio e não faz joins para
substituir MART. Toda lógica permanece no dbt.

## Rodar

```bash
make setup        # deps (inclui streamlit >= 1.36 para st.navigation)
make build        # dbt build → MARTS no DuckDB (main_marts)
make platform     # streamlit run app/main.py → http://localhost:8501
```

Fonte de dados por variável de ambiente:

```bash
DUCKDB_PATH=/path/retail.duckdb MARTS_SCHEMA=main_marts make platform
```

Para rodar como **Streamlit-in-Snowflake** no futuro: trocar `get_connection()` em
`services/connection.py` por `get_active_session()` e `MARTS_SCHEMA=MARTS`. Nenhuma
página muda.

## Estrutura

```
app/
├── main.py            # router: st.navigation + filtro global de período
├── services/          # conexão (1 lugar) e load_mart (único SQL: SELECT * FROM mart)
├── layout/            # tema/CSS e page_header
├── components/        # kpi_row, table, limitations, safe (resiliência)
├── charts/            # wrappers de gráficos nativos (line, bar)
├── utils/             # formatação (€, %, nº) e filtro de período
├── pages/             # 8 páginas, cada uma expõe render()
└── TODO.md            # limitações arquiteturais (KPIs sem MART direto)
```

## Navegação

| Seção | Página | Público |
|---|---|---|
| Strategy | 🎯 Executive Cockpit | CEO/COO/CFO |
| Growth | 📈 Revenue & Profit · 👥 Customer Intelligence | Comercial · CRM |
| Operations | 🔗 Supply Chain · 📦 Inventory & Stock · 🏪 Store Operations | Supply · Estoque · Lojas |
| Governance | 💳 Finance · 🛡️ Platform Health | CFO · Data Eng |

## Política presentation-only

- ✅ Permitido: `SELECT * FROM mart`, `SUM`/`COUNT`/`AVG` de medida **aditiva**,
  valor do **último mês**, filtro, ordenação, pivot de exibição.
- ❌ Proibido (→ registrado em `TODO.md`, nunca em Python): dividir dois agregados
  para formar um ratio (margem %, fill rate ponderado, churn %, OTIF), rejuntar
  marts para substituir um MART, reimplementar qualquer regra do dbt.
