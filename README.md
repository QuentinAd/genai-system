# Generative AI System

This repository contains a comprehensive data pipeline service, backend service, and infrastructure code designed for scalable generative AI workloads. The backend service provides a Quart web application using Blueprints, asyncio, httpx, Gunicorn, and LangChain for streaming chatbots.

## Architecture Overview

- **data-pipeline/** – Airflow DAGs jobs
- **app/** – Quart-based backend providing a streaming chat endpoint
- **infra/** – Terraform modules for AWS resources (VPC, EKS, S3, ECR, MWAA, DynamoDB, Neptune, OpenSearch)
- **helm/** – Kubernetes deployment charts with dynamic configuration
- **.github/workflows/** – CI/CD pipelines for automated deployment

## Infrastructure Setup

The infrastructure is provisioned using Terraform and includes:

### Core AWS Resources
- **VPC**: Custom VPC with public and private subnets across multiple AZs
- **EKS**: Managed Kubernetes cluster for running containerized workloads
- **S3**: Buckets for data storage, HiRAG ingestion, and Airflow DAG management
- **ECR**: Container registries for backend and DAG ETL images
- **MWAA**: Managed Airflow for orchestrating data pipelines
- **IAM**: Fine-grained roles and policies for secure access
- **DynamoDB**: Durable key-value cache and chat session history for HiRAG
- **Amazon Neptune**: Graph database supporting relationship traversal
- **OpenSearch**: Vector search domain and KNN index backing HiRAG retrievals

### Terraform Modules Structure
```
infra/
├── main.tf              # Root module orchestrating all components
├── vpc/                 # VPC, subnets, routing
├── eks/                 # EKS cluster and node groups
├── s3/                  # S3 buckets for data, DAGs, and HiRAG ingestion
├── ecr/                 # Container registries
├── mwaa/                # Managed Airflow environment
├── dynamodb/            # HiRAG DynamoDB tables, alarms, IAM policies
├── neptune/             # Neptune graph cluster and analytics configuration
└── opensearch/          # Vector search domain and index bootstrap
```

### Key Terraform Outputs
The infrastructure exports the following outputs for integration with CI/CD and runtime configuration:
- `eks_cluster_name` - EKS cluster name for kubectl configuration
- `ecr_backend_repository_url` - Backend application registry URL
- `dags_bucket` / `data_bucket` - S3 buckets for Airflow DAGs and shared datasets
- `hirag_ingestion_bucket` / `hirag_archive_prefix` - Buckets and prefixes used by the HiRAG ingestion DAG
- `hirag_kv_table_name` / `chat_history_table_name` - DynamoDB table names for storage bindings
- `neptune_writer_endpoint` / `neptune_reader_endpoint` - Neptune endpoints for graph traversal
- `opensearch_domain_endpoint` - Vector search endpoint utilized by the backend
- `vpc_id`, subnet IDs, and `vpc_cidr_block` for networking configuration

## HiRAG Infrastructure Runbook

### Provisioning Order
1. Configure the remote Terraform backend:
   - Create the S3 bucket and optional DynamoDB lock table in your AWS account.
   - In `backend.tf` replace the placeholders with your bootstrap s3 backend resource name.
   - Run `terraform init` inside `infra/`.
2. Apply Terraform under `infra/` (`terraform plan`, then `terraform apply`). This provisions S3, DynamoDB, Neptune, OpenSearch, and supporting IAM artifacts.
3. Deploy or update the data pipeline (Airflow/MWAA) so the HiRAG ingestion DAG has access to the new buckets and DynamoDB tables.

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
- **Neptune**: Use the Secrets Manager payload to connect via Gremlin or SPARQL and execute a simple traversal. Monitor CloudWatch for connection or query failures.
- **DynamoDB**: CloudWatch alarms (`*-read-capacity`, `*-write-capacity`) trigger when on-demand capacity spikes.
- **OpenSearch**: Terraform bootstraps the `hirag_embeddings` index. Query `_cluster/health` and run a sample KNN search to verify readiness.
- **Airflow DAG**: Confirm the HiRAG DAG consumes new S3 keys, archives objects to the configured prefix, and writes processed keys to DynamoDB.

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
- Deploy applications to EKS using Helm with dynamic configuration

## Helm Charts Integration

The Helm charts dynamically consume Terraform outputs for seamless deployment:

### Dynamic Configuration
Instead of hardcoded values, the charts use placeholders that are populated at deployment time:
- `BACKEND_IMAGE_PLACEHOLDER` → ECR backend image URI
- `EKS_CLUSTER_NAME_PLACEHOLDER` → Actual EKS cluster name
- `AWS_REGION_PLACEHOLDER` → Target AWS region

### Kubernetes Resources
The Helm chart deploys:
- **Deployment**: Backend API service with health checks and resource limits
- **Service**: ClusterIP service exposing the backend
- **Job**: ETL job for data processing
- **ConfigMap**: Non-sensitive configuration values
- **Secret**: Sensitive credentials (API keys, AWS credentials)

### Configuration Management
- **ConfigMaps**: Store environment-specific settings like bucket names, cluster details
- **Secrets**: Handle sensitive data like API keys and AWS credentials
- **Resource Limits**: Define CPU and memory constraints for optimal resource utilization

## Requirements
- Python 3.12+
- Docker & Docker Compose for local development
- Terraform >= 1.5 for infrastructure management
- kubectl and Helm for Kubernetes deployments
- AWS CLI configured with appropriate permissions

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
   - Deploy applications to EKS with Helm

### Manual Helm Deployment
```bash
# Update kubeconfig
aws eks update-kubeconfig --name <cluster-name> --region <region>

# Deploy with dynamic values
helm upgrade --install genai-system ./helm \
  --set backend.image="<ecr-uri>/genai-app:latest" \
  --set cluster.name="<cluster-name>" \
  --set aws.region="<region>" \
  --namespace genai-system \
  --create-namespace
```

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
- `EKS_CLUSTER_NAME`: Name of the EKS cluster
- `MWAA_DAGS_BUCKET`: S3 bucket for Airflow DAGs
- `DATA_BUCKET_NAME`: S3 bucket for processed data

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

- EKS cluster logs are exported to CloudWatch
- Application metrics available through Kubernetes native monitoring
- Airflow DAG execution logs available in MWAA console
- Container logs accessible via `kubectl logs`

## Security Considerations

- All sensitive credentials stored in Kubernetes Secrets
- EKS cluster uses private endpoints for enhanced security
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
