"""
test_load_raw.py
================
Testa scripts/load_raw_layer.py usando DuckDB temporário e CSV fixtures mínimas.
Não requer Snowflake nem dados reais.
"""

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False

pytestmark = pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="duckdb not installed")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_load_module():
    """Importa o módulo load_raw_layer sem executar main()."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "load_raw_layer",
        PROJECT_ROOT / "scripts" / "load_raw_layer.py",
    )
    mod = importlib.util.load_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Testes da função load()
# ---------------------------------------------------------------------------

class TestLoadRawLayer:
    """Testa a função load() do script load_raw_layer.py."""

    def test_load_creates_sales_table(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que a tabela sales é criada a partir do CSV fixture."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        # Overrides de ambiente antes de exec_module
        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        count = mod.load(con, "sales")
        con.close()

        assert count == 2, f"Esperado 2 linhas na tabela sales, obtido: {count}"

    def test_load_creates_customers_table(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que a tabela customers é criada com os dados do fixture."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        count = mod.load(con, "customers")
        con.close()

        assert count == 2, f"Esperado 2 clientes, obtido: {count}"

    def test_load_skips_missing_csv(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que load() retorna 0 e não levanta exceção para CSV ausente."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        # "stockouts" não existe no fixture — deve retornar 0 sem erro
        count = mod.load(con, "stockouts")
        con.close()

        assert count == 0, f"Esperado 0 para CSV ausente, obtido: {count}"

    def test_sales_table_has_customer_id_column(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que a tabela sales tem a coluna customer_id."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        mod.load(con, "sales")

        # Verifica que a coluna customer_id existe
        result = con.execute('SELECT customer_id FROM main."sales"').fetchall()
        con.close()

        assert len(result) == 2
        customer_ids = [row[0] for row in result]
        assert "CUST_ABC123" in customer_ids

    def test_customers_ids_are_unique_in_duckdb(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que customer_id é único na tabela carregada."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        mod.load(con, "customers")

        total = con.execute('SELECT count(*) FROM main."customers"').fetchone()[0]
        distinct = con.execute('SELECT count(DISTINCT customer_id) FROM main."customers"').fetchone()[0]
        con.close()

        assert total == distinct, "customer_id deve ser único na tabela customers"

    def test_products_not_empty(self, tmp_duckdb_path, sample_csv_dir):
        """Verifica que a tabela products tem pelo menos um registro."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)

        os.environ["DUCKDB_PATH"] = tmp_duckdb_path
        os.environ["CSV_DIR"] = str(sample_csv_dir)

        spec.loader.exec_module(mod)

        con = duckdb.connect(tmp_duckdb_path)
        con.execute("CREATE SCHEMA IF NOT EXISTS main")
        count = mod.load(con, "products")
        con.close()

        assert count > 0, "A tabela products não deve estar vazia"


# ---------------------------------------------------------------------------
# Testes de validação de constantes do módulo
# ---------------------------------------------------------------------------

class TestLoadRawConstants:
    """Testa constantes e configurações do load_raw_layer."""

    def test_tables_list_contains_core_tables(self):
        """Verifica que a lista TABLES inclui as tabelas core esperadas."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        core_tables = {"sales", "sale_lines", "customers", "products", "stores"}
        for table in core_tables:
            assert table in mod.TABLES, f"Tabela core ausente em TABLES: {table}"

    def test_exclude_columns_defined(self):
        """Verifica que EXCLUDE_COLUMNS é um dict (pode ser vazio)."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "load_raw_layer",
            PROJECT_ROOT / "scripts" / "load_raw_layer.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        assert isinstance(mod.EXCLUDE_COLUMNS, dict)
