"""
simulator/engine.py
Motor de simulação temporal (time-stepped) para o mercado espanhol.

Fluxo modelado:
    Fornecedor → PO agrupada (header+lines) → Recebimento no DC → Estoque DC
    → Transferência CD→Loja (reposição automática) → Estoque Loja / DC
    → Venda (tienda usa estoque da loja; ecommerce usa estoque do DC)
    → Entrega (só ecommerce) → Devolução (~2 %) → Pagamento AP

Loop diário (7 etapas):
    1. Processar recebimentos de POs vencidas (IN no DC)
    2. Processar entregas vencidas → agendar possíveis returns
    3. Aplicar transferências CD→Loja vencidas
    4. Processar devoluções vencidas
    5. Processar pagamentos a fornecedores vencidos (AP flush)
    6. Geração de demanda por canal (tienda / ecommerce)
    7. Flush do po_buffer → PO headers + lines + AP obligation

Classes:
    SimulationResult  — container imutável com todas as tabelas geradas
    SimulationEngine  — orquestra a simulação dia a dia
"""

import functools
import hashlib
import random
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Tuple

from erp.simulator.config import DEFAULT_CONFIG
from erp.simulator.schema import (
    build_purchase_order_header,
    build_purchase_order_lines,
    build_supplier_payment,
)
from erp.generators.profiles import CUSTOMER_PROFILES
from erp.generators.category_map import group_products


def _stable_hash(text: str) -> int:
    """Hash inteiro determinístico e ESTÁVEL entre processos.

    O ``hash()`` embutido de strings é salgado por processo (PYTHONHASHSEED),
    quebrando a reprodutibilidade byte-a-byte que o simulador promete com
    ``--seed``. Usamos md5 para garantir o mesmo offset de fase por cliente em
    qualquer execução, independentemente do ambiente.
    """
    return int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)


# ---------------------------------------------------------------------------
# Container de resultado
# ---------------------------------------------------------------------------

class SimulationResult:
    """
    Armazena todas as tabelas produzidas pelo SimulationEngine.

    Atributos (todos list[dict]):
        sales              — pedidos de venda confirmados (alias: orders)
        sale_lines         — linhas de itens de cada pedido (alias: order_items)
        stockouts          — registros de ruptura de estoque
        deliveries         — entregas realizadas (ecommerce; após prazo de envio)
        stock_movements    — movimentações de estoque (IN/OUT/TRANSFER/RETURN)
        po_headers         — cabeçalhos de ordens de compra (1 por supplier×DC×dia)
        po_lines           — linhas das ordens de compra (N por PO)
        goods_receipts     — recebimentos de mercadoria (1 por po_line recebida)
        supplier_payments  — obrigações de contas a pagar geradas por cada PO
        product_returns    — devoluções de produto (~2 % das entregas)
        stock_snapshots    — snapshot diário de estoque (opcional, gerado externamente)
        metadata           — metadados da simulação
    """

    __slots__ = (
        "sales",
        "sale_lines",
        "stockouts",
        "deliveries",
        "stock_movements",
        "po_headers",
        "po_lines",
        "goods_receipts",
        "supplier_payments",
        "product_returns",
        "product_waste",
        "stock_snapshots",
        "metadata",
    )

    def __init__(self):
        self.sales: List[Dict] = []
        self.sale_lines: List[Dict] = []
        self.stockouts: List[Dict] = []
        self.deliveries: List[Dict] = []
        self.stock_movements: List[Dict] = []
        self.po_headers: List[Dict] = []
        self.po_lines: List[Dict] = []
        self.goods_receipts: List[Dict] = []
        self.supplier_payments: List[Dict] = []
        self.product_returns: List[Dict] = []
        self.product_waste: List[Dict] = []
        self.stock_snapshots: List[Dict] = []
        self.metadata: Dict[str, Any] = {}

    # --- Aliases de retrocompatibilidade ---

    @property
    def orders(self) -> List[Dict]:
        """Alias legado para self.sales."""
        return self.sales

    @property
    def order_items(self) -> List[Dict]:
        """Alias legado para self.sale_lines."""
        return self.sale_lines

    @property
    def purchase_orders(self) -> List[Dict]:
        """Alias legado para self.po_headers."""
        return self.po_headers

    @property
    def purchase_order_lines(self) -> List[Dict]:
        """Alias legado para self.po_lines."""
        return self.po_lines

    @property
    def receipts(self) -> List[Dict]:
        """Alias legado para self.goods_receipts."""
        return self.goods_receipts

    def as_dict(self) -> Dict[str, Any]:
        """Retorna todas as tabelas como dicionário (adequado para serialização JSON)."""
        return {
            "sales":             self.sales,
            "sale_lines":        self.sale_lines,
            "stockouts":         self.stockouts,
            "deliveries":        self.deliveries,
            "stock_movements":   self.stock_movements,
            "po_headers":        self.po_headers,
            "po_lines":          self.po_lines,
            "goods_receipts":    self.goods_receipts,
            "supplier_payments": self.supplier_payments,
            "product_returns":   self.product_returns,
            "product_waste":     self.product_waste,
            "stock_snapshots":   self.stock_snapshots,
            "metadata":          self.metadata,
        }

    def summary(self) -> str:
        """Resumo textual do resultado."""
        lines = [
            "=== SimulationResult ===",
            f"  sales              : {len(self.sales):>7,}",
            f"  sale_lines         : {len(self.sale_lines):>7,}",
            f"  stockouts          : {len(self.stockouts):>7,}",
            f"  deliveries         : {len(self.deliveries):>7,}",
            f"  stock_movements    : {len(self.stock_movements):>7,}",
            f"  po_headers         : {len(self.po_headers):>7,}",
            f"  po_lines           : {len(self.po_lines):>7,}",
            f"  goods_receipts     : {len(self.goods_receipts):>7,}",
            f"  supplier_payments  : {len(self.supplier_payments):>7,}",
            f"  product_returns    : {len(self.product_returns):>7,}",
            f"  product_waste      : {len(self.product_waste):>7,}",
            f"  stock_snapshots    : {len(self.stock_snapshots):>7,}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Utilitários internos
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str[:10], "%Y-%m-%d")


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


@functools.lru_cache(maxsize=16)
def _easter_sunday(year: int) -> date:
    """Domingo de Páscoa (algoritmo Anonymous Gregorian / Gauss)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * m + 114) // 31
    day = ((h + ell - 7 * m + 114) % 31) + 1
    return date(year, month, day)


@functools.lru_cache(maxsize=16)
def _black_friday(year: int) -> date:
    """4ª sexta-feira de novembro (convenção de varejo)."""
    first = date(year, 11, 1)
    first_friday_day = 1 + (4 - first.weekday()) % 7
    return date(year, 11, first_friday_day + 21)


def _market_shock_multipliers(
    today_str: str,
    segment: str,
    profile_id: str,
    cfg: Dict,
) -> tuple:
    """
    Retorna (demand_mult, ticket_mult) resultante de todos os market_shocks
    ativos em today_str que afetam este (segment, profile_id).

    Múltiplos choques ativos se combinam multiplicativamente — raro mas possível
    (ex: greve logística + calor extremo simultâneos).
    """
    shocks = cfg.get("market_shocks", [])
    demand_mult = 1.0
    ticket_mult = 1.0
    for shock in shocks:
        if shock["start"] <= today_str <= shock["end"]:
            seg_filter = shock.get("segments")
            prof_filter = shock.get("profiles")
            seg_ok  = (seg_filter is None) or (segment in seg_filter)
            prof_ok = (prof_filter is None) or (profile_id in prof_filter)
            if seg_ok and prof_ok:
                demand_mult *= shock.get("demand_mult", 1.0)
                ticket_mult *= shock.get("ticket_mult", 1.0)
    return demand_mult, ticket_mult


def _maybe_switch_regime(
    customer: Dict,
    day_offset: int,
    rng: random.Random,
    cfg: Dict,
) -> str:
    """
    Verifica periodicamente se este cliente muda de regime de comportamento.

    Retorna o regime atual (possivelmente alterado). Persiste a mudança
    diretamente no dict do cliente (campo `ticket_trend`), assim o engine
    detecta o novo regime no próximo ciclo sem estado adicional.
    """
    check_interval = cfg.get("behavior_switch_check_days", 90)
    # Cada cliente tem um offset próprio para não avaliarem todos no mesmo dia
    cust_phase = _stable_hash(customer["customer_id"]) % check_interval
    if (day_offset + cust_phase) % check_interval != 0:
        return customer.get("ticket_trend", "stable")

    current = customer.get("ticket_trend", "stable")
    prob_map = cfg.get("behavior_switch_prob", {})
    switch_prob = prob_map.get(current, 0.0)

    if rng.random() >= switch_prob:
        return current

    transitions = cfg.get("behavior_switch_transitions", {})
    options = transitions.get(current, [])
    if not options:
        return current

    new_trends = [t[0] for t in options]
    new_weights = [t[1] for t in options]
    new_trend = rng.choices(new_trends, weights=new_weights, k=1)[0]
    customer["ticket_trend"] = new_trend
    # Resetar fator estável e marcar o dia do switch para o progress local
    customer.pop("_stable_factor", None)
    customer["_regime_start_day"] = day_offset
    return new_trend


def _supply_pressure_multiplier(d, cfg: Dict) -> float:
    """Lead-time multiplier during high-demand weeks (supply squeeze).

    During Black Friday, Navidad, and Semana Santa, suppliers take longer to
    deliver because their logistics networks are saturated. This causes stock
    to deplete before replenishment arrives, producing realistic fill-rate dips.
    """
    # Normalise: accept both datetime and date
    d_date = d.date() if hasattr(d, "date") else d
    year = d_date.year
    pressure = cfg.get("seasonal_supply_pressure", {})

    # Black Friday week (+/- 3 days around Black Friday)
    bf = _black_friday(year)
    if bf - timedelta(days=3) <= d_date <= bf + timedelta(days=3):
        return pressure.get("black_friday", 1.0)

    # Navidad week (23-31 December)
    if d_date.month == 12 and d_date.day >= 23:
        return pressure.get("navidad", 1.0)

    # Semana Santa (Holy Week)
    easter = _easter_sunday(year)
    if easter - timedelta(days=7) <= d_date <= easter:
        return pressure.get("semana_santa", 1.0)

    return 1.0


def _seasonal_event_multiplier(dt: datetime, cfg: Dict) -> float:
    """
    Multiplicador de datas MÓVEIS (calculadas por ano): Black Friday e
    Semana Santa. Complementa os eventos de data fixa de `special_events`.
    """
    mult = 1.0
    d = dt.date()
    year = dt.year

    # Black Friday (4ª sexta de novembro) + quinta véspera
    bf = _black_friday(year)
    if d == bf:
        mult *= 1.48
    elif d == bf - timedelta(days=1):
        mult *= 1.20

    # Semana Santa (móvel): boost na semana prévia; cierre na Sexta-feira Santa
    easter = _easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    if d == good_friday:
        mult *= cfg.get("semana_santa_closure", 0.30)
    elif easter - timedelta(days=7) <= d <= easter - timedelta(days=3):
        mult *= cfg.get("semana_santa_boost", 1.20)

    return mult


def _demand_multiplier(dt: datetime, cfg: Dict, rng: random.Random) -> float:
    """
    Multiplicador de demanda orgânico para o dia `dt`.

    Combina seis camadas:
      1. Dia da semana  (segunda 0.75 → sábado 1.45, domingo 0.35)
      2. Sazonalidade mensal  (jan 0.90 → dez 1.28)
      3. Efeito nómina dentro do mês  (início, quinzena, fim)
      4. Eventos de data fixa  (Nochebuena, Reyes…)
      5. Eventos móveis por ano  (Black Friday, Semana Santa)
      6. Ruído log-normal diário  (sigma=0.055, orgânico e não-reversível)
    """
    import math

    # 1. Dia da semana
    dow_map = cfg.get("day_of_week_multipliers", {
        0: 0.75, 1: 0.88, 2: 1.00, 3: 1.08, 4: 1.25, 5: 1.45, 6: 0.35,
    })
    mult = dow_map.get(dt.weekday(), 1.0)

    # 2. Sazonalidade mensal
    monthly = cfg.get("monthly_seasonal_index", {})
    mult *= monthly.get(dt.month, 1.0)

    # 3. Efeito nómina
    if dt.day <= 5:
        mult *= cfg.get("month_start_demand_multiplier", 1.14)
    elif dt.day in (15, 16):
        mult *= cfg.get("mid_month_boost", 1.06)
    elif dt.day >= 25:
        mult *= cfg.get("month_end_demand_multiplier", 1.10)

    # 4. Eventos de data fixa (MM-DD)
    events = cfg.get("special_events", {})
    key = dt.strftime("%m-%d")
    if key in events:
        mult *= events[key]

    # 5. Eventos móveis (Black Friday, Semana Santa) calculados por ano
    mult *= _seasonal_event_multiplier(dt, cfg)

    # 6. Ruído log-normal — cada dia tem variância própria e irrepetível
    sigma = cfg.get("daily_noise_sigma", 0.055)
    if sigma > 0:
        mult *= math.exp(rng.gauss(0.0, sigma))

    return max(0.0, mult)


def _order_timestamp(dt: datetime, cfg: Dict, rng: random.Random) -> str:
    """
    Carimba um pedido com hora do dia segundo a curva diurna de afluência
    (dois picos: meio da manhã e fim de tarde) → habilita análise de hora-punta.
    Determinístico dado o `rng` seedado.
    """
    weights = cfg.get("diurnal_hour_weights") or {12: 1.0}
    hours = list(weights.keys())
    wts   = list(weights.values())
    hour   = rng.choices(hours, weights=wts, k=1)[0]
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)
    return dt.replace(hour=hour, minute=minute, second=second).strftime("%Y-%m-%dT%H:%M:%S")


def _basket_size_multiplier(dt: datetime, cfg: Dict) -> float:
    """
    Fator sazonal aplicado ao TAMANHO da cesta (ticket alvo), não à frequência.

    Em retail real a cesta não cresce só em número de visitas no fim de ano —
    cada cesta também fica maior (compra de estocagem). Aplicamos metade do
    índice sazonal mensal ao ticket, mais um bônus em datas de estocagem.
    Resultado: AOV varia organicamente ao longo do ano (≈ €68 fev → €82 dez),
    em vez de ficar travado num valor único.
    """
    monthly = cfg.get("monthly_seasonal_index", {})
    idx = monthly.get(dt.month, 1.0)
    mult = 1.0 + (idx - 1.0) * 0.5            # metade do efeito sazonal vai ao ticket

    events = cfg.get("basket_size_events", {})
    mult *= events.get(dt.strftime("%m-%d"), 1.0)
    return mult


def _organic_line_qty(group_key: str, cfg: Dict, rng: random.Random) -> int:
    """
    Quantidade orgânica de UMA linha de cesta — pequena e independente do ticket.

    A maioria das linhas é 1-2 unidades; categorias "a granel" (leite,
    bebidas, limpeza) recebem um bônus ocasional simulando packs/garrafões.
    É o oposto da lógica antiga (qty = ticket_restante / preço), que empilhava
    até 30 unidades de um único produto.
    """
    weights = cfg.get("basket_qty_weights", {1: 0.55, 2: 0.25, 3: 0.12, 4: 0.05, 5: 0.02, 6: 0.01})
    qtys = list(weights.keys())
    wts  = list(weights.values())
    qty  = rng.choices(qtys, weights=wts, k=1)[0]

    bulk = cfg.get("bulk_categories", [])
    if group_key in bulk:
        bonus_w = cfg.get("bulk_qty_bonus_weights", {0: 0.45, 1: 0.25, 2: 0.15, 3: 0.10, 4: 0.05})
        b_keys = list(bonus_w.keys())
        b_wts  = list(bonus_w.values())
        qty += rng.choices(b_keys, weights=b_wts, k=1)[0]

    qty_max = cfg.get("order_qty_max", 12)
    return min(qty, qty_max)


# ---------------------------------------------------------------------------
# Motor de simulação
# ---------------------------------------------------------------------------

class SimulationEngine:
    """
    Motor de simulação temporal dia a dia para o mercado espanhol.

    Modela dois canais:
        tienda   — cliente compra na loja física; estoque descontado na loja.
        ecommerce — cliente compra online; estoque descontado no DC regional.

    POs são agrupadas por (supplier_id, dc_id, data) e geradas em batch ao
    final de cada dia (po_buffer flush), gerando cabeçalho + lines + AP.

    Uso básico::

        from erp.simulator.engine import SimulationEngine
        from erp.simulator.config import DEFAULT_CONFIG

        engine = SimulationEngine(
            products=products,
            customers=customers,
            suppliers=suppliers,
            stock=stock,          # dc_stock + store_stock concatenados
            stores=stores,
            distribution_centers=dcs,
            config=DEFAULT_CONFIG,
        )
        result = engine.run()
        print(result.summary())
    """

    def __init__(
        self,
        customers: List[Dict],
        products: List[Dict],
        suppliers: List[Dict],
        stock: List[Dict],
        stores: List[Dict] = None,
        distribution_centers: List[Dict] = None,
        config: Dict = None,
        on_day_complete=None,
    ):
        """
        Args:
            customers:             Lista de clientes (precisa de customer_id e
                                   nearest_store_id / ccaa).
            products:              Lista de produtos (precisa de product_id e price).
            suppliers:             Lista de fornecedores.
            stock:                 Estado inicial de estoque (concatenação de
                                   dc_stock + store_stock). Cada registro precisa
                                   de location_type ('DC' ou 'STORE') e location_id.
            stores:                Lista de lojas (geradas por generate_stores).
            distribution_centers:  Lista de DCs (gerados por get_distribution_centers).
            config:                Dicionário de configuração. Se None, usa DEFAULT_CONFIG.
            on_day_complete:       Callback(day_record) chamado ao fim de cada dia.
        """
        self.customers   = customers
        self.products    = products
        self.suppliers   = suppliers
        self.stores      = stores or []
        self.distribution_centers = distribution_centers or []
        self.on_day_complete = on_day_complete

        # Configuração (mesclada com DEFAULT_CONFIG)
        self._cfg = {**DEFAULT_CONFIG, **(config or {})}

        # --- Índices para lookup O(1) ---

        # stock_index[product_id][(location_type, location_id)] → registro de estoque (mutável)
        self.stock_index: Dict[str, Dict[Tuple[str, str], Dict]] = defaultdict(dict)
        for rec in stock:
            loc_type = rec.get("location_type", "DC")
            loc_id   = rec.get("location_id") or rec.get("dc_id", "")
            self.stock_index[rec["product_id"]][(loc_type, loc_id)] = rec

        # Índice de fornecedores
        self.supplier_index: Dict[str, Dict] = {
            s["supplier_id"]: s for s in suppliers
        }

        # Índice de produtos
        self.product_index: Dict[str, Dict] = {
            p["product_id"]: p for p in products
        }

        # Índice de clientes
        self.customer_index: Dict[str, Dict] = {
            c["customer_id"]: c for c in customers
        }

        # Índice de lojas
        self.stores_index: Dict[str, Dict] = {
            s["store_id"]: s for s in self.stores
        }

        # Índice de DCs
        self.dc_index: Dict[str, Dict] = {
            d["dc_id"]: d for d in self.distribution_centers
        }

        # Mapa região → DC (usa o do config, com fallback para DC_MAD)
        self.region_to_dc: Dict[str, str] = self._cfg.get("region_to_dc", {})

        # products_by_group — {group_id: [product_id, ...]} para seleção por perfil
        self.products_by_group: Dict[str, List[str]] = group_products(products)

    # ------------------------------------------------------------------
    # Ponto de entrada público
    # ------------------------------------------------------------------

    def run(self, days: int = None, config: Dict = None) -> SimulationResult:
        """
        Executa a simulação.

        Args:
            days:   Número de dias a simular. Se None, deriva de
                    ``config["start_date"]`` e ``config["end_date"]``.
            config: Dicionário de configuração adicional. Mescla com o
                    config passado no __init__ e com DEFAULT_CONFIG.

        Returns:
            SimulationResult com todas as tabelas preenchidas.
        """
        cfg = {**self._cfg, **(config or {})}

        # Gerador aleatório isolado e seedado — threaded por toda a simulação.
        # Não toca o `random` global (evita interferência entre geradores e
        # engine); reprodutível byte-a-byte dado (seed + ordem de clientes).
        seed = cfg.get("random_seed")
        rng = self.rng = random.Random(seed)

        # Janela temporal
        start_dt = _parse_date(cfg["start_date"])
        end_dt   = _parse_date(cfg["end_date"])
        if days is not None:
            end_dt = start_dt + timedelta(days=days - 1)
        total_days = (end_dt - start_dt).days + 1

        result = SimulationResult()
        self._current_result = result   # exposed for streaming callbacks

        # --- Contadores de IDs ---
        counters: Dict[str, int] = {
            "sale":     0,   # pedidos de venda
            "item":     0,   # linhas de venda
            "stockout": 0,
            "delivery": 0,
            "movement": 0,
            "po":       0,   # PO headers
            "po_line":  0,   # PO lines
            "receipt":  0,   # goods_receipts
            "payment":  0,   # supplier_payments (AP)
            "return":   0,   # product_returns
            "waste":    0,   # product_waste (merma / caducidad)
            "transfer": 0,   # transferências CD→Loja
        }

        # --- Filas de estado mútavel ---
        # POs abertas aguardando chegada no DC
        pending_pos: List[Dict] = []
        # Entregas pendentes aguardando prazo
        pending_deliveries: List[Dict] = []
        # Transferências CD→Loja agendadas
        pending_transfers: List[Dict] = []
        # Devoluções agendadas (~2 % das entregas)
        pending_returns: List[Dict] = []
        # Obrigações de contas a pagar (AP)
        pending_payments: List[Dict] = []

        # Buffer de linhas de PO agrupadas por (supplier_id, dc_id, date)
        # Cada valor é um dict com chaves supplier_id, dc_id, order_date, lines
        po_buffer: Dict[Tuple[str, str, str], Dict] = {}

        # Produtos com PO em trânsito por DC — evita reordenar o que já está a
        # caminho (e portanto evita sobre-compra e perda no cap de max_stock).
        in_transit_pos: set = set()   # {(product_id, dc_id), ...}

        # Transferências CD→Loja em trânsito — dedup O(1) (espelha in_transit_pos).
        # Sem isto, _schedule_transfer fazia varredura linear de pending_transfers
        # (~11k itens) a cada ruptura de loja → ~90% do runtime total (medido).
        in_transit_transfers: set = set()   # {(product_id, store_id), ...}

        # Linhas de PO pendentes de recebimento, por po_id. Mantidas fora do
        # header (que é persistido em result.po_headers) para não vazar o campo
        # interno `_lines` ao CSV/RAW.
        pending_po_lines: Dict[str, List[Dict]] = {}

        # --- Parâmetros de uso frequente ---
        base_rate    = cfg.get("demand_base_rate", 0.05)
        region_to_dc = self.region_to_dc
        delivery_days_map = cfg.get("delivery_days_by_region", {})
        active_suppliers  = [s for s in self.suppliers if s.get("active", True)]
        product_ids = list(self.product_index.keys())

        # Parâmetros de merma/caducidad (perecíveis)
        waste_prob      = cfg.get("waste_line_probability", 0.0)
        _waste_weights  = cfg.get("waste_qty_weights", {1: 0.60, 2: 0.28, 3: 0.12})
        waste_qty_keys  = list(_waste_weights.keys())
        waste_qty_wts   = list(_waste_weights.values())

        # Parâmetros de promoção (ofertas por linha) — ver config["promotions"]
        _promo          = cfg.get("promotions", {})
        _promo_prob     = _promo.get("line_promo_probability", 0.0)
        _promo_weights  = _promo.get("discount_pct_weights", {})
        _promo_keys     = list(_promo_weights.keys())
        _promo_wts      = list(_promo_weights.values())

        # Pré-computar choques ativos por data para O(1) lookup no loop interno.
        # active_shocks_by_date[date_str] = lista de shocks ativos naquele dia.
        # Elimina o loop O(n_shocks) × 10k clientes × 730 dias.
        _all_shocks = cfg.get("market_shocks", [])
        active_shocks_by_date: Dict[str, list] = {}
        for _d_off in range(total_days):
            _ds = _fmt(start_dt + timedelta(days=_d_off))
            _active = [s for s in _all_shocks if s["start"] <= _ds <= s["end"]]
            if _active:
                active_shocks_by_date[_ds] = _active
        # Pré-computar parâmetros de regime switching para evitar dict.get() no loop
        _switch_prob        = cfg.get("behavior_switch_prob", {})
        _switch_transitions = cfg.get("behavior_switch_transitions", {})
        _switch_interval    = cfg.get("behavior_switch_check_days", 90)
        _stockout_decay     = cfg.get("stockout_memory_decay", 0.985)
        _pen_per_hit        = cfg.get("stockout_penalty_per_hit", 0.025)
        _max_pen            = cfg.get("max_stockout_penalty", 0.35)
        _cust_phases        = {c["customer_id"]: _stable_hash(c["customer_id"]) % _switch_interval
                               for c in self.customers}

        # ----------------------------------------------------------------
        # Loop principal — um dia de cada vez
        # ----------------------------------------------------------------
        for day_offset in range(total_days):
            today     = start_dt + timedelta(days=day_offset)
            today_str = _fmt(today)
            year_str  = today_str[:4]

            # ================================================================
            # ETAPA 1 — Processar recebimentos de POs vencidas
            # ================================================================
            still_pending_pos = []
            for po in pending_pos:
                if po["expected_receipt_date"] <= today_str:
                    dc_id = po["dc_id"]
                    # Criar goods_receipt por line da PO
                    for po_line in pending_po_lines.pop(po["po_id"], []):
                        prod_id  = po_line["product_id"]
                        ordered_qty = po_line.get("quantity_ordered", 0)
                        reliability = self.supplier_index.get(
                            po.get("supplier_id", ""), {}
                        ).get("reliability_score", 0.95)
                        recv_qty = max(0, round(
                            ordered_qty * rng.uniform(min(reliability * 0.85, 1.0), 1.0)
                        ))

                        counters["receipt"] += 1
                        receipt_id = f"GR-{year_str}-{counters['receipt']:08d}"

                        # Recebe no DC; o ERP registra como recebido o que de fato
                        # entrou no estoque (após teto de max_stock) — sem fantasma.
                        applied = self._add_stock(
                            prod_id, "DC", dc_id,
                            recv_qty, result, counters, today_str,
                            reason="receipt", reference_id=receipt_id,
                        )

                        result.goods_receipts.append({
                            "receipt_id":     receipt_id,
                            "po_id":          po["po_id"],
                            "po_line_number": po_line.get("line_number"),
                            "dc_id":          dc_id,
                            "product_id":     prod_id,
                            "supplier_id":    po["supplier_id"],
                            "quantity_received": applied,
                            "receipt_date":   today_str,
                            "unit_cost":    po_line.get("unit_cost", 0.0),
                        })

                        # PO recebida → produto não está mais em trânsito
                        in_transit_pos.discard((prod_id, dc_id))

                    # Marcar PO como recebida
                    po["status"]              = "received"
                    po["actual_receipt_date"] = today_str
                else:
                    still_pending_pos.append(po)
            pending_pos = still_pending_pos

            # ================================================================
            # ETAPA 2 — Processar entregas vencidas → agendar possíveis returns
            # ================================================================
            still_pending_del = []
            for deliv in pending_deliveries:
                if deliv["scheduled_date"] <= today_str:
                    deliv["actual_delivery_date"] = today_str
                    deliv["delivery_status"]      = "delivered"
                    result.deliveries.append(deliv)

                    # Agendar return com 2 % de probabilidade
                    if rng.random() < 0.02:
                        order_lines = deliv.get("_order_lines", [])
                        if order_lines:
                            # Sortear 1-2 linhas do pedido para devolver
                            num_ret_lines = min(len(order_lines), rng.randint(1, 2))
                            ret_lines = rng.sample(order_lines, num_ret_lines)
                            for rl in ret_lines:
                                qty_delivered = rl.get("quantity", 1)
                                qty_returned  = rng.randint(1, max(1, qty_delivered))
                                reason        = rng.choice([
                                    "damaged", "wrong_item", "unwanted", "expired"
                                ])
                                ret_date = _fmt(
                                    today + timedelta(days=rng.randint(5, 15))
                                )
                                pending_returns.append({
                                    "order_id":     deliv["order_id"],
                                    "product_id":   rl["product_id"],
                                    "location_type": deliv["location_type"],
                                    "location_id":  deliv["location_id"],
                                    "customer_id":  deliv["customer_id"],
                                    "return_date":  ret_date,
                                    "quantity":     qty_returned,
                                    "reason":       reason,
                                    "unit_price_net": rl.get("unit_price", 0.0),
                                    "tax_rate":     rl.get("tax_rate", 0.10),
                                    "sale_id":      deliv.get("sale_id", ""),
                                })
                else:
                    still_pending_del.append(deliv)
            pending_deliveries = still_pending_del

            # ================================================================
            # ETAPA 3 — Aplicar transferências CD→Loja vencidas
            # ================================================================
            still_pending_tr = []
            for tr in pending_transfers:
                if tr["arrival_date"] <= today_str:
                    prod_id  = tr["product_id"]
                    from_dc  = tr["from_dc"]
                    to_store = tr["to_store"]
                    qty      = tr["quantity"]

                    # Conservação de unidades: move-se o MÍNIMO entre o agendado,
                    # o disponível no DC na chegada e o espaço livre na loja. Os dois
                    # lados (OUT no DC, IN na loja) usam a MESMA quantidade — a
                    # transferência não cria nem destrói estoque.
                    dc_rec    = self.stock_index.get(prod_id, {}).get(("DC", from_dc))
                    store_rec = self.stock_index.get(prod_id, {}).get(("STORE", to_store))
                    dc_avail   = dc_rec["quantity_on_hand"] if dc_rec else 0
                    store_room = (
                        max(0, store_rec["max_stock"] - store_rec["quantity_on_hand"])
                        if store_rec else qty
                    )
                    actual = max(0, min(qty, dc_avail, store_room))

                    if actual > 0:
                        # TRANSFER no DC (saída)
                        self._remove_stock(
                            prod_id, "DC", from_dc,
                            actual, result, counters, today_str,
                            reason="transfer_out", reference_id=tr["transfer_id"],
                        )
                        # TRANSFER na loja (entrada)
                        self._add_stock(
                            prod_id, "STORE", to_store,
                            actual, result, counters, today_str,
                            reason="transfer_in", reference_id=tr["transfer_id"],
                        )
                    # Transferência consumida: liberar o par (produto, loja) p/ novo reorder
                    in_transit_transfers.discard((prod_id, to_store))
                else:
                    still_pending_tr.append(tr)
            pending_transfers = still_pending_tr

            # ================================================================
            # ETAPA 4 — Processar devoluções vencidas
            # ================================================================
            still_pending_ret = []
            for ret in pending_returns:
                if ret["return_date"] <= today_str:
                    reason   = ret.get("reason", "unwanted")
                    qty_ret  = ret.get("quantity", 1)
                    loc_type = ret.get("location_type", "DC")
                    loc_id   = ret.get("location_id", "")
                    prod_id  = ret.get("product_id", "")

                    # Determinar se o produto volta para estoque
                    # damaged ou expired: 30 % chance de NÃO repor; outros: sempre repõe
                    if reason in ("damaged", "expired"):
                        restocked = rng.random() >= 0.30
                    else:
                        restocked = True

                    counters["return"] += 1
                    ret_id     = f"RET-{year_str}-{counters['return']:07d}"
                    unit_price = ret.get("unit_price_net", 0.0)
                    tax_rate   = ret.get("tax_rate", 0.10)
                    refund_amt = round(unit_price * qty_ret * (1.0 + tax_rate), 2)

                    result.product_returns.append({
                        "return_id":         ret_id,
                        "sale_id":           ret.get("sale_id", ""),
                        "order_id":          ret.get("order_id", ""),
                        "product_id":        prod_id,
                        "customer_id":       ret.get("customer_id", ""),
                        "location_type":     loc_type,
                        "location_id":       loc_id,
                        "return_date":       ret["return_date"],
                        "quantity_returned": qty_ret,
                        "unit_price_net":    unit_price,
                        "refund_amount":     refund_amt,
                        "reason":            reason,
                        "restocked":         1 if restocked else 0,
                    })

                    if restocked:
                        self._add_stock(
                            prod_id, loc_type, loc_id,
                            qty_ret, result, counters, today_str,
                            reason="return", reference_id=ret_id,
                        )
                else:
                    still_pending_ret.append(ret)
            pending_returns = still_pending_ret

            # ================================================================
            # ETAPA 5 — Processar pagamentos a fornecedores vencidos (AP)
            # ================================================================
            still_pending_pay = []
            for pay in pending_payments:
                if pay["due_date"] <= today_str:
                    if rng.random() < 0.90:
                        # Paga na data
                        pay["payment_date"] = pay["due_date"]
                        pay["status"]       = "paid"
                        pay["days_late"]    = 0
                    else:
                        # Pago COM ATRASO de N dias (1-15). A fatura foi paga
                        # (status='paid'); o atraso é codificado por days_late>0.
                        # Antes o status 'overdue' rotulava erroneamente uma
                        # linha já paga como em aberto.
                        late_days           = rng.randint(1, 15)
                        pay_dt              = _parse_date(pay["due_date"]) + timedelta(days=late_days)
                        pay["payment_date"] = _fmt(pay_dt)
                        pay["status"]       = "paid"
                        pay["days_late"]    = late_days
                    result.supplier_payments.append(pay)
                else:
                    still_pending_pay.append(pay)
            pending_payments = still_pending_pay

            # ================================================================
            # ETAPA 6 — Geração de demanda (loop por cliente)
            # ================================================================
            day_mult = _demand_multiplier(today, cfg, rng)
            # (progress global removido: cada cliente usa local_progress relativo
            # ao último switch de regime — ver _regime_start_day no loop abaixo)

            for customer in self.customers:
                cust_id    = customer["customer_id"]
                profile_id = customer.get("profile", "pareja")
                profile    = CUSTOMER_PROFILES.get(profile_id, CUSTOMER_PROFILES["pareja"])
                freq_mult  = profile.get("purchase_frequency_multiplier", 1.0)

                # Regime switching: verifica trimestralmente se o cliente muda
                cust_id_   = customer["customer_id"]
                cust_phase = _cust_phases[cust_id_]
                current_trend = customer.get("ticket_trend", "stable")
                if (day_offset + cust_phase) % _switch_interval == 0:
                    sw_prob = _switch_prob.get(current_trend, 0.0)
                    if rng.random() < sw_prob:
                        opts = _switch_transitions.get(current_trend, [])
                        if opts:
                            new_trend = rng.choices([o[0] for o in opts],
                                                    weights=[o[1] for o in opts], k=1)[0]
                            customer["ticket_trend"] = new_trend
                            customer.pop("_stable_factor", None)
                            customer["_regime_start_day"] = day_offset
                            current_trend = new_trend
                ticket_trend = current_trend

                avg_ticket_cust   = customer["avg_ticket"]
                behavior_variance = customer["behavior_variance"]

                # Progress local por regime: reseta quando o cliente muda de trend
                regime_start = customer.get("_regime_start_day", 0)
                regime_days  = day_offset - regime_start
                regime_total = max(1, total_days - regime_start)
                local_progress = regime_days / regime_total  # 0→1 desde o último switch

                if ticket_trend == "declining":
                    trend_factor = max(0.68, 1.0 - max(0.0, local_progress - 0.15) * 0.38)
                    if local_progress > 0.25:
                        freq_mult *= max(0.45, 1.0 - (local_progress - 0.25) / 0.75 * 0.55)
                elif ticket_trend == "growing":
                    trend_factor = min(1.20, 1.0 + local_progress * 0.20)
                else:
                    trend_factor = customer.setdefault(
                        "_stable_factor", round(rng.uniform(0.92, 1.08), 4)
                    )

                # Memória de experiência: rupturas acumuladas penalizam freq.
                stockout_penalty = customer.get("_stockout_penalty", 0.0)
                if stockout_penalty:
                    stockout_penalty *= _stockout_decay
                    customer["_stockout_penalty"] = stockout_penalty
                    freq_mult *= max(1.0 - _max_pen, 1.0 - stockout_penalty)

                # Choques de mercado: O(1) lookup via cache pré-computado
                segment = customer.get("segment", "Bronze")
                day_shocks = active_shocks_by_date.get(today_str)
                shock_demand = 1.0
                shock_ticket = 1.0
                if day_shocks:
                    for shock in day_shocks:
                        seg_filter  = shock.get("segments")
                        prof_filter = shock.get("profiles")
                        if ((seg_filter is None or segment in seg_filter) and
                                (prof_filter is None or profile_id in prof_filter)):
                            shock_demand *= shock.get("demand_mult", 1.0)
                            shock_ticket *= shock.get("ticket_mult", 1.0)
                freq_mult *= shock_demand

                effective_rate = min(1.0, base_rate * day_mult * freq_mult)
                if rng.random() > effective_rate:
                    continue

                # ---- Decisão de canal ----
                ch_prob = customer.get(
                    "channel_probability",
                    profile.get("online_tendency", 0.5),
                )
                channel = "ecommerce" if rng.random() < ch_prob else "tienda"

                # ---- Localização dependente do canal ----
                if channel == "tienda":
                    store_id = customer.get("nearest_store_id")
                    if not store_id:
                        # Sem loja associada: pular este pedido
                        continue
                    location_type    = "STORE"
                    location_id      = store_id
                    order_dc_id      = None
                    order_store_id   = store_id
                    region = customer.get("ccaa") or customer.get("region", "Madrid")
                else:  # ecommerce
                    ccaa    = customer.get("ccaa") or customer.get("region", "Madrid")
                    dc_id   = region_to_dc.get(ccaa) or region_to_dc.get("default", "DC_MAD")
                    location_type    = "DC"
                    location_id      = dc_id
                    order_dc_id      = dc_id
                    order_store_id   = None
                    region = ccaa

                # ---- Ticket alvo (sazonalidade + choque de mercado) ----
                noise          = rng.uniform(1.0 - behavior_variance, 1.0 + behavior_variance)
                basket_season  = _basket_size_multiplier(today, cfg)
                target_ticket  = max(3.0, avg_ticket_cust * trend_factor * noise * basket_season * shock_ticket)

                # ---- Construção ORGÂNICA da cesta ----
                # Supermercado real: a cesta cresce em VARIEDADE (muitos itens
                # distintos, 1-3 unidades cada) até atingir o ticket alvo — nunca
                # empilhando dezenas de unidades de um único SKU.
                category_weights = profile["category_weights"]
                group_keys       = list(category_weights.keys())
                group_wts        = [category_weights[g] for g in group_keys]
                max_distinct     = cfg.get("basket_max_distinct_items", 45)

                order_lines:  List[Dict] = []
                order_total      = 0.0   # bruto (com IVA) — usado para o ticket alvo
                order_total_net  = 0.0   # líquido (sem IVA) — base de receita
                has_stockout  = False
                seen_products: set = set()
                attempts      = 0
                max_attempts  = max_distinct * 3 + 20
                # Índice do 1º movimento de estoque deste pedido — usado para
                # reescrever reference_id='pending_order' → order_id real depois.
                mov_start = len(result.stock_movements)

                while (
                    order_total < target_ticket
                    and len(order_lines) < max_distinct
                    and attempts < max_attempts
                ):
                    attempts += 1

                    grp     = rng.choices(group_keys, weights=group_wts, k=1)[0]
                    pool    = self.products_by_group.get(grp) or product_ids
                    prod_id = rng.choice(pool)

                    if prod_id in seen_products:
                        continue
                    seen_products.add(prod_id)

                    product   = self.product_index[prod_id]
                    raw_price = product.get("price", 0)
                    try:
                        unit_price = float(str(raw_price).replace(",", "."))
                    except (ValueError, TypeError):
                        unit_price = 0.0
                    if unit_price <= 0:
                        unit_price = round(rng.uniform(1.5, 15.0), 2)

                    # Quantidade orgânica — pequena, independente do ticket restante
                    qty_requested = _organic_line_qty(grp, cfg, rng)

                    # Consultar estoque na localização correta
                    stock_rec = self.stock_index.get(prod_id, {}).get((location_type, location_id))

                    if stock_rec is None:
                        # Produto fora do SORTIMENTO desta localização (a loja não o
                        # comercializa). Não é ruptura de estoque — o cliente apenas
                        # escolhe outro item. Só o estoque ZERO de um item do
                        # sortimento conta como ruptura (abaixo).
                        continue

                    available = stock_rec["quantity_on_hand"]
                    if available <= 0:
                        # Ruptura real: item do sortimento, porém sem estoque
                        counters["stockout"] += 1
                        result.stockouts.append({
                            "stockout_id":        f"STO_{counters['stockout']:08d}",
                            "date":               today_str,
                            "customer_id":        cust_id,
                            "product_id":         prod_id,
                            "location_type":      location_type,
                            "location_id":        location_id,
                            "quantity_requested": qty_requested,
                            "quantity_available": 0,
                        })
                        has_stockout = True

                        # Acumular penalidade de experiência: cada ruptura
                        # degrada a frequência futura do cliente (memória negativa)
                        customer["_stockout_penalty"] = min(
                            _max_pen,
                            customer.get("_stockout_penalty", 0.0) + _pen_per_hit,
                        )

                        # Disparar reposição (DC: PO; STORE: transferência do DC)
                        if location_type == "DC":
                            self._buffer_po_line(
                                prod_id, location_id, stock_rec,
                                active_suppliers, today_str, po_buffer, in_transit_pos,
                            )
                        else:  # STORE
                            self._schedule_transfer(
                                prod_id, location_id, stock_rec,
                                today, counters, pending_transfers,
                                po_buffer, active_suppliers, today_str, in_transit_pos,
                                in_transit_transfers,
                            )
                        continue

                    # Atendimento (parcial quando o estoque não cobre tudo)
                    qty_delivered = min(qty_requested, available)
                    if qty_delivered < qty_requested:
                        has_stockout = True  # ruptura parcial: levou menos do que queria

                    # Decrementar estoque pelo que foi efetivamente entregue
                    self._remove_stock(
                        prod_id, location_type, location_id,
                        qty_delivered, result, counters, today_str,
                        reason="sale", reference_id="pending_order",
                    )

                    tax_rate   = product.get("tax_rate", 0.10)
                    # Promoção: com prob line_promo_probability a linha entra em
                    # oferta com desconto sorteado. Aplicado sobre o preço de
                    # tabela; o líquido acumulado no header usa a MESMA fórmula
                    # por-linha do builder (schema.build_sale_order_lines) →
                    # header.subtotal_net == soma(line_total_net), exato.
                    discount_pct = 0.0
                    if _promo_keys and rng.random() < _promo_prob:
                        discount_pct = rng.choices(_promo_keys, weights=_promo_wts, k=1)[0]
                    unit_price_net = round(unit_price / (1.0 + tax_rate), 4)
                    line_total_net = round(qty_delivered * unit_price_net * (1.0 - discount_pct), 2)
                    line_total     = round(qty_delivered * unit_price * (1.0 - discount_pct), 2)
                    order_lines.append({
                        "product_id":         prod_id,
                        "quantity":           qty_delivered,   # entregue (= saída de estoque)
                        "quantity_ordered":   qty_requested,   # pedido original do cliente
                        "quantity_delivered": qty_delivered,
                        "unit_price":         unit_price,       # preço de TABELA (bruto, s/ desconto)
                        "discount_pct":       discount_pct,
                        "line_total":         line_total,       # bruto COM desconto aplicado
                        "tax_rate":           tax_rate,
                    })
                    order_total     += line_total
                    order_total_net += line_total_net

                    # ---- Merma / caducidad (apenas perecíveis) ----
                    # Ao tocar um item perecível, há pequena chance de descartar
                    # unidades por validade. É uma SAÍDA real de estoque (reason
                    # 'waste') — mantém a integridade do inventário — além do
                    # evento product_waste para a análise de mermas do gerente.
                    if product.get("is_perishable") and waste_prob and rng.random() < waste_prob:
                        avail_now = stock_rec["quantity_on_hand"]
                        if avail_now > 0:
                            w_qty = min(
                                avail_now,
                                rng.choices(waste_qty_keys, weights=waste_qty_wts, k=1)[0],
                            )
                            counters["waste"] += 1
                            waste_id = f"WST-{year_str}-{counters['waste']:08d}"
                            unit_cost_w = stock_rec.get("unit_cost") or round(unit_price / (1.0 + tax_rate) * 0.75, 4)
                            self._remove_stock(
                                prod_id, location_type, location_id,
                                w_qty, result, counters, today_str,
                                reason="waste", reference_id=waste_id,
                            )
                            result.product_waste.append({
                                "waste_id":      waste_id,
                                "date":          today_str,
                                "product_id":    prod_id,
                                "category":      grp,
                                "location_type": location_type,
                                "location_id":   location_id,
                                "quantity":      w_qty,
                                "unit_cost":     round(unit_cost_w, 4),
                                "lost_cost":     round(w_qty * unit_cost_w, 2),
                                "reason":        "caducidad",
                            })

                    # Após decremento — checar se precisa reabastecer
                    stock_rec_after = self.stock_index.get(prod_id, {}).get(
                        (location_type, location_id)
                    )
                    if stock_rec_after and stock_rec_after["quantity_on_hand"] <= stock_rec_after["reorder_point"]:
                        if location_type == "DC":
                            self._buffer_po_line(
                                prod_id, location_id, stock_rec_after,
                                active_suppliers, today_str, po_buffer, in_transit_pos,
                            )
                        else:  # STORE
                            self._schedule_transfer(
                                prod_id, location_id, stock_rec_after,
                                today, counters, pending_transfers,
                                po_buffer, active_suppliers, today_str, in_transit_pos,
                                in_transit_transfers,
                            )

                if not order_lines:
                    continue

                # ---- Criar pedido de venda ----
                counters["sale"] += 1
                order_id = f"ORD_{counters['sale']:08d}"
                # Carimbo intradía (hora-punta) — hora do dia pela curva diurna.
                order_ts = _order_timestamp(today, cfg, rng)

                # Atualizar referência nas linhas com o order_id real
                for ol in order_lines:
                    ol["order_id"] = order_id

                # Reescrever reference_id dos movimentos de VENDA deste pedido
                # ('pending_order' → order_id real). Movimentos de merma mantêm
                # o próprio waste_id.
                for mov in result.stock_movements[mov_start:]:
                    if mov.get("reason") == "sale":
                        mov["reference_id"] = order_id

                result.sales.append({
                    "order_id":             order_id,
                    "customer_id":          cust_id,
                    "order_date":           today_str,
                    "order_ts":             order_ts,
                    "store_id":             order_store_id,
                    "dc_id":                order_dc_id,
                    "region":               region,
                    "channel":              channel,
                    "ticket_trend":         ticket_trend,
                    "num_items":            len(order_lines),
                    "total_amount":         round(order_total, 2),       # bruto
                    "total_amount_net":     round(order_total_net, 2),   # líquido (sem IVA)
                    "status":               "confirmed",
                    "has_partial_stockout": has_stockout,
                })

                for line in order_lines:
                    counters["item"] += 1
                    result.sale_lines.append({
                        "item_id":            f"ITM_{counters['item']:09d}",
                        "order_id":           order_id,
                        "product_id":         line["product_id"],
                        "quantity":           line["quantity"],
                        "quantity_ordered":   line["quantity_ordered"],
                        "quantity_delivered": line["quantity_delivered"],
                        "unit_price":         line["unit_price"],
                        "discount_pct":       line["discount_pct"],
                        "line_total":         line["line_total"],
                        "tax_rate":           line["tax_rate"],
                    })

                # ---- Entrega (apenas ecommerce) ----
                if channel == "ecommerce":
                    del_days = delivery_days_map.get(region, delivery_days_map.get("default", 3))
                    del_days = max(1, del_days + rng.randint(-1, 1))
                    sched_date = _fmt(today + timedelta(days=del_days))

                    # Determinar sale_id (padrão do schema.py)
                    seq_digits = "".join(filter(str.isdigit, order_id))
                    seq        = int(seq_digits) if seq_digits else counters["sale"]
                    sale_id    = f"SO-{year_str}-{seq:07d}"

                    counters["delivery"] += 1
                    del_record = {
                        "delivery_id":          f"DEL_{counters['delivery']:08d}",
                        "order_id":             order_id,
                        "sale_id":              sale_id,
                        "customer_id":          cust_id,
                        "dc_id":                order_dc_id,
                        "location_type":        location_type,
                        "location_id":          location_id,
                        "region":               region,
                        "channel":              channel,
                        "order_date":           today_str,
                        "scheduled_date":       sched_date,
                        "actual_delivery_date": None,
                        "delivery_status":      "in_transit",
                        "total_amount":         round(order_total, 2),
                        # Linhas internas para agendar returns (removidas no flush final)
                        "_order_lines": order_lines,
                    }
                    pending_deliveries.append(del_record)

            # ================================================================
            # ETAPA 7 — Flush do po_buffer → PO headers + lines + AP
            # ================================================================
            for buf_key, buf_entry in po_buffer.items():
                supplier_id, dc_id_po, _ = buf_key
                supplier = self.supplier_index.get(supplier_id)
                if not supplier or not buf_entry.get("lines"):
                    continue

                counters["po"] += 1
                po_header = build_purchase_order_header(
                    buf_entry, supplier, self.product_index, year_str, counters["po"]
                )

                po_lines = build_purchase_order_lines(
                    po_header["po_id"], buf_entry, self.product_index
                )

                result.po_headers.append(po_header)
                result.po_lines.extend(po_lines)

                # Registrar PO na fila de pendentes para processar recebimento futuro
                lead_time = supplier.get("lead_time_days", 14)
                supply_pressure = _supply_pressure_multiplier(today, cfg)
                actual_lead = max(1, round(lead_time * rng.uniform(0.8, 1.2) * supply_pressure))
                expected_receipt = _fmt(today + timedelta(days=actual_lead))
                po_header["expected_receipt_date"] = expected_receipt
                pending_pos.append(po_header)
                # Linhas guardadas FORA do header (evita vazar `_lines` ao CSV/RAW)
                pending_po_lines[po_header["po_id"]] = po_lines
                # Marcar produtos como em trânsito até o recebimento
                for pl in po_lines:
                    in_transit_pos.add((pl["product_id"], po_header["dc_id"]))

                # Criar obrigação AP
                counters["payment"] += 1
                pay_terms_days = supplier.get("payment_terms_days", 30)
                due_dt   = today + timedelta(days=pay_terms_days)
                due_date = _fmt(due_dt)

                ap_record = build_supplier_payment(
                    po_header, supplier, year_str, counters["payment"]
                )
                ap_record["due_date"] = due_date
                pending_payments.append(ap_record)

            # Limpar buffer após flush diário
            po_buffer.clear()

            # Callback opcional por dia
            if self.on_day_complete:
                self.on_day_complete({
                    "date":               today_str,
                    "day_of_week":        today.strftime("%A"),
                    "is_weekend":         int(today.weekday() >= 5),
                    "demand_multiplier":  round(day_mult, 4),
                    "pending_pos":        len(pending_pos),
                    "pending_deliveries": len(pending_deliveries),
                    "pending_transfers":  len(pending_transfers),
                    "pending_returns":    len(pending_returns),
                    "pending_payments":   len(pending_payments),
                })

        # ---- Flush de entregas ainda pendentes (após fim da simulação) ----
        for deliv in pending_deliveries:
            # Remover campo interno antes de persistir
            deliv.pop("_order_lines", None)
            result.deliveries.append(deliv)

        # ---- Flush de pagamentos AP ainda pendentes ----
        result.supplier_payments.extend(pending_payments)

        # ---- Metadados ----
        result.metadata = {
            "start_date":            cfg["start_date"],
            "end_date":              _fmt(end_dt),
            "total_days_simulated":  total_days,
            "num_customers":         len(self.customers),
            "num_products":          len(self.products),
            "num_suppliers":         len(self.suppliers),
            "num_stores":            len(self.stores),
            "num_dcs":               len(self.distribution_centers),
            "config_snapshot": {
                k: v for k, v in cfg.items()
                if not isinstance(v, (dict, list)) and v is not None
            },
        }

        return result

    # ------------------------------------------------------------------
    # Métodos auxiliares privados
    # ------------------------------------------------------------------

    def _add_stock(
        self,
        product_id: str,
        location_type: str,
        location_id: str,
        qty: int,
        result: SimulationResult,
        counters: Dict,
        date_str: str,
        reason: str,
        reference_id: str,
    ) -> int:
        """
        Adiciona `qty` unidades ao estoque e registra o movimento.

        Retorna a quantidade EFETIVAMENTE adicionada (após o teto de max_stock),
        para que o chamador (recebimento) registre exatamente o que entrou —
        garantindo que goods_receipts reconcilie com stock_movements.
        """
        key = (location_type, location_id)
        if product_id not in self.stock_index or key not in self.stock_index[product_id]:
            # Cria registro de estoque dinâmico caso não exista
            self.stock_index[product_id][key] = {
                "stock_id":        f"STK_DYN_{product_id}_{location_id}",
                "product_id":      product_id,
                "location_type":   location_type,
                "location_id":     location_id,
                "quantity_on_hand": 0,
                "reorder_point":   10,
                "max_stock":       200,
                "unit_cost":       1.0,
                "last_updated":    date_str,
            }

        rec       = self.stock_index[product_id][key]
        qty_before = rec["quantity_on_hand"]
        rec["quantity_on_hand"] = min(
            rec["quantity_on_hand"] + qty,
            rec.get("max_stock", rec["quantity_on_hand"] + qty),
        )
        rec["last_updated"] = date_str
        applied = rec["quantity_on_hand"] - qty_before

        # transfer_in é a contraparte de transfer_out: ambos são TRANSFER (interno)
        mov_type = "TRANSFER" if reason == "transfer_in" else "IN"

        counters["movement"] += 1
        result.stock_movements.append({
            "movement_id":    f"MOV_{counters['movement']:09d}",
            "date":           date_str,
            "product_id":     product_id,
            "location_type":  location_type,
            "location_id":    location_id,
            "movement_type":  mov_type,
            "reason":         reason,
            "reference_id":   reference_id,
            "quantity_delta": applied,
            "quantity_after": rec["quantity_on_hand"],
        })
        return applied

    def _remove_stock(
        self,
        product_id: str,
        location_type: str,
        location_id: str,
        qty: int,
        result: SimulationResult,
        counters: Dict,
        date_str: str,
        reason: str,
        reference_id: str,
    ):
        """Remove `qty` unidades do estoque e registra o movimento."""
        key = (location_type, location_id)
        rec = self.stock_index[product_id][key]
        qty_before = rec["quantity_on_hand"]
        rec["quantity_on_hand"] = max(0, rec["quantity_on_hand"] - qty)
        rec["last_updated"] = date_str

        # Determinar movement_type: TRANSFER para transferências, OUT para vendas/saídas
        if reason in ("transfer_out",):
            mov_type = "TRANSFER"
        else:
            mov_type = "OUT"

        counters["movement"] += 1
        result.stock_movements.append({
            "movement_id":    f"MOV_{counters['movement']:09d}",
            "date":           date_str,
            "product_id":     product_id,
            "location_type":  location_type,
            "location_id":    location_id,
            "movement_type":  mov_type,
            "reason":         reason,
            "reference_id":   reference_id,
            "quantity_delta": -(qty_before - rec["quantity_on_hand"]),
            "quantity_after": rec["quantity_on_hand"],
        })

    def _buffer_po_line(
        self,
        product_id: str,
        dc_id: str,
        stock_rec: Dict,
        active_suppliers: List[Dict],
        today_str: str,
        po_buffer: Dict,
        in_transit_pos: set,
    ):
        """
        Adiciona uma linha ao po_buffer para o DC indicado.

        O buffer é agrupado por (supplier_id, dc_id, date). Cada produto
        vai para o fornecedor de maior reliability_score que cobre a categoria
        do produto (ou o de maior reliability geral como fallback).

        Política de reposição = order-up-to-S: pede exatamente o necessário para
        recompor max_stock. Se o produto já tem PO em trânsito para o DC, NÃO
        reordena (evita sobre-compra e perda de unidades no teto de max_stock).
        """
        if not active_suppliers:
            return

        # Já há uma PO a caminho para este produto/DC → não reordenar
        if (product_id, dc_id) in in_transit_pos:
            return

        product  = self.product_index.get(product_id, {})
        # category_specialization dos fornecedores é lista de category_group
        # canônico (ver suppliers.py); casar pelo grupo do produto, não pelo leaf.
        category = product.get("category_group") or product.get("category", "otros")

        # Tentar fornecedor especializado na categoria
        specialized = [
            s for s in active_suppliers
            if category in s.get("category_specialization", [])
        ]
        supplier = max(
            specialized if specialized else active_suppliers,
            key=lambda s: s.get("reliability_score", 0.0),
        )
        supplier_id = supplier["supplier_id"]

        buf_key = (supplier_id, dc_id, today_str)

        # Inicializar entrada do buffer se necessário
        if buf_key not in po_buffer:
            po_buffer[buf_key] = {
                "supplier_id": supplier_id,
                "dc_id":       dc_id,
                "order_date":  today_str,
                "lines":       [],
                "_prod_ids":   set(),   # evita duplicatas de produto no mesmo dia/DC/supplier
            }

        entry = po_buffer[buf_key]
        if product_id in entry["_prod_ids"]:
            return  # já está no buffer para hoje

        entry["_prod_ids"].add(product_id)

        # Quantidade a pedir — order-up-to-max (repõe até o estoque máximo)
        qty_to_order = max(1, stock_rec["max_stock"] - stock_rec["quantity_on_hand"])
        unit_cost    = stock_rec.get("unit_cost", 1.0)

        entry["lines"].append({
            "product_id":     product_id,
            "quantity":       qty_to_order,
            "unit_cost":      unit_cost,
            "line_total_net": round(qty_to_order * unit_cost, 2),
            "tax_rate":       product.get("tax_rate", 0.10),
        })

    def _schedule_transfer(
        self,
        product_id: str,
        store_id: str,
        stock_rec: Dict,
        today: datetime,
        counters: Dict,
        pending_transfers: List[Dict],
        po_buffer: Dict,
        active_suppliers: List[Dict],
        today_str: str,
        in_transit_pos: set,
        in_transit_transfers: set,
    ):
        """
        Agenda uma transferência CD→Loja para reposição automática.

        A quantidade agendada é limitada ao que o DC tem disponível hoje, e a
        aplicação (ETAPA 3) reconfirma a disponibilidade — garantindo que a
        transferência conserve unidades. Se o DC ficar abaixo do reorder_point,
        dispara PO upstream via po_buffer.
        """
        # Determinar DC de origem da loja
        store = self.stores_index.get(store_id, {})
        from_dc = store.get("dc_id", "DC_MAD")

        # Dedup O(1): já há transferência pendente para este produto+loja?
        if (product_id, store_id) in in_transit_transfers:
            return  # já agendado

        # Quantidade para repor a loja, limitada ao disponível no DC
        max_stock    = stock_rec.get("max_stock", 50)
        qty_on_hand  = stock_rec.get("quantity_on_hand", 0)
        store_room   = max(1, max_stock - qty_on_hand)
        dc_stock_rec = self.stock_index.get(product_id, {}).get(("DC", from_dc))
        dc_avail     = dc_stock_rec["quantity_on_hand"] if dc_stock_rec else 0
        qty_transfer = min(store_room, dc_avail)

        if qty_transfer > 0:
            arrival_days = self.rng.randint(6, 14)
            arrival_date = _fmt(today + timedelta(days=arrival_days))

            counters["transfer"] += 1
            tr_id = f"TR-{today_str[:4]}-{counters['transfer']:07d}"

            pending_transfers.append({
                "transfer_id":  tr_id,
                "product_id":   product_id,
                "from_dc":      from_dc,
                "to_store":     store_id,
                "quantity":     qty_transfer,
                "request_date": today_str,
                "arrival_date": arrival_date,
            })
            in_transit_transfers.add((product_id, store_id))

        # Verificar se o DC também precisa de reposição (após a transferência)
        if dc_stock_rec:
            qty_dc_after = dc_stock_rec["quantity_on_hand"] - qty_transfer
            if qty_dc_after <= dc_stock_rec.get("reorder_point", 10):
                self._buffer_po_line(
                    product_id, from_dc, dc_stock_rec,
                    active_suppliers, today_str, po_buffer, in_transit_pos,
                )
