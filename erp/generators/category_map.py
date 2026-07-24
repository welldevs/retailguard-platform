"""
generators/category_map.py
Mapa das categorias reais do Soysuper (campo category_name) para grupos de perfil.

Grupos disponíveis:
    conservas         — Alimentação básica, conservas, legumes secos
    carne_pescado     — Carnes, embutidos, peixes e frutos do mar
    lacteos           — Laticínios, queijos, iogurtes
    snacks            — Snacks, doces, chocolates, aperitivos
    higiene_personal  — Higiene pessoal, cuidado corporal
    limpieza_hogar    — Limpeza doméstica
    congelados        — Produtos congelados
    panaderia         — Pão, bollería, massas
    bebidas           — Bebidas em geral
    infantil          — Produtos para bebé e criança
    saludable_fitness — Produtos saudáveis, orgânicos, fitness
    cosmetica         — Cosmética e beleza
"""

from typing import Dict, List

# ---------------------------------------------------------------------------
# Mapa: category_name (do Soysuper) → group_id
# ---------------------------------------------------------------------------
CATEGORY_TO_GROUP: Dict[str, str] = {
    # ---- conservas ----
    "Accesorios": "conservas",              # acessórios cozinha/genérico → fallback
    "Albóndigas": "carne_pescado",
    "Ali Oli Fresco": "conservas",
    "Almendras": "snacks",
    "Alubias": "conservas",
    "Alubias cocidas": "conservas",
    "Alubias congeladas": "congelados",
    "Anacardos": "snacks",
    "Arroz": "conservas",
    "Asiático": "conservas",
    "Azúcar": "conservas",
    "Banderillas": "conservas",
    "Bases": "conservas",
    "Bicarbonato sódico": "conservas",
    "Bizcocho, Mantecados y Ensaimadas": "panaderia",
    "Bogavante": "carne_pescado",
    "Caballa": "carne_pescado",
    "Cacahuetes": "snacks",
    "Calamares y Chipirones": "carne_pescado",
    "Caldo": "conservas",
    "Canela": "conservas",
    "Caracoles": "carne_pescado",
    "Carne": "carne_pescado",
    "Carne y Pollo": "carne_pescado",
    "Cefalópodos": "carne_pescado",
    "Cerdo": "carne_pescado",
    "Chorizo": "carne_pescado",
    "Chorizo fresco": "carne_pescado",
    "Clásicos": "conservas",
    "Coco Rallado para Repostería": "conservas",
    "Comida Mexicana": "conservas",
    "Comino": "conservas",
    "Confituras y Mermeladas": "conservas",
    "Conservas de Fruta": "conservas",
    "Corazones de Palmito": "conservas",
    "Cortezas y Torreznos": "snacks",
    "Coquitos": "snacks",
    "Crema de Cacao": "conservas",
    "Crema de Queso": "lacteos",
    "Cúrcuma": "conservas",
    "De Manzana": "conservas",
    "De Maíz": "conservas",
    "De Oliva": "conservas",
    "De Trigo": "conservas",
    "Decoración de tartas": "conservas",
    "Especias": "conservas",
    "Especiales": "conservas",
    "Finas Hierbas": "conservas",
    "Frutas Deshidratadas": "conservas",
    "Garbanzos": "conservas",
    "Garbanzos cocidos": "conservas",
    "Guindillas": "conservas",
    "Hinojo": "conservas",
    "Ketchup": "conservas",
    "Legumbres": "conservas",
    "Levadura": "conservas",
    "Limón": "conservas",
    "Macarrones-Plumas": "conservas",
    "Maíz en conserva": "conservas",
    "Mango": "conservas",
    "Manteca": "conservas",
    "Manzana": "conservas",
    "Manzanilla": "bebidas",
    "Mayonesa": "conservas",
    "Mejillones": "carne_pescado",
    "Melocotón": "conservas",
    "Melva": "carne_pescado",
    "Mezcla de Frutas": "conservas",
    "Mezcla de Hierbas": "conservas",
    "Mezcla para sofrito": "conservas",
    "Miel": "conservas",
    "Mojo Canario": "conservas",
    "Mostaza": "conservas",
    "Naranja": "conservas",
    "Negras": "conservas",
    "Normal": "conservas",
    "Nuez Moscada": "conservas",
    "Ñoras": "conservas",
    "Para Carne": "conservas",
    "Para Sopa": "conservas",
    "Pasta": "conservas",
    "Pasta preparada": "conservas",
    "Paté y Foie": "carne_pescado",
    "Pepinillos": "conservas",
    "Pimentón": "conservas",
    "Pimienta": "conservas",
    "Piña": "conservas",
    "Pipas": "snacks",
    "Pistachos": "snacks",
    "Sal": "conservas",
    "Salami": "carne_pescado",
    "Salazón": "carne_pescado",
    "Salsa De Pimienta": "conservas",
    "Salsa de Trufa": "conservas",
    "Salsas Internacionales": "conservas",
    "Salsas Orientales": "conservas",
    "Sazonadores": "conservas",
    "Sin sal": "conservas",
    "Sobrasadas y Cremas": "carne_pescado",
    "Sopa": "conservas",
    "Tomate": "conservas",
    "Tomate Frito": "conservas",
    "Tomillo": "conservas",
    "Varios": "conservas",
    "Verduras Preparadas": "conservas",
    "Verduras y Legumbres": "conservas",
    "Zanahoria": "conservas",

    # ---- carne_pescado ----
    "Atún": "carne_pescado",
    "Bacon y Panceta": "carne_pescado",
    "Bonito del Norte": "carne_pescado",
    "Butifarra": "carne_pescado",
    "Fiambres Varios": "carne_pescado",
    "Fuet - longaniza": "carne_pescado",
    "Gallo": "carne_pescado",
    "Mariscos": "carne_pescado",
    "Marisco Preparado": "carne_pescado",
    "Marrajo": "carne_pescado",
    "Merluza": "carne_pescado",
    "Pavo charcutería": "carne_pescado",
    "Pepito": "carne_pescado",
    "Pescado Azul": "carne_pescado",
    "Pescado Blanco": "carne_pescado",
    "Pescado y Marisco": "carne_pescado",
    "Pota": "carne_pescado",
    "Salchichas Frescas": "carne_pescado",
    "Salchichas envasadas": "carne_pescado",
    "Surimi y Gulas": "carne_pescado",
    "Almejas": "carne_pescado",
    "Zamburiñas": "carne_pescado",

    # ---- lacteos ----
    "Con Bífidus": "lacteos",
    "Con Chocolate": "lacteos",
    "Con Leche": "lacteos",
    "De Cabra y de Oveja": "lacteos",
    "De Mantequilla": "lacteos",
    "Desnatada": "lacteos",
    "Desnatado": "lacteos",
    "Digestive": "lacteos",
    "Edam, Gouda y Maasdam": "lacteos",
    "Emmental y Gruyer": "lacteos",
    "Entera": "lacteos",
    "Familiar": "lacteos",
    "Flan": "lacteos",
    "Fresco y para Ensaladas": "lacteos",
    "Gelatina": "lacteos",
    "L.Casei": "lacteos",
    "Light, Sin Sal y Sin Lactosa": "lacteos",
    "Lonchas, Rallado y en Porciones": "lacteos",
    "Montada": "lacteos",
    "Mousse": "lacteos",
    "Mozzarella, Parmesano y Ricotta": "lacteos",
    "Natillas": "lacteos",
    "Para montar": "lacteos",
    "Postres para Preparar": "lacteos",
    "Pudding": "lacteos",
    "Quesos Nacionales": "lacteos",
    "Refrigerados": "lacteos",
    "Roquefort y Quesos Azules": "lacteos",
    "Semidesnatada": "lacteos",
    "Sin Lactosa": "lacteos",
    "Tarrina": "lacteos",
    "Tierno, Semicurado y Curado": "lacteos",

    # ---- snacks ----
    "Barquillos": "snacks",
    "Barritas": "snacks",
    "Caramelos": "snacks",
    "Chicles": "snacks",
    "Chips": "snacks",
    "Chocolatinas": "snacks",
    "Conos": "snacks",
    "De Patata": "snacks",
    "Edulcorante": "snacks",
    "Frutas Rojas": "snacks",
    "Gominolas": "snacks",
    "Gusanitos": "snacks",
    "Integrales": "snacks",
    "Lisas": "snacks",
    "Onduladas": "snacks",
    "Oriental": "snacks",
    "Palomitas": "snacks",
    "Picos y Crackers": "snacks",
    "Sabores": "snacks",
    "Surtidas": "snacks",
    "Surtido": "snacks",
    "Tabletas": "snacks",
    "Tablas de Queso y Snacks": "snacks",
    "Turrón": "snacks",
    "Verdes": "snacks",

    # ---- higiene_personal ----
    "Acondicionador": "higiene_personal",
    "After Shave": "higiene_personal",
    "Botiquín": "higiene_personal",
    "Cepillo Dental": "higiene_personal",
    "Champú": "higiene_personal",
    "Compresas": "higiene_personal",
    "Desodorantes y Absorbeolores": "higiene_personal",
    "En Aerosol y Spray": "higiene_personal",
    "Enjuague Bucal": "higiene_personal",
    "Exfoliante": "higiene_personal",
    "Fijadores": "higiene_personal",
    "Gel de Baño": "higiene_personal",
    "Gel Íntimo": "higiene_personal",
    "Guantes": "higiene_personal",
    "Incontinencia": "higiene_personal",
    "Laca para Uñas": "higiene_personal",
    "Limpieza Facial": "higiene_personal",
    "Manicura y Pedicura": "higiene_personal",
    "Maquinillas": "higiene_personal",
    "Maquinillas de Afeitar": "higiene_personal",
    "Mascarilla": "higiene_personal",
    "Mascarillas": "higiene_personal",
    "Minispray": "higiene_personal",
    "Para Hombre": "higiene_personal",
    "Para baño": "higiene_personal",
    "Roll On": "higiene_personal",
    "Spray": "higiene_personal",
    "Tampones": "higiene_personal",
    "Tintes para el Cabello": "higiene_personal",
    "Toallitas Íntimas Frescas": "higiene_personal",
    "Tratamientos para el Cabello": "higiene_personal",

    # ---- limpieza_hogar ----
    "Activador del Lavado": "limpieza_hogar",
    "Antical": "limpieza_hogar",
    "Antipolillas y Carcoma": "limpieza_hogar",
    "Cubos de Limpieza": "limpieza_hogar",
    "Desatascador": "limpieza_hogar",
    "Detergente": "limpieza_hogar",
    "Eléctricos": "limpieza_hogar",
    "En Grano": "limpieza_hogar",
    "Estropajos": "limpieza_hogar",
    "Lejía y Líquidos Fuertes": "limpieza_hogar",
    "Limpia Gafas": "limpieza_hogar",
    "Limpiadores Multiusos": "limpieza_hogar",
    "Limpieza de Electrodomésticos": "limpieza_hogar",
    "Limpieza de cristales": "limpieza_hogar",
    "Líquido": "limpieza_hogar",
    "Mopas": "limpieza_hogar",
    "Paja": "limpieza_hogar",
    "Pinzas y Accesorios para Lavado": "limpieza_hogar",
    "Pilas": "limpieza_hogar",
    "Productos para Planchado": "limpieza_hogar",
    "Servilletas de Papel": "limpieza_hogar",
    "Cubiertos, Platos y Vasos": "limpieza_hogar",
    "Cremas, Betunes y Bálsamos": "limpieza_hogar",

    # ---- congelados ----
    "Alistados congelados": "congelados",
    "Brócoli congelado": "congelados",
    "Cangrejos congelados": "congelados",
    "Cardo congelado": "congelados",
    "Cefalópodos congelados": "congelados",
    "Coliflor Congelada": "congelados",
    "Croquetas, Bolas y Empanados": "congelados",
    "Espárragos congelados": "congelados",
    "Frutas Heladas": "congelados",
    "Gambas congeladas": "congelados",
    "Gambón congelado": "congelados",
    "Granizado": "congelados",
    "Habas congeladas": "congelados",
    "Judías verdes congeladas": "congelados",
    "Lenguado congelado": "congelados",
    "Maíz congelado": "congelados",
    "Patatas congeladas": "congelados",
    "Pimiento congelado": "congelados",
    "Pizzas": "congelados",
    "Zamburiñas congeladas": "congelados",
    "Polos": "congelados",
    "Bombón Helado": "congelados",

    # ---- panaderia ----
    "Bollos": "panaderia",
    "Cañas, Palmeras y Napolitanas": "panaderia",
    "Croissant": "panaderia",
    "De Mantequilla": "panaderia",  # duplicado intencional — lacteos prevalece (ver nota)  # noqa: F601
    "Empanadas y Pastel": "panaderia",
    "Empanadillas": "panaderia",
    "Formas": "panaderia",
    "Gofres": "panaderia",
    "Hojaldre": "panaderia",
    "Hojaldres": "panaderia",
    "Magdalenas": "panaderia",
    "Pan Burger y Panecillos": "panaderia",
    "Pan Fresco": "panaderia",
    "Pan Rallado": "panaderia",
    "Pan Tostado": "panaderia",
    "Pan Tostado, Aperitivos": "panaderia",
    "Pan de Molde": "panaderia",
    "Para Rebozar y Freir": "panaderia",
    "Sándwich": "panaderia",
    "Tartas": "panaderia",
    "Tortitas": "panaderia",
    "María": "panaderia",
    "Línea y Semillas": "panaderia",
    "para Rebozar y Freir": "panaderia",

    # ---- bebidas ----
    "Cápsulas": "bebidas",
    "Calientes": "bebidas",
    "Cola": "bebidas",
    "Con Gas": "bebidas",
    "Cóctel": "bebidas",
    "Cócteles": "bebidas",
    "Descafeinado": "bebidas",
    "Listo para Tomar": "bebidas",
    "Molido": "bebidas",
    "Soluble": "bebidas",
    "Té": "bebidas",

    # ---- infantil ----
    "Infantiles": "infantil",
    "Leche infantil": "infantil",
    "Pastel infantil": "infantil",
    "Postres Bebé": "infantil",
    "Tarritos": "infantil",
    "Talla 2": "infantil",
    "Talla 4": "infantil",
    "Talla 5": "infantil",
    "Comida para Perros": "infantil",   # pets → infantil como fallback próximo

    # ---- saludable_fitness ----
    "Frutas Rojas": "saludable_fitness",    # duplicado — snacks prevalece  # noqa: F601
    "Lechugas, Endivias, Col, etc.": "saludable_fitness",
    "Proteína": "saludable_fitness",
    "Sin Azúcares añadidos": "saludable_fitness",
    "Soja, Avena, Arroz,..": "saludable_fitness",
    "Vegetal": "saludable_fitness",
    "Vitaminas": "saludable_fitness",

    # ---- cosmetica ----
    "Crema": "cosmetica",
    "Crema Facial": "cosmetica",
    "Cremas": "cosmetica",
    "Cremas y Lociones": "cosmetica",
    "Maquillaje Facial": "cosmetica",
    "Maquillaje para Labios": "cosmetica",
    "Maquillaje para Ojos": "cosmetica",
    "Mist Facial": "cosmetica",
    "Mousse": "cosmetica",              # duplicado — lacteos prevalece  # noqa: F601
    "Productos Solares": "cosmetica",
    "Protector Solar": "cosmetica",

    # ---- entradas diversas ainda não mapeadas ----
    "Caldo": "conservas",  # noqa: F601
    "Lote": "conservas",
    "Rellena": "conservas",
    "Rellenas": "conservas",
    "Velas": "limpieza_hogar",
    "Velas ambientador": "limpieza_hogar",
}

# ---------------------------------------------------------------------------
# Corrige colisões: a última definição num dict literal Python prevalece.
# Aqui reforçamos explicitamente as intenções para categorias duplicadas.
# ---------------------------------------------------------------------------
_OVERRIDES: Dict[str, str] = {
    "Mousse": "lacteos",          # mousse de chocolate/lacteo > cosmética
    "De Mantequilla": "panaderia", # manteiga para massas > lacteos
    "Frutas Rojas": "saludable_fitness",  # frutas vermelhas > snacks
}
CATEGORY_TO_GROUP.update(_OVERRIDES)

# ---------------------------------------------------------------------------
# Grupos disponíveis
# ---------------------------------------------------------------------------
CATEGORY_GROUPS: List[str] = [
    "conservas",
    "carne_pescado",
    "lacteos",
    "snacks",
    "higiene_personal",
    "limpieza_hogar",
    "congelados",
    "panaderia",
    "bebidas",
    "infantil",
    "saludable_fitness",
    "cosmetica",
]

_DEFAULT_GROUP = "conservas"


# ---------------------------------------------------------------------------
# Taxonomia HIERÁRQUICA (fonte primária de verdade a partir de 2024-07)
# ---------------------------------------------------------------------------
# O `category_name` (leaf do Soysuper) é ambíguo ("Normal", "Varios", "Sabores")
# e cobre mal o catálogo — ~21% dos SKUs caíam no default `conservas`, inflando
# esse grupo e herdando margem/IVA/shelf-life errados. O `category_path` traz o
# DEPARTAMENTO real (só ~18 valores, cobertura ~100%). Mapeamos por
# (departamento, subdepartamento) quando o departamento é misto, senão pelo
# departamento; o leaf legado abaixo fica só como último fallback (produtos sem
# path, ex.: catálogo demo sintético).

# Departamento (1º nível do breadcrumb) → grupo
DEPARTMENT_TO_GROUP: Dict[str, str] = {
    "Perfumería y Parafarmacia":                "higiene_personal",  # refinado por subdept
    "Frescos y Charcutería":                    "carne_pescado",     # refinado por subdept
    "Conservas, Sopas, Aceites y Condimentos":  "conservas",
    "Droguería":                                "limpieza_hogar",
    "Congelados":                               "congelados",
    "Panadería, Pastelería y Repostería":       "panaderia",
    "Lácteos y Huevos":                         "lacteos",
    "Bebidas":                                  "bebidas",
    "Aperitivos":                               "snacks",
    "Chocolates y Dulces":                      "snacks",
    "Cereales y Galletas":                      "snacks",            # refinado por subdept
    "Cafés, Cacaos e Infusiones":               "bebidas",
    "Bebés y Niños":                            "infantil",
    "Pasta, Arroz y Legumbres":                 "conservas",
    "Mascotas":                                 "infantil",          # sem grupo pet → infantil
    "Bazar y Casa":                             "limpieza_hogar",    # menaje/decoração (não-alimentar)
    "Dietéticos":                               "saludable_fitness",
    "Ocio y Cultura":                           _DEFAULT_GROUP,
}

# (departamento, subdepartamento) → grupo — refina os departamentos mistos
SUBDEPARTMENT_TO_GROUP: Dict[tuple, str] = {
    # Perfumería: separa cosmética (maquiagem/rosto/corpo/solar) de higiene
    ("Perfumería y Parafarmacia", "Maquillaje"):            "cosmetica",
    ("Perfumería y Parafarmacia", "Cuidado Facial"):        "cosmetica",
    ("Perfumería y Parafarmacia", "Cuidado Corporal"):      "cosmetica",
    ("Perfumería y Parafarmacia", "Colonia"):               "cosmetica",
    ("Perfumería y Parafarmacia", "Productos Solares"):     "cosmetica",
    ("Perfumería y Parafarmacia", "Cuidado de Pies y Manos"): "cosmetica",
    ("Perfumería y Parafarmacia", "Lotes Regalo"):          "cosmetica",
    # Frescos: queso → lácteos; verduras frescas → saudável; resto → carne_pescado
    ("Frescos y Charcutería", "Queso"):                     "lacteos",
    ("Frescos y Charcutería", "Verduras, Hortalizas y Legumbres"): "saludable_fitness",
    # Cereales y Galletas: cereais de despensa → conservas; bolachas → snacks (default do dept)
    ("Cereales y Galletas", "Cereales"):                    "conservas",
}


def get_group(category_name: str, category_path: str = None) -> str:
    """
    Retorna o group_id canônico de um produto.

    Precedência (mais específico → mais genérico):
        1. (departamento, subdepartamento) do ``category_path``
        2. departamento do ``category_path``
        3. leaf ``category_name`` no mapa legado (fallback p/ produtos sem path)
        4. ``'conservas'`` (default)

    Args:
        category_name: leaf ``category_name`` do Soysuper.
        category_path: breadcrumb completo ("Dept > Sub > Leaf"); quando ausente,
                       cai no mapa de leaf legado.
    """
    if category_path:
        parts = [p.strip() for p in category_path.split(">") if p.strip()]
        if parts:
            dept = parts[0]
            sub = parts[1] if len(parts) > 1 else ""
            if (dept, sub) in SUBDEPARTMENT_TO_GROUP:
                return SUBDEPARTMENT_TO_GROUP[(dept, sub)]
            if dept in DEPARTMENT_TO_GROUP:
                return DEPARTMENT_TO_GROUP[dept]
    return CATEGORY_TO_GROUP.get(category_name, _DEFAULT_GROUP)


def group_products(products: list) -> dict:
    """
    Agrupa os produtos por group_id para lookup rápido em tempo de simulação.

    Args:
        products: Lista de dicts de produto. Cada dict precisa ter
                  ``product_id`` e opcionalmente ``category_name``/``category_path``.

    Returns:
        ``{group_id: [product_id, ...]}`` — todos os 12 grupos presentes,
        mesmo que vazios, para evitar KeyError durante a simulação.
    """
    grouped: Dict[str, List[str]] = {g: [] for g in CATEGORY_GROUPS}

    for product in products:
        prod_id = product.get("product_id") or product.get("id")
        if not prod_id:
            continue
        cat = product.get("category_name") or product.get("category") or ""
        path = product.get("category_path") or ""
        gid = get_group(cat, path)
        if gid not in grouped:
            grouped[gid] = []
        grouped[gid].append(prod_id)

    return grouped
