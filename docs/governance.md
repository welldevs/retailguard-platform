# Governance — RBAC + Dynamic Data Masking

Script: [`snowflake/sql/rbac_and_masking.sql`](../snowflake/sql/rbac_and_masking.sql)

This adds two governance controls on top of the Snowflake layer, both implemented in a single
**idempotent** SQL script (safe to re-run):

1. **Least-privilege RBAC** — moves the Streamlit dashboard off `ACCOUNTADMIN` onto a purpose-built
   role with only the grants the app actually uses.
2. **Dynamic Data Masking** — masks PII in `RETAIL_DB.RAW.CUSTOMERS` so only privileged roles see
   clear values.

> **Security:** the script contains **no passwords** and creates **no users**. Snowflake credentials
> come from environment variables / the `retail` connection. The Architect runs the deploy; this repo
> only holds the SQL.

## 1. RBAC — `RETAIL_DASHBOARD_ROLE`

A least-privilege role for the Streamlit app (`RETAIL_DB.PUBLIC.RETAIL_DASHBOARD`). It receives **no**
`ALL`/`OWNERSHIP`, only:

- `USAGE` on the database, the `RAW` / `MARTS` / `PUBLIC` schemas, and the `COMPUTE_WH` warehouse
  (no `OPERATE` — a read-only app does not need to resume/suspend the warehouse).
- `SELECT` on the three canonical RAW tables the app touches: `SALES`, `SALE_LINES`, `PRODUCTS`.
- `SELECT` on **all current and future** tables/views in `MARTS`, so new dbt marts are reachable
  without a manual grant.

There is also a commented, optional block to transfer **ownership** of the Streamlit object to the
role (`GRANT OWNERSHIP ... COPY CURRENT GRANTS`) so the app runs at runtime with only these
privileges. It is left commented because it must be tested in a non-prod environment first — if a
grant is missing, the app breaks.

A second role, **`RETAIL_GOVERNANCE_ROLE`**, is the compliance/audit role that bypasses masking and
can read `CUSTOMERS` in clear.

## 2. Dynamic Data Masking — PII in `RAW.CUSTOMERS`

Masking policies are applied to: `email`, `phone`, `nif`, `first_name`, `last_name`, `address_street`.

| Column | Policy | Masked output | Clear for |
|---|---|---|---|
| `email` | `MASK_EMAIL` | `***@<domain>` (domain preserved) | `ACCOUNTADMIN`, `RETAIL_GOVERNANCE_ROLE` |
| `nif` | `MASK_NIF` | `XXX****` | same |
| `phone` | `MASK_PHONE` | `***` | same |
| `first_name`, `last_name`, `address_street` | `MASK_TEXT_PII` | `***` | same |

Any other role — including `RETAIL_DASHBOARD_ROLE` — sees the masked value. Policies are applied with
`ALTER TABLE ... MODIFY COLUMN ... SET MASKING POLICY ... FORCE`, which is declarative and idempotent.

## How to apply

Run as `ACCOUNTADMIN` (or a role with `CREATE ROLE`, `MANAGE GRANTS`, and rights to create masking
policies and grant on the objects):

```bash
snow sql -c retail -f snowflake/sql/rbac_and_masking.sql
```

## How to test

The script ends with a commented **TESTES** block. In summary:

```sql
-- Governance role sees PII in clear:
USE ROLE RETAIL_GOVERNANCE_ROLE;
SELECT customer_id, first_name, email, phone, nif, address_street
  FROM RETAIL_DB.RAW.CUSTOMERS LIMIT 5;
-- → real values

-- Dashboard role sees PII masked (needs a temporary SELECT grant just for the test):
USE ROLE RETAIL_DASHBOARD_ROLE;
SELECT customer_id, first_name, email, phone, nif, address_street
  FROM RETAIL_DB.RAW.CUSTOMERS LIMIT 5;
-- → first_name='***', email='***@gmail.com', phone='***', nif='XXX****', address_street='***'
```

The app itself does **not** read `CUSTOMERS`, so revoke that temporary grant after testing. You can
also inspect where each policy is attached via
`INFORMATION_SCHEMA.POLICY_REFERENCES(REF_ENTITY_NAME => 'RETAIL_DB.RAW.CUSTOMERS', ...)`.

## How to revert (rollback)

The script ends with a commented **ROLLBACK** block. In order:

1. `UNSET MASKING POLICY` on each of the six columns.
2. `DROP MASKING POLICY` for `MASK_EMAIL`, `MASK_NIF`, `MASK_PHONE`, `MASK_TEXT_PII`.
3. (If ownership was transferred) return Streamlit ownership to `ACCOUNTADMIN`.
4. `DROP ROLE` for `RETAIL_DASHBOARD_ROLE` and `RETAIL_GOVERNANCE_ROLE` (implicitly revokes grants).
