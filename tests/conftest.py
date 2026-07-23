"""
conftest.py
===========
Fixtures compartilhadas para a suite de testes do retail_analytics.
"""

import csv
import sys
from pathlib import Path

import pytest

# Garante que o diretório raiz do projeto está no sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Caminho absoluto da raiz do projeto."""
    return PROJECT_ROOT


@pytest.fixture
def tmp_duckdb_path(tmp_path) -> str:
    """Caminho para um arquivo DuckDB temporário isolado por teste."""
    return str(tmp_path / "test_retail.duckdb")


@pytest.fixture
def sample_csv_dir(tmp_path) -> Path:
    """
    Cria um diretório temporário com CSVs mínimos de exemplo
    para testar o load_raw_layer.py sem depender de dados reais.
    """
    csv_dir = tmp_path / "source"
    csv_dir.mkdir()

    # sales.csv — campos mínimos obrigatórios
    sales_rows = [
        {
            "sale_id": "SALE_0001",
            "order_date": "2024-01-15",
            "customer_id": "CUST_ABC123",
            "store_id": "STORE_001",
            "dc_id": "DC_MAD",
            "region": "Madrid",
            "payment_method": "tarjeta",
            "payment_status": "paid",
            "payment_days": "0",
            "channel": "tienda",
            "subtotal_net": "45.00",
            "tax_amount": "9.45",
            "total_gross": "54.45",
            "status": "delivered",
            "ticket_trend": "stable",
        },
        {
            "sale_id": "SALE_0002",
            "order_date": "2024-01-16",
            "customer_id": "CUST_DEF456",
            "store_id": "STORE_002",
            "dc_id": "DC_BCN",
            "region": "Cataluña",
            "payment_method": "transferencia",
            "payment_status": "paid",
            "payment_days": "0",
            "channel": "ecommerce",
            "subtotal_net": "28.50",
            "tax_amount": "5.99",
            "total_gross": "34.49",
            "status": "delivered",
            "ticket_trend": "growing",
        },
    ]
    _write_csv(csv_dir / "sales.csv", sales_rows)

    # customers.csv — campos mínimos
    customers_rows = [
        {
            "customer_id": "CUST_ABC123",
            "first_name": "Antonio",
            "last_name": "García López",
            "email": "antonio.garcia@gmail.com",
            "phone": "+34612345678",
            "nif": "12345678Z",
            "postal_code": "28001",
            "municipality": "Madrid",
            "province": "Madrid",
            "ccaa": "Comunidad de Madrid",
            "segment": "Silver",
            "registration_date": "2023-01-01",
        },
        {
            "customer_id": "CUST_DEF456",
            "first_name": "María",
            "last_name": "Martínez Sánchez",
            "email": "maria.martinez@hotmail.com",
            "phone": "+34698765432",
            "nif": "87654321X",
            "postal_code": "08001",
            "municipality": "Barcelona",
            "province": "Barcelona",
            "ccaa": "Cataluña",
            "segment": "Gold",
            "registration_date": "2022-06-15",
        },
    ]
    _write_csv(csv_dir / "customers.csv", customers_rows)

    # products.csv — campos mínimos
    products_rows = [
        {
            "product_id": "PROD_000001",
            "sku": "DEMO_00001",
            "name": "Leche entera 1L",
            "brand": "Hacendado",
            "category": "Lácteos",
            "sale_price": "0.89",
            "unit_of_measure": "L",
            "active": "True",
        },
    ]
    _write_csv(csv_dir / "products.csv", products_rows)

    return csv_dir


def _write_csv(path: Path, rows: list) -> None:
    """Escreve uma lista de dicts como CSV."""
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture(scope="session")
def demo_products() -> list:
    """Retorna 10 produtos demo gerados sem dependências externas."""
    import random
    rng = random.Random(42)
    categories = ["Lácteos", "Bebidas", "Conservas", "Panadería", "Higiene"]
    brands = ["Hacendado", "Deliplus", "Bosque Verde", "Compy"]
    return [
        {
            "product_id": f"PROD_{i:06d}",
            "sku": f"DEMO_{i:05d}",
            "name": f"Producto demo {i}",
            "brand": rng.choice(brands),
            "category": rng.choice(categories),
            "category_path": "",
            "price": round(rng.uniform(0.5, 15.0), 2),
            "unit": "unidad",
            "image_url": "",
            "active": True,
        }
        for i in range(1, 11)
    ]


@pytest.fixture(scope="session")
def demo_postal_codes() -> list:
    """Retorna códigos postais mínimos para testes de geração de clientes."""
    return [
        {
            "postal_code": "28001",
            "municipality": "Madrid",
            "province": "Madrid",
            "ccaa": "Comunidad de Madrid",
            "population_density": 1000.0,
        },
        {
            "postal_code": "08001",
            "municipality": "Barcelona",
            "province": "Barcelona",
            "ccaa": "Cataluña",
            "population_density": 900.0,
        },
        {
            "postal_code": "41001",
            "municipality": "Sevilla",
            "province": "Sevilla",
            "ccaa": "Andalucía",
            "population_density": 600.0,
        },
    ]
