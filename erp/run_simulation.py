"""
run_simulation.py
=================
Entrypoint do Simulador de Vendas — mercado espanhol.

Targets de saída (--target):
    csv     — Exporta CSVs para source/ (default). Ingestão batch → DuckDB/Snowflake.
    kafka   — Publica eventos normalizados ao Kafka conforme cada dia é simulado
              (streaming → MinIO → Snowflake RAW). Memória constante.
              Requer: docker compose -f extensions/streaming/docker-compose.yml up -d

O batch (csv) é o caminho canônico e COMPLETO — 18 tabelas. O streaming (kafka) é uma
extensão EXPERIMENTAL que cobre 16 das 18 tabelas (`suppliers` e `stock_snapshots` ainda
NÃO são publicados) — ver extensions/streaming. Ambos normalizam via erp/simulator/normalize.py.

Modos de simulação (--mode):
    historical  — Simula período completo (default).
    realtime    — Loop dia a dia com feed ao vivo. Útil para demo de dashboards.

Períodos predefinidos (--period):
    365d / 180d / 90d / 30d → últimos N dias
    ytd                     → do início do ano corrente até hoje

Uso:
    python erp/run_simulation.py --period 365d
    python erp/run_simulation.py --target kafka --period 365d --seed 42
    python erp/run_simulation.py --target csv --period 90d
    python erp/run_simulation.py --mode realtime --interval 0.5
    python erp/run_simulation.py --start 2024-01-01 --end 2025-12-31 --customers 2000
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, date as _date, timedelta as _timedelta
from pathlib import Path

ERP_DIR       = Path(__file__).resolve().parent          # erp/
REPO_ROOT     = ERP_DIR.parent                            # repository root
RESOURCES_DIR = ERP_DIR / "resources" / "mercadona"
SOURCE_DIR    = Path(os.environ.get("SOURCE_DIR", REPO_ROOT / "source"))  # CSV export dir (env-overridable)

sys.path.insert(0, str(REPO_ROOT))                        # so `import erp.*` resolves

from erp.generators.geo_spain  import get_postal_codes
from erp.generators.stores     import generate_stores
from erp.generators.customers  import generate_customers, apply_segment_drift
from erp.generators.suppliers  import generate_suppliers
from erp.generators.inventory  import get_distribution_centers, generate_dc_stock, generate_store_stock

from erp.simulator.engine  import SimulationEngine
from erp.simulator.config  import DEFAULT_CONFIG
from erp.simulator.schema  import (
    build_products,
    build_customers,
    build_suppliers,
    build_stores,
    build_delivery_note,
    build_invoice,
    build_stock_snapshot,
)
from erp.simulator.normalize import (
    normalize_sales,
    group_lines_by_order,
    normalize_sale_lines,
    normalize_deliveries,
    normalize_invoices,
    adapt_raw_delivery,
)


# ---------------------------------------------------------------------------
# CSV helpers (only used with --export-csv)
# ---------------------------------------------------------------------------

def _save_csv(data: list, path: Path) -> None:
    if not data:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)
    print(f"  [csv] {path.name}  ({len(data):,} linhas)")


def _save_json(data, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    print(f"  [csv] {path.name}  ({len(data):,} registros)")


# ---------------------------------------------------------------------------
# Product loader
# ---------------------------------------------------------------------------

PRODUCTS_CATALOG_CSV = RESOURCES_DIR / "products_catalog.csv"


def _load_products() -> list:
    """Carrega o catálogo de produtos do CSV base versionado.

    Fonte única e versionada: ``erp/resources/mercadona/products_catalog.csv``
    (colunas: id, brand, name, variant, price, category_path, category_name,
    image_url). É a base do simulador — sem scraper nem fallback sintético.
    """
    if not PRODUCTS_CATALOG_CSV.exists():
        raise FileNotFoundError(
            f"Catálogo de produtos não encontrado: {PRODUCTS_CATALOG_CSV}. "
            "É o CSV base versionado do simulador."
        )
    with open(PRODUCTS_CATALOG_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [
        {
            "product_id":    f"PROD_{idx:06d}",
            "sku":           p.get("id") or f"SKU_{idx}",
            "name":          p.get("name") or "Producto sin nombre",
            "brand":         p.get("brand") or "Marca desconocida",
            "category":      p.get("category_name") or "Sin categoría",
            "category_path": p.get("category_path", ""),
            "price":         _parse_price(p.get("price", "0")),
            "unit":          p.get("variant") or "unidad",
            "image_url":     p.get("image_url", ""),
            "active":        True,
        }
        for idx, p in enumerate(rows, start=1)
    ]


def _parse_price(raw) -> float:
    try:
        return round(float(str(raw).replace(",", ".")), 2)
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _resolve_period(period: str, start_arg: str, end_arg: str):
    if period is None:
        return start_arg, end_arg
    today = _date.today()
    if period == "ytd":
        return str(_date(today.year, 1, 1)), str(today)
    if period.endswith("d"):
        n = int(period[:-1])  # qualquer Nd, incl. 730d (2 anos)
        return str(today - _timedelta(days=n - 1)), str(today)
    if period.endswith("m"):
        n = int(period[:-1])
        return str(today - _timedelta(days=n * 30)), str(today)
    raise ValueError(
        f"Período desconhecido: {period!r}. Use: 730d, 365d, 180d, 90d, 30d, ytd "
        "(ou qualquer Nd / Nm)."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Simulador de Vendas — Espanha")
    p.add_argument("--target",     type=str,   default="csv",
                   choices=["csv", "kafka"],
                   help="csv: exporta CSVs (batch) | kafka: stream normalizado para Kafka")
    p.add_argument("--mode",       type=str,   default="historical",
                   choices=["historical", "realtime"],
                   help="historical: batch completo | realtime: feed dia a dia")
    p.add_argument("--period",     type=str,   default=None,
                   help="Atalho de período: 730d (2 anos), 365d, 180d, 90d, 30d, ytd (ou Nd/Nm)")
    p.add_argument("--days",       type=int,   default=None,
                   help="Número de dias (ignora --start/--end)")
    p.add_argument("--start",      type=str,   default="2024-01-01",
                   help="Data inicial (YYYY-MM-DD)")
    p.add_argument("--end",        type=str,   default="2025-12-31",
                   help="Data final   (YYYY-MM-DD). Default = janela canônica de 2 anos "
                        "(2024-01-01..2025-12-31), na qual TODOS os market_shocks disparam.")
    p.add_argument("--customers",  type=int,   default=100000,
                   help="Número de clientes")
    p.add_argument("--stores",     type=int,   default=0,
                   help="Número de lojas Mercadona (0 = todas as lojas do CSV real, se disponível)")
    p.add_argument("--suppliers",  type=int,   default=20,
                   help="Número de fornecedores")
    p.add_argument("--seed",       type=int,   default=None,
                   help="Seed para reprodutibilidade")
    p.add_argument("--interval",   type=float, default=0.0,
                   help="(realtime) segundos entre cada dia simulado")
    p.add_argument("--export-csv", action="store_true",
                   help="Exportar para source/ em CSV (implícito quando --target csv)")
    p.add_argument("--segment-drift-event", action="store_true",
                   help="No export CSV, gravar também customers_drift.csv (v2) com "
                        "drift de segmento determinístico (~3%% dos clientes)")
    p.add_argument("--kafka-servers", type=str, default="localhost:9094",
                   help="Kafka bootstrap servers (quando --target kafka)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Kafka streaming mode
# ---------------------------------------------------------------------------

def _kafka_main(args) -> None:
    """
    Run simulation in Kafka streaming target mode.

    Events are NORMALIZED (via erp/simulator/normalize.py — as MESMAS funções do
    caminho CSV) e publicados aos tópicos Kafka conforme cada dia é simulado (via
    callback on_day_complete), em memória constante (só o delta do dia vive a cada
    instante). O schema publicado é o RAW canônico que o dbt lê → zero drift entre
    batch e streaming.

    Fluxo:
        1. Gera master data
        2. Publica master data 1x (products/customers/stores/suppliers/dcs)
        3. Roda o engine — on_day_complete normaliza e publica o delta do dia:
           - sales/sale_lines: build_sale_order_header/_lines
           - tienda → fatura no dia do pedido; ecommerce → stash até a entrega
           - deliveries maturadas → build_delivery_note + build_invoice (ecommerce)
           - stockouts/stock_movements/PO/receipts/payments/returns/waste: canônicos
        4. Resumo de throughput
    """
    import random as _random
    from erp.simulator.kafka_bus import KafkaEventBus

    print("=" * 65)
    print("  SIMULADOR DE VENDAS — ESPANHA  →  Kafka Streaming")
    print("=" * 65)

    # ── Resolve período ────────────────────────────────────────────────
    start, end = _resolve_period(args.period, args.start, args.end)
    if args.days:
        end = str((_date.fromisoformat(start) + _timedelta(days=args.days - 1)))

    # ── [1/4] Master data ──────────────────────────────────────────────
    print("\n[1/4] Gerando master data...")
    postal_codes = get_postal_codes()
    stores    = generate_stores(postal_codes, num_stores=args.stores, seed=args.seed)
    customers = generate_customers(args.customers, postal_codes, seed=args.seed, stores=stores)
    suppliers = generate_suppliers(args.suppliers, seed=args.seed)
    products  = _load_products()
    dcs       = get_distribution_centers()

    # Enriquece master data antes do estoque/engine (custo líquido + IVA corretos)
    erp_products  = build_products(products)
    erp_customers = build_customers(customers)
    erp_suppliers = build_suppliers(suppliers)
    erp_stores    = build_stores(stores)

    dc_stock  = generate_dc_stock(erp_products, dcs, seed=args.seed)
    store_stock = generate_store_stock(erp_products, stores, seed=args.seed)
    stock     = dc_stock + store_stock

    # Índices p/ a normalização canônica no callback (mesmos do caminho CSV)
    product_idx  = {p["product_id"]: p for p in erp_products}
    customer_idx = {c["customer_id"]: c for c in erp_customers}

    print(f"  {len(stores):,} lojas  |  {len(customers):,} clientes  |  {len(products):,} produtos")

    # ── [2/4] Conectar ao Kafka e publicar master data ─────────────────
    print(f"\n[2/4] Conectando ao Kafka ({args.kafka_servers}) e publicando master data...")
    bus = KafkaEventBus(args.kafka_servers)

    bus.publish_batch("distribution_centers", dcs)
    bus.publish_batch("stores",               erp_stores)
    bus.publish_batch("products",             erp_products)
    bus.publish_batch("customers",            erp_customers)
    bus.publish_batch("suppliers",            erp_suppliers)
    print(f"  {bus.total_published:,} registros de master data publicados ✓")

    # ── [3/4] Simulação com streaming por dia ──────────────────────────
    if args.seed is not None:
        _random.seed(args.seed)

    cfg = {
        **DEFAULT_CONFIG,
        "start_date":    start,
        "end_date":      end,
        "num_customers": args.customers,
        "num_suppliers": args.suppliers,
        "random_seed":   args.seed,
    }

    engine = SimulationEngine(
        products=erp_products,
        customers=customers,
        suppliers=suppliers,
        stock=stock,
        stores=stores,
        distribution_centers=dcs,
        config=cfg,
    )

    # Totais acumulados por entidade (as listas do result são esvaziadas a cada
    # dia → len(r.*) no fim seria 0). Constant-memory: a cada dia só vive o delta
    # daquele dia (~13k eventos), não os 9,5M do run inteiro.
    totals: dict[str, int] = {}
    days_done = 0

    # Stash de pedidos ecommerce aguardando entrega: order_id → (header, lines).
    # Populado quando o pedido é publicado; consumido quando a entrega maturar
    # (build_invoice ecommerce usa a data de entrega). Bounded pelo lead time
    # de entrega (~1-4 dias) → memória trivial, preserva constant-memory.
    open_ecom: dict = {}

    def _pub(entity: str, rows: list) -> int:
        if not rows:
            return 0
        n = bus.publish_batch(entity, rows)
        totals[entity] = totals.get(entity, 0) + len(rows)
        return n

    # Entidades já canônicas no engine (CSV exporta idênticas) → publicar raw.
    _RAW_CANONICAL = (
        "stock_movements", "stockouts", "purchase_orders", "purchase_order_lines",
        "goods_receipts", "supplier_payments", "product_returns", "product_waste",
    )

    def _normalize_publish_clear(r) -> int:
        """Normaliza o delta do dia para o schema canônico, publica e esvazia.

        Mesmos builders do caminho CSV (via normalize.py) → linhas idênticas.
        """
        day_total = 0

        # --- Sales + sale_lines (normalizados) ---
        headers, _ = normalize_sales(r.sales, customer_idx)
        items_by_order = group_lines_by_order(r.sale_lines)
        sale_lines_all, lines_by_sale_id = normalize_sale_lines(
            r.sales, items_by_order, product_idx
        )
        day_total += _pub("sales", headers)
        day_total += _pub("sale_lines", sale_lines_all)

        # --- Invoices: tienda agora; ecommerce fica em stash até a entrega ---
        tienda_invoices = []
        for sale, hdr in zip(r.sales, headers):
            lines = lines_by_sale_id.get(hdr["sale_id"], [])
            if hdr.get("channel") == "ecommerce":
                open_ecom[sale["order_id"]] = (hdr, lines)
            else:
                tienda_invoices.append(build_invoice(hdr, lines, None))
        day_total += _pub("invoices", tienda_invoices)

        # --- Deliveries maturadas hoje → nota + fatura ecommerce ---
        day_deliveries, ecom_invoices = [], []
        for raw_del in r.deliveries:
            hdr, lines = open_ecom.pop(raw_del.get("order_id", ""), ({}, []))
            note = build_delivery_note(adapt_raw_delivery(raw_del), hdr)
            day_deliveries.append(note)
            ecom_invoices.append(build_invoice(hdr, lines, note))
        day_total += _pub("deliveries", day_deliveries)
        day_total += _pub("invoices", ecom_invoices)

        # --- Entidades já canônicas → publicar raw ---
        for entity in _RAW_CANONICAL:
            attr = "po_headers" if entity == "purchase_orders" else (
                "po_lines" if entity == "purchase_order_lines" else entity
            )
            day_total += _pub(entity, getattr(r, attr))

        # --- Esvaziar TODAS as listas do dia (libera RAM) ---
        for lst in (r.sales, r.sale_lines, r.deliveries, r.stock_movements,
                    r.stockouts, r.po_headers, r.po_lines, r.goods_receipts,
                    r.supplier_payments, r.product_returns, r.product_waste):
            lst[:] = []
        return day_total

    def _on_day_kafka(day_rec: dict) -> None:
        nonlocal days_done
        r = engine._current_result  # exposed by the 1-line patch in engine.py
        day_total = _normalize_publish_clear(r)
        bus.flush()   # 1 flush por dia (não por batch) → drena o buffer do produtor
        days_done += 1
        print(
            f"  {day_rec['date']}  "
            f"→  {day_total:5,} eventos  "
            f"[total: {bus.total_published:,}]",
            end="\r", flush=True,
        )

    engine.on_day_complete = _on_day_kafka

    print("\n[3/4] Executando simulação com streaming Kafka...")
    print(f"  Período  : {start} → {end}")
    print(f"  Clientes : {args.customers:,}  |  Produtos : {len(products):,}  |  Seed : {args.seed}\n")

    t0 = time.time()
    engine.run(days=args.days, config=cfg)   # eventos saem via on_day_complete
    elapsed = time.time() - t0

    # Flush final: o engine faz flushes pós-loop (deliveries e supplier_payments
    # que maturam após o último dia). Normaliza e publica o resíduo — as entregas
    # residuais ainda casam com os pedidos em open_ecom (faturas ecommerce finais).
    r = engine._current_result
    _normalize_publish_clear(r)

    bus.close()

    # ── [4/4] Resumo ───────────────────────────────────────────────────
    print()
    rate = bus.total_published / elapsed if elapsed > 0 else 0
    print(f"\n[4/4] Concluído em {elapsed:.1f}s")
    print(f"\n{'=' * 65}")
    print("  Kafka Streaming — Resumo")
    print(f"{'=' * 65}")
    print(f"  Dias simulados      : {days_done:>8,}")
    print(f"  Total de eventos    : {bus.total_published:>8,}")
    print(f"  Taxa de publicação  : {rate:>8,.0f} eventos/s")
    # As listas foram esvaziadas (constant-memory) → usar os totais acumulados.
    print(f"  Vendas geradas      : {totals.get('sales', 0):>8,}")
    print(f"  Mov. de estoque     : {totals.get('stock_movements', 0):>8,}")
    print("  Tópicos             : retail.sales · retail.stock_movements · …")
    print("\n  Próximo passo:")
    print("    make kafka-consume   # MinIO Console → localhost:9001")
    print("    # Kafka UI           → localhost:8090")
    print(f"{'=' * 65}")


# ---------------------------------------------------------------------------
# Realtime mode
# ---------------------------------------------------------------------------

def _realtime_loop(engine: SimulationEngine, cfg: dict, interval: float):
    import itertools
    print("\n  Pressione Ctrl+C para interromper.\n")
    spinner = itertools.cycle("|/-\\")

    def on_day(rec: dict):
        spin = next(spinner)
        print(
            f"  {spin} {rec['date']}"
            f"  |  pending POs: {rec['pending_pos']:3d}"
            f"  |  pending entregas: {rec['pending_deliveries']:3d}"
        )
        if interval > 0:
            time.sleep(interval)

    engine.on_day_complete = on_day
    return engine.run(config=cfg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # ── Target routing ─────────────────────────────────────────────────
    if args.target == "kafka":
        _kafka_main(args)
        return

    # --target csv → exporta CSVs (ingestão batch via DuckDB/Snowflake).
    args.export_csv = True  # alias: --target csv → --export-csv

    print("=" * 65)
    print("  SIMULADOR DE VENDAS — ESPANHA  →  CSV (source/)")
    print("=" * 65)

    # ── Resolve período ────────────────────────────────────────────────
    start, end = _resolve_period(args.period, args.start, args.end)
    if args.days:
        end = str((_date.fromisoformat(start) + _timedelta(days=args.days - 1)))
    if start > end:
        print(f"\n  ERRO: janela temporal inválida — start ({start}) > end ({end}).")
        sys.exit(1)

    # ── [1/5] Geodados ─────────────────────────────────────────────────
    print("\n[1/5] Carregando geodados espanhóis...")
    postal_codes = get_postal_codes()
    print(f"  {len(postal_codes)} códigos postais carregados")

    # ── [2/5] Master data ──────────────────────────────────────────────
    print("\n[2/5] Gerando master data...")

    stores    = generate_stores(postal_codes, num_stores=args.stores, seed=args.seed)
    print(f"  {len(stores):,} lojas geradas")

    customers = generate_customers(args.customers, postal_codes, seed=args.seed, stores=stores)
    print(f"  {len(customers):,} clientes gerados")

    suppliers = generate_suppliers(args.suppliers, seed=args.seed)
    print(f"  {len(suppliers):,} fornecedores gerados")

    products  = _load_products()
    print(f"  {len(products):,} produtos carregados")

    # Enriquece master data via builders (antes do estoque/engine, para que o
    # custo líquido e a alíquota de IVA corretos fluam para tudo a jusante).
    erp_products  = build_products(products)
    erp_customers = build_customers(customers)
    erp_suppliers = build_suppliers(suppliers)
    erp_stores    = build_stores(stores)

    dcs       = get_distribution_centers()
    dc_stock  = generate_dc_stock(erp_products, dcs, seed=args.seed)
    store_stock = generate_store_stock(erp_products, stores, seed=args.seed)
    stock     = dc_stock + store_stock
    print(f"  {len(dcs)} DCs  |  {len(stock):,} registros de estoque inicial")

    # Índices rápidos
    product_idx  = {p["product_id"]: p for p in erp_products}
    customer_idx = {c["customer_id"]: c for c in erp_customers}

    # ── [3/5] Simulação ────────────────────────────────────────────────
    import random
    if args.seed is not None:
        random.seed(args.seed)

    cfg = {
        **DEFAULT_CONFIG,
        "start_date":    start,
        "end_date":      end,
        "num_customers": args.customers,
        "num_suppliers": args.suppliers,
        "random_seed":   args.seed,
    }

    print(f"\n[3/5] Executando simulação ({args.mode})...")
    print(f"  Período  : {start} → {end}")
    print(f"  Clientes : {args.customers:,}  |  Produtos : {len(products):,}  |  Seed : {args.seed}")

    trends = {}
    for c in customers:
        t = c.get("ticket_trend", "stable")
        trends[t] = trends.get(t, 0) + 1
    print(f"  Trends   : stable={trends.get('stable',0):,}  growing={trends.get('growing',0):,}  declining={trends.get('declining',0):,}")

    engine = SimulationEngine(
        products=erp_products,
        customers=customers,
        suppliers=suppliers,
        stock=stock,
        stores=stores,
        distribution_centers=dcs,
        config=cfg,
    )

    t0 = datetime.now()
    if args.mode == "realtime":
        result = _realtime_loop(engine, cfg, args.interval)
    else:
        result = engine.run(days=args.days, config=cfg)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\n  Concluído em {elapsed:.1f}s")
    print(result.summary())

    # ── [4/5] Normalizar dados transacionais ───────────────────────────
    print("\n[4/5] Normalizando schema do ERP...")

    # Normalização canônica via erp/simulator/normalize.py — as MESMAS funções
    # usadas pelo caminho streaming (_kafka_main), garantindo linhas idênticas
    # no RAW independente da ingestão (anti-drift).

    # --- Sales (header + lines) ---
    sales_headers, orders_by_order_id = normalize_sales(result.sales, customer_idx)

    items_by_order = group_lines_by_order(result.sale_lines)
    sale_lines_all, lines_by_sale_id = normalize_sale_lines(
        result.sales, items_by_order, product_idx
    )

    # Liberar memória: as linhas brutas já foram normalizadas. Em runs longos
    # (2 anos) evita manter DUAS cópias de milhões de linhas em RAM.
    result.sale_lines = []
    items_by_order.clear()

    # --- Deliveries (ecommerce) ---
    deliveries_built, delivery_by_order_id = normalize_deliveries(
        result.deliveries, orders_by_order_id
    )

    # --- Invoices (TODOS os canais: ecommerce na entrega, tienda no pedido) ---
    invoices_built = normalize_invoices(
        result.sales, sales_headers, lines_by_sale_id, delivery_by_order_id
    )

    # --- Stock snapshot (estado final do estoque no engine) ---
    stock_snapshot = build_stock_snapshot(engine.stock_index, end, product_idx)

    # ── [5/5] Export CSV opcional ──────────────────────────────────────
    if args.export_csv:
        print("\n[5/5] Exportando CSVs para source/ ...")
        SOURCE_DIR.mkdir(exist_ok=True)
        _save_csv(dcs,               SOURCE_DIR / "distribution_centers.csv")
        _save_csv(erp_stores,        SOURCE_DIR / "stores.csv")
        _save_csv(erp_products,      SOURCE_DIR / "products.csv")
        _save_csv(erp_customers,     SOURCE_DIR / "customers.csv")
        if args.segment_drift_event:
            # v2 drift: same in-memory rows already mapped to the CSV schema.
            # apply_segment_drift is pure → customers.csv is left untouched.
            drifted_customers, num_moved = apply_segment_drift(
                erp_customers, seed=args.seed if args.seed is not None else 42,
            )
            _save_csv(drifted_customers, SOURCE_DIR / "customers_drift.csv")
            print(f"  [drift] {num_moved:,} clientes mudaram de segmento "
                  f"(v2 → customers_drift.csv)")
        _save_csv(erp_suppliers,     SOURCE_DIR / "suppliers.csv")
        _save_csv(sales_headers,     SOURCE_DIR / "sales.csv")
        _save_csv(sale_lines_all,    SOURCE_DIR / "sale_lines.csv")
        _save_csv(result.po_headers, SOURCE_DIR / "purchase_orders.csv")
        _save_csv(result.po_lines,   SOURCE_DIR / "purchase_order_lines.csv")
        _save_csv(result.goods_receipts,    SOURCE_DIR / "goods_receipts.csv")
        _save_csv(deliveries_built,  SOURCE_DIR / "deliveries.csv")
        _save_csv(invoices_built,    SOURCE_DIR / "invoices.csv")
        _save_csv(result.supplier_payments, SOURCE_DIR / "supplier_payments.csv")
        _save_csv(result.product_returns,   SOURCE_DIR / "product_returns.csv")
        _save_csv(result.product_waste,     SOURCE_DIR / "product_waste.csv")
        _save_csv(result.stockouts,         SOURCE_DIR / "stockouts.csv")
        _save_csv(result.stock_movements,   SOURCE_DIR / "stock_movements.csv")
        _save_csv(stock_snapshot,           SOURCE_DIR / "stock_snapshots.csv")
        print(f"  CSVs em: {SOURCE_DIR}/")
    else:
        print("\n[5/5] CSV export ignorado (use --export-csv para staging Snowflake)")

    # ── Resumo final ───────────────────────────────────────────────────
    total_revenue = sum(o.get("total_gross", o.get("total_amount", 0.0)) for o in sales_headers)
    aov = total_revenue / len(sales_headers) if sales_headers else 0.0
    online = sum(1 for o in result.sales if o.get("channel") == "ecommerce")
    tienda = len(result.sales) - online

    trend_stats: dict = {}
    for o in result.sales:
        t = o.get("ticket_trend", "stable")
        trend_stats.setdefault(t, {"count": 0, "total": 0.0})
        trend_stats[t]["count"] += 1
        trend_stats[t]["total"] += o.get("total_amount", 0.0)

    print(f"\n{'=' * 65}")
    print("  Resumo final")
    print(f"{'=' * 65}")
    print(f"  Pedidos de venda    : {len(result.sales):>8,}")
    print(f"  GMV total (gross)   : €{total_revenue:>12,.2f}")
    print(f"  Ticket médio (AOV)  : €{aov:>9.2f}")
    print(f"  Canal ecommerce     : {online:>7,}  ({online/max(1,len(result.sales))*100:.1f}%)")
    print(f"  Canal tienda        : {tienda:>7,}  ({tienda/max(1,len(result.sales))*100:.1f}%)")
    print()
    print("  Ticket médio por comportamento:")
    for trend, st in sorted(trend_stats.items()):
        avg = st["total"] / st["count"] if st["count"] else 0
        print(f"    {trend:<10} : {st['count']:>6,} pedidos  |  €{avg:>8.2f} médio")
    print()
    print(f"  Rupturas de estoque : {len(result.stockouts):>8,}")
    print(f"  Pedidos de compra   : {len(result.po_headers):>8,}")
    print(f"  Linhas de PO        : {len(result.po_lines):>8,}")
    print(f"  Recebimentos        : {len(result.goods_receipts):>8,}")
    print(f"  Entregas            : {len(result.deliveries):>8,}")
    print(f"  Faturas             : {len(invoices_built):>8,}")
    print(f"  Pag. fornecedores   : {len(result.supplier_payments):>8,}")
    print(f"  Devoluções          : {len(result.product_returns):>8,}")
    waste_units = sum(w.get("quantity", 0) for w in result.product_waste)
    waste_cost  = sum(w.get("lost_cost", 0.0) for w in result.product_waste)
    print(f"  Mermas (eventos)    : {len(result.product_waste):>8,}  "
          f"({waste_units:,} un · €{waste_cost:,.0f})")
    print(f"  Mov. de estoque     : {len(result.stock_movements):>8,}")
    print(f"  Snapshot de estoque : {len(stock_snapshot):>8,}")
    print(f"\n  Dados exportados em CSV → {SOURCE_DIR}/")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
