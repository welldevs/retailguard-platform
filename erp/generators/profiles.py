import random
from typing import Dict, List

CUSTOMER_PROFILES: Dict[str, dict] = {
    "soltero": {
        "label": "Soltero/a",
        "age_range": (22, 38),
        "weight": 0.20,
        "purchase_frequency_multiplier": 1.3,
        "basket_size_range": (1, 3),
        "avg_ticket_range": (8.0, 25.0),
        "category_weights": {
            "snacks": 0.20,
            "congelados": 0.18,
            "higiene_personal": 0.18,
            "bebidas": 0.15,
            "panaderia": 0.12,
            "lacteos": 0.10,
            "limpieza_hogar": 0.07,
            "cosmetica": 0.08,
        },
        "brand_preference": "economico",
        "online_tendency": 0.70,
    },
    "pareja": {
        "label": "Pareja sin hijos",
        "age_range": (26, 45),
        "weight": 0.22,
        "purchase_frequency_multiplier": 1.0,
        "basket_size_range": (3, 6),
        "avg_ticket_range": (25.0, 60.0),
        "category_weights": {
            "lacteos": 0.15,
            "carne_pescado": 0.18,
            "higiene_personal": 0.15,
            "bebidas": 0.12,
            "limpieza_hogar": 0.13,
            "conservas": 0.12,
            "panaderia": 0.10,
            "snacks": 0.05,
            "cosmetica": 0.10,
        },
        "brand_preference": "indiferente",
        "online_tendency": 0.55,
    },
    "familia": {
        "label": "Familia con hijos",
        "age_range": (30, 52),
        "weight": 0.25,
        "purchase_frequency_multiplier": 0.8,
        "basket_size_range": (5, 12),
        "avg_ticket_range": (50.0, 130.0),
        "category_weights": {
            "carne_pescado": 0.20,
            "lacteos": 0.17,
            "limpieza_hogar": 0.15,
            "higiene_personal": 0.12,
            "infantil": 0.12,
            "conservas": 0.10,
            "congelados": 0.08,
            "panaderia": 0.06,
        },
        "brand_preference": "economico",
        "online_tendency": 0.35,
    },
    "mayor": {
        "label": "Persona mayor",
        "age_range": (60, 85),
        "weight": 0.18,
        "purchase_frequency_multiplier": 0.7,
        "basket_size_range": (2, 5),
        "avg_ticket_range": (15.0, 45.0),
        "category_weights": {
            "conservas": 0.22,
            "lacteos": 0.18,
            "carne_pescado": 0.20,
            "panaderia": 0.15,
            "limpieza_hogar": 0.12,
            "higiene_personal": 0.08,
            "bebidas": 0.05,
        },
        "brand_preference": "premium",
        "online_tendency": 0.15,
    },
    "saludable": {
        "label": "Estilo de vida saludable",
        "age_range": (25, 48),
        "weight": 0.08,
        "purchase_frequency_multiplier": 1.2,
        "basket_size_range": (3, 7),
        "avg_ticket_range": (30.0, 80.0),
        "category_weights": {
            "saludable_fitness": 0.30,
            "lacteos": 0.15,
            "carne_pescado": 0.20,
            "bebidas": 0.10,
            "higiene_personal": 0.15,
            "snacks": 0.05,
            "conservas": 0.05,
            "cosmetica": 0.10,
        },
        "brand_preference": "premium",
        "online_tendency": 0.65,
    },
    "joven_profesional": {
        "label": "Joven profesional",
        "age_range": (22, 35),
        "weight": 0.07,
        "purchase_frequency_multiplier": 1.4,
        "basket_size_range": (2, 5),
        "avg_ticket_range": (15.0, 45.0),
        "category_weights": {
            "congelados": 0.25,
            "bebidas": 0.18,
            "snacks": 0.15,
            "higiene_personal": 0.15,
            "lacteos": 0.12,
            "panaderia": 0.10,
            "limpieza_hogar": 0.05,
            "cosmetica": 0.12,
        },
        "brand_preference": "indiferente",
        "online_tendency": 0.75,
    },
}

_PROFILE_IDS: List[str] = list(CUSTOMER_PROFILES.keys())
_PROFILE_WEIGHT_VALUES: List[float] = [
    CUSTOMER_PROFILES[pid]["weight"] for pid in _PROFILE_IDS
]


def get_profile_weights() -> Dict[str, float]:
    """Retorna {profile_id: weight} para amostragem."""
    return {pid: CUSTOMER_PROFILES[pid]["weight"] for pid in _PROFILE_IDS}


def assign_profile(rng: random.Random) -> str:
    """Sorteia um profile_id ponderado por weight."""
    return rng.choices(_PROFILE_IDS, weights=_PROFILE_WEIGHT_VALUES, k=1)[0]


def get_profile(profile_id: str) -> dict:
    """Retorna o dict do perfil."""
    if profile_id not in CUSTOMER_PROFILES:
        raise KeyError(f"Profile '{profile_id}' not found. Available: {_PROFILE_IDS}")
    return CUSTOMER_PROFILES[profile_id]
