.PHONY: help app ui airflow down lint test

help: ## Display available targets
	@grep -E '^[a-zA-Z_-]+:.*##' Makefile | awk 'BEGIN {FS = ":.*##"}; {printf "%-20s %s\n", $$1, $$2}'

app: ## Build and run only the backend app service
	docker compose up --build -d app

ui: ## Build and run the backend and UI services
	docker compose up --build -d app ui

airflow: ## Build Spark image and start the full Airflow stack
	docker compose build spark
	docker compose up airflow-init
	docker compose up

down: ## Stop and remove all services
	docker compose down

lint: ## Format and lint Python and UI code
	ruff format .
	ruff check .
	cd ui && npm run lint && npm run format

test: ## Run backend and frontend test suites
	pytest
	cd ui && npm run test
