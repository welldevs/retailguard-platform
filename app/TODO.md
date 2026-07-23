# TODOs & limitações arquiteturais — camada de Serving

Registro honesto de KPIs que **não existem diretamente em um MART** e que, por
decisão de arquitetura (lógica de negócio só no dbt), **não são recalculados em
Python** na camada de apresentação. Cada item é evidência para a recomendação do
`mart_executive_mensal`.

## Ratios consolidados ausentes (exigem `sum(numerador)/sum(denominador)`)

| # | KPI | Página(s) | MART base | Grão disponível | O que falta |
|---|-----|-----------|-----------|-----------------|-------------|
| 1 | Margem bruta % (total/mês) | Cockpit, Revenue, Finance | mart_margem_por_categoria | categoria × mês | % consolidado por mês |
| 2 | GMV vs meta (%) | Cockpit, Revenue | mart_gmv_mensal + budget_mensal | mês (2 marts) | attainment % em uma linha |
| 3 | OTIF consolidado (%) | Cockpit, Supply Chain | mart_supplier_performance | fornecedor | média ponderada por volume |
| 4 | Churn rate (%) | Cockpit, Customers | mart_churn_60d | cliente (flag) | taxa = churned/total |
| 5 | Fill rate consolidado por loja | Store Operations | mart_store_day | loja × dia | ponderação por unidades |

**Resolução recomendada:** um único MART aditivo `mart_executive_mensal` (uma linha
por `year_month`) que materialize no dbt: `gmv_gross`, `gmv_net`, `gmv_meta`,
`attainment_pct`, `gross_profit`, `revenue`, `gross_margin_pct`,
`fill_rate_stockout_pct` (ponderado), `perfect_order_pct`, `unmet_units`,
`lost_cost`, `iva_cuota`. Isso remove os itens 1, 2 e (parcial) 5, e elimina o join
`gmv+budget` repetido em 2 páginas. Itens 3 e 4 são de outro grão (fornecedor,
cliente) e seguem melhor em marts próprios se um dia forem necessários como número
único.

## Limitação estrutural (fora de escopo — exigiria alterar MARTS congelados)

- **Filtro global de canal (tienda/ecommerce):** os marts mensais são pré-agregados
  sem a coluna `channel`; um filtro cross-página exigiria adicionar `channel` a
  marts existentes (Core congelado). Não implementar sem autorização do dono do dbt.

## Serving / plataforma

- [ ] Adicionar caminho Snowflake em `services/connection.py`
  (`get_active_session()` + `MARTS_SCHEMA=MARTS`) para rodar como Streamlit-in-Snowflake.
- [ ] Filtros contextuais adicionais por página (região via `dim_store`, segmento
  via RFM) quando houver demanda.
