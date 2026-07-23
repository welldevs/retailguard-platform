"""
generators/suppliers.py
Geração de fornecedores espanhóis/europeus realistas para o Simulador de Vendas.
"""

import random
from typing import List, Dict

from erp.generators.category_map import CATEGORY_GROUPS


# ---------------------------------------------------------------------------
# Dados de referência por país
# ---------------------------------------------------------------------------

_SUPPLIER_DATA = {
    "España": {
        "cities": ["Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza",
                   "Málaga", "Bilbao", "Alicante", "Valladolid", "Murcia"],
        "name_patterns": [
            "Distribuidora {apellido} S.L.",
            "Productos {apellido} S.A.",
            "Suministros {apellido} S.L.",
            "Comercial {apellido} S.A.",
            "Grupo {apellido} S.L.",
            "Almacenes {apellido} S.A.",
            "{apellido} & Asociados S.L.",
            "Importaciones {apellido} S.A.",
        ],
        "apellidos": [
            "García", "Martínez", "López", "Sánchez", "González",
            "Rodríguez", "Fernández", "Pérez", "Gómez", "Torres",
            "Ibérica", "Peninsular", "Mediterránea", "Atlántica",
        ],
        "payment_terms": [30, 45, 60, 90],
        "lead_time_range": (2, 6),
        "reliability_range": (0.82, 1.0),
    },
    "Alemania": {
        "cities": ["Berlín", "Múnich", "Hamburgo", "Frankfurt", "Colonia",
                   "Düsseldorf", "Stuttgart", "Leipzig"],
        "name_patterns": [
            "{name} GmbH",
            "{name} AG",
            "{name} & Co. KG",
            "{name} Handelsgesellschaft mbH",
        ],
        "apellidos": [
            "Müller", "Schneider", "Fischer", "Weber", "Hoffmann",
            "Becker", "Braun", "Richter", "Klein", "Wolf",
            "Eurohandel", "Norddeutsche", "Bayerische",
        ],
        "payment_terms": [30, 60, 90],
        "lead_time_range": (5, 12),
        "reliability_range": (0.88, 1.0),
    },
    "Francia": {
        "cities": ["París", "Lyon", "Marsella", "Toulouse", "Niza",
                   "Nantes", "Montpellier", "Burdeos"],
        "name_patterns": [
            "{name} S.A.S.",
            "{name} S.A.R.L.",
            "{name} & Cie.",
            "Groupe {name} S.A.",
        ],
        "apellidos": [
            "Dubois", "Martin", "Bernard", "Leroy", "Moreau",
            "Laurent", "Dupont", "Durand", "Girard", "Lefebvre",
            "Française", "Atlantique", "Méditerranée",
        ],
        "payment_terms": [30, 45, 60],
        "lead_time_range": (4, 10),
        "reliability_range": (0.80, 0.97),
    },
    "Italia": {
        "cities": ["Roma", "Milán", "Nápoles", "Turín", "Palermo",
                   "Génova", "Bolonia", "Florencia"],
        "name_patterns": [
            "{name} S.r.l.",
            "{name} S.p.A.",
            "{name} & C. S.n.c.",
            "Gruppo {name} S.r.l.",
        ],
        "apellidos": [
            "Rossi", "Russo", "Ferrari", "Esposito", "Bianchi",
            "Romano", "Colombo", "Ricci", "Marino", "Greco",
            "Italiana", "Meridionale", "Settentrionale",
        ],
        "payment_terms": [30, 60, 90, 120],
        "lead_time_range": (5, 12),
        "reliability_range": (0.75, 0.95),
    },
    "Portugal": {
        "cities": ["Lisboa", "Porto", "Braga", "Coimbra", "Aveiro",
                   "Faro", "Setúbal", "Viseu"],
        "name_patterns": [
            "Distribuidora {name} Lda.",
            "{name} & Filhos Lda.",
            "Comercial {name} S.A.",
            "Grupo {name} Lda.",
        ],
        "apellidos": [
            "Silva", "Santos", "Ferreira", "Pereira", "Oliveira",
            "Costa", "Martins", "Rodrigues", "Lopes", "Sousa",
            "Lusitana", "Atlântica", "Peninsular",
        ],
        "payment_terms": [30, 45, 60],
        "lead_time_range": (3, 8),
        "reliability_range": (0.78, 0.96),
    },
    "Holanda": {
        "cities": ["Ámsterdam", "Rotterdam", "La Haya", "Utrecht",
                   "Eindhoven", "Tilburg", "Groninga"],
        "name_patterns": [
            "{name} B.V.",
            "{name} N.V.",
            "{name} Groep B.V.",
            "{name} Handelsmaatschappij B.V.",
        ],
        "apellidos": [
            "de Vries", "Jansen", "de Boer", "Visser", "van den Berg",
            "van Dijk", "Bakker", "Janssen", "Meijer", "de Graaf",
            "Nederland", "Euro", "Holland",
        ],
        "payment_terms": [30, 60, 90],
        "lead_time_range": (5, 12),
        "reliability_range": (0.85, 1.0),
    },
}

# Pesos para a distribuição de países (mercado espanhol — fornecedores locais dominam)
_COUNTRY_WEIGHTS = {
    "España":   0.40,
    "Alemania": 0.15,
    "Francia":  0.15,
    "Italia":   0.12,
    "Portugal": 0.10,
    "Holanda":  0.08,
}


def _build_name(pattern: str, apellido: str) -> str:
    """Substitui {apellido} ou {name} no padrão pelo nome fornecido."""
    return pattern.replace("{apellido}", apellido).replace("{name}", apellido)


def generate_suppliers(num_suppliers: int, seed: int = None) -> List[Dict]:
    """
    Gera uma lista de fornecedores espanhóis/europeus realistas.

    Args:
        num_suppliers: Número de fornecedores a gerar.
        seed: Semente opcional para reprodutibilidade.

    Returns:
        Lista de dicts com os campos:
            supplier_id, name, country, city, lead_time_days,
            reliability_score, payment_terms_days, contact_email,
            phone, active
    """
    rng = random.Random(seed)  # RNG local — não vaza estado global entre geradores/engine

    countries = list(_COUNTRY_WEIGHTS.keys())
    weights = [_COUNTRY_WEIGHTS[c] for c in countries]

    suppliers: List[Dict] = []
    seen_names: set = set()

    for i in range(1, num_suppliers + 1):
        country = rng.choices(countries, weights=weights, k=1)[0]
        data = _SUPPLIER_DATA[country]

        city = rng.choice(data["cities"])
        pattern = rng.choice(data["name_patterns"])
        apellido = rng.choice(data["apellidos"])

        # Garante nome único adicionando sufixo se necessário
        name = _build_name(pattern, apellido)
        suffix = 2
        base_name = name
        while name in seen_names:
            name = f"{base_name} {suffix}"
            suffix += 1
        seen_names.add(name)

        lead_min, lead_max = data["lead_time_range"]
        rel_min, rel_max = data["reliability_range"]

        slug = name.lower().replace(" ", "").replace(".", "")[:18]
        country_slug = country.lower().replace("ñ", "n").replace("á", "a") \
                               .replace("é", "e").replace("ü", "u")

        # Sorteia 1-3 grupos de categorias de especialização do fornecedor
        specialization = rng.sample(CATEGORY_GROUPS, k=rng.randint(1, 3))

        suppliers.append({
            "supplier_id": f"SUP_{i:05d}",
            "name": name,
            "country": country,
            "city": city,
            "lead_time_days": rng.randint(lead_min, lead_max),
            "reliability_score": round(rng.uniform(rel_min, rel_max), 4),
            "payment_terms_days": rng.choice(data["payment_terms"]),
            "contact_email": f"ventas@{slug}.{country_slug[:2]}",
            "phone": f"+{rng.randint(30, 49)}{rng.randint(100000000, 999999999)}",
            "active": True,
            "category_specialization": specialization,
        })

    return suppliers
