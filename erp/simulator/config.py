"""
simulator/config.py
Parâmetros de configuração do Simulador de Vendas (mercado espanhol).
"""

from typing import Dict, Any

# ---------------------------------------------------------------------------
# Configuração padrão
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    # --- Janela temporal ---
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",

    # --- Dimensões ---
    "num_customers": 1000,
    "num_suppliers": 20,

    # --- Estoque ---
    # Multiplicador sobre reorder_point para calcular quantidade de reposição
    "stockout_reorder_multiplier": 1.5,

    # --- Demanda ---
    # Probabilidade base de um cliente realizar uma compra em qualquer dia
    "demand_base_rate": 0.05,

    # ── Sazonalidade dia-da-semana (substitui o binário weekend_multiplier) ──
    # Fonte: INE/CDMGE + estudos de footfall supermercados espanhóis
    "day_of_week_multipliers": {
        0: 0.75,   # Segunda — menor tráfego da semana
        1: 0.88,   # Terça
        2: 1.00,   # Quarta — base
        3: 1.08,   # Quinta — início do ciclo fim de semana
        4: 1.25,   # Sexta — pico entre semana
        5: 1.45,   # Sábado — pico absoluto
        6: 0.35,   # Domingo — restrições legais (média nacional, mix CCAA)
    },

    # ── Sazonalidade mensal (índice vs. média anual) ──
    # Jan baixo pós-Natal; Nov/Dez pico Black Friday + Natal
    "monthly_seasonal_index": {
        1: 0.90,  2: 0.92,  3: 1.00,  4: 1.02,  5: 0.98,  6: 1.02,
        7: 1.05,  8: 1.02,  9: 1.01, 10: 1.00, 11: 1.09, 12: 1.28,
    },

    # ── Efeito nómina — dentro do mês ──
    "month_start_demand_multiplier": 1.14,   # dias 1–5   (nóminas recebidas)
    "month_end_demand_multiplier":   1.10,   # dias 25–31 (antecipação de nómina)
    "mid_month_boost":               1.06,   # dias 15–16 (quinzena funcionários públicos)

    # ── Eventos pontuais — MM-DD: multiplicador sobre o dia normal ──
    # Nochebuena/Nochevieja são os maiores dias do ano em alimentação
    "special_events": {
        "12-24": 1.95,   # Nochebuena
        "12-23": 1.45,   # Véspera de Nochebuena (cesta de Natal)
        "12-31": 1.75,   # Nochevieja
        "12-30": 1.35,   # Véspera de Nochevieja
        "01-05": 1.50,   # Víspera de Reyes Magos
        "01-06": 0.25,   # Reyes (lojas fechadas em muitas CCAAas)
        "01-07": 1.30,   # Rebajas começam (liquidação pós-Reyes)
        # Black Friday e Semana Santa são datas MÓVEIS — calculadas por ano no
        # engine (_seasonal_event_multiplier), não fixadas aqui.
    },

    # ── Inchaço da CESTA em datas de estocagem (MM-DD) ──
    # Nestes dias o cliente não só compra mais vezes (special_events acima),
    # ele também enche mais a cesta (compra de Natal / fim de ano).
    "basket_size_events": {
        "12-23": 1.25,   # cesta de Natal
        "12-24": 1.35,   # Nochebuena
        "12-30": 1.20,   # véspera de fim de ano
        "12-31": 1.30,   # Nochevieja
        "01-05": 1.20,   # véspera de Reyes
    },

    # ── Semana Santa — janela relativa (dias antes de Domingo de Ramos) ──
    # A Semana Santa é móvel; aplicada via lógica no engine
    "semana_santa_boost": 1.20,      # +20% na semana prévia
    "semana_santa_closure": 0.30,    # Sexta-feira Santa (cierre parcial)

    # ── Ruído diário log-normal ──
    # Após aplicar todos os multiplicadores, aplica fator de ruído orgânico
    # sigma=0.055 → 68% dos dias variam ±5.5%; 95% variam ±11%
    "daily_noise_sigma": 0.055,

    # Mantido por compatibilidade (engine.py ainda pode referenciá-lo como fallback)
    "weekend_demand_multiplier": 1.20,

    # --- Entrega ---
    # Prazo de entrega (dias) por região de destino
    "delivery_days_by_region": {
        "Madrid":                  1,
        "Cataluña":                2,
        "Comunitat Valenciana":    2,
        "Andalucía":               3,
        "Aragón":                  2,
        "País Vasco":              3,
        "Castilla y León":         3,
        "Galicia":                 4,
        "Castilla-La Mancha":      3,
        "Canarias":                5,
        "Baleares":                4,
        "Murcia":                  3,
        "Extremadura":             4,
        "Asturias":                3,
        "Navarra":                 2,
        "Cantabria":               3,
        "La Rioja":                2,
        "default":                 3,
    },

    # --- Regiones de clientes con pesos de densidad poblacional ---
    # Usado para muestrear la región de origen de cada pedido
    "customer_regions": {
        "Madrid":                  0.165,
        "Cataluña":                0.161,
        "Andalucía":               0.178,
        "Comunitat Valenciana":    0.108,
        "País Vasco":              0.046,
        "Castilla y León":         0.050,
        "Galicia":                 0.057,
        "Castilla-La Mancha":      0.043,
        "Canarias":                0.046,
        "Murcia":                  0.031,
        "Aragón":                  0.028,
        "Extremadura":             0.022,
        "Baleares":                0.025,
        "Asturias":                0.021,
        "Navarra":                 0.014,
        "Cantabria":               0.012,
        "La Rioja":                0.007,
        "Ceuta":                   0.004,
        "Melilla":                 0.003,
    },

    # --- Centro de Distribuição de atendimento padrão por região ---
    # Mapeia região do cliente (ccaa) → dc_id mais próximo
    "region_to_dc": {
        "Madrid":                        "DC_MAD",
        "Comunidad de Madrid":           "DC_MAD",
        "Castilla y León":               "DC_MAD",
        "Castilla-La Mancha":            "DC_MAD",
        "Extremadura":                   "DC_MAD",
        "Cataluña":                      "DC_BCN",
        "Aragón":                        "DC_ZGZ",
        "Navarra":                       "DC_ZGZ",
        "Comunidad Foral de Navarra":    "DC_ZGZ",
        "La Rioja":                      "DC_ZGZ",
        "País Vasco":                    "DC_ZGZ",
        "Cantabria":                     "DC_ZGZ",
        "Asturias":                      "DC_ZGZ",
        "Principado de Asturias":        "DC_ZGZ",
        "Galicia":                       "DC_ZGZ",
        "Comunitat Valenciana":          "DC_VLC",
        "Comunidad Valenciana":          "DC_VLC",
        "Murcia":                        "DC_VLC",
        "Región de Murcia":              "DC_VLC",
        "Illes Balears":                 "DC_VLC",
        "Islas Baleares":                "DC_VLC",
        "Baleares":                      "DC_VLC",
        "Andalucía":                     "DC_SEV",
        "Canarias":                      "DC_SEV",
        "Ceuta":                         "DC_SEV",
        "Ciudad Autónoma de Ceuta":      "DC_SEV",
        "Melilla":                       "DC_SEV",
        "Ciudad Autónoma de Melilla":    "DC_SEV",
        "default":                       "DC_MAD",
    },

    # Alias legado para retrocompatibilidade (aponta para region_to_dc em runtime)
    # Não usar em código novo — preferir region_to_dc
    "region_to_warehouse": None,  # populado em runtime pelo engine se necessário

    # --- Itens por pedido (basket_size_range do perfil tem precedência no engine) ---
    "order_items_min": 1,
    "order_items_max": 20,

    # ── Construção orgânica da cesta ──────────────────────────────────────
    # Comportamento de supermercado real: MUITOS itens distintos, POUCAS
    # unidades por item. A cesta cresce em VARIEDADE até atingir o ticket
    # alvo — nunca empilhando 30 unidades de um único SKU.
    #
    # Distribuição de unidades por linha (qty: peso). Média ≈ 1,8 un/linha.
    "basket_qty_weights": {1: 0.55, 2: 0.25, 3: 0.12, 4: 0.05, 5: 0.02, 6: 0.01},
    # Categorias de "compra a granel" (bebidas, leite, limpeza) — somam um
    # bônus de unidades, simulando packs/garrafões. Média ≈ +0,9 un.
    # (Chaves devem ser GRUPOS reais de category_map; "agua" não é um grupo.)
    "bulk_categories": ["bebidas", "lacteos", "limpieza_hogar"],
    "bulk_qty_bonus_weights": {0: 0.45, 1: 0.25, 2: 0.15, 3: 0.10, 4: 0.05},
    # Teto de itens distintos por pedido (evita loop patológico em cestas
    # grandes de clientes Platinum; cestas reais de "compra do mês" chegam a ~40).
    "basket_max_distinct_items": 45,

    # ── Quantidade máxima por item (rede de segurança) ────────────────────
    # A cesta orgânica gera 1-9 un/linha; este teto só evita outliers.
    "order_qty_max": 12,

    # ── Hora do dia (curva diurna de afluência de supermercado) ───────────
    # Peso relativo de cada hora de abertura (09h–21h). Dois picos: meio da
    # manhã (11–13h) e fim de tarde (18–20h), como o tráfego real de loja.
    # Usado para carimbar `order_ts` em cada pedido → análise de hora-punta.
    "diurnal_hour_weights": {
        9: 0.045, 10: 0.075, 11: 0.110, 12: 0.120, 13: 0.105,
        14: 0.060, 15: 0.045, 16: 0.060, 17: 0.085,
        18: 0.110, 19: 0.105, 20: 0.080,
    },

    # ── Perecedero: vida útil (dias) por grupo de categoria ───────────────
    # Frescos têm shelf life curta → geram caducidad/merma. Categorias não
    # listadas são tratadas como não-perecíveis (sem merma por validade).
    "shelf_life_days_by_category": {
        "panaderia":     2,
        "pan":           2,
        "carne_pescado": 4,
        "lacteos":       12,
        "congelados":    180,
        "infantil":      120,
    },

    # ── Merma / caducidad (waste) ─────────────────────────────────────────
    # Modelo enxuto e conservador de estoque: ao vender uma linha de produto
    # perecível, há `waste_line_probability` de também descartar algumas
    # unidades por validade (caducidad), gerando um evento product_waste + um
    # movimento OUT de estoque (reason='waste') — mantém a integridade do
    # inventário (a merma é uma saída real, não um vazamento).
    "waste_line_probability": 0.015,
    "waste_qty_weights": {1: 0.60, 2: 0.28, 3: 0.12},

    # ── Transportadoras — perfil de fiabilidade ──────────────────────────────
    # share: quota de mercado (proporcional, não precisa somar 1.0 exactamente)
    # on_time: probabilidade de entrega no prazo prometido
    # max_delay_days: máximo de dias extra quando há atraso
    "carrier_profiles": {
        "MRW":             {"share": 0.38, "on_time": 0.96, "max_delay_days": 2},
        "SEUR":            {"share": 0.30, "on_time": 0.94, "max_delay_days": 3},
        "GLS":             {"share": 0.22, "on_time": 0.92, "max_delay_days": 3},
        "Correos Express": {"share": 0.10, "on_time": 0.89, "max_delay_days": 4},
    },

    # ── Margens brutas por categoria de produto ───────────────────────────────
    # cost_ratio = cost_price / sale_price; margem = 1 - cost_ratio
    # Gera distribuições diferenciadas no mart_margem_por_categoria
    "category_margin_rules": {
        "bebidas":          {"cost_ratio_min": 0.88, "cost_ratio_max": 0.92},  # 8-12% margem
        "carne_pescado":    {"cost_ratio_min": 0.74, "cost_ratio_max": 0.83},  # 17-26%
        "lacteos":          {"cost_ratio_min": 0.72, "cost_ratio_max": 0.80},  # 20-28%
        "frutas_verduras":  {"cost_ratio_min": 0.70, "cost_ratio_max": 0.78},  # 22-30%
        "panaderia":        {"cost_ratio_min": 0.76, "cost_ratio_max": 0.83},  # 17-24%
        "congelados":       {"cost_ratio_min": 0.68, "cost_ratio_max": 0.76},  # 24-32%
        "conservas":        {"cost_ratio_min": 0.62, "cost_ratio_max": 0.72},  # 28-38%
        "limpieza_hogar":   {"cost_ratio_min": 0.58, "cost_ratio_max": 0.68},  # 32-42%
        "higiene_personal": {"cost_ratio_min": 0.55, "cost_ratio_max": 0.62},  # 38-45%
        "default":          {"cost_ratio_min": 0.64, "cost_ratio_max": 0.76},  # 24-36%
    },

    # ── Pressão sazonal sobre o abastecimento ─────────────────────────────────
    # Multiplicador sobre lead_time de fornecedores em picos de demanda.
    # Valor > 1.0 = reposições demoram mais (supply squeeze) → mais rupturas.
    "seasonal_supply_pressure": {
        "black_friday": 1.35,  # semana do Black Friday (novembro)
        "navidad":      1.40,  # última semana de dezembro
        "semana_santa": 1.25,  # semana de Páscoa
    },

    # ── Eventos de mercado (choques) ─────────────────────────────────────────
    # Cada evento afeta subconjuntos de clientes com intensidades diferentes.
    # segments: lista de segmentos afetados (None = todos).
    # profiles: lista de perfis afetados (None = todos).
    # demand_mult: multiplicador sobre a taxa de compra durante o período.
    # ticket_mult: multiplicador sobre o ticket médio (cesta menor/maior).
    # Impacto assimétrico por design — um aumento de preços afeta Bronze mais
    # que Platinum; uma promoção de produto saudável afeta perfil saludable mais.
    "market_shocks": [
        # Aumento de preços no verão 2024 — impacta mais os segmentos baixos
        {
            "name":        "inflacion_verano_2024",
            "start":       "2024-07-01",
            "end":         "2024-08-31",
            "segments":    ["Bronze", "Silver"],
            "profiles":    None,
            "demand_mult": 0.88,
            "ticket_mult": 0.93,
        },
        # Campanha fidelidade outubro 2024 — reward para Gold/Platinum
        {
            "name":        "campanha_fidelidad_oct24",
            "start":       "2024-10-01",
            "end":         "2024-10-31",
            "segments":    ["Gold", "Platinum"],
            "profiles":    None,
            "demand_mult": 1.12,
            "ticket_mult": 1.08,
        },
        # Greve logística parcial fev 2025 — afeta e-commerce (profiles jovens)
        {
            "name":        "greve_logistica_feb25",
            "start":       "2025-02-10",
            "end":         "2025-02-24",
            "segments":    None,
            "profiles":    ["soltero", "joven_profesional"],
            "demand_mult": 0.75,
            "ticket_mult": 1.15,  # quem compra, estoca mais em loja
        },
        # Lançamento de marca própria premium abr 2025 — atrai Silver→Gold
        {
            "name":        "marca_propia_premium_abr25",
            "start":       "2025-04-01",
            "end":         "2025-05-15",
            "segments":    ["Silver", "Gold"],
            "profiles":    None,
            "demand_mult": 1.07,
            "ticket_mult": 1.10,
        },
        # Calor extremo verão 2025 — boost bebidas/higiene, retração carne/frescos
        {
            "name":        "calor_extremo_jul25",
            "start":       "2025-07-15",
            "end":         "2025-08-20",
            "segments":    None,
            "profiles":    None,
            "demand_mult": 1.05,
            "ticket_mult": 0.97,  # cestas menores mas mais frequentes
        },
        # Abertura de concorrente em Madrid/Barcelona set 2025 — churn Bronze
        {
            "name":        "concorrente_set25",
            "start":       "2025-09-01",
            "end":         "2025-11-30",
            "segments":    ["Bronze"],
            "profiles":    None,
            "demand_mult": 0.82,
            "ticket_mult": 0.95,
        },
        # Black Week estendida 2025 — antecipa compras de Natal
        {
            "name":        "black_week_extendida_25",
            "start":       "2025-11-17",
            "end":         "2025-11-30",
            "segments":    None,
            "profiles":    None,
            "demand_mult": 1.18,
            "ticket_mult": 1.12,
        },
    ],

    # ── Regime switching de comportamento ────────────────────────────────────
    # A cada N dias, um cliente tem probabilidade de mudar de regime
    # (growing → stable → declining ou vice-versa), simulando eventos de vida:
    # mudança de emprego, nascimento de filho, reforma, mudança de cidade, etc.
    # check_interval: a cada quantos dias avaliar a mudança (por cliente)
    # switch_prob_by_trend: probabilidade de SAIR do regime atual ao ser avaliado
    # (declining tem maior prob de recuperar parcialmente, growing de estabilizar)
    "behavior_switch_check_days": 90,   # avalia trimestralmente
    "behavior_switch_prob": {
        "growing":   0.18,   # 18% de chance de estabilizar ou começar a declinar
        "stable":    0.10,   # 10% de chance de começar a crescer ou declinar
        "declining": 0.22,   # 22% de chance de estabilizar (recuperação parcial)
    },
    # Transições possíveis: growing→stable, growing→declining (raro),
    # stable→growing, stable→declining, declining→stable, declining→growing (raro)
    "behavior_switch_transitions": {
        "growing":   [("stable", 0.75), ("declining", 0.25)],
        "stable":    [("growing", 0.50), ("declining", 0.50)],
        "declining": [("stable", 0.80), ("growing", 0.20)],
    },

    # ── Memória de experiência do cliente ────────────────────────────────────
    # Rupturas e atrasos acumulados degradam a relação do cliente com a loja.
    # stockout_memory_decay: a cada dia, o "crédito de ruptura" decai (esquece)
    # stockout_penalty_per_event: quanto cada ruptura penaliza a freq. de compra
    # max_stockout_penalty: teto da penalidade cumulativa (nunca zera a demanda)
    "stockout_memory_decay":    0.985,   # 1.5% de "esquecimento" por dia
    "stockout_penalty_per_hit": 0.025,   # cada ruptura reduz freq em 2.5%
    "max_stockout_penalty":     0.35,    # máximo de 35% de redução por rupturas

    # --- Seed para reprodutibilidade (None = aleatório) ---
    "random_seed": None,

    # --- Modo realtime: segundos de espera entre cada dia simulado ---
    "realtime_sleep_seconds": 1,
}
