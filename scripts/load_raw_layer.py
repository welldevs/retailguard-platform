"""
Load raw layer: imports all source CSVs as physical tables into DuckDB.

This replicates what COPY INTO does in Snowflake (RAW schema).
After running this script, DBeaver can query the staging views
without needing the CSV files on disk.

Usage:
    python scripts/load_raw_layer.py

Optional env vars:
    DUCKDB_PATH   — path to the DuckDB file (default: /tmp/retail_analytics_dev.duckdb)
    CSV_DIR       — directory with source CSVs (default: source/)
    SCHEMA_CSV_DIR — fallback CSV directory used only to infer schemas for empty
                    batch tables (default: seed_sample/)
"""

import os
import sys
from pathlib import Path

try:
    import duckdb
except ImportError:
    sys.exit("duckdb not installed. Run: pip install duckdb")

REPO_ROOT = Path(__file__).parent.parent
DUCKDB_PATH = os.environ.get("DUCKDB_PATH", "/tmp/retail_analytics_dev.duckdb")
CSV_DIR = Path(os.environ.get("CSV_DIR", str(REPO_ROOT / "source")))
SCHEMA_CSV_DIR = Path(os.environ.get("SCHEMA_CSV_DIR", str(REPO_ROOT / "seed_sample")))

TABLES = [
    "sales",
    "sale_lines",
    "customers",
    "products",
    "stores",
    "suppliers",
    "purchase_orders",
    "purchase_order_lines",
    "goods_receipts",
    "deliveries",
    "invoices",
    "supplier_payments",
    "product_returns",
    "product_waste",
    "stock_movements",
    "stockouts",
    "stock_snapshots",
    "distribution_centers",
]

# Columns to exclude per table (raw blobs not useful in SQL layer)
EXCLUDE_COLUMNS = {
    "purchase_orders": {"_lines"},
    "invoices": {"tax_breakdown"},
}


def load(con: duckdb.DuckDBPyConnection, table: str) -> int:
    csv_path = CSV_DIR / f"{table}.csv"
    schema_csv_path = SCHEMA_CSV_DIR / f"{table}.csv"
    if not csv_path.exists():
        if not schema_csv_path.exists():
            print(f"  SKIP  {table} — {csv_path} not found")
            return 0
        csv_path = schema_csv_path
        create_empty = True
    else:
        create_empty = False

    exclude = EXCLUDE_COLUMNS.get(table, set())

    # Read header to know which columns to select
    import csv as csv_mod
    with open(csv_path, newline="", encoding="utf-8") as f:
        headers = next(csv_mod.reader(f))

    cols = [c for c in headers if c not in exclude]
    col_list = ", ".join(f'"{c}"' for c in cols)

    con.execute(f'DROP TABLE IF EXISTS main."{table}"')
    con.execute(f"""
        CREATE TABLE main."{table}" AS
        SELECT {col_list}
        FROM read_csv_auto('{csv_path}', header=true)
        {"LIMIT 0" if create_empty else ""}
    """)

    count = con.execute(f'SELECT count(*) FROM main."{table}"').fetchone()[0]
    if create_empty:
        print(f"  EMPTY {table:<30} created from {schema_csv_path.name}")
    return count


def main():
    if not CSV_DIR.exists():
        sys.exit(f"CSV_DIR not found: {CSV_DIR}\nRun: python erp/run_simulation.py --period 365d --seed 42 --export-csv")

    print(f"DuckDB : {DUCKDB_PATH}")
    print(f"CSV dir: {CSV_DIR}")
    print(f"Schema fallback dir: {SCHEMA_CSV_DIR}")
    print()

    con = duckdb.connect(DUCKDB_PATH)
    con.execute("CREATE SCHEMA IF NOT EXISTS main")

    total = 0
    for table in TABLES:
        count = load(con, table)
        if count:
            print(f"  OK    {table:<30} {count:>10,} rows")
            total += count

    con.close()
    print()
    print(f"Done. {total:,} total rows loaded into main schema.")
    print()
    print("DBeaver: reconnect to the DuckDB file — staging views now work without CSV files.")


if __name__ == "__main__":
    main()
