# Local Airflow Testing

This repository provides a simple Docker Compose setup for running the Airflow DAG locally.

## Prerequisites
- Docker and Docker Compose v1.29+

## Quick start
```bash
# Start Postgres and Airflow (web UI available on http://localhost:8080)
docker compose up postgres airflow
```

## PDF to Chroma Example

An additional DAG `pdf_to_chroma_python` demonstrates creating OpenAI embeddings from a PDF
and storing them in a Chroma index. The sample PDF should be placed in
`data-pipeline/data/input.pdf` before running the DAG.
