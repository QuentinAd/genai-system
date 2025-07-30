# Generative AI System

This repository contains two main services along with Terraform infrastructure code.

- **data-pipeline/** – Airflow DAGs and PySpark jobs running on Kubernetes
- **app/** – Quart-based backend providing a streaming chat endpoint
- **infra/** – Terraform modules for AWS resources

## Requirements
- Python 3.12+
- Docker & Docker Compose for local Airflow testing
- Optional: Terraform >= 1.5 for infrastructure

## Setup
Clone the repository and install Python dependencies:

```bash
pip install -r app/requirements.txt
```

For the data pipeline you will also need Docker and Docker Compose.

## Running the Backend
The backend exposes a single `/chat` route that streams tokens from an LLM. It can be started locally using Gunicorn:

```bash
gunicorn -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 app.main:app
```

Alternatively build and run the Docker image:

```bash
docker build -f app/Dockerfile -t app .
docker run -p 8000:8000 --env-file .env app
```

Send a message via:

```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"message":"Hello"}' http://localhost:8000/chat
```

## Running the Airflow DAG Locally
The `data-pipeline` service includes a DAG to run a PySpark job either inside Docker or on a Kubernetes cluster. The quick start uses Docker Compose:

```bash
# Build the Spark image used by the DAG
docker compose build spark

# Start Postgres and Airflow (web UI on http://localhost:8080)
docker compose up postgres airflow
```

The DAG `etl_csv_to_parquet_k8s` will run the Spark job using `DockerOperator` when the `LOCAL_AIRFLOW` environment variable is set.

## Tests and Linting
Run the entire test suite from the repository root:

```bash
pytest
```

Format and lint the code with [Ruff](https://docs.astral.sh/ruff/):

```bash
ruff format .
ruff check .
```

## Infrastructure
Terraform modules for the data pipeline and backend live in `infra/`. Validate changes with:

```bash
terraform validate
terraform plan
```

