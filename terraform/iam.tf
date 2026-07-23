# ─────────────────────────────────────────────────────────────────────────────
# IAM — Role, Service Account, Grants
#
# RETAIL_ENGINEER role: full access to RETAIL_DB, used by dbt + Airflow + Streamlit.
# DBT_USER: service account that runs as RETAIL_ENGINEER.
# ─────────────────────────────────────────────────────────────────────────────

# ── Role ──────────────────────────────────────────────────────────────────────
resource "snowflake_account_role" "retail_engineer" {
  name    = "RETAIL_ENGINEER"
  comment = "Owner role for RETAIL_DB — dbt, Airflow, and Streamlit run under this role."
}

# ── Service account ───────────────────────────────────────────────────────────
resource "snowflake_user" "dbt_user" {
  name = "DBT_USER"
  # Key-pair-only when no password is supplied (recommended). A leaked/committed
  # password is a non-issue if there simply isn't one — auth is the RSA key.
  password          = var.dbt_user_password != "" ? var.dbt_user_password : null
  default_warehouse = snowflake_warehouse.retail.name
  default_role      = snowflake_account_role.retail_engineer.name
  default_namespace = "${snowflake_database.retail_db.name}.${snowflake_schema.raw.name}"
  comment           = "Service account for dbt transformations and Airflow DAG execution."

  # Key-pair (JWT) auth — the production standard for service accounts. When a
  # public key is supplied (scripts/gen_dbt_keypair.sh → terraform.tfvars), dbt
  # authenticates with the PRIVATE key and no password is needed. Password is
  # kept as a fallback; in a hardened prod you would null it out entirely.
  rsa_public_key = var.dbt_user_rsa_public_key != "" ? var.dbt_user_rsa_public_key : null

  must_change_password = false
  disabled             = false
}

resource "snowflake_grant_account_role" "engineer_to_dbt" {
  role_name = snowflake_account_role.retail_engineer.name
  user_name = snowflake_user.dbt_user.name
}

# Nest RETAIL_ENGINEER under SYSADMIN (Snowflake best practice: every custom role
# rolls up to SYSADMIN). This lets dbt run as the least-privilege RETAIL_ENGINEER
# and OWN the objects it builds, while admins (SYSADMIN/ACCOUNTADMIN) still inherit
# full control — no ownership ping-pong between the service account and admins.
resource "snowflake_grant_account_role" "engineer_to_sysadmin" {
  role_name        = snowflake_account_role.retail_engineer.name
  parent_role_name = "SYSADMIN"
}

# ── Account-level grants ──────────────────────────────────────────────────────
resource "snowflake_grant_privileges_to_account_role" "engineer_database" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["USAGE", "CREATE SCHEMA"]
  on_account_object {
    object_type = "DATABASE"
    object_name = snowflake_database.retail_db.name
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_warehouse" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["USAGE", "OPERATE"]
  on_account_object {
    object_type = "WAREHOUSE"
    object_name = snowflake_warehouse.retail.name
  }
}

# ── Schema-level grants ───────────────────────────────────────────────────────
resource "snowflake_grant_privileges_to_account_role" "engineer_schema_raw" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges = [
    "USAGE", "CREATE TABLE", "CREATE STAGE",
    "CREATE FILE FORMAT", "CREATE PIPE", "CREATE STREAM"
  ]
  on_schema {
    schema_name = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.raw.name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_schema_staging" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    schema_name = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.staging.name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_schema_marts" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["USAGE", "CREATE TABLE", "CREATE VIEW"]
  on_schema {
    schema_name = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.marts.name}\""
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_schema_public" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["USAGE", "CREATE STREAMLIT", "CREATE STAGE"]
  on_schema {
    schema_name = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.public.name}\""
  }
}

# ── Future grants — auto-applies to objects created by dbt ────────────────────
resource "snowflake_grant_privileges_to_account_role" "engineer_future_tables_raw" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.raw.name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_future_tables_staging" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.staging.name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_future_tables_marts" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
  on_schema_object {
    future {
      object_type_plural = "TABLES"
      in_schema          = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.marts.name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_future_views_staging" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.staging.name}\""
    }
  }
}

resource "snowflake_grant_privileges_to_account_role" "engineer_future_views_marts" {
  account_role_name = snowflake_account_role.retail_engineer.name
  privileges        = ["SELECT"]
  on_schema_object {
    future {
      object_type_plural = "VIEWS"
      in_schema          = "\"${snowflake_database.retail_db.name}\".\"${snowflake_schema.marts.name}\""
    }
  }
}
