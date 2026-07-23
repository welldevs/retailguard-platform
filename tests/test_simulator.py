"""
test_simulator.py
=================
Testa os módulos do simulador de vendas sem depender de conexões externas.
Usa apenas as funções puras de geração de dados.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Testes de build_products (erp/simulator/schema.py)
# ---------------------------------------------------------------------------

class TestBuildProducts:
    """Valida que build_products enriquece corretamente a lista de produtos."""

    def test_build_products_has_required_columns(self, demo_products):
        from erp.simulator.schema import build_products

        result = build_products(demo_products)

        required_columns = {
            "product_id",
            "sku",
            "name",
            "brand",
            "category",
            "sale_price",
            "barcode",
            "cost_price",
            "tax_rate",
            "unit_of_measure",
            "active_since",
        }
        assert len(result) == len(demo_products), "Deve retornar um produto por entrada"
        for col in required_columns:
            assert col in result[0], f"Coluna obrigatória ausente: {col}"

    def test_products_barcode_is_13_digits(self, demo_products):
        from erp.simulator.schema import build_products

        result = build_products(demo_products)

        for prod in result:
            barcode = prod["barcode"]
            assert len(barcode) == 13, f"EAN-13 deve ter 13 dígitos, obtido: {barcode!r}"
            assert barcode.isdigit(), f"EAN-13 deve conter apenas dígitos: {barcode!r}"

    def test_products_cost_price_below_sale_price(self, demo_products):
        from erp.simulator.schema import build_products

        result = build_products(demo_products)

        for prod in result:
            assert prod["cost_price"] < prod["sale_price"], (
                f"cost_price ({prod['cost_price']}) deve ser menor que sale_price ({prod['sale_price']})"
            )

    def test_products_tax_rate_valid(self, demo_products):
        from erp.simulator.schema import build_products

        valid_rates = {0.04, 0.10, 0.21}
        result = build_products(demo_products)

        for prod in result:
            assert prod["tax_rate"] in valid_rates, (
                f"tax_rate inválido: {prod['tax_rate']} (esperado: {valid_rates})"
            )


# ---------------------------------------------------------------------------
# Testes de generate_customers (erp/generators/customers.py)
# ---------------------------------------------------------------------------

class TestGenerateCustomers:
    """Valida que generate_customers gera clientes com dados consistentes."""

    def test_customers_csv_customer_id_unique(self, demo_postal_codes):
        from erp.generators.customers import generate_customers

        customers = generate_customers(50, demo_postal_codes, seed=42)
        ids = [c["customer_id"] for c in customers]
        assert len(ids) == len(set(ids)), "customer_id deve ser único para cada cliente"

    def test_customers_has_required_columns(self, demo_postal_codes):
        from erp.generators.customers import generate_customers

        required = {
            "customer_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "postal_code",
            "municipality",
            "province",
            "ccaa",
            "segment",
            "registration_date",
        }
        customers = generate_customers(10, demo_postal_codes, seed=42)
        assert len(customers) == 10
        for col in required:
            assert col in customers[0], f"Coluna obrigatória ausente: {col}"

    def test_customers_segment_valid(self, demo_postal_codes):
        from erp.generators.customers import generate_customers

        valid_segments = {"Bronze", "Silver", "Gold", "Platinum"}
        customers = generate_customers(30, demo_postal_codes, seed=99)

        for c in customers:
            assert c["segment"] in valid_segments, (
                f"Segmento inválido: {c['segment']!r}"
            )

    def test_customers_email_format(self, demo_postal_codes):
        from erp.generators.customers import generate_customers

        customers = generate_customers(20, demo_postal_codes, seed=7)

        for c in customers:
            assert "@" in c["email"], f"Email inválido: {c['email']!r}"

    def test_customers_reproducible_with_seed(self, demo_postal_codes):
        """
        customer_id usa uuid4() (não determinístico com seed do random),
        mas campos derivados do random.Random seedado devem ser estáveis.
        Valida que segmento, payment_method e avg_ticket são reproduzíveis.
        """
        from erp.generators.customers import generate_customers

        run1 = generate_customers(10, demo_postal_codes, seed=42)
        run2 = generate_customers(10, demo_postal_codes, seed=42)

        # Campos que dependem do random.Random seedado (não do uuid4)
        segments1 = [c["segment"] for c in run1]
        segments2 = [c["segment"] for c in run2]
        assert segments1 == segments2, "Com a mesma seed, segmentos devem ser idênticos"

        tickets1 = [c["avg_ticket"] for c in run1]
        tickets2 = [c["avg_ticket"] for c in run2]
        assert tickets1 == tickets2, "Com a mesma seed, avg_ticket deve ser idêntico"


# ---------------------------------------------------------------------------
# Testes de build_customers (erp/simulator/schema.py)
# ---------------------------------------------------------------------------

class TestBuildCustomers:
    """Valida que build_customers enriquece a lista gerada por generate_customers."""

    def test_build_customers_not_empty(self, demo_postal_codes):
        from erp.generators.customers import generate_customers
        from erp.simulator.schema import build_customers

        raw = generate_customers(5, demo_postal_codes, seed=42)
        result = build_customers(raw)

        assert len(result) == len(raw), "build_customers deve retornar um item por entrada"
        assert len(result) > 0, "Resultado não pode ser vazio"

    def test_build_customers_has_payment_days(self, demo_postal_codes):
        """
        build_customers adiciona payment_days (0, 15 ou 30) conforme segmento.
        Clientes Bronze/Silver: 0 dias; Gold: 15; Platinum: 30.
        """
        from erp.generators.customers import generate_customers
        from erp.simulator.schema import build_customers

        raw = generate_customers(5, demo_postal_codes, seed=42)
        result = build_customers(raw)

        valid_payment_days = {0, 15, 30}
        for cust in result:
            assert "payment_days" in cust, "build_customers deve adicionar payment_days"
            assert cust["payment_days"] in valid_payment_days, (
                f"payment_days inválido: {cust['payment_days']} (esperado: {valid_payment_days})"
            )


# ---------------------------------------------------------------------------
# Testes de DEFAULT_CONFIG (erp/simulator/config.py)
# ---------------------------------------------------------------------------

class TestSimulatorConfig:
    """Valida a integridade da configuração padrão do simulador."""

    def test_default_config_has_required_keys(self):
        from erp.simulator.config import DEFAULT_CONFIG

        required_keys = {
            "start_date",
            "end_date",
            "num_customers",
            "num_suppliers",
            "demand_base_rate",
            "weekend_demand_multiplier",
            "region_to_dc",
        }
        for key in required_keys:
            assert key in DEFAULT_CONFIG, f"Chave obrigatória ausente em DEFAULT_CONFIG: {key}"

    def test_demand_base_rate_range(self):
        from erp.simulator.config import DEFAULT_CONFIG

        rate = DEFAULT_CONFIG["demand_base_rate"]
        assert 0 < rate < 1, f"demand_base_rate deve estar entre 0 e 1, obtido: {rate}"

    def test_region_to_dc_madrid_exists(self):
        from erp.simulator.config import DEFAULT_CONFIG

        region_map = DEFAULT_CONFIG["region_to_dc"]
        assert "Madrid" in region_map, "Madrid deve estar mapeado em region_to_dc"
        assert region_map["Madrid"] == "DC_MAD"
