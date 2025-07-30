# Local Airflow Testing

This repository provides a simple Docker Compose setup for running the Airflow DAG locally.

## Prerequisites
- Docker and Docker Compose v1.29+

## Quick start
```bash
# Build the Spark image used by the DAG
docker compose build spark

# Start Postgres and Airflow (web UI available on http://localhost:8080)
docker compose up postgres airflow
```

The DAG `etl_csv_to_parquet_k8s` will run the Spark job using `DockerOperator` when the `LOCAL_AIRFLOW` environment variable is set (configured in `docker-compose.yaml`).

## PDF to FAISS Example

An additional DAG `pdf_to_faiss` demonstrates creating OpenAI embeddings from a PDF
and storing them in a FAISS index. The sample PDF should be placed in
`data-pipeline/data/input.pdf` before running the DAG.
