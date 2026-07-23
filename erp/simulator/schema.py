"""
simulator/schema.py
===================
Funções de normalização de dados brutos do SimulationEngine em tabelas que
simulam a saída de um ERP real (estilo SAP / Odoo / Dynamics 365).

Fluxo de uso típico:

    # Master data (gerado uma única vez, antes da simulação)
    products  = build_products(raw_products)
    customers = build_customers(raw_customers)
    suppliers = build_suppliers(raw_suppliers)
    stores    = build_stores(raw_stores)

    # Índices rápidos de lookup
    products_index  = {p["product_id"]: p for p in products}
    customers_index = {c["customer_id"]: c for c in customers}
    suppliers_index = {s["supplier_id"]: s for s in suppliers}

    # Dados transacionais (gerados depois de rodar engine.run())
    for raw_order, raw_items in zip(result.orders, grouped_items):
        customer = customers_index[raw_order["customer_id"]]
        header   = build_sale_order_header(raw_order, customer)
        lines    = build_sale_order_lines(raw_order, raw_items, products_index)
        delivery = build_delivery_note(raw_delivery, header)
        invoice  = build_invoice(header, delivery)

    # Snapshot diário de estoque
    snapshot = build_stock_snapshot(engine.stock_index, "2024-12-31")

Princípios:
    - Python puro, stdlib apenas.
    - Todas as funções são puras: mesmo input → mesmo output (dado uma seed fixa).
    - Tipos de retorno: sempre list[dict] ou dict.
"""

import random
import hashlib
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constantes ERP
# ---------------------------------------------------------------------------

# IVA espanhol: alíquotas vigentes
_IVA_RATES: Dict[str, float] = {
    "general":      0.21,   # artigos de higiene, limpieza, eletrónica, etc.
    "reducido":     0.10,   # alimentos em geral, restauração, transporte
    "superreducido": 0.04,  # pão, leite, ovos, frutas, produtos infantis essenciais
}

# Mapeamento de categoria ERP → alíquota IVA
_CATEGORY_TAX_MAP: Dict[str, float] = {
    # Tipo superreducido (4%)
    "pan":              0.04,
    "panaderia":        0.04,
    "infantil":         0.04,
    "lacteos":          0.04,
    # Tipo reducido (10%)
    "alimentos":        0.10,
    "bebidas":          0.10,
    "conservas":        0.10,
    "carne_pescado":    0.10,
    "congelados":       0.10,
    "saludable_fitness": 0.10,
    "snacks":           0.10,
    # Tipo general (21%)
    "higiene":          0.21,
    "higiene_personal": 0.21,
    "limpieza":         0.21,
    "limpieza_hogar":   0.21,
    "electronica":      0.21,
    "otros":            0.21,
}

# Vida útil (dias) por TOKEN de categoria perecível (frescos). O catálogo real
# usa nomes de categoria em espanhol ("Carne", "Pescado y marisco", "Yogures",
# "Frutas"…), por isso casamos por token contido no nome normalizado. Pega-se a
# menor vida útil entre os tokens que casam (sinal mais perecível vence).
# Categorias sem token → não-perecível (shelf_life_days=None, is_perishable=0).
_SHELF_LIFE_DAYS: Dict[str, int] = {
    "pan":         2,
    "panaderia":   2,
    "bolleria":    3,
    "pasteleria":  3,
    "carne":       4,
    "pollo":       4,
    "pavo":        4,
    "pescado":     3,
    "marisco":     3,
    "charcuteria": 7,
    "fiambre":     7,
    "fruta":       5,
    "verdura":     5,
    "hortaliza":   5,
    "ensalada":    4,
    "lacteo":      12,
    "leche":       10,
    "yogur":       18,
    "queso":       20,
    "huevo":       21,
    "mantequilla": 30,
    "refrigerad":  7,
    "fresco":      5,
    "congelad":    180,
    "helado":      180,
}

# Unidades de medida por categoria
_CATEGORY_UOM_MAP: Dict[str, str] = {
    "lacteos":          "L",
    "bebidas":          "L",
    "carne_pescado":    "KG",
    "congelados":       "KG",
    "panaderia":        "UND",
    "pan":              "UND",
    "snacks":           "UND",
    "conservas":        "UND",
    "higiene_personal": "UND",
    "higiene":          "UND",
    "limpieza_hogar":   "L",
    "limpieza":         "L",
    "infantil":         "UND",
    "saludable_fitness": "UND",
    "electronica":      "UND",
    "otros":            "UND",
}

# Crédito e prazo por segmento de cliente
_SEGMENT_CREDIT: Dict[str, float] = {
    "Bronze":   500.0,
    "Silver":   1500.0,
    "Gold":     3000.0,
    "Platinum": 8000.0,
}

_SEGMENT_PAYMENT_DAYS: Dict[str, int] = {
    "Bronze":   0,
    "Silver":   0,
    "Gold":     15,
    "Platinum": 30,
}

# Desconto por segmento (máx %)
_SEGMENT_DISCOUNT_MAX: Dict[str, float] = {
    "Bronze":   0.0,
    "Silver":   0.02,
    "Gold":     0.04,
    "Platinum": 0.05,
}

# Transportadoras espanholas — perfil de fiabilidade (share, on_time, max_delay_days)
_CARRIER_PROFILES: Dict[str, Dict] = {
    "MRW":             {"share": 0.38, "on_time": 0.96, "max_delay_days": 2},
    "SEUR":            {"share": 0.30, "on_time": 0.94, "max_delay_days": 3},
    "GLS":             {"share": 0.22, "on_time": 0.92, "max_delay_days": 3},
    "Correos Express": {"share": 0.10, "on_time": 0.89, "max_delay_days": 4},
}
_CARRIERS: List[str] = list(_CARRIER_PROFILES.keys())

# Margens brutas por categoria: cost_ratio = cost_price / sale_price
# (token de categoria → intervalo [min, max])
_CATEGORY_COST_RATIO_RANGES: Dict[str, tuple] = {
    "bebidas":          (0.88, 0.92),  # 8-12% margem (bebidas = alta rotação, baixa margem)
    "agua":             (0.86, 0.91),  # 9-14%
    "cerveza":          (0.85, 0.90),  # 10-15%
    "vino":             (0.82, 0.88),  # 12-18%
    "carne":            (0.75, 0.83),  # 17-25%
    "pescado":          (0.74, 0.82),  # 18-26%
    "lacteo":           (0.72, 0.80),  # 20-28%
    "fruta":            (0.70, 0.78),  # 22-30%
    "verdura":          (0.70, 0.78),  # 22-30%
    "hortaliz":         (0.70, 0.78),  # 22-30%
    "pan":              (0.76, 0.83),  # 17-24% (âncora de tráfego)
    "panaderia":        (0.76, 0.83),  # 17-24%
    "bolleria":         (0.72, 0.80),  # 20-28%
    "congelado":        (0.68, 0.76),  # 24-32%
    "conserva":         (0.62, 0.72),  # 28-38%
    "enlatado":         (0.62, 0.72),  # 28-38%
    "snack":            (0.63, 0.72),  # 28-37%
    "galleta":          (0.64, 0.73),  # 27-36%
    "chocolate":        (0.62, 0.72),  # 28-38%
    "limpieza":         (0.58, 0.68),  # 32-42% (limpeza do lar)
    "detergent":        (0.58, 0.68),  # 32-42%
    "suavizant":        (0.58, 0.68),  # 32-42%
    "higiene":          (0.55, 0.62),  # 38-45% (higiene pessoal — maior margem)
    "cosmetico":        (0.55, 0.62),  # 38-45%
    "perfum":           (0.52, 0.62),  # 38-48%
    "desodor":          (0.55, 0.63),  # 37-45%
    "champu":           (0.55, 0.63),  # 37-45%
    "bucal":            (0.55, 0.63),  # 37-45% (higiene bucal)
    "dental":           (0.55, 0.63),  # 37-45%
    "afeit":            (0.55, 0.63),  # 37-45% (gel/espuma de afeitar)
    "corporal":         (0.56, 0.63),  # 37-44% (crema corporal, gel de baño)
    "facial":           (0.54, 0.62),  # 38-46% (gel/crema facial)
    "intim":            (0.55, 0.63),  # 37-45% (gel íntimo)
    "depilat":          (0.54, 0.62),  # 38-46% (crema depilatoria)
    "repelent":         (0.52, 0.62),  # 38-48%
    "solar":            (0.52, 0.62),  # 38-48% (protector solar)
    "toallita":         (0.56, 0.64),  # 36-44%
    "bebe":             (0.65, 0.75),  # 25-35% (infantil)
    "infantil":         (0.65, 0.75),  # 25-35%
    "pet":              (0.60, 0.70),  # 30-40% (pet food — margem premium)
    "mascota":          (0.60, 0.70),  # 30-40%
    "saludable":        (0.62, 0.72),  # 28-38% (produtos health/fitness)
    "fitness":          (0.60, 0.70),  # 30-40%
    "electronica":      (0.72, 0.82),  # 18-28%
}

# Incoterms habituais em importações europeias
_INCOTERMS: List[str] = ["EXW", "FCA", "CIF", "DAP"]

# Termos de pagamento a fornecedores
_PAYMENT_TERMS: List[str] = ["30D", "45D", "60D", "90D"]

# Tipos IVA contabilístico espanhol
_IVA_TYPE_MAP: Dict[float, str] = {
    0.21: "S1",
    0.10: "S2",
    0.04: "S4",
}


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _rng_for(seed_str: str) -> random.Random:
    """Cria um Random isolado determinístico a partir de uma string (ex: product_id)."""
    digest = int(hashlib.md5(seed_str.encode()).hexdigest(), 16) % (2**32)
    return random.Random(digest)


def _normalize_category(category: str) -> str:
    """Normaliza o nome de categoria para lookup nos mapas acima."""
    return category.strip().lower().replace(" ", "_").replace("-", "_")


def _tax_rate_for_category(category: str) -> float:
    key = _normalize_category(category)
    for map_key, rate in _CATEGORY_TAX_MAP.items():
        if map_key in key or key in map_key:
            return rate
    return _IVA_RATES["general"]


def _uom_for_category(category: str) -> str:
    key = _normalize_category(category)
    for map_key, uom in _CATEGORY_UOM_MAP.items():
        if map_key in key or key in map_key:
            return uom
    return "UND"


def _shelf_life_for_category(category: str):
    """Vida útil (dias) para categorias perecíveis; None se não-perecível.

    Casa por token contido no nome normalizado; se vários tokens casam, retorna
    a MENOR vida útil (o sinal mais perecível prevalece).
    """
    key = _normalize_category(category)
    matches = [days for tok, days in _SHELF_LIFE_DAYS.items() if tok in key]
    return min(matches) if matches else None


def _ean13(seed_str: str) -> str:
    """Gera um EAN-13 sintético (12 dígitos + dígito verificador) de forma determinística."""
    rng = _rng_for(seed_str)
    digits = [rng.randint(0, 9) for _ in range(12)]
    # Dígito verificador EAN-13
    check = (10 - (sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits)) % 10)) % 10
    return "".join(map(str, digits)) + str(check)


def _random_date_between(start_year: int, end_year: int, rng: random.Random) -> str:
    """Retorna uma data ISO aleatória dentro do intervalo [start_year, end_year]."""
    start = date(start_year, 1, 1)
    end   = date(end_year, 12, 31)
    delta = (end - start).days
    return (start + timedelta(days=rng.randint(0, delta))).isoformat()


def _spanish_iban(rng: random.Random) -> str:
    """Gera um IBAN espanhol sintético com 24 caracteres (ES + 22 dígitos)."""
    digits = "".join(str(rng.randint(0, 9)) for _ in range(22))
    return f"ES{digits}"


def _cif_spain(rng: random.Random) -> str:
    """Gera um CIF espanhol sintético no formato 'B12345678'."""
    letters = "ABCDEFGHJKLMNPQRSUVW"
    return f"{rng.choice(letters)}{rng.randint(10000000, 99999999)}"


def _tracking_number(rng: random.Random) -> str:
    """Gera um número de rastreio de 13 dígitos."""
    return "".join(str(rng.randint(0, 9)) for _ in range(13))


def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str[:10], "%Y-%m-%d")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _fmt_ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _payment_term_days(payment_terms: str) -> int:
    """Parseia '30D' → 30, '45D' → 45, etc. Retorna 30 como default."""
    if payment_terms and payment_terms.endswith("D"):
        try:
            return int(payment_terms[:-1])
        except ValueError:
            pass
    return 30


# ---------------------------------------------------------------------------
# 1. Tabelas de Master Data
# ---------------------------------------------------------------------------

def build_products(raw_products: List[Dict]) -> List[Dict]:
    """
    Transforma produtos brutos em tabela de produtos.

    Campos adicionados/transformados:
        barcode           : EAN-13 sintético de 13 dígitos
        cost_price        : 65-80 % do sale_price (margem bruta 20-35 %)
        tax_rate          : 0.04 | 0.10 | 0.21 conforme categoria
        unit_of_measure   : UND | KG | L | PAK conforme categoria
        supplier_code     : código do fornecedor principal
        active_since      : data aleatória determinística entre 2018-2023
        iva_type          : S1 | S2 | S4

    Args:
        raw_products: Lista de produtos gerados por _load_products() em
                      run_simulation.py (campos: product_id, sku, name,
                      brand, category, price, unit, active, ...).

    Returns:
        Lista de dicts enriquecidos — um por produto.
    """
    products: List[Dict] = []

    for product in raw_products:
        prod_id  = product.get("product_id", "")
        category = product.get("category", "otros")
        rng      = _rng_for(prod_id)

        # Alíquota IVA (necessária para derivar o preço líquido)
        tax_rate = _tax_rate_for_category(category)

        # Preço de prateleira (BRUTO, com IVA) — é o que o cliente paga e o que
        # o scraper coleta. Mantido em `price`.
        raw_price = product.get("price", 0)
        try:
            gross_price = float(str(raw_price).replace(",", "."))
        except (ValueError, TypeError):
            gross_price = 0.0
        if gross_price <= 0:
            gross_price = round(rng.uniform(1.5, 50.0), 2)

        # sale_price = preço de venda LÍQUIDO (sem IVA). É a base correta de
        # receita (a receita reconhecida não inclui o imposto repassado).
        sale_price = round(gross_price / (1.0 + tax_rate), 4)

        # Custo de compra por categoria: cada grupo tem uma faixa de cost_ratio
        # (cost/sale) diferente, gerando margens reais por categoria.
        cat_key = _normalize_category(category)
        cost_ratio_range = (0.65, 0.78)  # default (22-35% margem)
        for token, ratio_range in _CATEGORY_COST_RATIO_RANGES.items():
            if token in cat_key:
                cost_ratio_range = ratio_range
                break
        cost_factor = rng.uniform(*cost_ratio_range)
        cost_price  = round(sale_price * cost_factor, 4)

        # Unidade de medida
        raw_uom = _uom_for_category(category)
        # PAK para itens com "pack" ou "caja" no nome
        name_lower = product.get("name", "").lower()
        if any(w in name_lower for w in ("pack", "caja", "lote", "surtido")):
            raw_uom = "PAK"
        uom = raw_uom

        # EAN-13
        barcode = _ean13(prod_id)

        # Fornecedor principal (pode vir do produto ou ser sintetizado)
        raw_supplier = product.get("supplier_id", "")
        if raw_supplier:
            seq = int("".join(filter(str.isdigit, str(raw_supplier))) or "1")
            supplier_code = f"PRV-{seq:05d}"
        else:
            supplier_code = f"PRV-{rng.randint(1, 99):05d}"

        # Data de ativação
        active_since = _random_date_between(2018, 2023, rng)

        # Perecibilidade (frescos) — habilita merma/caducidad no engine
        shelf_life = _shelf_life_for_category(category)

        products.append({
            **product,
            "barcode":          barcode,
            "sale_price":       sale_price,
            "cost_price":       cost_price,
            "tax_rate":         tax_rate,
            "iva_type":         _IVA_TYPE_MAP.get(tax_rate, "S1"),
            "unit_of_measure":  uom,
            "supplier_code":    supplier_code,
            "active_since":     active_since,
            "shelf_life_days":  shelf_life,
            "is_perishable":    1 if shelf_life is not None else 0,
        })

    return products


def build_customers(raw_customers: List[Dict]) -> List[Dict]:
    """
    Transforma clientes brutos em tabela de clientes.

    Campos adicionados/transformados:
        payment_days     : 0 (Bronze/Silver), 15 (Gold), 30 (Platinum)
        nif              : NIF espanhol sintético se não fornecido

    Args:
        raw_customers: Lista de clientes gerados por generate_customers()
                       (campos: customer_id, first_name, last_name, email,
                        phone, postal_code, municipality, province, ccaa,
                        registration_date, segment, nearest_store_id).

    Returns:
        Lista de dicts enriquecidos — um por cliente.
    """
    customers: List[Dict] = []

    for seq, customer in enumerate(raw_customers, start=1):
        cust_id  = customer.get("customer_id", "")
        segment  = customer.get("segment", "Bronze")
        rng      = _rng_for(cust_id)

        # NIF (vem do gerador de clientes se existir)
        nif = customer.get("nif", "")
        if not nif:
            # Gera NIF sintético determinístico
            nif_letters = "TRWAGMYFPDXBNJZSQVHLCKE"
            n = rng.randint(10_000_000, 99_999_999)
            nif = f"{n:08d}{nif_letters[n % 23]}"

        # Prazo de pagamento
        payment_days = _SEGMENT_PAYMENT_DAYS.get(segment, 0)

        customers.append({
            **customer,
            "nif":          nif,
            "payment_days": payment_days,
        })

    return customers


def build_suppliers(raw_suppliers: List[Dict]) -> List[Dict]:
    """
    Transforma fornecedores brutos em tabela de fornecedores.

    Campos adicionados/transformados:
        cif                     : CIF espanhol sintético "B12345678"
        payment_terms           : "30D" | "45D" | "60D" | "90D"
        incoterm                : "EXW" | "FCA" | "CIF" | "DAP"
        currency                : "EUR"
        iban                    : IBAN espanhol sintético "ES{22 dígitos}"
        category_specialization : lista de 1-3 categorias que fornece

    Args:
        raw_suppliers: Lista de fornecedores gerados por generate_suppliers()
                       (campos: supplier_id, name, country, city,
                        lead_time_days, reliability_score,
                        payment_terms_days, contact_email, phone, active).

    Returns:
        Lista de dicts enriquecidos — um por fornecedor.
    """
    _all_categories = [
        "lacteos", "bebidas", "conservas", "panaderia",
        "higiene_personal", "limpieza_hogar", "carne_pescado",
        "congelados", "snacks", "infantil", "saludable_fitness",
    ]

    suppliers: List[Dict] = []

    for seq, supplier in enumerate(raw_suppliers, start=1):
        sup_id = supplier.get("supplier_id", f"SUP_{seq:05d}")
        rng    = _rng_for(sup_id)

        # CIF apenas para fornecedores espanhóis; demais recebem o mesmo formato
        cif = _cif_spain(rng)

        # Prazo de pagamento
        raw_pt_days = supplier.get("payment_terms_days", 30)
        pt_str = f"{raw_pt_days}D"
        if pt_str not in _PAYMENT_TERMS:
            # Mapeia para o mais próximo disponível
            closest = min(_PAYMENT_TERMS, key=lambda x: abs(int(x[:-1]) - raw_pt_days))
            pt_str  = closest
        payment_terms = pt_str

        # Incoterm (varia com o país de origem)
        country = supplier.get("country", "España")
        if country == "España":
            incoterm = rng.choice(["EXW", "FCA"])
        elif country in ("Alemania", "Holanda", "Francia"):
            incoterm = rng.choice(["FCA", "DAP", "CIF"])
        else:
            incoterm = rng.choice(_INCOTERMS)

        # IBAN
        iban = _spanish_iban(rng)

        # Especialização por categoria (1-3 categorias)
        num_cats = rng.randint(1, 3)
        category_specialization = rng.sample(_all_categories, num_cats)

        suppliers.append({
            **supplier,
            "cif":                     cif,
            "payment_terms":           payment_terms,
            "incoterm":                incoterm,
            "currency":                "EUR",
            "iban":                    iban,
            "category_specialization": category_specialization,
        })

    return suppliers


def build_stores(raw_stores: List[Dict]) -> List[Dict]:
    """
    Passthrough; só normaliza tipos.

    Recebe lista de dicts do generators/stores.py e retorna lista
    no schema canônico do RAW (RAW.STORES).

    Args:
        raw_stores: Lista de lojas geradas pelo gerador de lojas.

    Returns:
        Lista de dicts — um por loja.
    """
    return list(raw_stores)


# ---------------------------------------------------------------------------
# 2. Tabelas Transacionais
# ---------------------------------------------------------------------------

def build_sale_order_header(raw_order: Dict, customer: Dict) -> Dict:
    """
    Transforma um pedido de venda bruto em cabeçalho ERP.

    O número de documento segue o padrão "SO-{ano}-{seq:07d}".

    Args:
        raw_order: Dict do engine (campos: order_id, customer_id, order_date,
                   store_id, dc_id, region, num_items, total_amount, status,
                   has_partial_stockout, channel).
        customer:  Dict do cliente (saída de build_customers).

    Returns:
        Dict com campos do cabeçalho de vendas no novo schema.
    """
    order_id   = raw_order.get("order_id", "")
    order_date = raw_order.get("order_date", "2024-01-01")
    rng        = _rng_for(order_id)

    # Extrai ano e sequência numérica do order_id (ex: "ORD_00000042" → seq=42)
    seq_digits = "".join(filter(str.isdigit, order_id))
    seq        = int(seq_digits) if seq_digits else rng.randint(1, 9999999)
    year       = order_date[:4]
    sale_id    = f"SO-{year}-{seq:07d}"

    # Método de pagamento
    segment = customer.get("segment", "Bronze")
    if segment in ("Gold", "Platinum"):
        payment_weights = [0.40, 0.55, 0.05]
    else:
        payment_weights = [0.65, 0.20, 0.15]
    payment_method = rng.choices(
        ["tarjeta", "transferencia", "contrareembolso"],
        weights=payment_weights,
        k=1,
    )[0]

    # Status do pagamento: Platinum/Gold têm prazo; Bronze/Silver pagam na hora
    payment_days = customer.get("payment_days", 0)
    payment_status = "pending" if payment_days > 0 else "paid"

    # Canal de venda: usa valor já calculado pelo engine
    channel = raw_order.get("channel") or ("online" if rng.random() < 0.50 else "tienda")

    # store_id e dc_id: passthrough do engine
    # store_id preenchido se channel='tienda'; dc_id se channel='ecommerce'
    store_id = raw_order.get("store_id")
    dc_id    = raw_order.get("dc_id")

    # Totais — o engine já fornece bruto (total_amount, com IVA) e líquido
    # (total_amount_net, sem IVA) somando o IVA real por produto. O IVA é a
    # diferença. (Antes: subtotal_net recebia o BRUTO e somava +10% por cima,
    # inflando o GMV ~10%+ — corrigido.)
    total_gross  = round(raw_order.get("total_amount", 0.0), 2)
    subtotal_net = round(raw_order.get("total_amount_net", total_gross / 1.10), 2)
    estimated_tax = round(total_gross - subtotal_net, 2)

    # Status do pedido
    raw_status = raw_order.get("status", "confirmed")
    status_map = {
        "confirmed":  "confirmed",
        "delivered":  "delivered",
        "in_transit": "shipped",
        "cancelled":  "cancelled",
    }
    erp_status = status_map.get(raw_status, "confirmed")

    return {
        "sale_id":            sale_id,
        "order_date":         order_date,
        "order_ts":           raw_order.get("order_ts") or f"{order_date}T12:00:00",
        "customer_id":        raw_order.get("customer_id", ""),
        "store_id":           store_id,
        "dc_id":              dc_id,
        "region":             raw_order.get("region", ""),
        "payment_method":     payment_method,
        "payment_status":     payment_status,
        "payment_days":       payment_days,
        "channel":            channel,
        "subtotal_net":       subtotal_net,
        "tax_amount":         estimated_tax,
        "total_gross":        total_gross,
        "status":             erp_status,
        "has_partial_stockout": raw_order.get("has_partial_stockout", False),
        "num_items":          raw_order.get("num_items", 0),
        # Sinal de comportamento individual do cliente (stable/growing/declining)
        # — preservado até o warehouse para análises de churn/tendência.
        "ticket_trend":       raw_order.get("ticket_trend", "stable"),
    }


def build_sale_order_lines(
    raw_order: Dict,
    raw_items: List[Dict],
    products_index: Dict[str, Dict],
) -> List[Dict]:
    """
    Transforma linhas brutas de pedido em linhas de venda.

    Numeração de linha em múltiplos de 10 (padrão SAP).

    Args:
        raw_order:      Dict do cabeçalho bruto do engine.
        raw_items:      Lista de dicts de itens do pedido (campos:
                        item_id, order_id, product_id, quantity,
                        unit_price, line_total).
        products_index: Dict {product_id: product_dict}.

    Returns:
        Lista de dicts — uma linha por item.
    """
    order_id   = raw_order.get("order_id", "")
    order_date = raw_order.get("order_date", "2024-01-01")
    year       = order_date[:4]
    seq_digits = "".join(filter(str.isdigit, order_id))
    seq        = int(seq_digits) if seq_digits else 0
    sale_id    = f"SO-{year}-{seq:07d}"

    lines: List[Dict] = []

    for line_idx, item in enumerate(raw_items, start=1):
        prod_id  = item.get("product_id", "")
        prod     = products_index.get(prod_id, {})

        # Quantidades — pedido vs entregue (o engine faz atendimento parcial
        # quando o estoque não cobre tudo, alimentando o fill rate real).
        qty_ordered   = item.get("quantity_ordered", item.get("quantity", 1))
        qty_delivered = item.get("quantity_delivered", item.get("quantity", qty_ordered))

        # Preço unitário sem IVA
        unit_price_gross = item.get("unit_price", 0.0)
        tax_rate = prod.get("tax_rate", 0.10)
        unit_price_net = round(unit_price_gross / (1.0 + tax_rate), 4)

        # SEM desconto sintético por linha: a receita líquida da linha é
        # qty_delivered × preço líquido, idêntica à soma usada no header
        # (engine.order_total_net). Isso reconcilia GMV header↔lines (antes um
        # desconto aleatório independente divergia das duas fontes).
        discount_pct = 0.0
        line_total_net = round(qty_delivered * unit_price_net, 2)

        lines.append({
            "sale_id":           sale_id,
            "line_number":       line_idx * 10,
            "product_id":        prod_id,
            "quantity_ordered":  qty_ordered,
            "quantity_delivered": qty_delivered,
            "unit_price_net":    unit_price_net,
            "discount_pct":      discount_pct,
            "tax_rate":          tax_rate,
            "line_total_net":    line_total_net,
        })

    return lines


# DEPRECATED — use build_purchase_order_header + build_purchase_order_lines
def build_purchase_order(
    raw_po: Dict,
    supplier: Dict,
    product: Dict,
) -> Dict:
    """
    DEPRECATED: Ordem de compra flat (1 produto/PO).

    O engine agora gera POs via buffer + flush usando
    build_purchase_order_header e build_purchase_order_lines.
    Esta função é mantida apenas para compatibilidade.
    """
    po_id      = raw_po.get("po_id", "")
    order_date = raw_po.get("order_date", "2024-01-01")
    year       = order_date[:4]
    seq_digits = "".join(filter(str.isdigit, po_id))
    seq        = int(seq_digits) if seq_digits else 0
    doc_number = f"PO-{year}-{seq:07d}"

    tax_rate       = product.get("tax_rate", 0.10)
    total_cost_net = round(raw_po.get("total_cost", 0.0), 2)
    total_cost_gross = round(total_cost_net * (1.0 + tax_rate), 2)

    raw_status = raw_po.get("status", "open")
    status_map = {
        "open":     "open",
        "received": "received",
        "partial":  "partially_received",
        "cancelled": "cancelled",
    }
    erp_status = status_map.get(raw_status, "open")
    if raw_po.get("actual_receipt_date"):
        erp_status = "received"

    return {
        "doc_number":             doc_number,
        "po_id":                  po_id,
        "supplier_id":            raw_po.get("supplier_id", ""),
        "supplier_name":          supplier.get("name", raw_po.get("supplier_name", "")),
        "product_id":             raw_po.get("product_id", ""),
        "warehouse_id":           raw_po.get("warehouse_id", ""),
        "order_date":             order_date,
        "quantity_ordered":       raw_po.get("quantity_ordered", 0),
        "unit_cost":              raw_po.get("unit_cost", 0.0),
        "total_cost_net":         total_cost_net,
        "tax_rate":               tax_rate,
        "total_cost_gross":       total_cost_gross,
        "currency":               "EUR",
        "expected_delivery_date": raw_po.get("expected_receipt_date", ""),
        "actual_receipt_date":    raw_po.get("actual_receipt_date"),
        "status":                 erp_status,
        "incoterm":               supplier.get("incoterm", "EXW"),
        "payment_terms":          supplier.get("payment_terms", "30D"),
    }


def build_purchase_order_header(
    po_buffer_entry: Dict,
    supplier: Dict,
    products_index: Dict[str, Dict],
    year: str,
    sequence: int,
) -> Dict:
    """
    Cria o cabeçalho de uma purchase order a partir de um buffer agrupado.

    Args:
        po_buffer_entry: Dict {supplier_id, dc_id, order_date, lines: [...]}.
                         Cada linha tem: product_id, quantity, unit_cost,
                         line_total_net, tax_rate (opcional).
        supplier:        Dict do fornecedor (saída de build_suppliers).
        products_index:  Dict {product_id: product_dict} para lookup de tax_rate.
        year:            Ano da PO (string "2024").
        sequence:        Número sequencial para gerar po_id.

    Returns:
        Dict com campos do cabeçalho PO.
    """
    lines       = po_buffer_entry.get("lines", [])
    order_date  = po_buffer_entry.get("order_date", "2024-01-01")
    lead_days   = supplier.get("lead_time_days", 7)

    try:
        expected_dt = _parse_date(order_date) + timedelta(days=int(lead_days))
        expected_receipt_date = _fmt(expected_dt)
    except (ValueError, TypeError):
        expected_receipt_date = order_date

    # Totais
    total_cost_net = round(sum(line.get("line_total_net", 0.0) for line in lines), 2)

    tax_amount = 0.0
    for line in lines:
        prod_id  = line.get("product_id", "")
        tax_rate = line.get("tax_rate") or products_index.get(prod_id, {}).get("tax_rate", 0.10)
        tax_amount += line.get("line_total_net", 0.0) * tax_rate
    tax_amount = round(tax_amount, 2)

    total_cost_gross = round(total_cost_net + tax_amount, 2)

    return {
        "po_id":                 f"PO-{year}-{sequence:07d}",
        "supplier_id":           supplier.get("supplier_id", po_buffer_entry.get("supplier_id", "")),
        "dc_id":                 po_buffer_entry.get("dc_id", ""),
        "order_date":            order_date,
        "expected_receipt_date": expected_receipt_date,
        "actual_receipt_date":   None,
        "status":                "open",
        "incoterm":              supplier.get("incoterm", "DAP"),
        "payment_terms":         supplier.get("payment_terms", "30D"),
        "currency":              supplier.get("currency", "EUR"),
        "total_cost_net":        total_cost_net,
        "tax_amount":            tax_amount,
        "total_cost_gross":      total_cost_gross,
    }


def build_purchase_order_lines(
    po_id: str,
    po_buffer_entry: Dict,
    products_index: Dict[str, Dict],
) -> List[Dict]:
    """
    Cria as linhas de uma purchase order a partir de um buffer agrupado.

    Args:
        po_id:           ID da PO gerado pelo build_purchase_order_header.
        po_buffer_entry: Dict com chave 'lines': [{product_id, quantity, unit_cost, ...}].
        products_index:  Dict {product_id: product_dict} para lookup de tax_rate.

    Returns:
        Lista de dicts — uma linha por produto.
    """
    lines  = po_buffer_entry.get("lines", [])
    result = []

    for idx, line in enumerate(lines, start=1):
        prod_id   = line.get("product_id", "")
        quantity  = line.get("quantity", 0)
        unit_cost = line.get("unit_cost", 0.0)
        tax_rate  = line.get("tax_rate") or products_index.get(prod_id, {}).get("tax_rate", 0.10)
        line_total_net = round(quantity * unit_cost, 2)

        result.append({
            "po_id":             po_id,
            "line_number":       idx,
            "product_id":        prod_id,
            "quantity_ordered":  quantity,
            "unit_cost":         unit_cost,
            "tax_rate":          tax_rate,
            "line_total_net":    line_total_net,
        })

    return result


def build_supplier_payment(
    po_header: Dict,
    supplier: Dict,
    year: str,
    sequence: int,
) -> Dict:
    """
    Cria um registro de contas a pagar (AP) para uma PO.

    Args:
        po_header:  Dict retornado por build_purchase_order_header.
        supplier:   Dict do fornecedor (saída de build_suppliers).
        year:       Ano do pagamento (string "2024").
        sequence:   Número sequencial para gerar payment_id.

    Returns:
        Dict com campos do pagamento ao fornecedor.
    """
    payment_terms = supplier.get("payment_terms", po_header.get("payment_terms", "30D"))
    obligation    = po_header.get("order_date", "2024-01-01")
    days          = _payment_term_days(payment_terms)

    try:
        due_dt  = _parse_date(obligation) + timedelta(days=days)
        due_date = _fmt(due_dt)
    except (ValueError, TypeError):
        due_date = obligation

    return {
        "payment_id":       f"SP-{year}-{sequence:07d}",
        "po_id":            po_header.get("po_id", ""),
        "supplier_id":      supplier.get("supplier_id", ""),
        "dc_id":            po_header.get("dc_id", ""),
        "obligation_date":  obligation,
        "due_date":         due_date,
        "payment_date":     None,
        "amount_net":       po_header.get("total_cost_net", 0.0),
        "amount_gross":     po_header.get("total_cost_gross", 0.0),
        "status":           "pending",
        "days_late":        0,
    }


def build_product_return(
    return_record: Dict,
    sale_line: Dict,
    customer: Dict,
    year: str,
    sequence: int,
) -> Dict:
    """
    Cria um registro de devolução de produto.

    Args:
        return_record: Dict com campos: product_id, location_type, location_id,
                       return_date, quantity, reason, restocked (opcional).
        sale_line:     Dict da linha de venda original (saída de build_sale_order_lines).
                       Deve ter: sale_id, line_id (opcional), unit_price_net, tax_rate.
        customer:      Dict do cliente.
        year:          Ano da devolução (string "2024").
        sequence:      Número sequencial para gerar return_id.

    Returns:
        Dict com campos da devolução de produto.
    """
    qty_returned   = return_record.get("quantity", 1)
    unit_price_net = sale_line.get("unit_price_net", 0.0)
    tax_rate       = sale_line.get("tax_rate", 0.10)
    refund_amount  = round(unit_price_net * qty_returned * (1.0 + tax_rate), 2)

    return {
        "return_id":         f"RET-{year}-{sequence:07d}",
        "sale_id":           sale_line.get("sale_id", ""),
        "sale_line_id":      sale_line.get("line_id"),
        "product_id":        return_record.get("product_id", ""),
        "customer_id":       customer.get("customer_id", ""),
        "location_type":     return_record.get("location_type", "DC"),
        "location_id":       return_record.get("location_id", ""),
        "return_date":       return_record.get("return_date", ""),
        "quantity_returned": qty_returned,
        "unit_price_net":    unit_price_net,
        "refund_amount":     refund_amount,
        "reason":            return_record.get("reason", ""),
        "restocked":         1 if return_record.get("restocked", True) else 0,
    }


def build_delivery_note(raw_delivery: Dict, order_header: Dict) -> Dict:
    """
    Cria uma nota de entrega / guia de transporte a partir de uma entrega bruta.

    Args:
        raw_delivery:  Dict do engine (campos: delivery_id, order_date,
                       scheduled_delivery_date, actual_delivery_date,
                       status, total_amount).
        order_header:  Dict do cabeçalho SO (saída de build_sale_order_header).

    Returns:
        Dict com campos da nota de entrega no novo schema.
    """
    del_id      = raw_delivery.get("delivery_id", "")
    order_date  = raw_delivery.get("order_date", "2024-01-01")
    year        = order_date[:4]
    seq_digits  = "".join(filter(str.isdigit, del_id))
    seq         = int(seq_digits) if seq_digits else 0
    delivery_id = f"ALB-{year}-{seq:07d}"
    rng         = _rng_for(del_id)

    # Transportadora — seleção ponderada pelo market share
    carriers = list(_CARRIER_PROFILES.keys())
    weights  = [_CARRIER_PROFILES[c]["share"] for c in carriers]
    carrier  = rng.choices(carriers, weights=weights, k=1)[0]

    # Número de rastreio
    tracking = _tracking_number(rng)

    # Datas
    dispatch_date  = raw_delivery.get("order_date", order_date)
    estimated_date = raw_delivery.get("scheduled_delivery_date", "")
    actual_date    = raw_delivery.get("actual_delivery_date")

    # Aplicar probabilidade de atraso por transportadora
    profile = _CARRIER_PROFILES[carrier]
    if actual_date and estimated_date and rng.random() > profile["on_time"]:
        delay_days = rng.randint(1, profile["max_delay_days"])
        try:
            from datetime import date as _date, timedelta as _td
            actual_date = (_date.fromisoformat(actual_date) + _td(days=delay_days)).isoformat()
        except (ValueError, AttributeError):
            pass

    # Status
    raw_status = raw_delivery.get("status", "in_transit")
    status_map = {
        "in_transit": "in_transit",
        "delivered":  "delivered",
        "pending":    "pending",
        "failed":     "failed",
    }
    delivery_status = status_map.get(raw_status, "in_transit")

    # Peso estimado (0.3 kg por item)
    num_items  = order_header.get("num_items", raw_delivery.get("num_items", 1))
    weight_kg  = round(0.3 * max(1, num_items), 2)

    # Assinatura requerida se total > 100 €
    total_amount       = raw_delivery.get("total_amount", 0.0)
    signature_required = total_amount > 100.0

    return {
        "delivery_id":             delivery_id,
        "sale_id":                 order_header.get("sale_id", raw_delivery.get("order_id", "")),
        "dc_id":                   raw_delivery.get("dc_id", order_header.get("dc_id", "")),
        "carrier":                 carrier,
        "tracking_number":         tracking,
        "dispatch_date":           dispatch_date,
        "estimated_delivery_date": estimated_date,
        "actual_delivery_date":    actual_date,
        "delivery_status":         delivery_status,
        "weight_kg":               weight_kg,
        "packages":                1,
        "signature_required":      signature_required,
        "total_amount":            round(total_amount, 2),
    }


def build_invoice(
    sale_order: Dict,
    sale_lines: List[Dict],
    delivery: Optional[Dict] = None,
) -> Dict:
    """
    Gera a fatura de uma venda — para TODOS os canais (corrige o bug em que só
    pedidos ecommerce eram faturados, deixando toda a venda em loja física sem
    invoice).

    - ecommerce: faturada na data de entrega (real, senão estimada);
    - tienda:    faturada na data do pedido (`delivery_id` = NULL).

    A desagregação do IVA é calculada a partir das LINHAS reais por alíquota
    (4 / 10 / 21 %), não estimada 100 % no bracket de 10 %.

    Args:
        sale_order: Cabeçalho SO (saída de build_sale_order_header).
        sale_lines: Linhas da MESMA venda (saída de build_sale_order_lines).
        delivery:   Nota de entrega (ecommerce) ou None (tienda).
    """
    sale_id    = sale_order.get("sale_id", "")
    year       = sale_id[3:7] if len(sale_id) >= 7 else "2024"
    seq_str    = sale_id.rsplit("-", 1)[-1] if "-" in sale_id else "0"
    seq        = int(seq_str) if seq_str.isdigit() else 0
    invoice_id = f"FAC-{year}-{seq:07d}"
    rng        = _rng_for(invoice_id)

    delivery = delivery or {}

    # Data da fatura: entrega (ecommerce) ou data do pedido (tienda)
    actual_del   = delivery.get("actual_delivery_date")
    est_del      = delivery.get("estimated_delivery_date")
    invoice_date = actual_del or est_del or sale_order.get("order_date", "2024-01-01")

    # Desagregação REAL do IVA por alíquota, a partir das linhas da venda
    _bracket = {0.04: "4%", 0.10: "10%", 0.21: "21%"}
    tax_breakdown = {"4%": 0.0, "10%": 0.0, "21%": 0.0}
    subtotal_net = 0.0
    for ln in sale_lines:
        net  = ln.get("line_total_net", 0.0)
        rate = ln.get("tax_rate", 0.10)
        subtotal_net += net
        tax_breakdown[_bracket.get(round(rate, 2), "10%")] += net * rate
    tax_breakdown = {k: round(v, 2) for k, v in tax_breakdown.items()}
    subtotal_net  = round(subtotal_net, 2)
    tax_amount    = round(sum(tax_breakdown.values()), 2)
    total_gross   = round(subtotal_net + tax_amount, 2)

    # Vencimento
    payment_days = sale_order.get("payment_days", 0)
    try:
        inv_dt = _parse_date(invoice_date)
    except ValueError:
        inv_dt = datetime(2024, 1, 1)
    due_date = _fmt(inv_dt + timedelta(days=payment_days))

    # Estado / data de pagamento
    payment_status = sale_order.get("payment_status", "paid")
    payment_date: Optional[str] = None
    if payment_status == "paid":
        paid_offset = rng.randint(0, max(1, payment_days))
        payment_date = _fmt(inv_dt + timedelta(days=paid_offset))

    return {
        "invoice_id":     invoice_id,
        "sale_id":        sale_id,
        "delivery_id":    delivery.get("delivery_id"),   # None p/ canal tienda
        "customer_id":    sale_order.get("customer_id", ""),
        "invoice_date":   invoice_date,
        "subtotal_net":   subtotal_net,
        "tax_breakdown":  tax_breakdown,
        "tax_amount":     tax_amount,
        "total_gross":    total_gross,
        "due_date":       due_date,
        "payment_days":   payment_days,
        "payment_status": payment_status,
        "payment_date":   payment_date,
    }


# ---------------------------------------------------------------------------
# 3. Snapshot de estoque
# ---------------------------------------------------------------------------

def build_stock_snapshot(
    stock_index: Dict[str, Dict[str, Dict]],
    date_str: str,
    products_index: Optional[Dict[str, Dict]] = None,
    pending_pos: Optional[List[Dict]] = None,
) -> List[Dict]:
    """
    Gera um snapshot diário do estoque, como um ERP exportaria ao final do dia.

    Args:
        stock_index:     Dict aninhado {product_id: {location_id: stock_rec}}
                         (atributo ``engine.stock_index`` após engine.run()).
                         Cada stock_rec deve ter location_type e location_id,
                         ou estes serão inferidos da chave.
        date_str:        Data do snapshot no formato "YYYY-MM-DD".
        products_index:  Opcional — dict {product_id: product_dict} para
                         enriquecer com cost_price.
        pending_pos:     Opcional — lista de POs abertas para calcular
                         quantity_in_transit por (product_id, location_id).

    Returns:
        Lista de dicts — um por combinação produto × location.
    """
    products_index = products_index or {}

    # Calcula qty_in_transit por (product_id, location_id) a partir de POs abertas
    in_transit: Dict[tuple, int] = {}
    if pending_pos:
        for po in pending_pos:
            if po.get("status") in ("open", "confirmed", "partially_received"):
                key = (po.get("product_id", ""), po.get("dc_id", po.get("warehouse_id", "")))
                in_transit[key] = in_transit.get(key, 0) + po.get("quantity_ordered", 0)

    snapshots: List[Dict] = []

    for product_id, loc_dict in stock_index.items():
        cost_price = products_index.get(product_id, {}).get("cost_price", 0.0)

        for loc_key, rec in loc_dict.items():
            # loc_key is a tuple (location_type, location_id) in the new engine
            if isinstance(loc_key, tuple):
                location_type, location_id = loc_key
            else:
                location_id   = loc_key
                location_type = rec.get("location_type", "DC")

            qty_on_hand   = rec.get("quantity_on_hand", 0)
            reorder_pt    = rec.get("reorder_point", 0)
            max_stock     = rec.get("max_stock", 0)
            qty_reserved  = 0
            qty_in_transit = in_transit.get((product_id, location_id), 0)
            unit_cost     = rec.get("unit_cost", cost_price)

            snapshots.append({
                "snapshot_date":       date_str,
                "product_id":          product_id,
                "location_type":       location_type,
                "location_id":         location_id,
                "quantity_on_hand":    qty_on_hand,
                "quantity_reserved":   qty_reserved,
                "quantity_in_transit": qty_in_transit,
                "reorder_point":       reorder_pt,
                "max_stock":           max_stock,
                "unit_cost":           unit_cost,
            })

    return snapshots
