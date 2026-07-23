"""
generators/inventory.py
Gera o estado inicial do estoque nos centros de distribuição e lojas Mercadona.
"""

import random
from typing import List, Dict


# ---------------------------------------------------------------------------
# Centros de distribuição e densidade regional
# ---------------------------------------------------------------------------

# stock_weight = fração da DEMANDA NACIONAL que cada DC atende, derivada do
# mapeamento region_to_dc × customer_regions (config.py). Antes os pesos eram
# arbitrários (MAD 0.32, BCN 0.28, …) e NÃO batiam com a demanda: o DC_ZGZ
# atendia ~18% da demanda (7 CCAAs) com só 10% do estoque → 58% dos SKUs a zero.
# Alinhar estoque à demanda é o que mantém a disponibilidade ~97% em escala.
#   MAD: Madrid+CyL+CLM+Extremadura      ≈ 0.274
#   SEV: Andalucía+Canarias+Ceuta+Melilla≈ 0.226
#   ZGZ: Aragón+Navarra+Rioja+PV+Cant+Ast+Galicia ≈ 0.181
#   VLC: C.Valenciana+Murcia+Baleares    ≈ 0.161
#   BCN: Cataluña                        ≈ 0.158
DISTRIBUTION_CENTERS: List[Dict] = [
    {
        "dc_id": "DC_MAD",
        "name": "Centro de Distribuição Madrid",
        "city": "Madrid",
        "region": "Madrid",
        "latitude": 40.4168,
        "longitude": -3.7038,
        # Fração da demanda nacional atendida por este DC (region_to_dc × densidade)
        "stock_weight": 0.274,
    },
    {
        "dc_id": "DC_BCN",
        "name": "Centro de Distribuição Barcelona",
        "city": "Barcelona",
        "region": "Cataluña",
        "latitude": 41.3851,
        "longitude": 2.1734,
        "stock_weight": 0.158,
    },
    {
        "dc_id": "DC_VLC",
        "name": "Centro de Distribuição Valencia",
        "city": "Valencia",
        "region": "Comunitat Valenciana",
        "latitude": 39.4699,
        "longitude": -0.3763,
        "stock_weight": 0.161,
    },
    {
        "dc_id": "DC_SEV",
        "name": "Centro de Distribuição Sevilla",
        "city": "Sevilla",
        "region": "Andalucía",
        "latitude": 37.3891,
        "longitude": -5.9845,
        "stock_weight": 0.226,
    },
    {
        "dc_id": "DC_ZGZ",
        "name": "Centro de Distribuição Zaragoza",
        "city": "Zaragoza",
        "region": "Aragón",
        "latitude": 41.6488,
        "longitude": -0.8891,
        "stock_weight": 0.181,
    },
]

# Multiplicadores de custo por DC (reflexo de custos operacionais locais)
_COST_MULTIPLIERS = {
    "DC_MAD": 1.08,
    "DC_BCN": 1.10,
    "DC_VLC": 1.00,
    "DC_SEV": 0.96,
    "DC_ZGZ": 0.98,
}


def get_distribution_centers() -> List[Dict]:
    """Retorna a lista canônica de centros de distribuição espanhóis."""
    return [dc.copy() for dc in DISTRIBUTION_CENTERS]


# Alias legado para não quebrar imports existentes
get_warehouses = get_distribution_centers


def generate_dc_stock(
    products: List[Dict],
    distribution_centers: List[Dict] = None,
    seed: int = None,
    base_max_stock: int = 1800,
    base_reorder_fraction: float = 0.32,
) -> List[Dict]:
    """
    Gera o estado inicial do estoque para cada combinação produto × centro de distribuição.

    O estoque é distribuído proporcionalmente ao ``stock_weight`` do DC,
    simulando que grandes centros urbanos mantêm mais mercadoria.

    Args:
        products:             Lista de dicts de produtos (precisa de ``product_id``
                              e, opcionalmente, ``price`` para calcular ``unit_cost``).
        distribution_centers: Lista de dicts de DCs. Se None, usa os 5 centros
                              de distribuição espanhóis padrão.
        seed:                 Semente para reprodutibilidade.
        base_max_stock:       Teto máximo de unidades por produto por DC.
        base_reorder_fraction: Fracção de ``max_stock`` usada como ponto de reposição.

    Returns:
        Lista de dicts com os campos:
            stock_id, product_id, location_type, location_id, dc_id,
            quantity_on_hand, reorder_point, max_stock, unit_cost, last_updated
    """
    # RNG isolado e seedado — NÃO reseta o `random` global (antes
    # `random.seed(seed)` vazava estado para outros geradores/engine).
    rng = random.Random(seed)

    if distribution_centers is None:
        distribution_centers = get_distribution_centers()

    # Normaliza pesos para garantir soma = 1
    total_weight = sum(dc.get("stock_weight", 1.0) for dc in distribution_centers)
    norm_weights = [dc.get("stock_weight", 1.0) / total_weight for dc in distribution_centers]

    stock_records: List[Dict] = []
    stock_counter = 1

    for product in products:
        product_id = product.get("product_id", f"PROD_{stock_counter:06d}")

        # Custo unitário base: usa o cost_price (líquido) do produto enriquecido
        # quando disponível — mantém o custo de compra coerente com o COGS dos
        # marts. Fallback: estima a partir do preço quando não houver cost_price.
        base_cost = product.get("cost_price", 0) or 0
        if base_cost <= 0:
            raw_price = product.get("price", 0)
            try:
                sale_price = float(str(raw_price).replace(",", "."))
            except (ValueError, TypeError):
                sale_price = 0.0
            if sale_price <= 0:
                sale_price = round(rng.uniform(1.5, 50.0), 2)
            base_cost = round(sale_price * rng.uniform(0.65, 0.78), 4)

        # max_stock varia ±30 % entre produtos para simular diferentes SKUs
        product_max = max(10, int(base_max_stock * rng.uniform(0.7, 1.3)))

        for dc, weight in zip(distribution_centers, norm_weights):
            dc_id = dc["dc_id"]
            city = dc.get("city", dc_id)

            # Estoque máximo proporcional ao peso do DC
            max_stock = max(5, round(product_max * weight * rng.uniform(0.85, 1.15)))

            # Ponto de reposição: entre 15 % e 30 % do máximo
            reorder_frac = rng.uniform(
                base_reorder_fraction * 0.75,
                base_reorder_fraction * 1.50,
            )
            reorder_point = max(2, round(max_stock * reorder_frac))

            # Estoque inicial — DCs operam com estoque de segurança, então a
            # ruptura literal (zero) no centro é rara; a maioria está saudável.
            roll = rng.random()
            if roll < 0.03:
                # ~3 %: ruptura no DC
                qty_on_hand = 0
            elif roll < 0.12:
                # ~9 %: abaixo do ponto de reposição (PO já a caminho)
                qty_on_hand = rng.randint(1, max(1, reorder_point - 1))
            elif roll < 0.42:
                # ~30 %: estoque médio (entre reorder e 60% do máx)
                qty_on_hand = rng.randint(reorder_point, max(reorder_point + 1, int(max_stock * 0.60)))
            else:
                # ~58 %: estoque saudável
                qty_on_hand = rng.randint(int(max_stock * 0.55), max_stock)

            # Custo unitário ajustado pelo multiplicador do DC
            cost_mult = _COST_MULTIPLIERS.get(dc_id, 1.0)
            unit_cost = round(base_cost * cost_mult * rng.uniform(0.97, 1.03), 4)

            stock_records.append({
                "stock_id": f"STK_{stock_counter:08d}",
                "product_id": product_id,
                "location_type": "DC",
                "location_id": dc_id,
                "dc_id": dc_id,
                "warehouse_city": city,   # mantido para retrocompatibilidade
                "quantity_on_hand": qty_on_hand,
                "reorder_point": reorder_point,
                "max_stock": max_stock,
                "unit_cost": unit_cost,
                "last_updated": "2024-01-01",
            })
            stock_counter += 1

    return stock_records


# Alias legado para não quebrar imports existentes
generate_stock = generate_dc_stock


def generate_store_stock(
    products: List[Dict],
    stores: List[Dict],
    seed: int = None,
    catalog_fraction: float = 0.50,
    base_reorder_point_range: tuple = (2, 6),
) -> List[Dict]:
    """
    Gera o estado inicial do estoque para cada combinação produto × loja.

    Cada loja recebe ~50 % do catálogo de produtos, com quantidades proporcionais
    ao tamanho da loja (sqm). Volume esperado: 150 lojas × ~50 % produtos.

    Args:
        products:               Lista de dicts de produtos (precisa de ``product_id``
                                e opcionalmente ``price``).
        stores:                 Lista de dicts de lojas (gerados por generate_stores()).
                                Precisa de ``store_id``, ``dc_id``, ``sqm``.
        seed:                   Semente para reprodutibilidade.
        catalog_fraction:       Fração do catálogo presente em cada loja (padrão 0.50).
        base_reorder_point_range: Faixa (min, max) para reorder_point nas lojas.

    Returns:
        Lista de dicts com os campos:
            stock_id, product_id, location_type, location_id, dc_id,
            quantity_on_hand, reorder_point, max_stock, unit_cost, last_updated
    """
    rng = random.Random(seed)

    # Pré-calcular custo base dos produtos (prefere cost_price líquido do produto
    # enriquecido; fallback estima a partir do preço).
    product_costs: Dict[str, float] = {}
    for product in products:
        base_cost = product.get("cost_price", 0) or 0
        if base_cost <= 0:
            raw_price = product.get("price", 0)
            try:
                sale_price = float(str(raw_price).replace(",", "."))
            except (ValueError, TypeError):
                sale_price = 0.0
            if sale_price <= 0:
                sale_price = round(rng.uniform(1.5, 50.0), 2)
            base_cost = round(sale_price * rng.uniform(0.65, 0.78), 4)
        product_costs[product.get("product_id", "")] = base_cost

    stock_records: List[Dict] = []
    stock_counter = 1

    for store in stores:
        store_id = store["store_id"]
        dc_id = store.get("dc_id", "DC_MAD")
        sqm = store.get("sqm", 1500)

        # Seleciona ~catalog_fraction do catálogo para esta loja
        num_products = max(1, round(len(products) * catalog_fraction))
        store_products = rng.sample(products, k=min(num_products, len(products)))

        for product in store_products:
            product_id = product.get("product_id", f"PROD_{stock_counter:06d}")
            base_cost = product_costs.get(product_id, 5.0)

            # max_stock proporcional ao sqm (lojas maiores estoam mais)
            # Base: sqm // 250 × fator aleatório por SKU — estoque enxuto para
            # gerar rupturas realistas (~3-7% fill rate gap) com lead time de 6-14d
            max_stock = max(3, round((sqm // 250) * rng.uniform(0.7, 1.4)))

            # reorder_point menor que no CD (5-15 unidades)
            rp_min, rp_max = base_reorder_point_range
            reorder_point = rng.randint(rp_min, rp_max)
            reorder_point = min(reorder_point, max(1, max_stock - 1))

            # Estoque inicial nas lojas — operação enxuta: rupturas frequentes
            # são normais em supermercados (3-7% de fill rate gap é realista).
            roll = rng.random()
            if roll < 0.12:
                # ~12 %: ruptura na loja (prateleira vazia)
                qty_on_hand = 0
            elif roll < 0.30:
                # ~18 %: abaixo do ponto de reposição
                qty_on_hand = rng.randint(1, max(1, reorder_point - 1))
            elif roll < 0.58:
                # ~28 %: estoque médio
                qty_on_hand = rng.randint(reorder_point, max(reorder_point + 1, max_stock // 2))
            else:
                # ~42 %: estoque saudável
                qty_on_hand = rng.randint(max_stock // 2, max_stock)

            # Custo unitário com pequena variação por loja
            cost_mult = _COST_MULTIPLIERS.get(dc_id, 1.0)
            unit_cost = round(base_cost * cost_mult * rng.uniform(0.97, 1.03), 4)

            stock_records.append({
                "stock_id": f"STK_{stock_counter:08d}",
                "product_id": product_id,
                "location_type": "STORE",
                "location_id": store_id,
                "dc_id": dc_id,
                "quantity_on_hand": qty_on_hand,
                "reorder_point": reorder_point,
                "max_stock": max_stock,
                "unit_cost": unit_cost,
                "last_updated": "2024-01-01",
            })
            stock_counter += 1

    return stock_records
