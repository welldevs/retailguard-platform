"""
Load all source CSVs into Snowflake RAW schema.

Steps per table:
  1. PUT file://source/<table>.csv → @RETAIL_STAGE/<table>/
  2. TRUNCATE TABLE
  3. COPY INTO (FORCE=TRUE to reload regardless of load history)

Usage:
    python scripts/load_snowflake_raw.py
    python scripts/load_snowflake_raw.py --table sales

Env vars (or .env):
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
    SNOWFLAKE_ROLE     (default: ACCOUNTADMIN)
    SNOWFLAKE_WAREHOUSE (default: COMPUTE_WH)
    SNOWFLAKE_DATABASE  (default: RETAIL_DB)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        pass

try:
    import snowflake.connector
except ImportError:
    sys.exit("Run: pip install snowflake-connector-python")

REPO_ROOT   = Path(__file__).parent.parent
CSV_DIR     = REPO_ROOT / "source"
DATABASE    = os.environ.get("SNOWFLAKE_DATABASE", "RETAIL_DB")
RAW_SCHEMA  = f"{DATABASE}.RAW"
STAGE       = f"{RAW_SCHEMA}.RETAIL_STAGE"
FMT         = f"{RAW_SCHEMA}.CSV_FORMAT"

# (table_name, csv_filename) — same order as dependency graph
TABLES = [
    ("DISTRIBUTION_CENTERS",  "distribution_centers.csv"),
    ("STORES",                "stores.csv"),
    ("SUPPLIERS",             "suppliers.csv"),
    ("CUSTOMERS",             "customers.csv"),
    ("PRODUCTS",              "products.csv"),
    ("SALES",                 "sales.csv"),
    ("SALE_LINES",            "sale_lines.csv"),
    ("PURCHASE_ORDERS",       "purchase_orders.csv"),
    ("PURCHASE_ORDER_LINES",  "purchase_order_lines.csv"),
    ("GOODS_RECEIPTS",        "goods_receipts.csv"),
    ("DELIVERIES",            "deliveries.csv"),
    ("INVOICES",              "invoices.csv"),
    ("SUPPLIER_PAYMENTS",     "supplier_payments.csv"),
    ("PRODUCT_RETURNS",       "product_returns.csv"),
    ("PRODUCT_WASTE",         "product_waste.csv"),
    ("STOCK_MOVEMENTS",       "stock_movements.csv"),
    ("STOCKOUTS",             "stockouts.csv"),
    ("STOCK_SNAPSHOTS",       "stock_snapshots.csv"),
]

# Columns to drop from CSV before loading (JSON blobs, etc.)
EXCLUDE_COLS = {
    "PURCHASE_ORDERS": {"_lines"},
    "INVOICES":        {"tax_breakdown"},
}

# CSV column name → Snowflake column name renames (lowercased CSV header → SF col)
RENAME_COLS: dict[str, dict[str, str]] = {
    "STOCK_MOVEMENTS": {"date": "movement_date"},
    "STOCKOUTS":       {"date": "event_date"},
    "PRODUCT_WASTE":   {"date": "waste_date"},
}


def sf_connect() -> snowflake.connector.SnowflakeConnection:
    account  = os.environ.get("SNOWFLAKE_ACCOUNT")
    user     = os.environ.get("SNOWFLAKE_USER")
    password = os.environ.get("SNOWFLAKE_PASSWORD")
    missing  = [k for k, v in [
        ("SNOWFLAKE_ACCOUNT", account),
        ("SNOWFLAKE_USER", user),
        ("SNOWFLAKE_PASSWORD", password),
    ] if not v]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    return snowflake.connector.connect(
        account=account, user=user, password=password,
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=DATABASE, schema="RAW",
    )


def csv_headers(path: Path) -> list[str]:
    import csv
    with open(path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f))


def load_table(cur, table: str, csv_path: Path) -> int:
    stage_prefix = f"@{STAGE}/{table.lower()}/"

    # 0. PURGE the stage path. The COPY INTO below reads the WHOLE directory
    # with FORCE=TRUE, so any previously-staged file under this prefix (e.g. a
    # prior customers.csv when we now load customers_drift.csv) would be
    # re-loaded too and duplicate every row. Clearing first guarantees COPY
    # only sees the single file we are about to PUT.
    cur.execute(f"REMOVE {stage_prefix}")
    print("    REMOVE stage done.")

    # 1. PUT
    put_sql = f"PUT 'file://{csv_path.as_posix()}' {stage_prefix} AUTO_COMPRESS=TRUE OVERWRITE=TRUE"
    print("    PUT …", end=" ", flush=True)
    cur.execute(put_sql)
    put_row = cur.fetchone()
    put_status = put_row[6] if put_row and len(put_row) > 6 else "?"
    print(put_status)

    # 2. TRUNCATE
    cur.execute(f"TRUNCATE TABLE {RAW_SCHEMA}.{table}")
    print("    TRUNCATE done.")

    # 3. COPY INTO — via a positional SELECT $n transformation so that
    # EXCLUDED columns (e.g. the invoices tax_breakdown JSON blob) are SKIPPED
    # by position and renames are applied by position. A plain column list with
    # an excluded column would MISALIGN every later field (the blob would land
    # in the next column) — the bug ON_ERROR='ABORT_STATEMENT' surfaced.
    exclude = EXCLUDE_COLS.get(table, set())
    renames = RENAME_COLS.get(table, {})
    headers = csv_headers(csv_path)
    target_cols  = []
    select_exprs = []
    for idx, header in enumerate(headers, start=1):
        if header in exclude:
            continue
        target_cols.append(renames.get(header, header))
        select_exprs.append(f"${idx}")
    col_list    = ", ".join(target_cols)
    select_list = ", ".join(select_exprs)

    copy_sql = f"""
COPY INTO {RAW_SCHEMA}.{table} ({col_list})
FROM (SELECT {select_list} FROM @{STAGE}/{table.lower()}/)
FILE_FORMAT = (FORMAT_NAME = '{FMT}')
ON_ERROR = 'ABORT_STATEMENT'
FORCE = TRUE
"""
    cur.execute(copy_sql.strip())
    total_loaded = 0
    for row in cur.fetchall():
        file_name   = row[0]
        status      = row[1] if len(row) > 1 else "?"
        rows_parsed = row[2] if len(row) > 2 else 0
        rows_loaded = row[3] if len(row) > 3 else 0
        errors_seen = row[5] if len(row) > 5 else 0
        suffix = f"  errors={errors_seen}" if errors_seen else ""
        short = Path(file_name).name if file_name else "?"
        print(f"    {short:55s}  {status}  parsed={rows_parsed}  loaded={rows_loaded}{suffix}")
        try:
            total_loaded += int(rows_loaded)
        except (TypeError, ValueError):
            pass
    return total_loaded


def main() -> None:
    parser = argparse.ArgumentParser(description="Load source CSVs → Snowflake RAW")
    parser.add_argument("--table", help="Load only this table (uppercase, e.g. SALES)")
    parser.add_argument(
        "--file",
        help="Override CSV path for the single --table load "
             "(e.g. source/customers_drift.csv). Requires --table.",
    )
    args = parser.parse_args()

    if args.file and not args.table:
        sys.exit("--file requires --table (it overrides the path for that one table).")

    if args.table:
        targets = [(t, f) for t, f in TABLES if t == args.table.upper()]
        if not targets:
            sys.exit(f"Unknown table '{args.table}'. Valid: {[t for t,_ in TABLES]}")
        if args.file:
            # Load this table from an explicit path instead of source/<table>.csv,
            # so e.g. customers_drift.csv loads into CUSTOMERS without touching
            # customers.csv on disk. Mark with an absolute path sentinel.
            targets = [(targets[0][0], None)]
    else:
        targets = TABLES

    print("\n" + "=" * 65)
    print("  Snowflake RAW Loader — CSV → stage → COPY INTO")
    print("=" * 65)
    print(f"\n  CSV dir : {CSV_DIR}")
    print(f"  Stage   : {STAGE}")
    print(f"  Schema  : {RAW_SCHEMA}\n")

    con = sf_connect()
    cur = con.cursor()

    total = 0
    for table, csv_file in targets:
        csv_path = Path(args.file) if (args.file and csv_file is None) else CSV_DIR / csv_file
        if not csv_path.exists():
            print(f"\n  SKIP  {table} — {csv_path} not found")
            continue
        size_mb = csv_path.stat().st_size / 1_048_576
        print(f"\n  [{table}]  ({size_mb:.1f} MB)")
        rows = load_table(cur, table, csv_path)
        total += rows
        print(f"  → {rows:,} rows loaded into {RAW_SCHEMA}.{table}")

    cur.close()
    con.close()

    print(f"\n{'=' * 65}")
    print(f"  Done. Total rows loaded: {total:,}")
    print(f"{'=' * 65}\n")


if __name__ == "__main__":
    main()
