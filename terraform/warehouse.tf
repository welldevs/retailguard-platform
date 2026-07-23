resource "snowflake_warehouse" "retail" {
  name                = "RETAIL_WH_XS"
  warehouse_size      = var.warehouse_size
  auto_suspend        = 60
  auto_resume         = true
  initially_suspended = true
  comment             = "Dedicated virtual warehouse for retail workloads (dbt + Streamlit + ad-hoc SQL)."
}
