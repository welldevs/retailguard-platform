# ─────────────────────────────────────────────────────────────────────────────
# Streamlit in Snowflake — RETAIL_DASHBOARD
#
# The `snow streamlit deploy` command (Snowflake CLI) handles both the file
# upload (PUT to an internal stage) and object creation. This null_resource
# runs it as a local-exec provisioner so Terraform controls the deploy
# lifecycle alongside the rest of the infrastructure.
#
# The trigger on app_hash + env_hash means Terraform re-deploys automatically
# whenever streamlit_app.py or environment.yml changes.
# ─────────────────────────────────────────────────────────────────────────────

resource "null_resource" "streamlit_deploy" {
  count = var.deploy_streamlit ? 1 : 0

  triggers = {
    # Re-deploy whenever the app code or its dependencies change.
    app_hash = filemd5("${path.module}/../snowflake/streamlit_app.py")
    env_hash = filemd5("${path.module}/../snowflake/environment.yml")
    # Also re-deploy if key infra objects were recreated.
    schema_public_id = snowflake_schema.public.id
    schema_marts_id  = snowflake_schema.marts.id
    warehouse_name   = snowflake_warehouse.retail.name
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/../snowflake"
    interpreter = ["/bin/bash", "-c"]
    command     = "snow streamlit deploy --replace --prune --connection ${var.snow_connection}"
  }

  depends_on = [
    snowflake_schema.public,
    snowflake_schema.marts,
    snowflake_warehouse.retail,
    snowflake_grant_privileges_to_account_role.engineer_schema_public,
    snowflake_grant_privileges_to_account_role.engineer_schema_marts,
  ]
}
