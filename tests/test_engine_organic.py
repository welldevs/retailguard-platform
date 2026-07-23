"""
test_engine_organic.py
======================
Invariantes de ORGANICIDADE do motor de simulação — protegem o comportamento de
"varejo real" contra regressões (a cesta já esteve invertida: 1,6 itens/pedido e
~15 unidades por linha; estes testes garantem que não volte a quebrar).

Roda uma simulação pequena (poucos clientes, poucos dias) com seed fixa e valida:
  - cesta com MUITOS itens distintos e POUCAS unidades por linha;
  - atendimento coerente (entregue ≤ pedido);
  - conservação de estoque (recebimento = entrada; transferência IN = OUT);
  - disponibilidade (fill rate) alta.
"""

import pytest

from erp.generators.stores import generate_stores
from erp.generators.customers import generate_customers
from erp.generators.suppliers import generate_suppliers
from erp.generators.inventory import (
    get_distribution_centers,
    generate_dc_stock,
    generate_store_stock,
)
from erp.simulator.engine import SimulationEngine
from erp.simulator.schema import build_products
from erp.simulator.config import DEFAULT_CONFIG


@pytest.fixture(scope="module")
def sim_result(demo_postal_codes):
    """Roda uma simulação pequena e determinística (seed=42, 180 dias, 300 clientes).

    Janela de 180d (não 30d) para amortizar o cold-start: a reposição leva
    6-14d (transferência CD→loja) + lead de PO, então as primeiras ~2 semanas
    têm fill rate baixo por estoque inicial finito. Com a revisão orgânica
    (stockout memory + market shocks), o steady-state estabiliza em ~0.90 —
    medir só 30d capturaria majoritariamente o warmup.
    """
    seed = 42
    stores = generate_stores(demo_postal_codes, num_stores=6, seed=seed)
    customers = generate_customers(300, demo_postal_codes, seed=seed, stores=stores)
    suppliers = generate_suppliers(8, seed=seed)

    # Catálogo determinístico (com price/category) → enriquecido com tax/cost líquidos
    raw_products = [
        {
            "product_id": f"PROD_{i:06d}",
            "sku": f"SKU_{i}",
            "name": f"Producto {i}",
            "brand": "Hacendado",
            "category": ["lacteos", "bebidas", "snacks", "conservas",
                         "carne_pescado", "higiene_personal", "limpieza_hogar"][i % 7],
            "price": round(1.0 + (i % 20) * 0.5, 2),
            "active": True,
        }
        for i in range(1, 201)
    ]
    products = build_products(raw_products)

    dcs = get_distribution_centers()
    stock = (
        generate_dc_stock(products, dcs, seed=seed)
        + generate_store_stock(products, stores, seed=seed)
    )

    cfg = {**DEFAULT_CONFIG, "start_date": "2025-06-01", "end_date": "2025-11-27",
           "num_customers": 300, "random_seed": seed}
    engine = SimulationEngine(
        products=products, customers=customers, suppliers=suppliers,
        stock=stock, stores=stores, distribution_centers=dcs, config=cfg,
    )
    return engine.run(config=cfg)


def _basket_stats(result):
    lines_by_order = {}
    for sl in result.sale_lines:
        lines_by_order.setdefault(sl["order_id"], []).append(sl)
    n_orders = len(lines_by_order)
    n_lines = len(result.sale_lines)
    n_units = sum(sl["quantity"] for sl in result.sale_lines)
    return n_orders, n_lines, n_units


def test_simulation_produces_sales(sim_result):
    assert len(sim_result.sales) > 0, "A simulação deve gerar vendas"
    assert len(sim_result.sale_lines) > 0, "A simulação deve gerar linhas de venda"


def test_basket_has_many_distinct_items(sim_result):
    """Cesta orgânica: vários itens distintos por pedido (não 1-2)."""
    n_orders, n_lines, _ = _basket_stats(sim_result)
    avg_lines = n_lines / n_orders
    assert avg_lines >= 4.0, (
        f"Cesta deve ter muitos itens distintos (média {avg_lines:.2f} < 4 — "
        "regressão: cesta voltou a empilhar poucos SKUs)"
    )


def test_line_quantity_is_small(sim_result):
    """Unidades por linha pequenas (1-3 típico), nunca empilhando dezenas."""
    n_orders, n_lines, n_units = _basket_stats(sim_result)
    avg_units_per_line = n_units / n_lines
    max_qty = max(sl["quantity"] for sl in sim_result.sale_lines)
    assert avg_units_per_line < 5.0, (
        f"Unidades/linha deve ser pequeno (média {avg_units_per_line:.2f} ≥ 5 — "
        "regressão: voltou a calcular qty = ticket/preço)"
    )
    assert max_qty <= DEFAULT_CONFIG["order_qty_max"], (
        f"qty máxima por linha ({max_qty}) excede o teto {DEFAULT_CONFIG['order_qty_max']}"
    )


def test_delivered_not_exceeding_ordered(sim_result):
    """Atendimento coerente: entregue ≤ pedido em toda linha."""
    for sl in sim_result.sale_lines:
        assert sl["quantity_delivered"] <= sl["quantity_ordered"], (
            f"quantity_delivered > quantity_ordered na linha {sl.get('item_id')}"
        )


def test_transfers_conserve_units(sim_result):
    """Transferência CD→Loja conserva unidades: total IN == total OUT."""
    tin = sum(m["quantity_delta"] for m in sim_result.stock_movements
              if m["reason"] == "transfer_in")
    tout = -sum(m["quantity_delta"] for m in sim_result.stock_movements
                if m["reason"] == "transfer_out")
    assert tin == tout, f"Transferências não conservam: IN={tin} != OUT={tout}"


def test_receipts_reconcile_with_stock_in(sim_result):
    """Sem estoque fantasma: unidades recebidas == entrada de estoque por recebimento."""
    received = sum(gr["quantity_received"] for gr in sim_result.goods_receipts)
    stock_in = sum(m["quantity_delta"] for m in sim_result.stock_movements
                   if m["reason"] == "receipt")
    assert received == stock_in, (
        f"Recebimentos ({received}) != entrada de estoque ({stock_in}) — estoque fantasma"
    )


def test_availability_fill_rate_is_high(sim_result):
    """Disponibilidade (entregue / demandado) realista para supermercado.

    Piso de 0.80: a revisão orgânica (stockout memory + market shocks +
    recalibração de inventário) reduziu o fill rate DE PROPÓSITO, saindo do
    irreal ~99.7% para uma faixa crível. Nesta escala pequena (300 clientes,
    6 lojas, 180d) o steady-state fica ~0.82; a 10k clientes o MART_FILL_RATE_MENSAL
    fica em ~84-96%. O teste garante apenas que a disponibilidade não desaba
    (estoque mal dimensionado), não um alvo de >90%.
    """
    delivered = sum(sl["quantity_delivered"] for sl in sim_result.sale_lines)
    unmet = sum(so["quantity_requested"] for so in sim_result.stockouts)
    fill = delivered / (delivered + unmet) if (delivered + unmet) else 1.0
    assert fill > 0.80, f"Fill rate de disponibilidade {fill:.3f} ≤ 0.80 (estoque mal dimensionado)"
