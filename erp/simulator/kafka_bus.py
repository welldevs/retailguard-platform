"""
kafka_bus.py — streams simulation events to Kafka topics as they are generated.

When active (--target kafka in run_simulation.py), each NORMALIZED event is
published to the corresponding Kafka topic in near-real time (day granularity via
on_day_complete callback) — a alternativa de streaming ao export CSV (batch).

Topic layout:
    retail.sales                ← pedidos de venda
    retail.sale_lines           ← linhas de cada pedido
    retail.stock_movements      ← movimentações de estoque (IN/OUT/TRANSFER)
    retail.stockouts            ← rupturas de estoque
    retail.deliveries           ← notas de entrega (ecommerce)
    retail.invoices             ← faturas (todos os canais)
    retail.purchase_orders      ← cabeçalhos de PO
    retail.purchase_order_lines ← linhas de PO
    retail.goods_receipts       ← recebimentos de mercadoria
    retail.supplier_payments    ← obrigações AP
    retail.product_returns      ← devoluções de produto
    retail.product_waste        ← mermas / caducidad de perecíveis
    retail.customers            ← master data (publicado 1x no início)
    retail.products             ← master data
    retail.stores               ← master data
    retail.distribution_centers ← master data

NOTA (experimental): este caminho cobre 16 das 18 tabelas canônicas — `suppliers` e
`stock_snapshots` ainda NÃO são publicados. O caminho batch (CSV) é o completo. Ver
extensions/README.md.

The Parquet consumer (extensions/streaming/consumers/parquet_consumer.py) subscribes and writes
Parquet files to MinIO partitioned by date: raw/<entity>/dt=YYYY-MM-DD/*.parquet
"""
from __future__ import annotations

import json
import sys

try:
    from kafka import KafkaProducer
    from kafka.errors import NoBrokersAvailable
    _KAFKA_AVAILABLE = True
except ImportError:
    _KAFKA_AVAILABLE = False


TOPIC_MAP: dict[str, str] = {
    "sales":                "retail.sales",
    "sale_lines":           "retail.sale_lines",
    "stock_movements":      "retail.stock_movements",
    "stockouts":            "retail.stockouts",
    "deliveries":           "retail.deliveries",
    "invoices":             "retail.invoices",
    "purchase_orders":      "retail.purchase_orders",
    "purchase_order_lines": "retail.purchase_order_lines",
    "goods_receipts":       "retail.goods_receipts",
    "supplier_payments":    "retail.supplier_payments",
    "product_returns":      "retail.product_returns",
    "product_waste":        "retail.product_waste",
    "customers":            "retail.customers",
    "products":             "retail.products",
    "stores":               "retail.stores",
    "distribution_centers": "retail.distribution_centers",
}

_KEY_FIELD: dict[str, str] = {
    # Eventos transacionais normalizados usam sale_id/delivery_id/invoice_id
    "sales":                "sale_id",
    "sale_lines":           "sale_id",
    "stock_movements":      "product_id",
    "stockouts":            "product_id",
    "deliveries":           "delivery_id",
    "invoices":             "invoice_id",
    "purchase_orders":      "po_id",
    "purchase_order_lines": "po_id",
    "goods_receipts":       "receipt_id",
    "supplier_payments":    "payment_id",
    "product_returns":      "return_id",
    "product_waste":        "waste_id",
    "customers":            "customer_id",
    "products":             "product_id",
    "stores":               "store_id",
    "distribution_centers": "dc_id",
}


class KafkaEventBus:
    """
    Thin wrapper around KafkaProducer for streaming simulation events.

    Each call to ``publish_batch`` sends all rows to the entity's Kafka topic
    and flushes before returning (at-least-once semantics with acks='all').

    Lifecycle::

        bus = KafkaEventBus("localhost:9094")
        # master data (published once)
        bus.publish_batch("products", products_list)
        # transactional events (published per day)
        bus.publish_batch("sales", today_sales)
        bus.close()
        print(f"Total published: {bus.total_published}")
    """

    def __init__(self, bootstrap_servers: str = "localhost:9094") -> None:
        if not _KAFKA_AVAILABLE:
            sys.exit(
                "kafka-python not installed.\n"
                "Run: pip install kafka-python"
            )

        try:
            self._producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers.split(","),
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks=1,                 # líder confirma (single-node); acks='all' não
                                        # agrega num broker só e dobra a latência
                retries=5,
                linger_ms=50,           # janela maior de micro-batching
                batch_size=256 * 1024,  # 256KB por batch (default 16KB era pequeno)
                buffer_memory=128 * 1024 * 1024,  # 128MB de buffer → back-pressure só no teto
                compression_type="lz4",
                request_timeout_ms=60_000,
            )
        except NoBrokersAvailable:
            sys.exit(
                f"Cannot reach Kafka at {bootstrap_servers}.\n"
                "Start the streaming stack:\n"
                "  docker compose -f extensions/streaming/docker-compose.yml up -d\n"
                "  (wait ~15 s for Kafka to become healthy)"
            )

        self._total: int = 0

    def publish_batch(self, entity: str, rows: list[dict]) -> int:
        """
        Publish ``rows`` to the Kafka topic for ``entity``.

        Os envios são ASSÍNCRONOS (bufferizados pelo produtor com linger_ms +
        compressão). NÃO faz flush aqui — flush por batch serializa cada envio
        esperando acks='all' do broker, o que torna o streaming O(dias × entidades)
        round-trips e degrada o throughput em ~50×. O flush acontece 1× por dia
        (chamador) e no close(). O buffer do produtor é limitado (buffer_memory),
        então send() aplica back-pressure naturalmente — a RAM não cresce sem teto.

        Returns the number of messages published (0 if rows is empty or
        entity has no topic mapping).
        """
        topic = TOPIC_MAP.get(entity)
        if not topic or not rows:
            return 0

        key_field = _KEY_FIELD.get(entity)
        producer_send = self._producer.send   # hoist do atributo (hot loop)
        for row in rows:
            key = str(row.get(key_field, "")) or None if key_field else None
            producer_send(topic, key=key, value=row)

        self._total += len(rows)
        return len(rows)

    def flush(self) -> None:
        self._producer.flush()

    def close(self) -> None:
        self._producer.flush()
        self._producer.close()

    @property
    def total_published(self) -> int:
        return self._total
