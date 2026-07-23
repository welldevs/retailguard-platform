"""
simulator/normalize.py
======================
Normalização canônica engine-raw → schema ERP, COMPARTILHADA pelos dois caminhos:

    - batch  : run_simulation.main()      (--target csv)
    - stream : run_simulation._kafka_main()(--target kafka)

Ambos os caminhos chamam as MESMAS funções aqui, garantindo que as linhas que
chegam ao RAW canônico do Snowflake sejam byte-idênticas independentemente da
ingestão (anti-drift). Antes, a normalização vivia inline no bloco [4/5] de
run_simulation (só batch) e o streaming publicava dicts brutos do engine —
schemas divergentes que quebravam o dbt. Esta extração unifica os dois.

Todas as funções são puras (mesmo input → mesmo output dada seed fixa) e
reusam os builders de erp/simulator/schema.py.
"""
from typing import Dict, List, Tuple

from erp.simulator.schema import (
    build_sale_order_header,
    build_sale_order_lines,
    build_delivery_note,
    build_invoice,
)


def normalize_sales(
    raw_sales: List[Dict],
    customer_idx: Dict[str, Dict],
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Cabeçalhos SO normalizados.

    Returns:
        (headers, orders_by_order_id) — headers é a lista de cabeçalhos ERP;
        orders_by_order_id mapeia order_id (bruto) → header, para uso posterior
        em deliveries/invoices.
    """
    headers: List[Dict] = []
    orders_by_order_id: Dict[str, Dict] = {}
    for sale in raw_sales:
        cust = customer_idx.get(sale["customer_id"], {})
        hdr = build_sale_order_header(sale, cust)
        headers.append(hdr)
        orders_by_order_id[sale["order_id"]] = hdr
    return headers, orders_by_order_id


def group_lines_by_order(raw_lines: List[Dict]) -> Dict[str, List[Dict]]:
    """Agrupa linhas brutas do engine por order_id."""
    items_by_order: Dict[str, List[Dict]] = {}
    for item in raw_lines:
        items_by_order.setdefault(item["order_id"], []).append(item)
    return items_by_order


def normalize_sale_lines(
    raw_sales: List[Dict],
    items_by_order: Dict[str, List[Dict]],
    product_idx: Dict[str, Dict],
) -> Tuple[List[Dict], Dict[str, List[Dict]]]:
    """Linhas de venda normalizadas.

    Returns:
        (sale_lines_all, lines_by_sale_id) — lista plana de linhas e o índice
        sale_id → linhas (necessário para a desagregação de IVA da fatura).
    """
    sale_lines_all: List[Dict] = []
    lines_by_sale_id: Dict[str, List[Dict]] = {}
    for sale in raw_sales:
        lines = build_sale_order_lines(
            sale, items_by_order.get(sale["order_id"], []), product_idx
        )
        sale_lines_all.extend(lines)
        if lines:
            lines_by_sale_id[lines[0]["sale_id"]] = lines
    return sale_lines_all, lines_by_sale_id


def adapt_raw_delivery(raw_del: Dict) -> Dict:
    """Adapta os nomes de campo do engine ao que build_delivery_note espera."""
    return {
        **raw_del,
        "scheduled_delivery_date": raw_del.get(
            "scheduled_date", raw_del.get("scheduled_delivery_date", "")
        ),
        "status": raw_del.get("delivery_status", raw_del.get("status", "in_transit")),
    }


def normalize_deliveries(
    raw_deliveries: List[Dict],
    orders_by_order_id: Dict[str, Dict],
) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Notas de entrega normalizadas.

    Returns:
        (deliveries_built, delivery_by_order_id).
    """
    built_list: List[Dict] = []
    delivery_by_order_id: Dict[str, Dict] = {}
    for raw_del in raw_deliveries:
        order_header = orders_by_order_id.get(raw_del.get("order_id", ""), {})
        built = build_delivery_note(adapt_raw_delivery(raw_del), order_header)
        built_list.append(built)
        delivery_by_order_id[raw_del.get("order_id", "")] = built
    return built_list, delivery_by_order_id


def normalize_invoices(
    raw_sales: List[Dict],
    sales_headers: List[Dict],
    lines_by_sale_id: Dict[str, List[Dict]],
    delivery_by_order_id: Dict[str, Dict],
) -> List[Dict]:
    """Faturas para TODOS os canais (ecommerce: data de entrega; tienda: pedido).

    delivery_by_order_id pode não conter o pedido (tienda) → delivery=None.
    """
    invoices: List[Dict] = []
    for sale, sale_hdr in zip(raw_sales, sales_headers):
        sale_id = sale_hdr.get("sale_id")
        lines = lines_by_sale_id.get(sale_id, [])
        delivery = delivery_by_order_id.get(sale["order_id"])
        invoices.append(build_invoice(sale_hdr, lines, delivery))
    return invoices
