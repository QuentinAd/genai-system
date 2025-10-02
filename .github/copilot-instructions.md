# Generative AI System

This repository contains a data pipeline service, a backend service, a frontend UI, and infrastructure code. The backend service provides a Quart web application using Blueprints, asyncio, httpx, Gunicorn, and LangChain for streaming chatbots. The frontend is a Vite + React + TypeScript app that consumes the streaming chat endpoint.

Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.

## Working Effectively

- Bootstrap, build, and test the repository:
  - `pip install -r data-pipeline/requirements.txt` -- takes 48 seconds. NEVER CANCEL. Set timeout to 90+ seconds.
  - `pip install -r app/requirements.txt` -- takes 49 seconds. NEVER CANCEL. Set timeout to 90+ seconds.
  - `cd ui && npm ci` -- installs UI dependencies. Use Node 22+. NEVER CANCEL.
- Format and lint code:
  - Python: `ruff format .` then `ruff check .` -- both ~0.01 seconds
  - UI: from `ui/` run `npm run lint` and `npm run format`
- Run tests:
  - Backend/Data Pipeline: `pytest` -- takes ~3 seconds. Expect 6 pass, 2 skip (Airflow) depending on environment.
  - UI: from `ui/` run `npm run test` -- Vitest unit tests
- Run the backend service:
  - ALWAYS install dependencies first
  - Backend requires OpenAI API key set in `.env` file: `OPENAI_API_KEY=sk-proj-xxxxxxxx`
  - Production command: `gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000 app.main:app`
  - For testing without OpenAI API key: Use DummyChatBot by creating custom app instance
- Run the frontend UI:
  - Dev server: from `ui/` run `npm run dev` (Vite). Proxy to backend is configured in `vite.config.ts` and respects `VITE_BACKEND_URL`.
  - Build: from `ui/` run `npm run build` then `npm run preview` to serve static build
- Run Airflow locally:
  - `docker compose up airflow-init && docker compose up` -- starts full Airflow stack
  - Web UI: http://localhost:8080 (admin/admin)

## Validation

- ALWAYS run `ruff format .` and `ruff check .` before committing or CI will fail
- ALWAYS run `pytest` to validate Python changes - tests must pass
- ALWAYS run `ui` tests and lint before committing UI changes: `cd ui && npm run lint && npm run format && npm run test`
- Test backend functionality by creating app with DummyChatBot for local testing without OpenAI key
- Test chat end-to-end:
  - Backend: `curl -X POST -H "Content-Type: application/json" -d '{"message":"Hello"}' http://localhost:8000/chat`
  - Frontend: start UI dev server and send a message in the chat UI
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
├── ui/                  # Frontend Vite + React app
│   ├── src/             # React components and tests
│   ├── public/          # Static assets
│   ├── vite.config.ts   # Vite and Vitest config (proxy to backend)
│   ├── tailwind.config.ts # Tailwind (dark mode + typography)
│   ├── eslint.config.js # ESLint flat config
│   ├── vitest.setup.ts  # Vitest setup (jest-dom, polyfills)
│   └── package.json     # UI dependencies and scripts
├── data-pipeline/       # Airflow DAG ETL
│   ├── dags/            # Airflow DAGs
│   ├── tests/           # Pipeline tests
│   └── requirements.txt # Pipeline dependencies
├── infra/               # Terraform infrastructure
├── helm/                # Kubernetes deployment
├── docker-compose.yaml  # Local Airflow setup (+ app/ui services)
├── pyproject.toml       # Ruff configuration
└── pytest.ini           # Test configuration
```

### Key Services

**Frontend UI (ui/)**
- Vite + React + TypeScript app
- TailwindCSS with class-based dark mode and typography plugin
- Markdown rendering with `react-markdown` and syntax highlighting via `rehype-highlight`
- Vitest + Testing Library for unit tests

**Backend Service (app/)**
- Quart application with async routes
- LangChain integration for OpenAI streaming
- Uses Blueprints for route organization
- Test with DummyChatBot to avoid OpenAI API requirements

**Data Pipeline (data-pipeline/)**
- Airflow DAGs for orchestration
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
cd ui && npm ci                                # install UI deps
```

Lint and format:
```bash
ruff format . && ruff check .      # Python
cd ui && npm run lint && npm run format  # UI
```

Test everything:
```bash
pytest                      # 3 seconds, ~6 pass / 2 skip
cd ui && npm run test       # UI unit tests
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

Frontend development:
```bash
cd ui
npm run dev                 # Vite dev server (proxy to backend)
VITE_BACKEND_URL=http://localhost:8000 npm run dev  # override proxy target

# Or run with Docker Compose (app + ui only)
# UI runs on Debian-based Node image to avoid rollup musl optional deps
# and expects @tailwindcss/typography to be installed
# If you hit npm optional dep errors, remove node_modules and package-lock.json then npm ci

docker compose up -d app ui
# UI: http://localhost:5173, Backend: http://localhost:8000
```

Local Airflow development:
```bash
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

**Node Requirements:**
- Node 22+ recommended
- Use `npm ci` for reproducible installs in CI

**Docker Requirements:**
- Docker 28.0.4+ for containerization
- Docker Compose v2.38.2+ for Airflow stack

**Key Environment Variables:**
- `OPENAI_API_KEY` - Required for OpenAI integration (use DummyChatBot for testing)
- `VITE_BACKEND_URL` - URL for UI dev server proxy to backend
- `LOCAL_AIRFLOW` - Set in docker-compose.yaml for local DAG execution

### Testing Strategy

**Unit Tests:**
- app/tests/ - Backend service tests with async mocking
- data-pipeline/tests/unit/ - DAG tests
- ui/src/__tests__/ - UI unit tests with Vitest + Testing Library

**Integration Tests:**
- Start backend with DummyChatBot for API testing
- Use Vite dev server or Docker Compose for UI-to-backend testing
- Use Docker Compose for full Airflow stack testing

**Manual Validation Scenarios:**
1. Install dependencies and run linting: `pip install -r data-pipeline/requirements.txt && pip install -r app/requirements.txt && ruff format . && ruff check . && cd ui && npm ci && npm run lint`
2. Execute test suites and verify all pass: `pytest && cd ui && npm run test`
3. Start backend service and test chat endpoint: Start backend with DummyChatBot, then `curl -X POST -H "Content-Type: application/json" -d '{"message":"Hello"}' http://localhost:8000/chat`
4. Start UI dev server and send a test message; verify markdown rendering and theme toggle
5. Start Airflow stack and verify DAG loading: `docker compose up`

### Timing Expectations

- Dependency installation: 48-49 seconds each for Python; UI `npm ci` depends on network
- Ruff linting: <1 second
- Test execution: ~3 seconds for Python; UI Vitest similar
- Backend startup: <5 seconds
- Docker builds: 3-15 minutes (may fail due to network restrictions)

### Known Limitations

- Docker builds may fail in restricted network environments due to SSL certificate or DNS issues
- Terraform commands require terraform binary installation (not available in all environments)
- OpenAI integration requires valid API key (use DummyChatBot for testing)
- Some tests skip when Airflow not installed (expected behavior)
- UI container uses Debian-based Node to avoid musl optional dependency issues with Rollup

### CI/CD Pipeline

GitHub Actions workflow (`.github/workflows/ci.yaml`):
1. Install Python dependencies
2. Run Ruff linting
3. Execute pytest test suite
4. Install UI dependencies and run lint/test/build
5. Build Docker images
6. Upload test artifacts

Always ensure local validation matches CI requirements before pushing changes.
