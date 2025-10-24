# Generative AI System

This repository contains a comprehensive data pipeline service, backend service, and infrastructure code designed for scalable generative AI workloads. The backend service provides a Quart web application using Blueprints, asyncio, httpx, Gunicorn, and LangChain for streaming chatbots.

## Architecture Overview

- **data-pipeline/** – Airflow DAGs jobs
- **app/** – Quart-based backend providing a streaming chat endpoint
- **infra/** – Terraform modules for AWS resources (VPC, S3, ECR, MWAA, DynamoDB, Neptune, OpenSearch)
- **.github/workflows/** – CI/CD pipelines for automated deployment

## Infrastructure Setup

The infrastructure is provisioned using Terraform and includes:

### Core AWS Resources
- **VPC**: Custom VPC with public and private subnets across multiple AZs
- **S3**: Buckets for data storage, HiRAG ingestion, and Airflow DAG management
- **ECR**: Container registries for backend and DAG ETL images
- **MWAA**: Managed Airflow for orchestrating data pipelines
- **IAM**: Fine-grained roles and policies for secure access
- **DynamoDB**: Durable key-value cache and chat session history for HiRAG
- **Amazon Neptune**: Graph database supporting relationship traversal
- **OpenSearch**: Vector search domain and KNN index backing HiRAG retrievals
- **CloudFront + S3**: Static hosting for the frontend UI with global distribution

### Terraform Modules Structure
```
infra/
├── main.tf              # Root module orchestrating all components
├── vpc/                 # VPC, subnets, routing
├── s3/                  # S3 buckets for data, DAGs, and HiRAG ingestion
├── ecr/                 # Container registries
├── mwaa/                # Managed Airflow environment
├── dynamodb/            # HiRAG DynamoDB tables, alarms, IAM policies
├── neptune/             # Neptune graph cluster and analytics configuration
├── opensearch/          # Vector search domain and index bootstrap
└── cloudfront_ui/       # Static website bucket + CloudFront distribution for the UI
```

### Key Terraform Outputs
The infrastructure exports the following outputs for integration with CI/CD and runtime configuration:
- `ecr_backend_repository_url` - Backend application registry URL
- `dags_bucket` / `data_bucket` - S3 buckets for Airflow DAGs and shared datasets
- `hirag_ingestion_bucket` / `hirag_archive_prefix` - Buckets and prefixes used by the HiRAG ingestion DAG
- `hirag_kv_table_name` / `chat_history_table_name` - DynamoDB table names for storage bindings
- `neptune_writer_endpoint` / `neptune_reader_endpoint` - Neptune endpoints for graph traversal
- `opensearch_domain_endpoint` - Vector search endpoint utilized by the backend
- `ui_bucket_name` / `ui_distribution_domain_name` / `ui_distribution_id` - Static UI hosting bucket, CloudFront domain, and distribution handle
- `vpc_id`, subnet IDs, and `vpc_cidr_block` for networking configuration

## HiRAG Infrastructure Runbook

### Provisioning Order
1. Configure the remote Terraform backend:
   - Create the S3 bucket and optional DynamoDB lock table in your AWS account.
   - Copy `infra/backend.hcl.example` to `backend.hcl` and replace the placeholders with your resource names.
   - Run `terraform init -backend-config=backend.hcl` inside `infra/`.
2. Apply Terraform under `infra/` (`terraform plan`, then `terraform apply`). This provisions S3, DynamoDB, Neptune, OpenSearch, and supporting IAM artifacts.
3. Deploy or update the data pipeline (Airflow/MWAA) so the HiRAG ingestion DAG has access to the new buckets and DynamoDB tables.
4. Build the frontend UI (`npm run build` under `ui/`) and sync the `dist/` folder to the Terraform-provisioned UI bucket. The provided CD workflow automates this and handles CloudFront invalidations.
5. Deploy the backend container image from ECR to your runtime of choice (for example, ECS Fargate or Lambda). The CD workflow publishes the latest image tags.

> **Note:** If this is the first time you are creating an OpenSearch domain in the account, set `create_service_linked_role = true` for the `opensearch` module (or pass `-var opensearch_hirag_create_service_linked_role=true`) so Terraform can create the required service-linked role. Leave it `false` (default) if the role already exists to avoid conflicts.

### Required Environment Variables
- `HIRAG_SOURCE_BUCKET` → `hirag_ingestion_bucket`
- `HIRAG_ARCHIVE_PREFIX` → `hirag_archive_prefix`
- `DYNAMO_PROCESSED_TABLE` → `hirag_kv_table_name`
- `HIRAG_AWS_CONN_ID`, `HIRAG_BATCH_SIZE`, `HIRAG_MAX_CONCURRENCY`, `HIRAG_TEMP_BASE_DIR`, `HIRAG_WORKING_DIR` (existing, ensure values remain aligned)
- Backend services additionally require:
  - `OPENSEARCH_ENDPOINT` → `opensearch_domain_endpoint`
  - `OPENSEARCH_INDEX` → `hirag_embeddings`
  - `NEPTUNE_ENDPOINT` → `neptune_writer_endpoint`
  - `NEPTUNE_READER_ENDPOINT` → `neptune_reader_endpoint`
  - `HIRAG_KV_TABLE` → `hirag_kv_table_name`
  - `HIRAG_CHAT_HISTORY_TABLE` → `chat_history_table_name`

Store credentials using the generated Secrets Manager secrets:
- `opensearch_admin_secret_arn`
- `neptune_secret_arn`

### Health Checks
- **Neptune**: Use the Secrets Manager payload to connect via Gremlin or SPARQL and execute a simple traversal. Monitor CloudWatch for connection or query failures.
- **DynamoDB**: CloudWatch alarms (`*-read-capacity`, `*-write-capacity`) trigger when on-demand capacity spikes.
- **OpenSearch**: Terraform bootstraps the `hirag_embeddings` index. Query `_cluster/health` and run a sample KNN search to verify readiness.
- **Airflow DAG**: Confirm the HiRAG DAG consumes new S3 keys, archives objects to the configured prefix, and writes processed keys to DynamoDB.
- **CloudFront UI**: Load the distribution domain (`ui_distribution_domain_name`) and verify static assets resolve; check the distribution for recent invalidations.

## CI/CD Pipelines

The repository implements three automated workflows:

### 1. Continuous Integration (CI) - `.github/workflows/ci.yaml`
**Trigger**: Push to main branch, pull requests
**Purpose**: Code quality and testing

**Steps:**
- Install Python dependencies
- Run linting with [Ruff](https://docs.astral.sh/ruff/)
- Execute test suite with pytest
- Build Docker images for validation

### 2. Infrastructure Deployment - `.github/workflows/infrastructure.yaml`
**Trigger**: Manual dispatch, changes to `infra/` directory
**Purpose**: Provision and manage AWS infrastructure

**Steps:**
- Initialize and validate Terraform configuration
- Plan infrastructure changes
- Apply changes to AWS (main branch only)
- Export Terraform outputs as JSON for downstream workflows

### 3. Continuous Deployment (CD) - `.github/workflows/cd.yaml`
**Trigger**: Manual dispatch, completion of infrastructure workflow
**Purpose**: Build and deploy applications

**Steps:**
- Build and push Docker images to ECR
- Deploy DAGs to MWAA S3 bucket
- Build the UI and publish static assets to the CloudFront-backed S3 bucket, then invalidate the distribution cache

## Deployment Targets

### Frontend UI (CloudFront + S3)
- Terraform provisions a versioned S3 bucket and CloudFront distribution dedicated to the UI.
- The CD workflow (or a manual `npm run build` followed by `aws s3 sync`) publishes the `ui/dist/` assets.
- Non-HTML assets are uploaded with long-lived cache headers; HTML is uploaded with `no-cache` to ensure clients fetch new releases.
- CloudFront invalidations (triggered automatically in the workflow) guarantee fast propagation of UI changes.

### Backend Service (Container Image in ECR)
- Terraform creates ECR repositories (`etl`, `genai-app`) for the pipeline and backend services.
- The CD workflow builds and pushes fresh `latest` tags for both images.
- Run the backend container using your preferred compute platform (ECS Fargate, EC2, Lambda, etc.) pointing to the emitted ECR URI and providing the environment variables listed earlier.
- The infrastructure stack surfaces IAM policies and storage endpoints required by the backend.

## Requirements
- Python 3.12+
- Docker & Docker Compose for local development
- Terraform >= 1.5 for infrastructure management
- AWS CLI configured with appropriate permissions
- Node.js 20+ for building the UI

## Local Development Setup

### Backend Service
```bash
# Install dependencies
pip install -r app/requirements.txt

# Run locally with Gunicorn
gunicorn -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 app.main:app

# Or with Docker
docker build -f app/Dockerfile -t genai-app .
docker run -p 8000:8000 --env-file .env genai-app
```

### Data Pipeline (Local Airflow)
```bash
# Start Airflow (web UI at http://localhost:8080)
docker compose up airflow-init && docker compose up
```

### Frontend UI
```bash
# From the ui/ directory
cd ui

# Start Vite dev server (proxies /chat and /health to the backend)
npm run dev

# Override proxy target if backend is not on localhost:8000
VITE_BACKEND_URL=http://localhost:8000 npm run dev

# Lint, format, test, and build
npm run lint && npm run format && npm run test && npm run build
```

### Run app and UI together (Docker Compose)
```bash
# Start only the app and ui services
docker compose up -d app ui

# URLs
# UI:      http://localhost:5173
# Backend: http://localhost:8000
```

## Testing and Quality Assurance

### Running Tests
```bash
# Run complete test suite
pytest

# Run with coverage
pytest --cov=app --cov=data-pipeline
```

### Code Quality
```bash
# Format code
ruff format .

# Check linting
ruff check .

# Fix auto-fixable issues
ruff check . --fix
```

### UI
```bash
cd ui
npm run lint && npm run format && npm run test
```

## Deployment

### Infrastructure Deployment
1. Configure AWS credentials and Terraform backend
2. Trigger the infrastructure workflow manually or push changes to `infra/`
3. Review Terraform plan in the workflow logs
4. Infrastructure is automatically applied on the main branch

### Application Deployment
1. Ensure infrastructure is deployed first
2. Trigger the CD workflow manually
3. The workflow will:
   - Build and push Docker images
   - Deploy DAGs to MWAA
   - Build the UI and publish it through CloudFront

### Manual UI Deployment
```bash
# Build the production bundle
cd ui
npm ci
npm run build

# Sync assets (long-lived cache) and HTML (no-cache)
aws s3 sync dist s3://<ui-bucket> --delete --cache-control "public, max-age=31536000" --exclude "index.html"
aws s3 cp dist/index.html s3://<ui-bucket>/index.html --cache-control "no-cache"

# Invalidate CloudFront so users see the refresh immediately
aws cloudfront create-invalidation --distribution-id <distribution-id> --paths "/*"
```

### Manual Backend Deployment
1. Pull the published image from ECR: `docker pull <account>.dkr.ecr.<region>.amazonaws.com/genai-app:latest`.
2. Supply the environment variables listed earlier (`OPENSEARCH_ENDPOINT`, `HIRAG_KV_TABLE`, etc.).
3. Run the container locally (`docker run -p 8000:8000 ...`) or reference the image from your compute platform (ECS service, Lambda, EC2, etc.).

## Configuration

### Environment Variables
- `OPENAI_API_KEY`: OpenAI API key for LLM integration
- `VITE_BACKEND_URL`: Backend API base URL for the UI (defaults to http://localhost:8000)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`: AWS credentials
- `AWS_REGION`: Target AWS region

### GitHub Secrets Required
- `AWS_ACCESS_KEY_ID`: AWS access key for deployments
- `AWS_SECRET_ACCESS_KEY`: AWS secret key for deployments
- `AWS_ACCOUNT_ID`: AWS account ID for ECR
- `MWAA_DAGS_BUCKET`: S3 bucket for Airflow DAGs
- `UI_BUCKET_NAME`: Terraform-provisioned bucket for the UI static assets
- `UI_DISTRIBUTION_ID`: CloudFront distribution ID backing the UI

## API Usage

### Chat Endpoint
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"message":"Hello"}' http://localhost:8000/chat
```

### Health Check
```bash
curl http://localhost:8000/health
```

## Monitoring and Observability

- Application metrics available through your chosen deployment platform
- Airflow DAG execution logs available in MWAA console
- Container logs accessible via your container orchestrator tooling

## Security Considerations

- All sensitive credentials stored securely (for example, AWS Secrets Manager or parameter stores)
- IAM roles follow principle of least privilege
- Container images scanned for vulnerabilities in ECR
- Network policies can be implemented for additional isolation

## Contributing

1. Follow the Test-Driven Development (TDD) approach
2. Ensure all tests pass: `pytest`
3. Format code: `ruff format .`
4. Check linting: `ruff check .`
5. Update documentation for any new features
6. Submit pull requests for review

For more detailed information about individual components, refer to the README files in each service directory.
