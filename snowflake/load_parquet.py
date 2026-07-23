"""
snowflake/load_parquet.py
Download Parquet files from MinIO → PUT to Snowflake internal stage → COPY INTO.

This is the Streaming ingestion path: Kafka → Parquet/MinIO → Snowflake.

Schema notes
------------
O streaming publica eventos NORMALIZADOS (via erp/simulator/normalize.py), então
o Parquet tem o MESMO schema canônico dos CSVs e do RAW.* lido pelo dbt. Por isso
TODAS as entidades carregam em RAW.<TABLE> canônico (não há mais *_STREAM): batch
(CSV) e streaming (Kafka) alimentam as mesmas tabelas, e o dbt transforma de forma
idêntica — fonte única de verdade, zero drift.

Renomeios (parquet `date` → coluna canônica): stock_movements→movement_date,
stockouts→event_date, product_waste→waste_date. Excluído: invoices.tax_breakdown
(dict; fica NULL no RAW, como no caminho CSV).

Prerequisites:
    pip install snowflake-connector-python minio pyarrow lz4
    Export: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD
    Optional: SNOWFLAKE_ROLE (default: ACCOUNTADMIN)
              SNOWFLAKE_WAREHOUSE (default: COMPUTE_WH)
              SNOWFLAKE_DATABASE (default: RETAIL_DB)
              MINIO_HOST (default: localhost:9000)
              MINIO_ACCESS_KEY (default: minioadmin)
              MINIO_SECRET_KEY (default: minioadmin123)
              MINIO_BUCKET (default: retail-datalake)

Usage:
    python snowflake/load_parquet.py
    python snowflake/load_parquet.py --entity sales
    python snowflake/load_parquet.py --force   # reload already-loaded files
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

# Load .env from repo root (if present) — never overwrites already-set vars
_env_file = Path(__file__).parent.parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file, override=False)
    except ImportError:
        pass  # python-dotenv not installed; fall back to manually exported vars

try:
    import snowflake.connector
except ImportError:
    sys.exit("Run: pip install snowflake-connector-python")

try:
    from minio import Minio
except ImportError:
    sys.exit("Run: pip install minio")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATABASE  = os.environ.get("SNOWFLAKE_DATABASE", "RETAIL_DB")
SCHEMA    = f"{DATABASE}.RAW"
STAGE     = f"{DATABASE}.RAW.RETAIL_STAGE_PARQUET"
FMT       = f"{DATABASE}.RAW.RETAIL_PARQUET_FMT"

MINIO_HOST       = os.environ.get("MINIO_HOST", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET     = os.environ.get("MINIO_BUCKET", "retail-datalake")

# ---------------------------------------------------------------------------
# Parquet → Snowflake RAW (CANÔNICO) column mappings
# Each entry: (target_table, [(parquet_field, snowflake_column, sf_type), ...])
#
# O streaming agora publica eventos NORMALIZADOS (via erp/simulator/normalize.py),
# então o Parquet tem o MESMO schema canônico que os CSVs e que o RAW.* lido pelo
# dbt. Por isso o destino é RAW.<TABLE> (não mais *_STREAM): batch e streaming
# alimentam as MESMAS tabelas, e o dbt transforma de forma idêntica (zero drift).
#
# Renomeios (parquet `date` → coluna canônica): stock_movements/stockouts/
# product_waste (espelha RENAME_COLS de scripts/load_snowflake_raw.py).
# Excluídos por omissão: invoices.tax_breakdown (dict; NULL no RAW, como no CSV),
# purchase_orders._lines (blob).
#
# truncate=True em TODAS: cada run é uma re-simulação completa (full refresh).
# ---------------------------------------------------------------------------

ENTITY_MAP: dict[str, dict] = {
    # ── Master data ──────────────────────────────────────────────────────────
    "distribution_centers": {
        "target": f"{SCHEMA}.DISTRIBUTION_CENTERS", "truncate": True, "ddl": None,
        "columns": [
            ("dc_id",        "dc_id",        "VARCHAR(10)"),
            ("name",         "name",         "VARCHAR(100)"),
            ("city",         "city",         "VARCHAR(100)"),
            ("region",       "region",       "VARCHAR(60)"),
            ("latitude",     "latitude",     "NUMBER(9,6)"),
            ("longitude",    "longitude",    "NUMBER(9,6)"),
            ("stock_weight", "stock_weight", "NUMBER(6,4)"),
        ],
    },
    "stores": {
        "target": f"{SCHEMA}.STORES", "truncate": True, "ddl": None,
        "columns": [
            ("store_id",     "store_id",     "VARCHAR(10)"),
            ("name",         "name",         "VARCHAR(100)"),
            ("postal_code",  "postal_code",  "VARCHAR(5)"),
            ("municipality", "municipality", "VARCHAR(100)"),
            ("province",     "province",     "VARCHAR(60)"),
            ("ccaa",         "ccaa",         "VARCHAR(60)"),
            ("dc_id",        "dc_id",        "VARCHAR(10)"),
            ("opening_date", "opening_date", "VARCHAR(10)"),
            ("sqm",          "sqm",          "NUMBER(6)"),
            ("latitude",     "latitude",     "NUMBER(9,6)"),
            ("longitude",    "longitude",    "NUMBER(9,6)"),
            ("active",       "active",       "VARCHAR(5)"),
        ],
    },
    "suppliers": {
        "target": f"{SCHEMA}.SUPPLIERS", "truncate": True, "ddl": None,
        "columns": [
            ("supplier_id",             "supplier_id",             "VARCHAR(30)"),
            ("name",                    "name",                    "VARCHAR(200)"),
            ("country",                 "country",                 "VARCHAR(50)"),
            ("city",                    "city",                    "VARCHAR(100)"),
            ("lead_time_days",          "lead_time_days",          "NUMBER(3)"),
            ("reliability_score",       "reliability_score",       "NUMBER(5,2)"),
            ("payment_terms_days",      "payment_terms_days",      "NUMBER(3)"),
            ("contact_email",           "contact_email",           "VARCHAR(150)"),
            ("phone",                   "phone",                   "VARCHAR(20)"),
            ("active",                  "active",                  "VARCHAR(5)"),
            ("category_specialization", "category_specialization", "VARCHAR(500)"),
            ("cif",                     "cif",                     "VARCHAR(10)"),
            ("payment_terms",           "payment_terms",           "VARCHAR(5)"),
            ("incoterm",                "incoterm",                "VARCHAR(5)"),
            ("currency",                "currency",                "VARCHAR(3)"),
            ("iban",                    "iban",                    "VARCHAR(30)"),
        ],
    },
    # ── A: Load into existing RAW tables ─────────────────────────────────────
    # Master data: TRUNCATE before load (Parquet is authoritative snapshot)
    "customers": {
        "target": f"{SCHEMA}.CUSTOMERS",
        "truncate": True,   # clear existing rows — Parquet is full refresh
        "ddl": None,   # table already exists
        "columns": [
            ("customer_id",         "customer_id",         "VARCHAR(30)"),
            ("first_name",          "first_name",          "VARCHAR(100)"),
            ("last_name",           "last_name",           "VARCHAR(100)"),
            ("email",               "email",               "VARCHAR(150)"),
            ("phone",               "phone",               "VARCHAR(20)"),
            ("nif",                 "nif",                 "VARCHAR(10)"),
            ("address_street",      "address_street",      "VARCHAR(200)"),
            ("postal_code",         "postal_code",         "VARCHAR(5)"),
            ("municipality",        "municipality",        "VARCHAR(100)"),
            ("province",            "province",            "VARCHAR(60)"),
            ("ccaa",                "ccaa",                "VARCHAR(60)"),
            ("registration_date",   "registration_date",   "VARCHAR(10)"),
            ("segment",             "segment",             "VARCHAR(10)"),
            ("profile",             "profile",             "VARCHAR(30)"),
            ("birth_year",          "birth_year",          "NUMBER(4)"),
            ("age",                 "age",                 "NUMBER(3)"),
            ("payment_method",      "payment_method",      "VARCHAR(30)"),
            ("avg_ticket",          "avg_ticket",          "NUMBER(10,2)"),
            ("ticket_trend",        "ticket_trend",        "VARCHAR(20)"),
            ("behavior_variance",   "behavior_variance",   "NUMBER(5,2)"),
            ("channel_probability", "channel_probability", "NUMBER(5,4)"),
            ("nearest_store_id",    "nearest_store_id",    "VARCHAR(10)"),
            ("payment_days",        "payment_days",        "NUMBER(3)"),
        ],
    },
    "products": {
        "target": f"{SCHEMA}.PRODUCTS",
        "truncate": True,
        "ddl": None,
        "columns": [
            ("product_id",      "product_id",    "VARCHAR(30)"),
            ("sku",             "sku",           "VARCHAR(50)"),
            ("name",            "name",          "VARCHAR(300)"),
            ("brand",           "brand",         "VARCHAR(100)"),
            ("category",        "category",      "VARCHAR(100)"),
            ("category_path",   "category_path", "VARCHAR(300)"),
            ("price",           "price",         "NUMBER(10,2)"),
            ("unit",            "unit",          "VARCHAR(200)"),
            ("image_url",       "image_url",     "VARCHAR(500)"),
            # active is BOOLEAN in Parquet, VARCHAR in DDL — cast to '1'/'0'
            ("active",          "active",        "VARCHAR(5)"),
            ("barcode",         "barcode",       "VARCHAR(13)"),
            ("sale_price",      "sale_price",    "NUMBER(10,2)"),
            ("cost_price",      "cost_price",    "NUMBER(10,4)"),
            ("tax_rate",        "tax_rate",      "NUMBER(4,2)"),
            ("iva_type",        "iva_type",      "VARCHAR(5)"),
            ("unit_of_measure", "unit_of_measure","VARCHAR(5)"),
            ("supplier_code",   "supplier_code", "VARCHAR(15)"),
            ("active_since",    "active_since",  "VARCHAR(10)"),
            # shelf_life_days/is_perishable alimentam os marts de merma (faltavam)
            ("shelf_life_days", "shelf_life_days", "NUMBER(6)"),
            ("is_perishable",   "is_perishable",   "NUMBER(1)"),
        ],
    },
    "purchase_orders": {
        "target": f"{SCHEMA}.PURCHASE_ORDERS",
        "truncate": True,   # re-simulação completa → full refresh
        "ddl": None,
        "columns": [
            ("po_id",                  "po_id",                  "VARCHAR(25)"),
            ("supplier_id",            "supplier_id",            "VARCHAR(30)"),
            ("dc_id",                  "dc_id",                  "VARCHAR(10)"),
            ("order_date",             "order_date",             "VARCHAR(10)"),
            ("expected_receipt_date",  "expected_receipt_date",  "VARCHAR(10)"),
            ("actual_receipt_date",    "actual_receipt_date",    "VARCHAR(10)"),
            ("status",                 "status",                 "VARCHAR(25)"),
            ("incoterm",               "incoterm",               "VARCHAR(5)"),
            ("payment_terms",          "payment_terms",          "VARCHAR(5)"),
            ("currency",               "currency",               "VARCHAR(3)"),
            ("total_cost_net",         "total_cost_net",         "NUMBER(14,2)"),
            ("tax_amount",             "tax_amount",             "NUMBER(14,2)"),
            ("total_cost_gross",       "total_cost_gross",       "NUMBER(14,2)"),
            # _lines (nested list) is intentionally skipped
        ],
    },

    # ── Transacionais (normalizados → RAW canônico, lidos pelo dbt) ──────────
    "sales": {
        "target": f"{SCHEMA}.SALES", "truncate": True, "ddl": None,
        "columns": [
            ("sale_id",              "sale_id",              "VARCHAR(25)"),
            ("order_date",           "order_date",           "VARCHAR(10)"),
            ("order_ts",             "order_ts",             "VARCHAR(25)"),
            ("customer_id",          "customer_id",          "VARCHAR(30)"),
            ("store_id",             "store_id",             "VARCHAR(10)"),
            ("dc_id",                "dc_id",                "VARCHAR(10)"),
            ("region",               "region",               "VARCHAR(60)"),
            ("payment_method",       "payment_method",       "VARCHAR(20)"),
            ("payment_status",       "payment_status",       "VARCHAR(20)"),
            ("payment_days",         "payment_days",         "NUMBER(3)"),
            ("channel",              "channel",              "VARCHAR(10)"),
            ("subtotal_net",         "subtotal_net",         "NUMBER(14,2)"),
            ("tax_amount",           "tax_amount",           "NUMBER(14,2)"),
            ("total_gross",          "total_gross",          "NUMBER(14,2)"),
            ("status",               "status",               "VARCHAR(20)"),
            ("has_partial_stockout", "has_partial_stockout", "VARCHAR(5)"),
            ("num_items",            "num_items",            "NUMBER(5)"),
            ("ticket_trend",         "ticket_trend",         "VARCHAR(20)"),
        ],
    },
    "sale_lines": {
        "target": f"{SCHEMA}.SALE_LINES", "truncate": True, "ddl": None,
        "columns": [
            ("sale_id",            "sale_id",            "VARCHAR(25)"),
            ("line_number",        "line_number",        "NUMBER(5)"),
            ("product_id",         "product_id",         "VARCHAR(30)"),
            ("quantity_ordered",   "quantity_ordered",   "NUMBER(10)"),
            ("quantity_delivered", "quantity_delivered", "NUMBER(10)"),
            ("unit_price_net",     "unit_price_net",     "NUMBER(12,4)"),
            ("discount_pct",       "discount_pct",       "NUMBER(6,4)"),
            ("tax_rate",           "tax_rate",           "NUMBER(4,2)"),
            ("line_total_net",     "line_total_net",     "NUMBER(14,2)"),
        ],
    },
    "purchase_order_lines": {
        "target": f"{SCHEMA}.PURCHASE_ORDER_LINES", "truncate": True, "ddl": None,
        "columns": [
            ("po_id",            "po_id",            "VARCHAR(25)"),
            ("line_number",      "line_number",      "NUMBER(5)"),
            ("product_id",       "product_id",       "VARCHAR(30)"),
            ("quantity_ordered", "quantity_ordered", "NUMBER(10)"),
            ("unit_cost",        "unit_cost",        "NUMBER(12,4)"),
            ("tax_rate",         "tax_rate",         "NUMBER(4,2)"),
            ("line_total_net",   "line_total_net",   "NUMBER(14,2)"),
        ],
    },
    "goods_receipts": {
        "target": f"{SCHEMA}.GOODS_RECEIPTS", "truncate": True, "ddl": None,
        "columns": [
            ("receipt_id",        "receipt_id",        "VARCHAR(30)"),
            ("po_id",             "po_id",             "VARCHAR(25)"),
            ("po_line_number",    "po_line_number",    "NUMBER(5)"),
            ("product_id",        "product_id",        "VARCHAR(30)"),
            ("dc_id",             "dc_id",             "VARCHAR(10)"),
            ("supplier_id",       "supplier_id",       "VARCHAR(30)"),
            ("quantity_received", "quantity_received", "NUMBER(10)"),
            ("receipt_date",      "receipt_date",      "VARCHAR(10)"),
            ("unit_cost",         "unit_cost",         "NUMBER(12,4)"),
        ],
    },
    "deliveries": {
        "target": f"{SCHEMA}.DELIVERIES", "truncate": True, "ddl": None,
        "columns": [
            ("delivery_id",             "delivery_id",             "VARCHAR(25)"),
            ("sale_id",                 "sale_id",                 "VARCHAR(25)"),
            ("dc_id",                   "dc_id",                   "VARCHAR(10)"),
            ("carrier",                 "carrier",                 "VARCHAR(30)"),
            ("tracking_number",         "tracking_number",         "VARCHAR(20)"),
            ("dispatch_date",           "dispatch_date",           "VARCHAR(10)"),
            ("estimated_delivery_date", "estimated_delivery_date", "VARCHAR(10)"),
            ("actual_delivery_date",    "actual_delivery_date",    "VARCHAR(10)"),
            ("delivery_status",         "delivery_status",         "VARCHAR(20)"),
            ("weight_kg",               "weight_kg",               "NUMBER(8,2)"),
            ("packages",                "packages",                "NUMBER(3)"),
            ("signature_required",      "signature_required",      "VARCHAR(5)"),
            ("total_amount",            "total_amount",            "NUMBER(14,2)"),
        ],
    },
    "invoices": {
        # tax_breakdown (dict) é EXCLUÍDO por omissão — NULL no RAW, como no CSV.
        "target": f"{SCHEMA}.INVOICES", "truncate": True, "ddl": None,
        "columns": [
            ("invoice_id",     "invoice_id",     "VARCHAR(25)"),
            ("sale_id",        "sale_id",        "VARCHAR(25)"),
            ("delivery_id",    "delivery_id",    "VARCHAR(25)"),
            ("customer_id",    "customer_id",    "VARCHAR(30)"),
            ("invoice_date",   "invoice_date",   "VARCHAR(10)"),
            ("subtotal_net",   "subtotal_net",   "NUMBER(14,2)"),
            ("tax_amount",     "tax_amount",     "NUMBER(14,2)"),
            ("total_gross",    "total_gross",    "NUMBER(14,2)"),
            ("due_date",       "due_date",       "VARCHAR(10)"),
            ("payment_days",   "payment_days",   "NUMBER(3)"),
            ("payment_status", "payment_status", "VARCHAR(20)"),
            ("payment_date",   "payment_date",   "VARCHAR(10)"),
        ],
    },
    "supplier_payments": {
        "target": f"{SCHEMA}.SUPPLIER_PAYMENTS", "truncate": True, "ddl": None,
        "columns": [
            ("payment_id",      "payment_id",      "VARCHAR(25)"),
            ("po_id",           "po_id",           "VARCHAR(25)"),
            ("supplier_id",     "supplier_id",     "VARCHAR(30)"),
            ("dc_id",           "dc_id",           "VARCHAR(10)"),
            ("obligation_date", "obligation_date", "VARCHAR(10)"),
            ("due_date",        "due_date",        "VARCHAR(10)"),
            ("payment_date",    "payment_date",    "VARCHAR(10)"),
            ("amount_net",      "amount_net",      "NUMBER(14,2)"),
            ("amount_gross",    "amount_gross",    "NUMBER(14,2)"),
            ("status",          "status",          "VARCHAR(20)"),
            ("days_late",       "days_late",       "NUMBER(5)"),
        ],
    },
    "product_returns": {
        "target": f"{SCHEMA}.PRODUCT_RETURNS", "truncate": True, "ddl": None,
        "columns": [
            ("return_id",         "return_id",         "VARCHAR(25)"),
            ("sale_id",           "sale_id",           "VARCHAR(25)"),
            ("order_id",          "order_id",          "VARCHAR(25)"),
            ("product_id",        "product_id",        "VARCHAR(30)"),
            ("customer_id",       "customer_id",       "VARCHAR(30)"),
            ("location_type",     "location_type",     "VARCHAR(10)"),
            ("location_id",       "location_id",       "VARCHAR(10)"),
            ("return_date",       "return_date",       "VARCHAR(10)"),
            ("quantity_returned", "quantity_returned", "NUMBER(10)"),
            ("unit_price_net",    "unit_price_net",    "NUMBER(12,4)"),
            ("refund_amount",     "refund_amount",     "NUMBER(14,2)"),
            ("reason",            "reason",            "VARCHAR(20)"),
            ("restocked",         "restocked",         "VARCHAR(5)"),
        ],
    },
    "product_waste": {
        # parquet `date` → coluna canônica `waste_date`
        "target": f"{SCHEMA}.PRODUCT_WASTE", "truncate": True, "ddl": None,
        "columns": [
            ("waste_id",      "waste_id",      "VARCHAR(30)"),
            ("date",          "waste_date",    "VARCHAR(10)"),
            ("product_id",    "product_id",    "VARCHAR(30)"),
            ("category",      "category",      "VARCHAR(60)"),
            ("location_type", "location_type", "VARCHAR(10)"),
            ("location_id",   "location_id",   "VARCHAR(10)"),
            ("quantity",      "quantity",      "NUMBER(10)"),
            ("unit_cost",     "unit_cost",     "NUMBER(12,4)"),
            ("lost_cost",     "lost_cost",     "NUMBER(14,2)"),
            ("reason",        "reason",        "VARCHAR(20)"),
        ],
    },
    "stock_movements": {
        # parquet `date` → coluna canônica `movement_date`
        "target": f"{SCHEMA}.STOCK_MOVEMENTS", "truncate": True, "ddl": None,
        "columns": [
            ("movement_id",    "movement_id",    "VARCHAR(30)"),
            ("date",           "movement_date",  "VARCHAR(10)"),
            ("product_id",     "product_id",     "VARCHAR(30)"),
            ("location_type",  "location_type",  "VARCHAR(10)"),
            ("location_id",    "location_id",    "VARCHAR(10)"),
            ("movement_type",  "movement_type",  "VARCHAR(10)"),
            ("reason",         "reason",         "VARCHAR(50)"),
            ("reference_id",   "reference_id",   "VARCHAR(30)"),
            ("quantity_delta", "quantity_delta", "NUMBER(12)"),
            ("quantity_after", "quantity_after", "NUMBER(12)"),
        ],
    },
    "stockouts": {
        # parquet `date` → coluna canônica `event_date`
        "target": f"{SCHEMA}.STOCKOUTS", "truncate": True, "ddl": None,
        "columns": [
            ("stockout_id",        "stockout_id",        "VARCHAR(30)"),
            ("date",               "event_date",         "VARCHAR(10)"),
            ("customer_id",        "customer_id",        "VARCHAR(30)"),
            ("product_id",         "product_id",         "VARCHAR(30)"),
            ("location_type",      "location_type",      "VARCHAR(10)"),
            ("location_id",        "location_id",        "VARCHAR(10)"),
            ("quantity_requested", "quantity_requested", "NUMBER(10)"),
            ("quantity_available", "quantity_available", "NUMBER(10)"),
        ],
    },
}


# ---------------------------------------------------------------------------
# Snowflake helpers
# ---------------------------------------------------------------------------

def sf_connect() -> snowflake.connector.SnowflakeConnection:
    account  = os.environ.get("SNOWFLAKE_ACCOUNT")
    user     = os.environ.get("SNOWFLAKE_USER")
    password = os.environ.get("SNOWFLAKE_PASSWORD")
    missing  = [k for k, v in [("SNOWFLAKE_ACCOUNT", account), ("SNOWFLAKE_USER", user), ("SNOWFLAKE_PASSWORD", password)] if not v]
    if missing:
        sys.exit(f"Missing env vars: {', '.join(missing)}")

    return snowflake.connector.connect(
        account=account, user=user, password=password,
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database=DATABASE, schema="RAW",
    )


def setup_stage(cur) -> None:
    cur.execute(f"""
        CREATE OR REPLACE FILE FORMAT {FMT}
            TYPE                = PARQUET
            SNAPPY_COMPRESSION  = TRUE
            BINARY_AS_TEXT      = FALSE
            NULL_IF             = ('NULL', 'null', '')
    """)
    cur.execute(f"""
        CREATE STAGE IF NOT EXISTS {STAGE}
            FILE_FORMAT = {FMT}
            COMMENT     = 'Internal stage for Parquet files downloaded from MinIO'
    """)
    print(f"  Stage {STAGE} ready.")


def ensure_table(cur, entity: str, meta: dict) -> None:
    if meta["ddl"]:
        cur.execute(meta["ddl"].strip())
    if meta.get("truncate"):
        cur.execute(f"TRUNCATE TABLE {meta['target']}")
        print(f"    TRUNCATE {meta['target']} (full refresh)")


def purge_stage_dir(cur, entity: str) -> None:
    """Remove arquivos de execuções anteriores no stage desta entidade.

    O stage interno PERSISTE entre runs; sem isso, Parquet de simulações antigas
    (datas/schema diferentes) ficam acumulados e o COPY (PATTERN '.*.parquet')
    tenta recarregá-los — falhando por schema ou, pior, injetando dados velhos.
    Purgar garante que o COPY veja somente os arquivos do MinIO atual.
    """
    cur.execute(f"REMOVE @{STAGE}/{entity}/")


def put_file(cur, local_path: Path, entity: str) -> None:
    stage_path = f"@{STAGE}/{entity}/"
    sql = f"PUT 'file://{local_path.as_posix()}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
    cur.execute(sql)


def copy_into(cur, entity: str, meta: dict, force: bool) -> int:
    cols     = meta["columns"]
    col_list = ", ".join(c for _, c, _ in cols)
    sel_list = ", ".join(f"$1:{p}::{t}" for p, _, t in cols)
    force_cl = "\nFORCE = TRUE" if force else ""

    sql = f"""
COPY INTO {meta['target']} ({col_list})
FROM (
    SELECT {sel_list}
    FROM @{STAGE}/{entity}/
)
FILE_FORMAT = (FORMAT_NAME = '{FMT}')
PATTERN     = '.*\\.parquet'
ON_ERROR    = 'CONTINUE'{force_cl}
"""
    cur.execute(sql.strip())
    rows = 0
    for row in cur.fetchall():
        status  = row[1] if len(row) > 1 else "?"
        parsed  = row[2] if len(row) > 2 else "?"
        loaded  = row[3] if len(row) > 3 else 0
        # col[4] = error_limit (not errors_seen); col[5] = errors_seen
        errors_seen = row[5] if len(row) > 5 else 0
        suffix = f"  errors={errors_seen}" if errors_seen else ""
        print(f"    {str(row[0]):50s}  {status}  parsed={parsed}  loaded={loaded}{suffix}")
        try:
            rows += int(loaded)
        except (TypeError, ValueError):
            pass
    return rows


# ---------------------------------------------------------------------------
# MinIO helpers
# ---------------------------------------------------------------------------

def minio_connect() -> Minio:
    return Minio(MINIO_HOST, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)


def download_entity(client: Minio, entity: str, dest_dir: Path) -> list[Path]:
    entity_dir = dest_dir / entity
    entity_dir.mkdir(parents=True, exist_ok=True)
    prefix  = f"raw/{entity}/"
    objects = list(client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=True))
    if not objects:
        print(f"  [{entity}] No files in MinIO — skipping.")
        return []
    paths: list[Path] = []
    for obj in objects:
        fname = obj.object_name.replace("/", "__")
        local = entity_dir / fname
        client.fget_object(MINIO_BUCKET, obj.object_name, str(local))
        paths.append(local)
    print(f"  [{entity}] Downloaded {len(paths)} files from MinIO.")
    return paths


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MinIO Parquet → Snowflake loader")
    p.add_argument("--entity", choices=list(ENTITY_MAP), help="Load a single entity (default: all)")
    p.add_argument("--force",  action="store_true", help="Reload files already loaded (FORCE=TRUE)")
    return p.parse_args()


def main() -> None:
    args    = parse_args()
    targets = [args.entity] if args.entity else list(ENTITY_MAP)

    print("\n" + "="*65)
    print("  MinIO Parquet → Snowflake")
    print("="*65)

    # ── 1. Connect ────────────────────────────────────────────────────────────
    print("\n[1/4] Connecting …")
    mc  = minio_connect()
    con = sf_connect()
    cur = con.cursor()
    print(f"  MinIO  : {MINIO_HOST} / {MINIO_BUCKET}")
    print(f"  Snowflake: {os.environ.get('SNOWFLAKE_ACCOUNT')} · {DATABASE}.RAW")

    # ── 2. Stage setup ────────────────────────────────────────────────────────
    print("\n[2/4] Setting up Snowflake stage …")
    setup_stage(cur)

    with tempfile.TemporaryDirectory(prefix="sf_parquet_") as tmpdir:
        tmp = Path(tmpdir)

        # ── 3. Download from MinIO ────────────────────────────────────────────
        print("\n[3/4] Downloading Parquet files from MinIO …")
        entity_files: dict[str, list[Path]] = {}
        for entity in targets:
            files = download_entity(mc, entity, tmp)
            if files:
                entity_files[entity] = files

        # ── 4. PUT + COPY INTO ─────────────────────────────────────────────────
        print("\n[4/4] PUT → Snowflake stage → COPY INTO …")
        total_rows = 0
        for entity, files in entity_files.items():
            meta = ENTITY_MAP[entity]
            print(f"\n  [{entity}] → {meta['target']}")

            # TRUNCATE a tabela RAW canônica (full refresh por re-simulação)
            ensure_table(cur, entity, meta)

            # Purga arquivos de runs anteriores no stage (evita COPY de Parquet velho)
            purge_stage_dir(cur, entity)

            # PUT all files for this entity
            for f in files:
                put_file(cur, f, entity)

            # When truncating, force-reload even files already in load history
            force = args.force or meta.get("truncate", False)
            rows = copy_into(cur, entity, meta, force)
            total_rows += rows
            print(f"    → {rows:,} rows loaded")

    cur.close()
    con.close()

    print(f"\n{'='*65}")
    print(f"  Done.  Total rows loaded into Snowflake: {total_rows:,}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    main()
