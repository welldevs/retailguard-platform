import random
from datetime import datetime, timedelta
from typing import List, Dict

from erp.generators.profiles import assign_profile, get_profile


# Segment multiplier applied to the profile's avg_ticket_range base value.
# Calibrado para cestas de supermercado plausíveis: um cliente Platinum faz
# uma "compra do mês" maior, não um ticket de €650. Ex.: familia base €130 →
# Platinum ≈ €338 máx (compra de estocagem), não €650.
_SEGMENT_TICKET_MULT: Dict[str, float] = {
    "Bronze":   1.0,
    "Silver":   1.35,
    "Gold":     1.9,
    "Platinum": 2.6,
}

_TICKET_TREND_WEIGHTS = [
    ("stable",   0.60),
    ("declining", 0.25),
    ("growing",   0.15),
]
_TICKET_TREND_IDS     = [t[0] for t in _TICKET_TREND_WEIGHTS]
_TICKET_TREND_W_VALS  = [t[1] for t in _TICKET_TREND_WEIGHTS]


_FIRST_NAMES: List[str] = [
    "Antonio", "Manuel", "José", "Francisco", "David", "Juan", "Javier",
    "Daniel", "Miguel", "Carlos", "Alejandro", "Pedro", "Sergio", "Rafael",
    "Fernando", "María", "Carmen", "Ana", "Isabel", "Laura", "Marta",
    "Sara", "Paula", "Elena", "Cristina", "Lucía", "Nuria", "Raquel",
    "Silvia", "Patricia",
]

_LAST_NAMES: List[str] = [
    "García", "Martínez", "López", "Sánchez", "González", "Pérez",
    "Rodríguez", "Fernández", "Jiménez", "Ruiz", "Hernández", "Díaz",
    "Torres", "Ramírez", "Flores", "Morales", "Ortega", "Molina",
    "Castro", "Suárez", "Blanco", "Romero", "Gil", "Serrano",
    "Vázquez", "Navarro", "Medina", "Reyes", "Delgado", "Moreno",
]

_SEGMENTS: List[str] = ["Bronze", "Silver", "Gold", "Platinum"]
_SEGMENT_WEIGHTS: List[float] = [0.50, 0.30, 0.15, 0.05]

_STREET_TYPES: List[str] = [
    "Calle", "Avenida", "Plaza", "Paseo", "Ronda", "Travesía", "Callejón",
]
_STREET_NAMES: List[str] = [
    "Mayor", "Real", "del Sol", "de la Paz", "Nueva", "del Carmen",
    "de la Cruz", "del Prado", "de Alcalá", "de Colón", "de Goya",
    "de Velázquez", "de Cervantes", "de Lope de Vega", "de los Reyes",
    "de la Constitución", "de España", "de la Libertad", "de Castilla",
    "de Aragón", "de Andalucía", "del Mediterráneo", "de Valencia",
]
_FLOORS: List[str] = ["1°A", "1°B", "2°A", "2°B", "3°A", "3°B", "4°A", "4°B", "Bajo", "Entlo."]

_PAYMENT_METHODS: List[str] = ["tarjeta", "transferencia", "contrareembolso"]
_PAYMENT_WEIGHTS: List[float] = [0.60, 0.25, 0.15]

NIF_LETTERS: str = "TRWAGMYFPDXBNJZSQVHLCKE"


def _generate_nif(rng: random.Random) -> str:
    n = rng.randint(10_000_000, 99_999_999)
    letter = NIF_LETTERS[n % 23]
    return f"{n:08d}{letter}"


def _generate_address_street(rng: random.Random) -> str:
    street_type = rng.choice(_STREET_TYPES)
    street_name = rng.choice(_STREET_NAMES)
    number = rng.randint(1, 150)
    floor = rng.choice(_FLOORS)
    return f"{street_type} {street_name} {number}, {floor}"


def _weighted_sample_postal_codes(
    postal_codes: List[Dict], num_customers: int, rng: random.Random
) -> List[Dict]:
    total_density = sum(pc["population_density"] for pc in postal_codes)
    weights = [pc["population_density"] / total_density for pc in postal_codes]
    return rng.choices(postal_codes, weights=weights, k=num_customers)


def _generate_spanish_phone(rng: random.Random) -> str:
    mobile_prefixes = ["6", "7"]
    landline_prefix = "9"
    if rng.random() < 0.70:
        prefix = rng.choice(mobile_prefixes)
        rest = f"{rng.randint(10000000, 99999999)}"
        number = prefix + rest
    else:
        rest = f"{rng.randint(10000000, 99999999)}"
        number = landline_prefix + rest
    return f"+34{number}"


def _generate_email(
    first_name: str, last_name: str, customer_index: int, rng: random.Random
) -> str:
    domains = [
        "gmail.com", "hotmail.com", "outlook.es", "yahoo.es",
        "telefonica.net", "orange.es", "movistar.es",
    ]
    slug_first = (
        first_name.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    slug_last = (
        last_name.lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ñ", "n")
    )
    separator = rng.choice([".", "_", ""])
    suffix = str(customer_index) if rng.random() < 0.50 else ""
    domain = rng.choice(domains)
    return f"{slug_first}{separator}{slug_last}{suffix}@{domain}"


# Tier ladders for segment drift. Promotion moves up one tier (Platinum is
# the ceiling); demotion moves down one tier (Bronze is the floor).
_SEGMENT_ORDER: List[str] = ["Bronze", "Silver", "Gold", "Platinum"]
_PROMOTE_NEXT: Dict[str, str] = {
    "Bronze": "Silver",
    "Silver": "Gold",
    "Gold":   "Platinum",
    # Platinum has no higher tier — stays put.
}
_DEMOTE_NEXT: Dict[str, str] = {
    "Platinum": "Gold",
    "Gold":     "Silver",
    "Silver":   "Bronze",
    # Bronze has no lower tier — stays put.
}


def apply_segment_drift(customers, seed, fraction=0.03):
    """Deterministically drift a fraction of customers between segments.

    Single source of truth for the segment-drift (SCD2) demo: among customers
    whose ``ticket_trend == 'growing'`` a fraction are promoted one tier
    (Bronze→Silver→Gold→Platinum, Platinum stays); among those whose
    ``ticket_trend == 'declining'`` a fraction are demoted one tier
    (Platinum→Gold→Silver→Bronze, Bronze stays). When a customer moves, their
    ``avg_ticket`` is rescaled by the ratio of the new/old segment multipliers
    (``_SEGMENT_TICKET_MULT``). All other fields are preserved verbatim.

    The function is pure and deterministic given ``(customers, seed)``:
        - it does NOT mutate the input list or its dicts (returns new dicts);
        - selection uses a local ``random.Random(seed)`` so repeated calls with
          the same seed yield byte-identical output.

    Args:
        customers: list of customer dicts (must contain ``segment``,
            ``ticket_trend`` and ``avg_ticket``).
        seed: int seed driving the deterministic selection.
        fraction: target share of the *total* customer base to move
            (default 0.03 → ≈600 for 20k). The count is capped by the number of
            eligible customers, and movers are drawn only from the eligible set.
            "Eligible" = customers who can actually change tier in their trend
            direction (growing & not Platinum, or declining & not Bronze).

    Returns:
        (drifted_list, num_moved): a new list of customer dicts (new objects)
        and the integer count of customers whose segment changed.
    """
    rng = random.Random(seed)

    # Eligible = trend points in a direction AND there is a tier to move to.
    eligible_idx: List[int] = []
    for i, c in enumerate(customers):
        trend = c.get("ticket_trend")
        segment = c.get("segment")
        if trend == "growing" and segment in _PROMOTE_NEXT:
            eligible_idx.append(i)
        elif trend == "declining" and segment in _DEMOTE_NEXT:
            eligible_idx.append(i)

    # Target ≈ fraction of the FULL customer base (≈600 for 20k at 0.03),
    # capped by how many customers can actually move. Movers are then sampled
    # deterministically from the eligible set via the local rng.
    n_move = round(len(customers) * fraction)
    n_move = max(0, min(n_move, len(eligible_idx)))
    moved_set = set(rng.sample(eligible_idx, n_move)) if n_move else set()

    drifted: List[Dict] = []
    num_moved = 0
    for i, c in enumerate(customers):
        new_c = dict(c)  # shallow copy → never mutate the input dict
        if i in moved_set:
            segment = c["segment"]
            trend = c["ticket_trend"]
            new_segment = (
                _PROMOTE_NEXT[segment]
                if trend == "growing"
                else _DEMOTE_NEXT[segment]
            )
            old_mult = _SEGMENT_TICKET_MULT.get(segment, 1.0)
            new_mult = _SEGMENT_TICKET_MULT.get(new_segment, 1.0)
            try:
                old_ticket = float(c.get("avg_ticket", 0.0) or 0.0)
            except (TypeError, ValueError):
                old_ticket = 0.0
            new_c["segment"] = new_segment
            new_c["avg_ticket"] = round(old_ticket * (new_mult / old_mult), 2)
            num_moved += 1
        drifted.append(new_c)

    return drifted, num_moved


def generate_customers(
    num_customers: int,
    postal_codes: List[Dict],
    seed: int = None,
    stores: List[Dict] = None,
) -> List[Dict]:
    if not postal_codes:
        raise ValueError("postal_codes list must not be empty")

    rng = random.Random(seed)
    sampled_locations = _weighted_sample_postal_codes(postal_codes, num_customers, rng)
    # Data de referência ÚNICA para idade e tenure (antes idade usava 2024 e o
    # registro usava 2026 — inconsistente). birth_year = reference_year - age.
    reference_date = datetime(2026, 5, 28)
    reference_year = reference_date.year
    seen_ids: set = set()  # garante customer_id único e determinístico

    # Índices de lookup para atribuir nearest_store_id por CEP → província → CCAA.
    # A escolha dentro do grupo é PONDERADA por sqm: lojas maiores têm catchment
    # maior (mais clientes atribuídos) — dá sentido real ao volume por loja no
    # mart_store_day. A capacidade de estoque já escala com sqm (inventory.py),
    # então loja grande = mais clientes E mais estoque (consistente, sem só gerar
    # mais ruptura).
    stores_by_postal: Dict[str, List[str]] = {}
    stores_by_province: Dict[str, List[str]] = {}
    stores_by_ccaa: Dict[str, List[str]] = {}
    store_sqm: Dict[str, float] = {}
    if stores:
        for s in stores:
            stores_by_postal.setdefault(s["postal_code"], []).append(s["store_id"])
            stores_by_province.setdefault(s["province"], []).append(s["store_id"])
            stores_by_ccaa.setdefault(s["ccaa"], []).append(s["store_id"])
            store_sqm[s["store_id"]] = float(s.get("sqm") or 1000)

    def _pick_store(store_ids: List[str]) -> str:
        """Escolhe uma loja do grupo, ponderando por sqm (catchment ∝ tamanho)."""
        if len(store_ids) == 1:
            return store_ids[0]
        weights = [store_sqm.get(sid, 1000.0) for sid in store_ids]
        return rng.choices(store_ids, weights=weights, k=1)[0]

    customers: List[Dict] = []
    for i, location in enumerate(sampled_locations, start=1):
        # customer_id determinístico (seedado) e único — reprodutível byte-a-byte
        # com a mesma seed (antes: uuid4(), não reprodutível).
        while True:
            customer_id = f"CUST_{rng.getrandbits(48):012X}"
            if customer_id not in seen_ids:
                seen_ids.add(customer_id)
                break
        first_name = rng.choice(_FIRST_NAMES)
        last_name_1 = rng.choice(_LAST_NAMES)
        last_name_2 = rng.choice(_LAST_NAMES)
        full_last_name = f"{last_name_1} {last_name_2}"

        segment = rng.choices(_SEGMENTS, weights=_SEGMENT_WEIGHTS, k=1)[0]
        # Tenure até ~8 anos (antes 3) → base de clientes com antiguidade madura.
        registration_date = reference_date - timedelta(days=rng.randint(30, 2920))

        profile_id = assign_profile(rng)
        profile = get_profile(profile_id)
        age_min, age_max = profile["age_range"]
        age = rng.randint(age_min, age_max)
        birth_year = reference_year - age

        payment_method = rng.choices(
            _PAYMENT_METHODS, weights=_PAYMENT_WEIGHTS, k=1
        )[0]

        # Individual purchase behavior — drives engine basket building
        ticket_min, ticket_max = profile["avg_ticket_range"]
        seg_mult = _SEGMENT_TICKET_MULT.get(segment, 1.0)
        base_ticket = rng.uniform(ticket_min, ticket_max)
        avg_ticket = round(base_ticket * seg_mult, 2)

        ticket_trend = rng.choices(
            _TICKET_TREND_IDS, weights=_TICKET_TREND_W_VALS, k=1
        )[0]
        behavior_variance = round(rng.uniform(0.10, 0.35), 2)

        # Channel preference derived from profile tendency + individual noise
        online_pref = profile.get("online_tendency", 0.5)
        # Add ±15 % personal variation
        channel_probability = max(0.05, min(0.95, online_pref + rng.uniform(-0.15, 0.15)))

        # Atribuir loja mais próxima: fallback CEP → província → CCAA → None
        nearest_store_id = None
        if stores:
            pc_code = location["postal_code"]
            prov = location["province"]
            ccaa = location["ccaa"]
            if pc_code in stores_by_postal:
                nearest_store_id = _pick_store(stores_by_postal[pc_code])
            elif prov in stores_by_province:
                nearest_store_id = _pick_store(stores_by_province[prov])
            elif ccaa in stores_by_ccaa:
                nearest_store_id = _pick_store(stores_by_ccaa[ccaa])

        customers.append({
            "customer_id": customer_id,
            "first_name": first_name,
            "last_name": full_last_name,
            "email": _generate_email(first_name, last_name_1, i, rng),
            "phone": _generate_spanish_phone(rng),
            "nif": _generate_nif(rng),
            "address_street": _generate_address_street(rng),
            "postal_code": location["postal_code"],
            "municipality": location["municipality"],
            "province": location["province"],
            "ccaa": location["ccaa"],
            "registration_date": registration_date.strftime("%Y-%m-%d"),
            "segment": segment,
            "profile": profile_id,
            "birth_year": birth_year,
            "age": age,
            "payment_method": payment_method,
            # Individual behavior fields
            "avg_ticket": avg_ticket,
            "ticket_trend": ticket_trend,
            "behavior_variance": behavior_variance,
            "channel_probability": round(channel_probability, 2),
            # Loja física mais próxima (opcional — None se stores não informado)
            "nearest_store_id": nearest_store_id,
        })

    return customers
