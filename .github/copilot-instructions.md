# Generative AI System

This repository contains a data pipeline service, a backend service, and infrastructure code. The backend service provides a Quart web application using Blueprints, asyncio, httpx, Gunicorn, and LangChain for streaming chatbots.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

- Bootstrap, build, and test the repository:
  - `pip install -r data-pipeline/requirements.txt` -- takes 48 seconds. NEVER CANCEL. Set timeout to 90+ seconds.
  - `pip install -r app/requirements.txt` -- takes 49 seconds. NEVER CANCEL. Set timeout to 90+ seconds.
- Format and lint code:
  - `ruff format .` -- takes 0.01 seconds
  - `ruff check .` -- takes 0.01 seconds  
- Run tests: `pytest` -- takes 3 seconds. 6 tests pass, 2 skip due to missing Airflow.
- Run the backend service:
  - ALWAYS install dependencies first
  - Backend requires OpenAI API key set in `.env` file: `OPENAI_API_KEY=sk-proj-xxxxxxxx`
  - Production command: `gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app`
  - For testing without OpenAI API key: Use DummyChatBot by creating custom app instance
- Run Airflow locally:
  - `docker compose build spark` -- builds Spark image for DAG. NEVER CANCEL. Can take 3-15 minutes.
  - `docker compose up airflow-init && docker compose up` -- starts full Airflow stack
  - Web UI: http://localhost:8080 (admin/admin)

## Validation

- ALWAYS run `ruff format .` and `ruff check .` before committing or CI will fail
- ALWAYS run `pytest` to validate changes - tests must pass
- Test backend functionality by creating app with DummyChatBot for local testing without OpenAI key
- Test chat endpoint: `curl -X POST -H "Content-Type: application/json" -d '{"message":"Hello"}' http://localhost:8000/chat`
- Docker builds may fail in some environments due to network restrictions - document limitations in that case

## Common Tasks

The following are outputs from frequently run commands. Reference them instead of running bash commands to save time.

### Repository Structure
```
.
├── .github/
│   └── workflows/       # CI/CD pipelines
├── app/                 # Quart backend service
│   ├── services/
│   │   └── chatbot.py   # OpenAIChatBot, DummyChatBot, RAGChatBot
│   ├── tests/           # Backend tests
│   ├── main.py          # App entrypoint
│   ├── routes.py        # API endpoints
│   └── requirements.txt # Backend dependencies
├── data-pipeline/       # Airflow + Spark ETL
│   ├── dags/            # Airflow DAGs
│   ├── spark_jobs/      # PySpark scripts
│   ├── tests/           # Pipeline tests
│   └── requirements.txt # Pipeline dependencies
├── infra/               # Terraform infrastructure
├── helm/                # Kubernetes deployment
├── docker-compose.yaml  # Local Airflow setup
├── pyproject.toml       # Ruff configuration
└── pytest.ini          # Test configuration
```

### Key Services

**Backend Service (app/)**
- Quart application with async routes
- LangChain integration for OpenAI streaming
- Uses Blueprints for route organization
- Test with DummyChatBot to avoid OpenAI API requirements

**Data Pipeline (data-pipeline/)**
- Airflow DAGs for orchestration
- PySpark jobs for data processing
- Docker-based local development
- Tests in data-pipeline/tests/unit/

**Infrastructure (infra/)**
- Terraform modules for AWS
- EKS, S3, VPC, MWAA components
- Use `terraform validate` and `terraform plan` before applying

### Development Commands

Install all dependencies:
```bash
pip install -r data-pipeline/requirements.txt  # 48 seconds
pip install -r app/requirements.txt            # 49 seconds
```

Lint and format:
```bash
ruff format .  # Always run before commit
ruff check .   # Must pass or CI fails
```

Test everything:
```bash
pytest  # 3 seconds, 6 pass / 2 skip
```

Backend development:
```bash
# Create .env file with OPENAI_API_KEY=sk-proj-xxxxxxxx
gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app

# For testing without OpenAI key, use DummyChatBot:
python3 -c "
from app import create_app
from app.services.chatbot import DummyChatBot
app = create_app(chatbot=DummyChatBot())
app.run(host='0.0.0.0', port=8000)"
```

Local Airflow development:
```bash
docker compose build spark        # NEVER CANCEL. Takes 3-15 minutes. Set timeout to 20+ minutes.
docker compose up airflow-init && docker compose up
# Access http://localhost:8080 with admin/admin
```

### Test Chat Endpoint
```bash
curl -X POST -H "Content-Type: application/json" \
     -d '{"message":"Hello"}' http://localhost:8000/chat
```

### Environment Setup

**Python Requirements:**
- Python 3.12+ (tested with 3.12.3)
- pip for package installation

**Docker Requirements:**
- Docker 28.0.4+ for containerization
- Docker Compose v2.38.2+ for Airflow stack

**Key Environment Variables:**
- `OPENAI_API_KEY` - Required for OpenAI integration (use DummyChatBot for testing)
- `LOCAL_AIRFLOW` - Set in docker-compose.yaml for local DAG execution

### Testing Strategy

**Unit Tests:** Run `pytest` from repository root
- app/tests/ - Backend service tests with async mocking
- data-pipeline/tests/unit/ - Spark job and DAG tests

**Integration Tests:** 
- Start backend with DummyChatBot for API testing
- Use Docker Compose for full Airflow stack testing

**Manual Validation Scenarios:**
1. Install dependencies and run linting: `pip install -r data-pipeline/requirements.txt && pip install -r app/requirements.txt && ruff format . && ruff check .`
2. Execute test suite and verify all pass: `pytest`
3. Start backend service and test chat endpoint: Start backend with DummyChatBot, then `curl -X POST -H "Content-Type: application/json" -d '{"message":"Hello"}' http://localhost:8000/chat`
4. Build Docker images (if network allows): `docker compose build spark`
5. Start Airflow stack and verify DAG loading: `docker compose up`

### Timing Expectations

- Dependency installation: 48-49 seconds each (NEVER CANCEL - set 90+ second timeouts)
- Ruff linting: <1 second
- Test execution: 3 seconds
- Backend startup: <5 seconds
- Docker builds: 3-15 minutes (may fail due to network restrictions)

### Known Limitations

- Docker builds may fail in restricted network environments due to SSL certificate or DNS issues
- Terraform commands require terraform binary installation (not available in all environments)
- OpenAI integration requires valid API key (use DummyChatBot for testing)
- Some tests skip when Airflow not installed (expected behavior)
- PySpark jobs require Spark runtime environment or Docker for full testing

### CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yaml`):
1. Install Python dependencies
2. Run Ruff linting 
3. Execute pytest test suite
4. Build Docker images
5. Upload test artifacts

Always ensure local validation matches CI requirements before pushing changes.