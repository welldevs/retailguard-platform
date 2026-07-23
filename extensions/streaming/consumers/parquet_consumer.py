#!/usr/bin/env python3
"""
Parquet consumer — reads JSON events from Kafka topics and writes Parquet files
to MinIO using Hive-style date partitioning:

    retail-datalake/raw/<entity>/dt=YYYY-MM-DD/part-NNNN.parquet

MinIO is S3-compatible, so the same Snowflake external stage SQL works against
AWS S3, Cloudflare R2, Azure ADLS Gen2, or any S3-compatible endpoint.

Usage:
    python extensions/streaming/consumers/parquet_consumer.py
    python extensions/streaming/consumers/parquet_consumer.py --flush-interval 60 --max-batch 50000
    python extensions/streaming/consumers/parquet_consumer.py --once   # drain current messages and exit
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

try:
    from kafka import KafkaConsumer
    from kafka.errors import NoBrokersAvailable
except ImportError:
    sys.exit("kafka-python not installed. Run: pip install kafka-python")

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError:
    sys.exit("pyarrow not installed. Run: pip install pyarrow")

try:
    from minio import Minio
    from minio.error import S3Error
except ImportError:
    sys.exit("minio not installed. Run: pip install minio")

# ── configuration (all overridable via env) ────────────────────────────────────
KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9094")
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT",   "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_BUCKET     = os.getenv("MINIO_BUCKET",     "retail-datalake")

TOPICS = [
    # Transacionais (delta diário via streaming)
    "retail.sales",
    "retail.sale_lines",
    "retail.stock_movements",
    "retail.stockouts",
    "retail.deliveries",
    "retail.invoices",
    "retail.purchase_orders",
    "retail.purchase_order_lines",
    "retail.goods_receipts",
    "retail.supplier_payments",
    "retail.product_returns",
    "retail.product_waste",
    # Master data (publicado 1x no início)
    "retail.customers",
    "retail.products",
    "retail.suppliers",
    "retail.stores",
    "retail.distribution_centers",
]

# Field that determines the partition date (falls back to ingestion date).
# Os nomes batem com as chaves de data que o engine emite por entidade.
DATE_FIELD: dict[str, str] = {
    # Eventos normalizados: sales=order_date, deliveries=actual_delivery_date,
    # invoices=invoice_date. Os já-canônicos mantêm `date`/datas próprias.
    "sales":               "order_date",
    "sale_lines":          None,          # linha não tem data própria → ingestão
    "stock_movements":     "date",
    "stockouts":           "date",
    "deliveries":          "actual_delivery_date",
    "invoices":            "invoice_date",
    "purchase_orders":     "order_date",
    "purchase_order_lines": None,         # linha de PO → ingestão
    "goods_receipts":      "receipt_date",
    "supplier_payments":   "due_date",
    "product_returns":     "return_date",
    "product_waste":       "date",
    "customers":           None,   # master data — sem data natural
    "products":            None,
    "suppliers":           None,
    "stores":              None,
    "distribution_centers": None,
}


def topic_to_entity(topic: str) -> str:
    return topic.split(".")[-1]


def infer_partition_date(entity: str, row: dict, fallback: str) -> str:
    field = DATE_FIELD.get(entity)
    if field and field in row and row[field]:
        raw = str(row[field])
        return raw[:10]   # keep YYYY-MM-DD prefix
    return fallback


def flush_partition(
    client: Minio,
    entity: str,
    date_str: str,
    rows: list[dict],
    part_num: int,
) -> None:
    if not rows:
        return

    table = pa.Table.from_pylist(rows)
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="snappy")
    size = buf.tell()
    buf.seek(0)

    object_path = f"raw/{entity}/dt={date_str}/part-{part_num:04d}.parquet"
    client.put_object(
        MINIO_BUCKET,
        object_path,
        buf,
        length=size,
        content_type="application/octet-stream",
    )
    print(f"  ✓ {object_path}  ({len(rows):,} rows · {size / 1024:.1f} KB)")


def build_consumer(servers: str, once: bool) -> KafkaConsumer:
    return KafkaConsumer(
        *TOPICS,
        bootstrap_servers=servers.split(","),
        group_id="parquet-consumer-v1",
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        # In --once mode: stop iteration after flush_interval of silence
        consumer_timeout_ms=5_000 if once else -1,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Kafka → Parquet → MinIO consumer")
    parser.add_argument("--servers", default=KAFKA_BOOTSTRAP)
    parser.add_argument("--flush-interval", type=int, default=30,
                        help="Seconds between MinIO flushes")
    parser.add_argument("--max-batch", type=int, default=100_000,
                        help="Max rows per entity before forced flush")
    parser.add_argument("--once", action="store_true",
                        help="Drain current messages and exit (no persistent loop)")
    args = parser.parse_args()

    minio = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False,
    )
    if not minio.bucket_exists(MINIO_BUCKET):
        minio.make_bucket(MINIO_BUCKET)
        print(f"Created bucket: {MINIO_BUCKET}")

    print(f"Connecting to Kafka at {args.servers} …")
    try:
        consumer = build_consumer(args.servers, args.once)
    except NoBrokersAvailable:
        sys.exit(
            "Cannot reach Kafka. Start the stack first:\n"
            "  docker compose -f extensions/streaming/docker-compose.yml up -d"
        )

    # buffers[entity][date_str] = [rows]
    buffers: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    part_counters: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_messages = 0
    last_flush = time.monotonic()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def flush_all() -> None:
        nonlocal today
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for entity, date_buckets in buffers.items():
            for date_str, rows in list(date_buckets.items()):
                if rows:
                    flush_partition(minio, entity, date_str, rows, part_counters[entity][date_str])
                    part_counters[entity][date_str] += 1
                    date_buckets[date_str] = []

    print(f"Subscribed to {len(TOPICS)} topics → MinIO bucket '{MINIO_BUCKET}'")
    print("Press Ctrl+C to stop and flush remaining data.\n")

    try:
        for msg in consumer:
            entity = topic_to_entity(msg.topic)
            row = msg.value
            date_str = infer_partition_date(entity, row, today)
            buffers[entity][date_str].append(row)
            total_messages += 1

            elapsed = time.monotonic() - last_flush
            entity_total = sum(len(v) for v in buffers[entity].values())
            if elapsed >= args.flush_interval or entity_total >= args.max_batch:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Flushing {total_messages:,} messages …")
                flush_all()
                last_flush = time.monotonic()

    except KeyboardInterrupt:
        print(f"\nInterrupted. Flushing {total_messages:,} messages …")
    except StopIteration:
        print(f"\nDrained {total_messages:,} messages. Flushing …")
    finally:
        flush_all()
        consumer.close()
        print(f"\nDone. Total: {total_messages:,} events written to MinIO.")


if __name__ == "__main__":
    main()
