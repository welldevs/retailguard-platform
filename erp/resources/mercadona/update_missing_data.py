#!/usr/bin/env python3
"""
Script para atualizar dados incompletos nos produtos.
Executa apenas o backfill de dados faltantes (categorias, imagens, preços unitários).

Uso:
    python update_missing_data.py
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import from scraper
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from scraper import (
    fetch_page_with_retry,
    BeautifulSoup,
    time,
    csv,
    json,
    OUTPUT_CSV,
    OUTPUT_JSON,
    CSV_FIELDS,
    CATEGORY_DELAY
)
import requests

def main():
    """Execute data backfill operation."""
    print("=" * 70)
    print("PRODUTO DATA BACKFILL - Atualizar Dados Incompletos")
    print("=" * 70)

    # Force backfill mode
    os.environ["BACKFILL_ONLY"] = "1"
    os.environ["FETCH_PRODUCT_CATEGORIES"] = "1"

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
        "Connection": "keep-alive"
    })

    print("\nCarregando dados dos produtos...")
    if not OUTPUT_CSV.exists() or not OUTPUT_JSON.exists():
        print("✗ Erro: Arquivos de produtos não encontrados.")
        print("  Execute webscraper_produtos.py primeiro para coletar dados.")
        sys.exit(1)

    # Load existing data
    csv_rows = []
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        csv_rows = list(csv.DictReader(f))

    json_data = []
    with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    print(f"✓ Carregados {len(csv_rows)} produtos do CSV")
    print(f"✓ Carregados {len(json_data)} produtos do JSON")

    # Build lookup tables
    rows_by_id = {row.get("id"): row for row in csv_rows if row.get("id")}
    products_by_id = {}
    for item in json_data:
        if isinstance(item, dict) and item.get("id"):
            products_by_id[item["id"]] = item

    # Identify missing data
    print("\nAnalisando dados incompletos...")

    missing_categories = [
        item for item in products_by_id.values()
        if item.get("product_url") and (not item.get("category_path") or not item.get("category_name"))
    ]

    missing_images = [
        item for item in products_by_id.values()
        if item.get("product_url") and not item.get("image_url")
    ]

    missing_unit_price = [
        item for item in products_by_id.values()
        if item.get("product_url") and not item.get("unit_price")
    ]

    print(f"\n  Produtos sem categoria: {len(missing_categories)}")
    print(f"  Produtos sem imagem: {len(missing_images)}")
    print(f"  Produtos sem preço unitário: {len(missing_unit_price)}")

    if not missing_categories and not missing_images and not missing_unit_price:
        print("\n✓ Todos os dados estão completos!")
        return

    # Process updates
    print(f"\nAtualizando dados (Total: {len(products_by_id)} produtos)...")

    updated_count = 0
    processed = 0

    for index, item in enumerate(products_by_id.values(), start=1):
        product_url = item.get("product_url")
        if not product_url:
            continue

        product_id = item.get("id")
        row = rows_by_id.get(product_id)
        needs_update = False

        # Check if needs update
        if not item.get("category_path") or not item.get("category_name"):
            html = fetch_page_with_retry(session, product_url, retries=2)
            if html:
                soup = BeautifulSoup(html, "html.parser")

                # Try breadcrumbs first
                breadcrumb_list = soup.select_one("section#subheader ul.breadcrumbs")
                if breadcrumb_list:
                    breadcrumbs = breadcrumb_list.select("li.breadcrumbs__item a")
                    if breadcrumbs:
                        category_parts = []
                        for breadcrumb in breadcrumbs:
                            text = breadcrumb.get_text(strip=True)
                            if text:
                                category_parts.append(text)
                        if category_parts:
                            item["category_path"] = " > ".join(category_parts)
                            item["category_name"] = category_parts[-1]
                            if row:
                                row["category_path"] = item["category_path"]
                                row["category_name"] = item["category_name"]
                            needs_update = True

                # Try JSON visibility script
                if not item.get("category_path"):
                    visibility = soup.find("script", id="visibility", type="application/json")
                    if visibility and visibility.string:
                        try:
                            category_slug = json.loads(visibility.string).get("category", "")
                            if category_slug:
                                item["category_path"] = category_slug.replace("/", " > ").replace("-", " ").title()
                                item["category_name"] = category_slug.rsplit("/", 1)[-1].replace("-", " ").title()
                                if row:
                                    row["category_path"] = item["category_path"]
                                    row["category_name"] = item["category_name"]
                                needs_update = True
                        except Exception:
                            pass

        if needs_update:
            updated_count += 1

        processed += 1
        if processed % 100 == 0 or processed == len(products_by_id):
            pct = int((processed / len(products_by_id)) * 100)
            print(f"  Progresso: {processed}/{len(products_by_id)} ({pct}%) - Atualizados: {updated_count}")

        time.sleep(CATEGORY_DELAY / 2)  # Lighter delay

    # Save updated data
    print(f"\nSalvando {updated_count} produtos atualizados...")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(csv_rows)
    print(f"✓ Salvo: {OUTPUT_CSV}")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"✓ Salvo: {OUTPUT_JSON}")

    print("\n" + "=" * 70)
    print("BACKFILL CONCLUÍDO COM SUCESSO!")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrompido pelo usuário.")
    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
