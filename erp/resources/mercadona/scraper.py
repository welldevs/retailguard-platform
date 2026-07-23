import os
import csv
import json
import time
import math
import urllib.parse
import requests
from bs4 import BeautifulSoup
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Configuration
BRANDS = ["hacendado", "deliplus", "bosque-verde", "compy"]
OUTPUT_CSV = BASE_DIR / "produtos_mix.csv"
OUTPUT_JSON = BASE_DIR / "produtos_mix.json"
STATE_FILE = BASE_DIR / "scraper_state.json"
DELAY = 1.5  # Seconds between requests
CATEGORY_DELAY = 0.4  # Extra pause when fetching product detail pages
FETCH_PRODUCT_CATEGORIES = os.getenv("FETCH_PRODUCT_CATEGORIES", "1").lower() not in {"0", "false", "no"}
BACKFILL_ONLY = os.getenv("BACKFILL_ONLY", "").lower() in {"1", "true", "yes"}
REQUEST_CONNECT_TIMEOUT = float(os.getenv("REQUEST_CONNECT_TIMEOUT", "5"))
REQUEST_READ_TIMEOUT = float(os.getenv("REQUEST_READ_TIMEOUT", "8"))
REQUEST_TIMEOUT = (REQUEST_CONNECT_TIMEOUT, REQUEST_READ_TIMEOUT)
CSV_FIELDS = [
    "id",
    "brand",
    "name",
    "variant",
    "price",
    "unit_price",
    "category_path",
    "category_name",
    "category_url",
    "image_url",
    "product_url",
    "scraped_at"
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8,en-US;q=0.5,en;q=0.3",
    "Connection": "keep-alive"
}

def clean_existing_data():
    """Clean duplicates from existing output files to fix any prior issues on startup."""
    print("Cleaning and deduplicating existing data files...")

    # 1. Clean CSV
    if OUTPUT_CSV.exists():
        try:
            cleaned_rows = []
            seen_ids = set()
            with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pid = row.get("id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        cleaned_rows.append({field: row.get(field, "") for field in CSV_FIELDS})

            with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()
                writer.writerows(cleaned_rows)
            print(f"-> Cleaned CSV: Removed duplicates. Unique items: {len(seen_ids)}")
        except Exception as e:
            print(f"Error cleaning CSV: {e}")

    # 2. Clean JSON
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)

            cleaned_data = []
            seen_ids = set()
            for item in data:
                if isinstance(item, dict) and "id" in item:
                    pid = item["id"]
                    if pid not in seen_ids:
                        seen_ids.add(pid)
                        for field in CSV_FIELDS:
                            item.setdefault(field, "")
                        cleaned_data.append(item)

            with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
                json.dump(cleaned_data, f, indent=4, ensure_ascii=False)
            print(f"-> Cleaned JSON: Removed duplicates. Unique items: {len(seen_ids)}")
        except Exception as e:
            print(f"Error cleaning JSON: {e}")

def load_existing_scraped_ids():
    """Load already scraped product IDs from both CSV and JSON to avoid any duplicate rows."""
    scraped_ids = set()

    # Load from CSV
    if OUTPUT_CSV.exists():
        try:
            with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if row:
                        scraped_ids.add(row[0])  # First column is ID
        except Exception as e:
            print(f"Warning loading existing CSV IDs: {e}")

    # Load from JSON
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data:
                    if isinstance(item, dict) and "id" in item:
                        scraped_ids.add(item["id"])
        except Exception as e:
            print(f"Warning loading existing JSON IDs: {e}")

    return scraped_ids

def load_state():
    """Load the progress state of the scraper to allow resuming."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load state file: {e}. Starting fresh.")

    # Default initial state
    return {
        "current_brand_index": 0,
        "current_page": 1,
        "completed_brands": []
    }

def save_state(state):
    """Save the progress state to a JSON file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def initialize_output_files():
    """Ensure output CSV and JSON files are properly initialized."""
    # Initialize CSV header if it doesn't exist
    if not OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_FIELDS)

    # Initialize JSON file as an empty list if it doesn't exist
    if not OUTPUT_JSON.exists():
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump([], f, indent=4)

def save_products(products_data, scraped_ids):
    """Save products to both CSV and JSON, filtering duplicates and updating scraped_ids."""
    new_products = []
    for p in products_data:
        pid = p["id"]
        if pid not in scraped_ids:
            new_products.append(p)
            scraped_ids.add(pid)

    if not new_products:
        return 0

    # Append to CSV
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        for p in new_products:
            writer.writerow({field: p.get(field, "") for field in CSV_FIELDS})

    # Load, append, and save to JSON
    json_data = []
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not parse existing JSON, resetting list: {e}")

    json_data.extend(new_products)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=4, ensure_ascii=False)

    return len(new_products)

def fetch_page_with_retry(session, url, retries=3):
    """Fetch URL with retries and exponential backoff."""
    for attempt in range(retries):
        try:
            print(
                f"Requesting {url} (attempt {attempt + 1}/{retries}, "
                f"timeout {REQUEST_CONNECT_TIMEOUT:g}s/{REQUEST_READ_TIMEOUT:g}s)...",
                flush=True
            )
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.text
            elif response.status_code == 429:
                wait_time = (attempt + 1) * 10
                print(f"Rate limited (429). Waiting {wait_time}s before retry...", flush=True)
                time.sleep(wait_time)
            else:
                print(f"Failed to fetch {url} (Status: {response.status_code}). Attempt {attempt + 1}/{retries}", flush=True)
                time.sleep(2)
        except requests.exceptions.Timeout as e:
            print(f"Timeout fetching {url}: {e}. Attempt {attempt + 1}/{retries}", flush=True)
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            print(f"Network error fetching {url}: {e}. Attempt {attempt + 1}/{retries}", flush=True)
            time.sleep(2)
    return None

def parse_category_from_product_html(html):
    """Extract product category details from a Soysuper product page."""
    soup = BeautifulSoup(html, "html.parser")
    breadcrumb_list = soup.select_one("section#subheader ul.breadcrumbs") or soup.select_one("ul.breadcrumbs")
    breadcrumbs = breadcrumb_list.select("li.breadcrumbs__item a") if breadcrumb_list else []
    if breadcrumbs:
        category_parts = []
        category_url = ""
        for breadcrumb in breadcrumbs:
            text = breadcrumb.get_text(strip=True)
            if text:
                category_parts.append(text)
                category_url = urllib.parse.urljoin("https://soysuper.com", breadcrumb.get("href", ""))
        if category_parts:
            return {
                "category_path": " > ".join(category_parts),
                "category_name": category_parts[-1],
                "category_url": category_url
            }

    visibility = soup.find("script", id="visibility", type="application/json")
    if visibility and visibility.string:
        try:
            category_slug = json.loads(visibility.string).get("category", "")
        except json.JSONDecodeError:
            category_slug = ""
        if category_slug:
            return {
                "category_path": category_slug.replace("/", " > ").replace("-", " ").title(),
                "category_name": category_slug.rsplit("/", 1)[-1].replace("-", " ").title(),
                "category_url": urllib.parse.urljoin("https://soysuper.com/c/", category_slug)
            }

    return {
        "category_path": "",
        "category_name": "",
        "category_url": ""
    }

def fetch_product_category(session, product_url, category_cache):
    """Fetch and cache category details from a product detail page."""
    empty_category = {
        "category_path": "",
        "category_name": "",
        "category_url": ""
    }
    if not product_url:
        return empty_category
    if product_url in category_cache:
        return category_cache[product_url]

    html = fetch_page_with_retry(session, product_url)
    category = parse_category_from_product_html(html) if html else empty_category
    category_cache[product_url] = category
    time.sleep(CATEGORY_DELAY)
    return category

def backfill_missing_data(session):
    """Fill missing fields for products already present in the CSV/JSON outputs."""
    if not FETCH_PRODUCT_CATEGORIES:
        return

    csv_rows = []
    if OUTPUT_CSV.exists():
        with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
            csv_rows = [
                {field: row.get(field, "") for field in CSV_FIELDS}
                for row in csv.DictReader(f)
            ]

    json_data = []
    if OUTPUT_JSON.exists():
        try:
            with open(OUTPUT_JSON, "r", encoding="utf-8") as f:
                json_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not parse existing JSON for backfill: {e}")

    rows_by_id = {row.get("id"): row for row in csv_rows if row.get("id")}
    products_by_id = {}
    for item in json_data:
        if isinstance(item, dict) and item.get("id"):
            products_by_id[item["id"]] = item

    for row in csv_rows:
        pid = row.get("id")
        if pid and pid not in products_by_id:
            products_by_id[pid] = row
            json_data.append(row)

    # Find products with missing critical data
    targets_categories = [
        item for item in products_by_id.values()
        if item.get("product_url") and (not item.get("category_path") or not item.get("category_name"))
    ]

    targets_images = [
        item for item in products_by_id.values()
        if item.get("product_url") and not item.get("image_url")
    ]

    targets_unit_price = [
        item for item in products_by_id.values()
        if item.get("product_url") and not item.get("unit_price")
    ]

    all_targets = list(set([item.get("id") for item in targets_categories + targets_images + targets_unit_price]))

    if not all_targets:
        print("No missing data to backfill.")
        return

    print(f"\nBackfilling missing data for {len(all_targets)} products...")
    print(f"  - Missing categories: {len(targets_categories)}")
    print(f"  - Missing images: {len(targets_images)}")
    print(f"  - Missing unit prices: {len(targets_unit_price)}")

    category_cache = {}
    updated_count = 0

    for index, item in enumerate(products_by_id.values(), start=1):
        if item.get("id") not in all_targets:
            continue

        product_url = item.get("product_url")
        if not product_url:
            continue

        # Fetch category and other details from product page
        if not item.get("category_path") or not item.get("category_name"):
            category = fetch_product_category(session, product_url, category_cache)
            item.update(category)
            row = rows_by_id.get(item.get("id"))
            if row:
                row.update(category)
            updated_count += 1

        # Try to fetch additional details if image or unit price is missing
        if not item.get("image_url") or not item.get("unit_price"):
            html = fetch_page_with_retry(session, product_url)
            if html:
                soup = BeautifulSoup(html, "html.parser")

                # Update image if missing
                if not item.get("image_url"):
                    img_tag = soup.find("img", class_="product-image")
                    if img_tag:
                        img_url = img_tag.get("src", "")
                        if img_url:
                            item["image_url"] = urllib.parse.urljoin("https://soysuper.com", img_url)
                            row = rows_by_id.get(item.get("id"))
                            if row:
                                row["image_url"] = item["image_url"]

                # Update unit price if missing
                if not item.get("unit_price"):
                    unit_price_span = soup.find("span", class_="unitprice")
                    if unit_price_span:
                        unit_price = unit_price_span.get_text(strip=True)
                        item["unit_price"] = unit_price
                        row = rows_by_id.get(item.get("id"))
                        if row:
                            row["unit_price"] = unit_price

            time.sleep(CATEGORY_DELAY)

        if index % 100 == 0 or index == len(products_by_id):
            pct = int((index / len(products_by_id)) * 100)
            print(f"-> Backfill progress: {index}/{len(products_by_id)} ({pct}%) - Updated: {updated_count}")

    print(f"Backfill completed. Updated {updated_count} products.\n")

    # Save updated data
    if csv_rows:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"✓ Saved updated CSV: {OUTPUT_CSV}")

    if json_data:
        with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=4, ensure_ascii=False)
        print(f"✓ Saved updated JSON: {OUTPUT_JSON}")

def parse_products_from_html(html, search_brand, session=None, category_cache=None, scraped_ids=None):
    """Parse product list from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    ul = soup.find("ul", class_="productlist")
    if not ul:
        return [], 0

    # Find total product count from the page text or h1
    total_count = 0
    subheader = soup.find("section", id="subheader")
    if subheader:
        h1 = subheader.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            # Extract numbers from title (e.g. "2645 productos" -> 2645)
            numbers = "".join(filter(str.isdigit, h1_text))
            if numbers:
                total_count = int(numbers)

    products = []
    items = ul.find_all("li", recursive=False)

    for item in items:
        pid = item.get("data-pid")
        if not pid:
            continue

        # Get brand
        brand_tag = item.find("span", class_="brand")
        brand = brand_tag.get_text(strip=True) if brand_tag else search_brand.replace("-", " ").title()

        # Get name and link
        name_link_tag = item.find("a", class_="name")
        name = "Unknown"
        product_url = ""
        if name_link_tag:
            product_url = urllib.parse.urljoin("https://soysuper.com", name_link_tag.get("href", ""))

            # Find the actual product name span
            name_span = name_link_tag.find("span", class_="productname")
            if name_span:
                name = name_span.get_text(strip=True)
            else:
                name = name_link_tag.get_text(strip=True)

        # Get image
        img_tag = item.find("img", itemprop="image")
        image_url = img_tag.get("src", "") if img_tag else ""

        # Get price details
        price = ""
        unit_price = ""
        variant = ""

        details_span = item.find("span", class_="details")
        if details_span:
            # Try to get meta price
            meta_price = details_span.find("meta", itemprop="price")
            if meta_price:
                price = meta_price.get("content", "")

            # Get display price containing variant (e.g. "1,56€  / Paquete 1 kg")
            price_span = details_span.find("span", class_="price")
            if price_span:
                price_text = price_span.get_text(strip=True)
                if "/" in price_text:
                    parts = price_text.split("/", 1)
                    variant = parts[1].strip()
                    if not price:
                        price = parts[0].replace("€", "").strip()
                else:
                    if not price:
                        price = price_text.replace("€", "").strip()

            # Get unit price
            unit_price_span = details_span.find("span", class_="unitprice")
            if unit_price_span:
                unit_price = unit_price_span.get_text(strip=True)

        category = {
            "category_path": "",
            "category_name": "",
            "category_url": ""
        }
        is_new_product = scraped_ids is None or pid not in scraped_ids
        if FETCH_PRODUCT_CATEGORIES and is_new_product and session and category_cache is not None:
            category = fetch_product_category(session, product_url, category_cache)

        products.append({
            "id": pid,
            "brand": brand,
            "name": name,
            "variant": variant,
            "price": price,
            "unit_price": unit_price,
            "category_path": category.get("category_path", ""),
            "category_name": category.get("category_name", ""),
            "category_url": category.get("category_url", ""),
            "image_url": image_url,
            "product_url": product_url,
            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")
        })

    return products, total_count

def run_scraper():
    """Main function to run the scraper with resume support."""
    print("=" * 60)
    print("STARTING PRODUTO MIX SCRAPER")
    print("=" * 60)

    session = requests.Session()
    session.headers.update(HEADERS)
    category_cache = {}

    # 1. Deduplicate files and load already scraped IDs
    clean_existing_data()
    initialize_output_files()
    backfill_missing_data(session)
    if BACKFILL_ONLY:
        print("BACKFILL_ONLY enabled. Data backfill finished; skipping product search.")
        return

    scraped_ids = load_existing_scraped_ids()
    print(f"Loaded {len(scraped_ids)} unique product IDs already saved in files.\n")

    state = load_state()

    start_brand_idx = state["current_brand_index"]
    start_page = state["current_page"]

    for brand_idx in range(start_brand_idx, len(BRANDS)):
        brand = BRANDS[brand_idx]
        print(f"\nProcessing brand: {brand.upper()} ({brand_idx + 1}/{len(BRANDS)})")

        page = start_page if brand_idx == start_brand_idx else 1
        total_products = -1
        total_pages = 1

        while page <= total_pages:
            url = f"https://soysuper.com/search?q={brand.replace('-', '+')}&page={page}"
            print(f"[{brand.upper()}] Fetching page {page}/{total_pages if total_products != -1 else '?'}...")

            html = fetch_page_with_retry(session, url)
            if not html:
                print(f"Skipping page {page} due to persistent fetch errors.")
                page += 1
                state["current_page"] = page
                save_state(state)
                continue

            products, count = parse_products_from_html(html, brand, session, category_cache, scraped_ids)

            # If it's page 1 (or we haven't updated total pages yet), set the limits
            if total_products == -1 and count > 0:
                total_products = count
                total_pages = math.ceil(total_products / 25)
                print(f"[{brand.upper()}] Found {total_products} products in total -> {total_pages} pages.")
            elif total_products == -1:
                # No products found at all for this brand search
                print(f"[{brand.upper()}] No products found.")
                break

            if products:
                # Save new products and filter out duplicates
                added_count = save_products(products, scraped_ids)
                print(f"[{brand.upper()}] Page {page}: parsed {len(products)} products, added {added_count} new unique items.")
            else:
                print(f"[{brand.upper()}] Warning: No products parsed from page {page} (but list is not completed).")

            # Update state after successful page scrape
            page += 1
            state["current_page"] = page
            save_state(state)

            # Sleep between requests to respect rate limiters
            time.sleep(DELAY)

        # Brand completed
        print(f"[{brand.upper()}] Brand scraping completed successfully.")
        state["completed_brands"].append(brand)
        state["current_brand_index"] = brand_idx + 1
        state["current_page"] = 1
        save_state(state)

    # All brands completed
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED SUCCESSFULLY!")
    print(f"Output saved to:\n  CSV: {OUTPUT_CSV}\n  JSON: {OUTPUT_JSON}")
    print("=" * 60)

    # Remove state file upon successful completion
    if STATE_FILE.exists():
        STATE_FILE.unlink()

if __name__ == "__main__":
    try:
        run_scraper()
    except KeyboardInterrupt:
        print("\nInterrupted by user. Progress already saved up to the last completed page.")
