"""
generators/stores.py
Gera lojas Mercadona distribuídas pela Espanha.

Quando disponível, usa a base real/sintética de endereços Mercadona em
erp/resources/mercadona/stores_mercadona.csv. O fallback mantém o gerador
anterior, ponderado por densidade populacional dos códigos postais.
"""

from typing import List, Dict, Tuple
from pathlib import Path
import csv
import random
import unicodedata

from erp.simulator.config import DEFAULT_CONFIG


REAL_STORES_CSV = (
    Path(__file__).resolve().parents[1]
    / "resources"
    / "mercadona"
    / "stores_mercadona.csv"
)


# ---------------------------------------------------------------------------
# Mapeamento CCAA → dc_id (Centro de Distribuição) — FONTE ÚNICA no config.
# Antes havia um mapa duplicado aqui e em config.py (risco de divergência entre
# o dc_id da loja e a rota de e-commerce do engine). Agora ambos leem o mesmo
# dicionário canônico de DEFAULT_CONFIG["region_to_dc"].
# ---------------------------------------------------------------------------

REGION_TO_DC: Dict[str, str] = DEFAULT_CONFIG["region_to_dc"]

CCAA_ALIASES: Dict[str, str] = {
    "Comunidad Valenciana": "Comunitat Valenciana",
    "Euskadi": "País Vasco",
    "Baleares": "Illes Balears",
}

# Centroides aproximados (lat, lon) por CCAA canônico — para geocodificar lojas.
# Não são coordenadas exatas do endereço (o CSV real não as traz); dão dispersão
# geográfica realista para mapas. Jitter determinístico por loja é aplicado sobre
# o centroide em _geocode().
CCAA_CENTROIDS: Dict[str, Tuple[float, float]] = {
    "Comunidad de Madrid":        (40.42, -3.70),
    "Cataluña":                   (41.60,  1.60),
    "Andalucía":                  (37.40, -4.80),
    "Comunitat Valenciana":       (39.48, -0.75),
    "País Vasco":                 (43.05, -2.62),
    "Castilla y León":            (41.65, -4.72),
    "Galicia":                    (42.76, -7.98),
    "Castilla-La Mancha":         (39.50, -3.00),
    "Canarias":                   (28.30, -16.50),
    "Región de Murcia":           (37.99, -1.13),
    "Aragón":                     (41.60, -0.90),
    "Extremadura":                (39.20, -6.15),
    "Illes Balears":              (39.57,  2.92),
    "Principado de Asturias":     (43.30, -5.99),
    "Comunidad Foral de Navarra": (42.70, -1.65),
    "Cantabria":                  (43.20, -3.99),
    "La Rioja":                   (42.29, -2.54),
    "Ceuta":                      (35.89, -5.32),
    "Melilla":                    (35.29, -2.94),
}
_DEFAULT_CENTROID = (40.42, -3.70)  # Madrid


def _geocode(ccaa: str, rng: random.Random) -> Tuple[float, float]:
    """Coordenada aproximada = centroide da CCAA + jitter determinístico (±~0.4°)."""
    base_lat, base_lon = CCAA_CENTROIDS.get(ccaa, _DEFAULT_CENTROID)
    lat = round(base_lat + rng.uniform(-0.4, 0.4), 5)
    lon = round(base_lon + rng.uniform(-0.4, 0.4), 5)
    return lat, lon


def _normalize_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(value.lower().split())


def _canonical_ccaa(value: str) -> str:
    return CCAA_ALIASES.get(value, value)


def _load_real_store_rows() -> List[Dict]:
    if not REAL_STORES_CSV.exists():
        return []

    with REAL_STORES_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _build_location_indexes(postal_codes: List[Dict]) -> Tuple[Dict, Dict, Dict, Dict]:
    by_city_province: Dict[Tuple[str, str], List[Dict]] = {}
    by_city: Dict[str, List[Dict]] = {}
    by_province: Dict[str, List[Dict]] = {}
    by_ccaa: Dict[str, List[Dict]] = {}

    for pc in postal_codes:
        city_key = _normalize_key(pc.get("municipality", ""))
        province_key = _normalize_key(pc.get("province", ""))
        ccaa_key = _normalize_key(_canonical_ccaa(pc.get("ccaa", "")))

        by_city_province.setdefault((city_key, province_key), []).append(pc)
        by_city.setdefault(city_key, []).append(pc)
        by_province.setdefault(province_key, []).append(pc)
        by_ccaa.setdefault(ccaa_key, []).append(pc)

    return by_city_province, by_city, by_province, by_ccaa


def _pick_location(row: Dict, indexes: Tuple[Dict, Dict, Dict, Dict], rng: random.Random) -> Dict:
    by_city_province, by_city, by_province, by_ccaa = indexes

    city_key = _normalize_key(row.get("city", ""))
    province_key = _normalize_key(row.get("province", ""))
    ccaa_key = _normalize_key(_canonical_ccaa(row.get("region", "")))

    candidates = (
        by_city_province.get((city_key, province_key))
        or by_city.get(city_key)
        or by_province.get(province_key)
        or by_ccaa.get(ccaa_key)
        or []
    )
    return rng.choice(candidates) if candidates else {}


def _opening_date(rng: random.Random) -> str:
    year = rng.randint(2010, 2023)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{year}-{month:02d}-{day:02d}"


def _store_size(row: Dict, location: Dict, rng: random.Random) -> int:
    density = location.get("population_density", 100)
    has_listo = str(row.get("has_listo_para_comer", "")).lower() in ("t", "true", "1")
    has_cafe = str(row.get("has_cafe_service", "")).lower() in ("t", "true", "1")

    if density > 5000:
        sqm = rng.randint(2000, 3500)
    elif density > 1000:
        sqm = rng.randint(1200, 2500)
    else:
        sqm = rng.randint(800, 1600)

    if has_listo:
        sqm += rng.randint(80, 180)
    if has_cafe:
        sqm += rng.randint(40, 120)

    return min(sqm, 3800)


def _generate_real_stores(
    postal_codes: List[Dict],
    num_stores: int,
    seed: int = None,
) -> List[Dict]:
    rng = random.Random(seed)
    rows = _load_real_store_rows()
    indexes = _build_location_indexes(postal_codes)

    enriched = []
    for row in rows:
        location = _pick_location(row, indexes, rng)
        enriched.append((row, location))

    if num_stores and num_stores > 0 and num_stores < len(enriched):
        scoped = [item for item in enriched if item[1]]
        sample_frame = scoped if len(scoped) >= num_stores else enriched
        enriched = rng.sample(sample_frame, k=num_stores)

    enriched.sort(key=lambda item: int(item[0].get("id") or 0))

    stores: List[Dict] = []
    for row, location in enriched:
        original_id = int(row.get("id") or len(stores) + 1)
        city = row.get("city", "").strip()
        address = row.get("address", "").strip()
        ccaa = _canonical_ccaa(row.get("region", "").strip())
        province = row.get("province", "").strip()
        dc_id = REGION_TO_DC.get(ccaa) or REGION_TO_DC.get(row.get("region", ""), "DC_MAD")
        name = f"Mercadona {city} - {address}".strip(" -")

        store_ccaa = ccaa or location.get("ccaa", "")
        opening = _opening_date(rng)
        sqm_val = _store_size(row, location, rng)
        lat, lon = _geocode(store_ccaa, rng)
        stores.append({
            "store_id": f"ST_{original_id:05d}",
            "name": name[:100],
            "postal_code": location.get("postal_code", ""),
            "municipality": city or location.get("municipality", ""),
            "province": province or location.get("province", ""),
            "ccaa": store_ccaa,
            "dc_id": dc_id,
            "opening_date": opening,
            "sqm": sqm_val,
            "latitude": lat,
            "longitude": lon,
            "active": True,
        })

    return stores


def generate_stores(
    postal_codes: List[Dict],
    num_stores: int = 0,
    seed: int = None,
) -> List[Dict]:
    """
    Gera N lojas Mercadona.

    Se stores_mercadona.csv existir, usa endereços reais/sintéticos desse arquivo
    e enriquece com CEP/CCAA/DC a partir de geo_spain.py. Passe ``num_stores=0``
    ou um valor negativo para usar todas as lojas disponíveis no CSV.

    Args:
        postal_codes: Lista de dicts de geo_spain (campos: postal_code,
                      municipality, province, ccaa, population_density).
        num_stores:   Número de lojas a gerar (padrão 150).
        seed:         Semente para reprodutibilidade.

    Returns:
        Lista de dicts correspondentes à tabela ``stores`` do DDL:
            store_id, name, postal_code, municipality, province, ccaa,
            dc_id, opening_date, sqm, latitude, longitude, active
    """
    if not postal_codes:
        raise ValueError("postal_codes list must not be empty")

    if _load_real_store_rows():
        return _generate_real_stores(postal_codes, num_stores, seed)

    rng = random.Random(seed)

    # Amostragem ponderada por densidade (com reposição: postais densos podem ter +1 loja)
    weights = [pc.get("population_density", 100) for pc in postal_codes]
    selected = rng.choices(postal_codes, weights=weights, k=num_stores)

    stores: List[Dict] = []
    for i, pc in enumerate(selected, start=1):
        ccaa = pc.get("ccaa", "")
        dc_id = REGION_TO_DC.get(ccaa, "DC_MAD")   # fallback Madrid

        # sqm: lojas maiores em municípios de alta densidade
        density = pc.get("population_density", 100)
        if density > 5000:
            sqm = rng.randint(2000, 3500)
        elif density > 1000:
            sqm = rng.randint(1200, 2500)
        else:
            sqm = rng.randint(800, 1500)

        # opening_date entre 2010-2023
        year = rng.randint(2010, 2023)
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        opening_date = f"{year}-{month:02d}-{day:02d}"

        store_id = f"ST_{i:05d}"
        municipality = pc.get("municipality", "")
        name = f"Mercadona {municipality}"
        lat, lon = _geocode(_canonical_ccaa(ccaa), rng)

        stores.append({
            "store_id": store_id,
            "name": name[:100],
            "postal_code": pc.get("postal_code", ""),
            "municipality": municipality,
            "province": pc.get("province", ""),
            "ccaa": ccaa,
            "dc_id": dc_id,
            "opening_date": opening_date,
            "sqm": sqm,
            "latitude": lat,
            "longitude": lon,
            "active": True,
        })

    return stores
