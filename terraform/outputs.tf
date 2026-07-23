output "database" {
  description = "Snowflake database created."
  value       = snowflake_database.retail_db.name
}

output "warehouse" {
  description = "Virtual warehouse (auto-suspends after 60 s of inactivity)."
  value       = snowflake_warehouse.retail.name
}

output "schemas" {
  description = "All schemas created inside RETAIL_DB."
  value = {
    raw     = snowflake_schema.raw.name
    staging = snowflake_schema.staging.name
    marts   = snowflake_schema.marts.name
    public  = snowflake_schema.public.name
  }
}

output "retail_engineer_role" {
  description = "Grant this role to any human or service account that needs access to RETAIL_DB."
  value       = snowflake_account_role.retail_engineer.name
}

output "dbt_user" {
  description = "Service account for dbt and Airflow. Set SNOWFLAKE_USER=DBT_USER in dbt profiles.yml."
  value       = snowflake_user.dbt_user.name
}

output "internal_stage_ref" {
  description = "Use this path in PUT commands to upload CSVs."
  value       = "@${snowflake_database.retail_db.name}.${snowflake_schema.raw.name}.RETAIL_STAGE"
}

output "minio_stage_created" {
  description = "Whether the MinIO external stage (streaming path) was provisioned."
  value       = var.minio_endpoint != "" ? "yes — @RETAIL_DB.RAW.RETAIL_STAGE_MINIO" : "no — set minio_endpoint to enable"
}

output "snowpipes_notification_channel" {
  description = "SQS ARN for each Snowpipe. Configure this ARN as the MinIO bucket notification target."
  value = {
    sales           = try(snowflake_pipe.sales[0].notification_channel, null)
    sale_lines      = try(snowflake_pipe.sale_lines[0].notification_channel, null)
    stock_movements = try(snowflake_pipe.stock_movements[0].notification_channel, null)
    stockouts       = try(snowflake_pipe.stockouts[0].notification_channel, null)
  }
}

output "next_steps" {
  description = "Manual steps to complete after terraform apply."
  value       = <<-STEPS
    ── Post-apply checklist ───────────────────────────────────────────────
    1. Generate simulation data (if not done yet):
         make simulate          # python erp/run_simulation.py --period 365d --seed 42

    2. Load CSVs into Snowflake RAW:
         make load-raw-snow     # python snowflake/load_snowflake_raw.py

    3. Run dbt transformations:
         cd dbt && dbt deps && dbt build --target snowflake

    4. Streamlit app:
         Deployed automatically if deploy_streamlit = true.
         Open in Snowflake UI → Apps → Streamlit → RETAIL_DASHBOARD.

    5. Streaming — if minio_endpoint was set:
         a. Copy the SQS ARN from 'snowpipes_notification_channel' output.
         b. Configure MinIO bucket notification → SQS → that ARN.
         c. Start the pipeline: make kafka-up && make simulate-kafka && make kafka-consume
  STEPS
}
