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

The `hirag_index` DAG orchestrates hierarchical RAG indexing using the vendored HiRAG package wired to AWS-native services:
- Watches an ingestion bucket for new documents.
- Downloads batches to a temporary workspace and deduplicates them via DynamoDB.
- Calls the HiRAG graph builder, which writes metadata to DynamoDB, embeddings to OpenSearch, and graph data to Neptune.
- Archives processed files and records their hashes to avoid reprocessing.

### Configuration
Set the following environment variables (or add them to `airflow.cfg`) before starting Airflow:
- `HIRAG_SOURCE_BUCKET` / `HIRAG_SOURCE_PREFIX`: location of incoming documents in S3.
- `HIRAG_ARCHIVE_PREFIX`: prefix where processed files are moved.
- `HIRAG_AWS_CONN_ID`: Airflow connection ID with S3 access.
- `HIRAG_BATCH_SIZE` / `HIRAG_MAX_CONCURRENCY`: default batch size and concurrency, overridable via DAG params.
- `HIRAG_WORKING_DIR`: working directory used by HiRAG when caching intermediates.
- `HIRAG_PROCESSED_NAMESPACE`: namespace key for processed-key tracking.
- `HIRAG_TEMP_BASE_DIR`: base directory for temporary downloads prior to ingestion.
- `DYNAMO_PROCESSED_TABLE` (or `DYNAMO_KV_TABLE`): DynamoDB table that stores processed document hashes.
- `OPENSEARCH_ENDPOINT` / `OPENSEARCH_INDEX`: OpenSearch endpoint and index for HiRAG vectors.
- `NEPTUNE_ENDPOINT`, `NEPTUNE_IAM_ROLE_ARN`, `NEPTUNE_GRAPH_BUCKET`: Neptune connection parameters used by the bulk loader.
- `AWS_REGION`: AWS region shared by the above services.

### Local Testing
1. Install the dependencies listed in `third_party/hhy-huang_hirag/requirements.txt` and ensure `boto3`, `opensearch-py`, and `requests-aws4auth` are available inside the Airflow environment.
2. Provide local or mocked AWS services (e.g., LocalStack) and seed environment variables noted above.
3. Start the docker compose stack: `docker compose up postgres airflow`.
4. In the Airflow UI, trigger `hirag_index` manually or run `airflow dags test hirag_index 2024-01-01` inside the scheduler container to execute a single run.
5. When testing without AWS access, set `HIRAG_STORAGE_MODE=local` to fall back to the vendored storage implementations.
