"""
test_normalize.py
=================
Garante o invariante central da arquitetura "streaming alimenta o dbt": as
funções de erp/simulator/normalize.py — usadas por AMBOS os caminhos (CSV batch
e Kafka streaming) — produzem o schema RAW canônico que o dbt lê. Se o schema
divergir, o dbt quebra; este teste falha primeiro (barato, sem infra).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from erp.simulator.normalize import (
    normalize_sales,
    group_lines_by_order,
    normalize_sale_lines,
    normalize_deliveries,
    normalize_invoices,
)

# Colunas canônicas do RAW (espelham snowflake/sql/ddl_raw.sql). O loader Parquet
# (snowflake/load_parquet.py) e o CSV (scripts/load_snowflake_raw.py) mapeiam estes
# nomes 1:1; invoices.tax_breakdown é excluído no load (dict → NULL), por isso a
# normalize PODE emitir tax_breakdown, mas ele não conta para a paridade do RAW.
RAW_SALES_COLS = {
    "sale_id", "order_date", "order_ts", "customer_id", "store_id", "dc_id",
    "region", "payment_method", "payment_status", "payment_days", "channel",
    "subtotal_net", "tax_amount", "total_gross", "status", "has_partial_stockout",
    "num_items", "ticket_trend",
}
RAW_SALE_LINES_COLS = {
    "sale_id", "line_number", "product_id", "quantity_ordered",
    "quantity_delivered", "unit_price_net", "discount_pct", "tax_rate",
    "line_total_net",
}
RAW_DELIVERIES_COLS = {
    "delivery_id", "sale_id", "dc_id", "carrier", "tracking_number",
    "dispatch_date", "estimated_delivery_date", "actual_delivery_date",
    "delivery_status", "weight_kg", "packages", "signature_required",
    "total_amount",
}
RAW_INVOICES_COLS = {  # tax_breakdown excluído no load → não exigido aqui
    "invoice_id", "sale_id", "delivery_id", "customer_id", "invoice_date",
    "subtotal_net", "tax_amount", "total_gross", "due_date", "payment_days",
    "payment_status", "payment_date",
}


def _raw_sale(order_id, customer_id, channel, date="2025-03-10"):
    return {
        "order_id": order_id, "customer_id": customer_id, "order_date": date,
        "order_ts": f"{date}T11:30:00", "store_id": "ST_0001", "dc_id": "DC_MAD",
        "region": "Comunidad de Madrid", "channel": channel, "num_items": 2,
        "total_amount": 50.0, "total_amount_net": 45.45, "status": "confirmed",
        "has_partial_stockout": False, "ticket_trend": "stable",
    }


def _raw_line(order_id, prod):
    return {
        "item_id": f"ITM_{order_id}_{prod}", "order_id": order_id,
        "product_id": prod, "quantity": 2, "quantity_ordered": 2,
        "quantity_delivered": 2, "unit_price": 25.0, "line_total": 50.0,
        "tax_rate": 0.10,
    }


def _fixtures():
    cust_idx = {
        "CUST_1": {"customer_id": "CUST_1", "segment": "Bronze", "payment_days": 0},
        "CUST_2": {"customer_id": "CUST_2", "segment": "Gold", "payment_days": 30},
    }
    prod_idx = {"PROD_000001": {"product_id": "PROD_000001", "tax_rate": 0.10}}
    return cust_idx, prod_idx


def test_normalize_sales_emits_canonical_schema():
    cust_idx, _ = _fixtures()
    raw = [_raw_sale("ORD_00000001", "CUST_1", "tienda")]
    headers, by_oid = normalize_sales(raw, cust_idx)
    assert set(headers[0].keys()) == RAW_SALES_COLS
    assert headers[0]["sale_id"] == "SO-2025-0000001"
    assert by_oid["ORD_00000001"]["sale_id"] == "SO-2025-0000001"


def test_normalize_sale_lines_emits_canonical_schema():
    _, prod_idx = _fixtures()
    raw = [_raw_sale("ORD_00000001", "CUST_1", "tienda")]
    lines_raw = [_raw_line("ORD_00000001", "PROD_000001")]
    ibo = group_lines_by_order(lines_raw)
    all_lines, by_sid = normalize_sale_lines(raw, ibo, prod_idx)
    assert set(all_lines[0].keys()) == RAW_SALE_LINES_COLS
    assert all_lines[0]["sale_id"] == "SO-2025-0000001"
    assert "SO-2025-0000001" in by_sid


def test_normalize_deliveries_and_invoices_canonical_schema():
    cust_idx, prod_idx = _fixtures()
    raw = [_raw_sale("ORD_00000009", "CUST_2", "ecommerce")]
    headers, by_oid = normalize_sales(raw, cust_idx)
    ibo = group_lines_by_order([_raw_line("ORD_00000009", "PROD_000001")])
    _, by_sid = normalize_sale_lines(raw, ibo, prod_idx)

    raw_del = [{
        "order_id": "ORD_00000009", "delivery_id": "DEL_00000009",
        "order_date": "2025-03-10", "scheduled_date": "2025-03-13",
        "actual_delivery_date": "2025-03-13", "delivery_status": "delivered",
        "dc_id": "DC_MAD", "total_amount": 50.0, "num_items": 1,
    }]
    deliveries, by_del_oid = normalize_deliveries(raw_del, by_oid)
    assert set(deliveries[0].keys()) == RAW_DELIVERIES_COLS

    invoices = normalize_invoices(raw, headers, by_sid, by_del_oid)
    inv_keys = set(invoices[0].keys()) - {"tax_breakdown"}  # excluído no load
    assert inv_keys == RAW_INVOICES_COLS
    # ecommerce → fatura na data de entrega; delivery_id preenchido
    assert invoices[0]["invoice_date"] == "2025-03-13"
    assert invoices[0]["delivery_id"] == "ALB-2025-0000009"


def test_tienda_invoice_has_no_delivery():
    cust_idx, prod_idx = _fixtures()
    raw = [_raw_sale("ORD_00000002", "CUST_1", "tienda")]
    headers, _ = normalize_sales(raw, cust_idx)
    ibo = group_lines_by_order([_raw_line("ORD_00000002", "PROD_000001")])
    _, by_sid = normalize_sale_lines(raw, ibo, prod_idx)
    invoices = normalize_invoices(raw, headers, by_sid, {})  # sem entrega (tienda)
    assert invoices[0]["delivery_id"] is None
    assert invoices[0]["invoice_date"] == "2025-03-10"  # data do pedido


def test_csv_and_stream_paths_are_identical():
    """Paridade: a normalização em lote (CSV) == por-pedido (streaming)."""
    cust_idx, prod_idx = _fixtures()
    raw = [
        _raw_sale("ORD_00000001", "CUST_1", "tienda"),
        _raw_sale("ORD_00000002", "CUST_2", "ecommerce"),
    ]
    lines_raw = [
        _raw_line("ORD_00000001", "PROD_000001"),
        _raw_line("ORD_00000002", "PROD_000001"),
    ]

    # Caminho "CSV": tudo de uma vez
    headers_batch, _ = normalize_sales(raw, cust_idx)
    ibo = group_lines_by_order(lines_raw)
    lines_batch, _ = normalize_sale_lines(raw, ibo, prod_idx)

    # Caminho "streaming": pedido a pedido (como no callback diário)
    headers_stream, lines_stream = [], []
    for sale in raw:
        h, _ = normalize_sales([sale], cust_idx)
        headers_stream.extend(h)
        sub_ibo = group_lines_by_order([ln for ln in lines_raw if ln["order_id"] == sale["order_id"]])
        sl, _ = normalize_sale_lines([sale], sub_ibo, prod_idx)
        lines_stream.extend(sl)

    assert headers_batch == headers_stream
    assert lines_batch == lines_stream
