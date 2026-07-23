# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Tables — Declarative Streaming Marts
#
# These three snowflake_execute resources provision the DT_* dynamic tables in
# RETAIL_DB.MARTS.  Each table auto-refreshes within a 1-hour TARGET_LAG budget;
# Snowflake schedules and executes the refresh — no Airflow DAG or cron needed.
#
# IDEMPOTENCY: CREATE DYNAMIC TABLE IF NOT EXISTS means terraform apply is safe
# to run even after the tables have already been created live (e.g. via
# snowflake/sql/dynamic_tables.sql).  The execute statement becomes a no-op.
#
# SHOWCASE: estas DT_* são uma VITRINE de streaming declarativo nativo do
# Snowflake (auto-refresh sem orquestrador), NÃO a fonte do dashboard — o
# Streamlit lê MARTS.MART_* construídas pelo dbt (fonte única de verdade). Leem
# as MESMAS tabelas base RAW.* que o dbt, então demonstram marts auto-atualizáveis
# sobre a mesma fonte canônica.
#
# WAREHOUSE NOTE: The trial account uses COMPUTE_WH (RETAIL_WH_XS is commented
# out in ddl_raw.sql).  Switch WAREHOUSE = RETAIL_WH_XS once the warehouse
# is provisioned.
# ─────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# DT_GMV_MENSAL
# Grain: one row per calendar month.
# Columns: year_month, year, month, gmv_gross_header, gmv_gross, gmv_net,
#          num_pedidos, ticket_medio.
# gmv_net  = SUM(line_total_net)                          [already net after IVA]
# gmv_gross = SUM(line_total_net * (1 + sl.tax_rate))    [matches dbt mart]
# gmv_gross_header = SUM(SALES.total_gross) per month    [header-level cross-check]
# ──────────────────────────────────────────────────────────────────────────────
resource "snowflake_execute" "dt_gmv_mensal" {
  execute = <<-SQL
    CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_GMV_MENSAL
        TARGET_LAG     = '1 hour'
        WAREHOUSE      = COMPUTE_WH
        REFRESH_MODE   = AUTO
        INITIALIZE     = ON_CREATE
        COMMENT        = 'Dynamic Table: monthly GMV (gross + net) from base RAW tables. Auto-refreshes within 1 hour of source changes. Replaces the orchestrator-driven CREATE OR REPLACE pattern.'
    AS
    WITH sale_dates AS (
        SELECT
            sale_id,
            LEFT(order_date, 7)      AS year_month,
            total_gross              AS header_gross
        FROM RETAIL_DB.RAW.SALES
        WHERE order_date IS NOT NULL
    ),
    line_agg AS (
        SELECT
            sd.year_month,
            sl.sale_id,
            sl.line_total_net                                    AS line_net,
            sl.line_total_net * (1 + sl.tax_rate)               AS line_gross
        FROM RETAIL_DB.RAW.SALE_LINES sl
        JOIN sale_dates sd ON sl.sale_id = sd.sale_id
    ),
    header_agg AS (
        SELECT year_month, SUM(header_gross) AS sum_header_gross
        FROM sale_dates
        GROUP BY year_month
    )
    SELECT
        la.year_month,
        LEFT(la.year_month, 4)::NUMBER                                          AS year,
        SUBSTR(la.year_month, 6, 2)::NUMBER                                     AS month,
        CAST(ha.sum_header_gross              AS NUMBER(18,2))                  AS gmv_gross_header,
        CAST(SUM(la.line_gross)               AS NUMBER(18,2))                  AS gmv_gross,
        CAST(SUM(la.line_net)                 AS NUMBER(18,2))                  AS gmv_net,
        COUNT(DISTINCT la.sale_id)                                              AS num_pedidos,
        CAST(SUM(la.line_gross) / NULLIF(COUNT(DISTINCT la.sale_id), 0)
             AS NUMBER(14,2))                                                   AS ticket_medio
    FROM line_agg la
    JOIN header_agg ha ON la.year_month = ha.year_month
    GROUP BY la.year_month, ha.sum_header_gross
    ORDER BY la.year_month
  SQL

  revert     = "DROP DYNAMIC TABLE IF EXISTS RETAIL_DB.MARTS.DT_GMV_MENSAL"
  depends_on = [snowflake_schema.marts]
}


# ──────────────────────────────────────────────────────────────────────────────
# DT_MARGEM_POR_CATEGORIA
# Grain: year_month x product_category.
# Columns: year_month, year, month, product_category, revenue, cost,
#          gross_profit, margin_pct, total_units.
# revenue  = SUM(line_total_net)           [net after IVA and discounts]
# cost     = SUM(quantity_delivered * cost_price)
# PRODUCTS is deduped (known duplicate product_id rows in RAW).
# ──────────────────────────────────────────────────────────────────────────────
resource "snowflake_execute" "dt_margem_por_categoria" {
  execute = <<-SQL
    CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_MARGEM_POR_CATEGORIA
        TARGET_LAG     = '1 hour'
        WAREHOUSE      = COMPUTE_WH
        REFRESH_MODE   = AUTO
        INITIALIZE     = ON_CREATE
        COMMENT        = 'Dynamic Table: monthly margin by product category. Auto-refreshes within 1 hour. Replaces orchestrator-driven CREATE OR REPLACE.'
    AS
    WITH prod AS (
        SELECT *
        FROM RETAIL_DB.RAW.PRODUCTS
        QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY 1) = 1
    ),
    sale_dates AS (
        SELECT sale_id, LEFT(order_date, 7) AS year_month
        FROM RETAIL_DB.RAW.SALES
        WHERE order_date IS NOT NULL
    ),
    base AS (
        SELECT
            sd.year_month,
            p.category                                      AS product_category,
            sl.line_total_net                               AS net_rev,
            sl.quantity_delivered * p.cost_price            AS cost_line,
            sl.quantity_delivered                           AS units
        FROM RETAIL_DB.RAW.SALE_LINES sl
        JOIN sale_dates sd  ON sl.sale_id    = sd.sale_id
        JOIN prod p         ON sl.product_id = p.product_id
    )
    SELECT
        year_month,
        LEFT(year_month, 4)::NUMBER                                             AS year,
        SUBSTR(year_month, 6, 2)::NUMBER                                        AS month,
        product_category,
        CAST(SUM(net_rev)                    AS NUMBER(18,2))                   AS revenue,
        CAST(SUM(cost_line)                  AS NUMBER(18,2))                   AS cost,
        CAST(SUM(net_rev) - SUM(cost_line)   AS NUMBER(18,2))                   AS gross_profit,
        CAST((SUM(net_rev) - SUM(cost_line)) / NULLIF(SUM(net_rev), 0)
             AS NUMBER(8,4))                                                    AS margin_pct,
        SUM(units)                                                              AS total_units
    FROM base
    GROUP BY year_month, product_category
    ORDER BY year_month, revenue DESC
  SQL

  revert     = "DROP DYNAMIC TABLE IF EXISTS RETAIL_DB.MARTS.DT_MARGEM_POR_CATEGORIA"
  depends_on = [snowflake_schema.marts]
}


# ──────────────────────────────────────────────────────────────────────────────
# DT_TOP_PRODUTOS
# Grain: year_month x product_id.
# Columns: year_month, year, month, product_id, product_name, category,
#          revenue, units, cost, margin_pct.
# Same dedup + margin logic as DT_MARGEM_POR_CATEGORIA, at product grain.
# ──────────────────────────────────────────────────────────────────────────────
resource "snowflake_execute" "dt_top_produtos" {
  execute = <<-SQL
    CREATE DYNAMIC TABLE IF NOT EXISTS RETAIL_DB.MARTS.DT_TOP_PRODUTOS
        TARGET_LAG     = '1 hour'
        WAREHOUSE      = COMPUTE_WH
        REFRESH_MODE   = AUTO
        INITIALIZE     = ON_CREATE
        COMMENT        = 'Dynamic Table: monthly revenue, units, and margin per product. Auto-refreshes within 1 hour. Replaces orchestrator-driven CREATE OR REPLACE.'
    AS
    WITH prod AS (
        SELECT *
        FROM RETAIL_DB.RAW.PRODUCTS
        QUALIFY ROW_NUMBER() OVER (PARTITION BY product_id ORDER BY 1) = 1
    ),
    sale_dates AS (
        SELECT sale_id, LEFT(order_date, 7) AS year_month
        FROM RETAIL_DB.RAW.SALES
        WHERE order_date IS NOT NULL
    ),
    base AS (
        SELECT
            sd.year_month,
            sl.product_id,
            p.name                                          AS product_name,
            p.category,
            sl.line_total_net                               AS net_rev,
            sl.quantity_delivered * p.cost_price            AS cost_line,
            sl.quantity_delivered                           AS units
        FROM RETAIL_DB.RAW.SALE_LINES sl
        JOIN sale_dates sd  ON sl.sale_id    = sd.sale_id
        JOIN prod p         ON sl.product_id = p.product_id
    )
    SELECT
        year_month,
        LEFT(year_month, 4)::NUMBER                                             AS year,
        SUBSTR(year_month, 6, 2)::NUMBER                                        AS month,
        product_id,
        product_name,
        category,
        CAST(SUM(net_rev)                    AS NUMBER(18,2))                   AS revenue,
        SUM(units)                                                              AS units,
        CAST(SUM(cost_line)                  AS NUMBER(18,2))                   AS cost,
        CAST((SUM(net_rev) - SUM(cost_line)) / NULLIF(SUM(net_rev), 0)
             AS NUMBER(8,4))                                                    AS margin_pct
    FROM base
    GROUP BY year_month, product_id, product_name, category
    ORDER BY year_month, revenue DESC
  SQL

  revert     = "DROP DYNAMIC TABLE IF EXISTS RETAIL_DB.MARTS.DT_TOP_PRODUTOS"
  depends_on = [snowflake_schema.marts]
}
