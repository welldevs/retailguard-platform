"""erp — OLTP source layer (simulador de ERP de varejo espanhol).

Agrupa o motor de simulação, geradores de dados-mestre e os recursos (catálogo
Mercadona). É a FONTE do pipeline: emite eventos normalizados via CSV (batch) ou
Kafka (streaming) → RAW (Snowflake) → dbt → marts.
"""
