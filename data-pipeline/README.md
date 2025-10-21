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

## HiRAG Index DAG

The `hirag_index` DAG orchestrates hierarchical RAG indexing using the vendored HiRAG package:
- Watches an ingestion bucket for new documents.
- Downloads batches to a temporary workspace.
- Hashes and deduplicates documents with HiRAG utilities.
- Calls the HiRAG graph builder to insert new content.
- Triggers the Bedrock Knowledge Base sync endpoint.
- Archives processed files and records their hashes to avoid reprocessing.

### Configuration
Set the following environment variables (or add them to `airflow.cfg`) before starting Airflow:
- `HIRAG_SOURCE_BUCKET` / `HIRAG_SOURCE_PREFIX`: location of incoming documents in S3.
- `HIRAG_ARCHIVE_PREFIX`: prefix where processed files are moved.
- `HIRAG_AWS_CONN_ID`: Airflow connection ID with S3 access.
- `HIRAG_SYNC_ENDPOINT`: backend HTTP endpoint that initiates Bedrock synchronization.
- `HIRAG_BATCH_SIZE` / `HIRAG_MAX_CONCURRENCY`: default batch size and concurrency, overridable via DAG params.
- `HIRAG_WORKING_DIR`: working directory used by HiRAG for persistent graph state and JSON KV stores.
- `HIRAG_PROCESSED_NAMESPACE`: namespace key for the JSON store that tracks processed S3 objects.
- `HIRAG_TEMP_BASE_DIR`: base directory for temporary downloads prior to ingestion.

### Local Testing
1. Ensure the backend service exposes the Bedrock sync endpoint locally (for example, via Docker Compose).
2. Install the dependencies listed in `third_party/hhy-huang_hirag/requirements.txt` inside the Airflow environment.
3. Start the docker compose stack: `docker compose up postgres airflow`.
4. In the Airflow UI, trigger `hirag_index` manually or run `airflow dags test hirag_index 2024-01-01` inside the scheduler container to execute a single run.
5. When testing without AWS access, mock the S3 connection using [LocalStack](https://www.localstack.cloud/) or substitute `S3Hook` with a custom backend via the Airflow connection system.
