# rag-system

Production-oriented multi-tenant RAG system.

## Features

- FastAPI API service
- Postgres metadata and audit storage
- MinIO raw and parsed object storage
- Milvus vector storage
- Remote model endpoints configured through `.env`
- Optional query rewrite, vector search, full-text search, hybrid search, rerank, and agent search
- First supported file formats: `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, `.webp`

Model configuration is loaded from environment variables and is never accepted in API request bodies.

## Requirements

- Python 3.11+
- Docker and Docker Compose
- Remote model-compatible endpoints for embedding, rerank, query rewrite, LLM, and OCR when those capabilities are enabled

## Install

```bash
git clone https://github.com/ACBBZ/rag-system.git
cd rag-system

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Configure

Copy the example environment file:

```bash
cp .env.example .env
```

Set infrastructure values:

- `POSTGRES_DSN`: SQLAlchemy async Postgres DSN, for example `postgresql+asyncpg://rag:rag@localhost:5432/rag`
- `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET`, `MINIO_SECURE`
- `MILVUS_URI`, `MILVUS_COLLECTION`

Set model endpoint values:

- `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`
- `RERANK_URL`, `RERANK_MODEL`, `RERANK_API_KEY`
- `QUERY_REWRITE_URL`, `QUERY_REWRITE_MODEL`, `QUERY_REWRITE_API_KEY`
- `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY`
- `OCR_URL`, `OCR_MODEL`, `OCR_API_KEY`

Set default retrieval behavior:

- `DEFAULT_QUERY_REWRITE_ENABLED`
- `DEFAULT_VECTOR_SEARCH_ENABLED`
- `DEFAULT_FULL_TEXT_SEARCH_ENABLED`
- `DEFAULT_HYBRID_SEARCH_ENABLED`
- `DEFAULT_RERANK_ENABLED`
- `DEFAULT_AGENT_SEARCH_ENABLED`

## Local Services

Start Postgres, MinIO, and Milvus:

```bash
docker compose up -d
```

MinIO console is available at `http://localhost:9001` with the credentials from `docker-compose.yml`.

## Database

The first schema migration is stored in `migrations/versions/0001_initial.py`. The current repository contains the migration code but does not include an `alembic.ini`; add one for your deployment target before running Alembic in an environment.

API authentication requires an active tenant API key row in Postgres. Requests must send:

```http
Authorization: Bearer <api-key>
```

## Start API

Development server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production-style single-process start:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The OpenAPI schema is available at `http://localhost:8000/docs`.

## Deploy

1. Provision Postgres, MinIO-compatible object storage, Milvus, and the remote model services.
2. Configure all required environment variables from `.env.example`.
3. Apply the database migration for `migrations/versions/0001_initial.py`.
4. Seed tenant, knowledge base, user, and API key rows.
5. Run the FastAPI service with `uvicorn app.main:app --host 0.0.0.0 --port 8000` behind your process manager or container runtime.
6. Configure TLS, request size limits, logging, backups, and secret management outside the application process.

## API Usage

All protected endpoints require:

```http
Authorization: Bearer <api-key>
```

### Health Check

```bash
curl http://localhost:8000/health
```

### Embed Document

`POST /v1/documents/embed`

Multipart form parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_base_id` | string | yes | Target knowledge base ID. |
| `title` | string | yes | Document title. |
| `file` | file | yes | Uploaded document. |
| `source_uri` | string | no | Original source URL or external file URI. |

Example:

```bash
curl -X POST http://localhost:8000/v1/documents/embed \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -F "knowledge_base_id=kb_001" \
  -F "title=Product Handbook" \
  -F "source_uri=s3://source/product-handbook.pdf" \
  -F "file=@./product-handbook.pdf"
```

Response:

```json
{
  "job_id": "job_...",
  "document_id": "doc_...",
  "status": "completed"
}
```

### Update Document

`PATCH /v1/documents/{document_id}`

Form parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_base_id` | string | yes | Knowledge base that owns the document. |

Example:

```bash
curl -X PATCH http://localhost:8000/v1/documents/doc_001 \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -F "knowledge_base_id=kb_001"
```

Response:

```json
{
  "job_id": "job_...",
  "document_id": "doc_001",
  "version": 2,
  "status": "completed"
}
```

### Hard Delete Document

`DELETE /v1/documents/{document_id}/purge`

Query parameters:

| Name | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_base_id` | string | yes | Knowledge base that owns the document. |

Example:

```bash
curl -X DELETE "http://localhost:8000/v1/documents/doc_001/purge?knowledge_base_id=kb_001" \
  -H "Authorization: Bearer $RAG_API_KEY"
```

Response:

```json
{
  "document_id": "doc_001",
  "status": "purged"
}
```

### Retrieval Search

`POST /v1/retrieval/search`

JSON body:

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `knowledge_base_id` | string | yes | Knowledge base to search. |
| `query` | string | yes | User query. |
| `options` | object | no | Retrieval feature toggles and limits. |
| `filters` | object | no | Document and metadata filters. |

`options` fields:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `query_rewrite` | boolean or null | null | Enable query rewrite for this request. |
| `vector_search` | boolean or null | null | Enable vector search for this request. |
| `full_text_search` | boolean or null | null | Enable full-text search for this request. |
| `hybrid_search` | boolean or null | null | Enable hybrid retrieval and result fusion. |
| `rerank` | boolean or null | null | Enable reranking. |
| `agent_search` | boolean or null | null | Return answer generation fields in addition to chunks. |
| `top_k` | integer | 20 | Candidate retrieval limit, 1 to 100. |
| `final_k` | integer | 5 | Final chunk limit, 1 to 50. |

`filters` fields:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `document_ids` | string array | `[]` | Limit search to specific documents. |
| `metadata` | object | `{}` | Exact metadata filters with string, number, or boolean values. |

Example:

```bash
curl -X POST http://localhost:8000/v1/retrieval/search \
  -H "Authorization: Bearer $RAG_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "knowledge_base_id": "kb_001",
    "query": "How do I reset a user password?",
    "options": {
      "query_rewrite": true,
      "vector_search": true,
      "hybrid_search": true,
      "rerank": true,
      "agent_search": true,
      "top_k": 20,
      "final_k": 5
    },
    "filters": {
      "document_ids": [],
      "metadata": {
        "department": "support"
      }
    }
  }'
```

Response shape:

```json
{
  "query_id": "qry_...",
  "rewritten_query": "How can an admin reset a user password?",
  "chunks": [
    {
      "chunk_id": "chunk_...",
      "document_id": "doc_...",
      "text": "Relevant passage...",
      "score": 0.92,
      "retrieval_method": "hybrid",
      "source": {
        "title": "Product Handbook",
        "source_uri": "s3://source/product-handbook.pdf",
        "page": 4
      },
      "metadata": {
        "department": "support"
      }
    }
  ],
  "answer": "Answer text when agent_search is enabled.",
  "citations": [
    {
      "chunk_id": "chunk_...",
      "document_id": "doc_...",
      "title": "Product Handbook",
      "source_uri": "s3://source/product-handbook.pdf",
      "page": 4,
      "quote": "Relevant passage..."
    }
  ],
  "usage": {
    "prompt_tokens": 100,
    "completion_tokens": 50
  }
}
```

Current implementation note: `/v1/retrieval/search` exposes the API contract and currently returns an empty retrieval skeleton until the storage-backed retrieval service is wired into the route.

## Validate

```bash
ruff check .
pytest -v
```
