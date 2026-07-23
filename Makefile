.PHONY: help setup simulate load load-raw build build-staging build-marts platform test lint docs clean \
        kafka-up kafka-down kafka-status kafka-consume simulate-kafka load-parquet \
        build-snowflake deploy-streamlit deploy-streamlit-reset \
        airflow-up airflow-down airflow-status \
        tf-init tf-plan tf-apply tf-destroy tf-output tf-fmt

help:  ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

setup:  ## Install Python deps + dbt packages (run once after clone)
	pip install -r requirements.txt
	cd dbt && dbt deps

simulate:  ## Run OLTP simulator and export CSVs (canonical 2-year dataset)
	python erp/run_simulation.py --period 730d --customers 10000 --stores 150 --seed 42 --export-csv

load: load-raw  ## Alias for load-raw (load CSVs into the DuckDB RAW layer)

load-raw:  ## Load CSVs into DuckDB RAW layer (disconnect DBeaver first)
	python scripts/load_raw_layer.py

build:  ## Run full dbt build (dev_raw target)
	cd dbt && dbt build --target dev_raw

build-staging:  ## Build only staging models
	cd dbt && dbt build --select staging --target dev_raw

build-marts:  ## Build only marts models
	cd dbt && dbt build --select marts --target dev_raw

platform:  ## Executive Decision Platform (Streamlit multipage) — lê os MARTS (localhost:8501)
	streamlit run app/main.py

test:  ## Run pytest tests
	pytest tests/ -v

lint:  ## Lint Python with ruff
	ruff check erp/ scripts/ tests/ --select E,W,F --ignore E501

docs:  ## Generate dbt docs
	cd dbt && dbt docs generate --target dev_raw

clean:  ## Clean generated artifacts
	cd dbt && dbt clean
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── Airflow batch orchestration ───────────────────────────────────────────────
airflow-up:  ## Start Airflow batch orchestrator (UI: localhost:8080, admin/admin)
	docker compose -f airflow/docker-compose.yml up --build

airflow-down:  ## Stop Airflow batch orchestrator (keeps volumes)
	docker compose -f airflow/docker-compose.yml down

airflow-status:  ## Show Airflow container status
	docker compose -f airflow/docker-compose.yml ps

# ── Streaming pipeline (Kafka → MinIO → Snowflake) ────────────────────────────
kafka-up:  ## Start Kafka + MinIO + Kafka UI (localhost:8090, 9000, 9001)
	docker compose -f extensions/streaming/docker-compose.yml up -d

kafka-down:  ## Stop and remove Kafka + MinIO containers (keeps volumes)
	docker compose -f extensions/streaming/docker-compose.yml down

kafka-status:  ## Show streaming-stack container status
	docker compose -f extensions/streaming/docker-compose.yml ps

kafka-consume:  ## Consume Kafka events → Parquet → MinIO (drain + exit)
	python extensions/streaming/consumers/parquet_consumer.py --once

simulate-kafka:  ## Stream simulation events (normalizados) direto para Kafka
	python erp/run_simulation.py --target kafka --period 730d --customers 10000 --stores 150 --seed 42

load-parquet:  ## Download Parquet from MinIO → PUT → COPY INTO Snowflake (Phase 7)
	python snowflake/load_parquet.py

build-snowflake:  ## dbt build no Snowflake — SEMPRE --full-refresh (load-parquet recarrega RAW por inteiro)
	# load_parquet trunca+recarrega RAW.* a cada run. Os fatos incrementais
	# (fct_sales, fct_inventory_movements) usam `where order_date > max(date_id)`:
	# sem --full-refresh eles MANTÊM linhas de simulações anteriores (datas/valores
	# antigos), diluindo fill rate, perfect-order e churn. Full-refresh reconstrói
	# os incrementais do zero a partir do RAW atual.
	cd dbt && dbt build --full-refresh --target snowflake

deploy-streamlit:  ## Deploy Streamlit app to Snowflake via snow CLI (updates files only)
	snow streamlit deploy --connection retail

deploy-streamlit-reset:  ## Full replace (WARNING: resets execution mode to legacy)
	snow streamlit deploy --replace --prune --connection retail

# ── Terraform (Snowflake IaC) ─────────────────────────────────────────────────
tf-init:  ## terraform init — download providers (run once per clone)
	scripts/tf_deploy.sh init

tf-plan:  ## terraform plan — preview all Snowflake infra changes
	scripts/tf_deploy.sh plan

tf-apply:  ## terraform apply — provision / update Snowflake infra
	scripts/tf_deploy.sh apply

tf-destroy:  ## terraform destroy — tear down ALL Snowflake infra (irreversible!)
	scripts/tf_deploy.sh destroy

tf-output:  ## Print Terraform outputs (warehouse name, stage ref, SQS ARNs…)
	scripts/tf_deploy.sh output

tf-fmt:  ## Format Terraform files in-place
	scripts/tf_deploy.sh fmt
