# ─────────────────────────────────────────────────────────────────────────────
# RetailGuard — Snowflake Infrastructure as Code
#
# Provider : snowflakedb/snowflake ~> 0.100
# Terraform : >= 1.5.0
#
# AUTHENTICATION — export these before running:
#   export SNOWFLAKE_ORGANIZATION_NAME="ZIZJNNI"    # first part of account locator
#   export SNOWFLAKE_ACCOUNT_NAME="HD09953"         # second part (after the dash)
#   export SNOWFLAKE_USER="WELTON"
#   export SNOWFLAKE_PASSWORD="your-password"
#
# Or just run the wrapper — it parses SNOWFLAKE_ACCOUNT from .env automatically:
#   scripts/tf_deploy.sh [init|plan|apply|destroy]
#
# FIRST TIME:
#   terraform init
#   cp terraform.tfvars.example terraform.tfvars   # fill in secrets
#   terraform plan
#   terraform apply
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    snowflake = {
      source  = "snowflakedb/snowflake"
      version = "~> 0.100"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

# Connection reads from environment variables:
#   SNOWFLAKE_ORGANIZATION_NAME, SNOWFLAKE_ACCOUNT_NAME, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
# Role is forced to ACCOUNTADMIN for bootstrapping all objects.
# After initial setup, day-to-day ops should use RETAIL_ENGINEER.
provider "snowflake" {
  role = "ACCOUNTADMIN"
}
