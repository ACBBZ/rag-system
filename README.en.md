<p align="center">
  <a href="./README.md">简体中文</a> · <a href="./README.en.md">English</a>
</p>

# RAG System

<p align="center">
  <strong>A production-oriented multi-tenant RAG platform with asynchronous ingestion, hybrid retrieval, verifiable citations, RAGAS evaluation, and full observability.</strong>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-green">
  <img alt="CI" src="https://github.com/ACBBZ/rag-system/actions/workflows/ci.yml/badge.svg">
</p>

## Overview

RAG System is a multi-tenant retrieval-augmented generation platform built with FastAPI, PostgreSQL, MinIO, and Milvus. It separates document ingestion, version activation, vector and lexical retrieval, reranking, answer generation, citation validation, offline evaluation, and production operations into focused modules. Tenant-level vector routing and knowledge-base ACLs provide defense-in-depth isolation.

Typical use cases include:

- enterprise knowledge bases and internal question answering;
- a multi-tenant RAG SaaS backend;
- an observable and evaluation-driven RAG engineering baseline;
- integration with self-hosted model endpoints and private data infrastructure.

> The repository includes production-oriented engineering capabilities. Before a real deployment, calibrate capacity, security controls, evaluation baselines, and operational policies for your traffic, models, and data sensitivity.

## Key capabilities

### Multi-tenancy and authorization

- Tenants, users, roles, direct permissions, and knowledge-base ACLs;
- scoped API keys with optional knowledge-base restrictions;
- a dedicated Milvus Collection Alias per tenant;
- `tenant_id` and `knowledge_base_id` filters in PostgreSQL and Milvus;
- separate credentials for the platform control plane and tenant APIs.

### Asynchronous ingestion

- A durable PostgreSQL job queue;
- concurrent job claiming with `FOR UPDATE SKIP LOCKED`;
- an independent `rag-worker` process;
- document versions, staging, validation, and atomic activation;
- idempotent uploads, retries, and reconciliation foundations;
- TXT, Markdown, PDF, DOCX, CSV, XLS/XLSX, and common image formats;
- page-aware PDFs, OCR fallback for scanned documents, tables, and title paths;
- token-aware stable chunks, overlap, content hashes, and stable context keys.

### Retrieval and generation

- Vector, PostgreSQL full-text, and hybrid retrieval;
- configurable weighted RRF, candidate counts, score thresholds, and per-document limits;
- query rewriting, reranking, and answer generation;
- Milvus V2 pre-ANN metadata filtering;
- token-budgeted context construction;
- structured answers, abstention states, and server-side citation ID validation;
- per-stage scores, timings, and retrieval methods.

### Evaluation and observability

- Deterministic Hit Rate, Precision, Recall, MRR, and nDCG metrics;
- filter accuracy, tenant leakage, knowledge-base leakage, duplicate context, and abstention accuracy;
- RAGAS Faithfulness, Answer Relevancy, Context Precision, Context Recall, and Factual Correctness;
- Golden, Smoke, and Adversarial datasets;
- baseline comparison and CI quality gates;
- Prometheus metrics, OpenTelemetry spans, and query/retrieval logs;
- `/health/live`, `/health/ready`, and `/metrics` endpoints.

## Architecture

```text
Client
  │
  ▼
FastAPI API
  ├── Authentication / ACL
  ├── Document and job APIs
  ├── Retrieval and generation API
  └── Health / Metrics
       │
       ├── PostgreSQL
       │    ├── Tenants and authorization
       │    ├── Documents, versions, and chunks
       │    ├── Ingestion job queue
       │    ├── Full-text retrieval
       │    └── Query / Retrieval / Audit logs
       │
       ├── MinIO / S3
       │    ├── Raw files
       │    └── Parsed artifacts
       │
       ├── Milvus
       │    └── Tenant-scoped vector Collections and Aliases
       │
       └── Remote model endpoints
            ├── Embedding
            ├── Rerank
            ├── Query Rewrite
            ├── LLM
            └── OCR

rag-worker
  └── Parse → Chunk → Embed → Index → Validate → Activate
```

## Technology stack

| Layer | Technology |
|---|---|
| API | FastAPI, Pydantic v2, Uvicorn |
| Database | PostgreSQL 16, SQLAlchemy Async, Alembic |
| Object storage | MinIO / S3-compatible storage |
| Vector database | Milvus |
| Retrieval | Milvus ANN, PostgreSQL Full-Text Search, Weighted RRF |
| Model protocol | OpenAI-compatible and custom HTTP endpoints |
| Evaluation | RAGAS and built-in deterministic metrics |
| Observability | Prometheus and OpenTelemetry |
| Quality | Pytest, Ruff, Bandit, pip-audit, CycloneDX |

## Quick start

### 1. Clone and install

```bash
git clone https://github.com/ACBBZ/rag-system.git
cd rag-system

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

At minimum, configure:

- `POSTGRES_DSN`;
- `MINIO_*`;
- `MILVUS_*`;
- `API_KEY_PEPPER` and `PLATFORM_API_KEY`;
- the Embedding, Rerank, Rewrite, LLM, and OCR endpoints used by enabled capabilities.

Never commit real credentials. `API_KEY_PEPPER` should contain at least 32 random bytes and remain stable in a secret manager.

### 3. Start infrastructure

```bash
docker compose up -d
```

The default stack starts PostgreSQL, MinIO, and Milvus. The MinIO Console is available at `http://localhost:9001` by default.

### 4. Apply database migrations

```bash
alembic upgrade head
```

The migration chain includes tenant authorization, vector resources, full-text retrieval, durable ingestion, Retrieval V3, and observability tables.

### 5. Start the API

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- OpenAPI: `http://localhost:8000/docs`
- Liveness: `http://localhost:8000/health/live`
- Readiness: `http://localhost:8000/health/ready`
- Metrics: `http://localhost:8000/metrics`

### 6. Start the ingestion worker

Run in a separate terminal:

```bash
rag-worker
```

The API accepts files and creates durable jobs. Parsing, chunking, embedding, indexing, and version activation run in the worker.

## Main APIs

Tenant APIs require:

```http
Authorization: Bearer <tenant-api-key>
```

The platform control plane uses the separate `PLATFORM_API_KEY`.

### Platform and tenants

```text
POST /v1/platform/tenants
GET  /v1/platform/tenants/{tenant_id}/vector-resource
POST /v1/platform/tenants/{tenant_id}/vector-resource/retry
```

### Users, API keys, and knowledge bases

```text
POST   /v1/users
PATCH  /v1/users/{user_id}/role
PUT    /v1/users/{user_id}/scope-grants
DELETE /v1/users/{user_id}/scope-grants/{permission}
POST   /v1/api-keys
DELETE /v1/api-keys/{api_key_id}
POST   /v1/knowledge-bases
PUT    /v1/knowledge-bases/{knowledge_base_id}/members/{user_id}
```

### Documents and ingestion jobs

```text
POST   /v1/documents/embed
PATCH  /v1/documents/{document_id}
DELETE /v1/documents/{document_id}/purge
GET    /v1/ingestion-jobs/{job_id}
POST   /v1/ingestion-jobs/{job_id}/retry
```

The upload endpoint accepts `Idempotency-Key` and returns `202 Accepted` after a durable job is queued.

### Retrieval

```text
POST /v1/retrieval/search
```

Example:

```bash
curl -X POST http://localhost:8000/v1/retrieval/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_base_id": "kb_example",
    "query": "How many paid annual leave days do employees receive?",
    "options": {
      "retrieval_mode": "hybrid",
      "query_rewrite": true,
      "rerank": true,
      "agent_search": true,
      "top_k": 30,
      "final_k": 6
    },
    "filters": {
      "metadata": {"department": "hr"}
    }
  }'
```

Retrieval modes:

- `vector`: Milvus vector retrieval only;
- `full_text`: PostgreSQL full-text retrieval only;
- `hybrid`: parallel retrieval merged with weighted RRF;
- `auto`: resolve the effective mode from request values and environment defaults.

Responses include `trace_id`, `effective_options`, stage timings, chunk scores, answer status, and validated citations.

## Evaluation

Install evaluation dependencies:

```bash
python -m pip install -e '.[eval]'
```

Run deterministic evaluation:

```bash
rag-eval \
  --dataset evals/datasets/golden.jsonl \
  --output evals/reports/results.jsonl \
  --summary evals/reports/summary.json \
  --baseline evals/baselines/main.json
```

Enable RAGAS:

```bash
rag-eval \
  --dataset evals/datasets/golden.jsonl \
  --output evals/reports/results.jsonl \
  --summary evals/reports/summary.json \
  --baseline evals/baselines/main.json \
  --ragas
```

Before using the bundled datasets as quality gates, replace the example knowledge-base identifiers, references, and stable context keys with a real fixture corpus.

## Testing and quality

```bash
ruff check .
pytest -v
```

Migration regression:

```bash
alembic upgrade head
alembic downgrade 0004_retrieval_v2
alembic upgrade head
```

Security tooling:

```bash
python -m pip install -e '.[security]'
bandit -c pyproject.toml -r app rag
pip-audit
```

Load testing:

```bash
python -m pip install -e '.[load]'
locust -f load/locustfile.py
```

## Docker

Build the API image:

```bash
docker build -t rag-system:latest .
```

In production, run and scale the API and `rag-worker` independently while sharing PostgreSQL, MinIO, Milvus, and model endpoint configuration.

## Operations documentation

- [Production deployment](docs/production-v2.md)
- [Runbook](docs/runbook.md)
- [SLO](docs/slo.md)
- [Backup and restore](docs/backup-restore.md)
- [Retrieval V2 and RAGAS](docs/retrieval-v2-and-ragas.md)
- [Authorization API](docs/authorization-v2-api.md)

## Security

- Never place production credentials in `.env.example`, logs, issues, or commits;
- enforce upload limits at both the gateway and application layers;
- use TLS, rate limiting, audit logs, a secret manager, and network isolation for public deployments;
- treat document content as untrusted input and validate model-returned citation IDs;
- add malware scanning, retention, and deletion policies for sensitive data environments.

Avoid disclosing sensitive vulnerability details in public issues. Prefer a private reporting channel provided by the repository owner.

## Contributing

Issues and improvements are welcome. Before submitting code, run:

```bash
ruff check .
pytest -v
```

Large changes should include a migration strategy, failure recovery plan, tests, and an evaluation impact statement.

## License

This project is licensed under the [MIT License](LICENSE).
