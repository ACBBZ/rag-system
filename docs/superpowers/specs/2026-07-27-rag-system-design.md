# RAG System Design

Date: 2026-07-27

## Goal

Build a production-oriented, multi-tenant RAG system based on the useful parts of `rag-blackbox` and the referenced RAG design article. The system exposes document embedding/update APIs and a retrieval API. The retrieval API can optionally run agent search, which adds context building and LLM answering on top of retrieved chunks. It uses FastAPI, Postgres, MinIO, and Milvus, without depending on LangChain, LlamaIndex, or similar orchestration frameworks.

The first implementation must support serious multi-tenancy from the start. Tenant identity, knowledge-base scope, storage isolation, metadata filtering, and audit logging are core requirements rather than future extensions.

## Non-Goals

- No LangChain or LlamaIndex dependency.
- No model paths or infrastructure credentials in API request bodies.
- No frontend in the first implementation.
- No OpenSearch in the first implementation.
- No agent framework or graph orchestration in the first implementation.

## Source Context

`rag-blackbox` already provides a thin RAG service with:

- FastAPI endpoints for query and upsert.
- Chroma-based vector search.
- BM25-based full-text search.
- RRF fusion.
- CrossEncoder rerank.

The current implementation is useful as a behavior reference, but it is not production-ready because retrieval returns mostly raw strings, BM25 is rebuilt from all Chroma documents at query time, metadata is weak, model settings are exposed in request payloads, and there is no multi-tenant isolation, citation model, ingestion job state, or evaluation loop.

The referenced article emphasizes production lessons around data cleaning, metadata enrichment, mixed document sources, chunking strategy, hybrid retrieval, reranking, image/table handling, and feedback loops. This design applies those ideas while keeping the first implementation bounded.

## Architecture

```text
Client
  -> FastAPI
    -> Tenant/Auth Context
      -> Embedding/Upsert API
        -> MinIO raw object storage
        -> Parser
        -> Cleaner
        -> Metadata enrichment
        -> Chunker
        -> Postgres metadata/chunk store
        -> Milvus vector store
        -> optional Postgres keyword index

      -> Update API
        -> Version document
        -> Re-parse/re-chunk
        -> Replace Postgres chunk metadata
        -> Replace Milvus vectors
        -> Replace optional keyword index rows

      -> Retrieval API
        -> optional query rewrite
        -> optional vector search
        -> optional full-text search
        -> optional hybrid RRF fusion
        -> optional rerank
        -> structured retrieved chunks
        -> optional agent search
          -> context builder
          -> LLM answer
          -> answer with citations
        -> query/audit/feedback logs
```

## Services And Boundaries

### API Layer

FastAPI owns request validation, tenant context extraction, response shaping, and HTTP error mapping. Business logic stays in the `rag/` package.

Initial API groups:

- `POST /v1/documents/embed`: ingest and embed a new document or raw text.
- `PATCH /v1/documents/{document_id}`: update metadata or replace document content.
- `DELETE /v1/documents/{document_id}`: soft-delete a document and remove active retrieval visibility.
- `POST /v1/retrieval/search`: retrieve structured chunks, optionally with agent search answer generation.
- `GET /v1/jobs/{job_id}`: inspect ingestion/update job status.
- `POST /v1/feedback`: store answer feedback.
- `GET /health`: service health.

### Ingestion Layer

The ingestion pipeline handles file/text normalization before indexing:

1. Store raw file or raw text in MinIO.
2. Parse supported formats.
3. Clean boilerplate, repeated whitespace, control characters, and broken layout artifacts.
4. Enrich metadata: tenant, knowledge base, source URI, filename, MIME type, title path, page, language, checksum, version.
5. Chunk text using structure-aware splitting.
6. Persist document/chunk records in Postgres.
7. Embed active chunks and upsert vectors into Milvus.
8. Optionally update keyword index rows.

Initial file support:

- `.txt`
- `.md`
- `.pdf`
- `.docx`
- `.csv`
- `.xlsx`
- `.xls`
- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

Table files are converted into row-aware text chunks with sheet name, row range, and column metadata. Embedded tables in PDF and DOCX files should be extracted when the selected parser can do so reliably. Image files are processed through an OCR/vision adapter and stored with extracted text plus image metadata. Parsers are local adapters. They must not rely on LangChain document loaders.

### Retrieval Layer

Retrieval returns structured candidates by default. When `agent_search` is enabled, the same endpoint also builds context and calls the configured LLM to return an answer with citations.

Retrieval stages are individually configurable by server-side tenant defaults and request-level boolean switches:

- `query_rewrite`
- `vector_search`
- `full_text_search`
- `hybrid_search`
- `rerank`
- `agent_search`

Request-level switches can disable or enable features, but they cannot override model names, model paths, Milvus connection settings, Postgres DSN, MinIO credentials, or tenant isolation settings.

### Agent Search Layer

Agent search is exposed as an optional mode of `POST /v1/retrieval/search`, not as a separate public endpoint.

When enabled, agent search owns:

1. Input validation.
2. Retrieval pipeline call.
3. Context building.
4. Prompt assembly.
5. LLM call.
6. Citation mapping.
7. Query log persistence.
8. Response formatting.

`Context Builder -> LLM Answer` is not exposed as a separate public API in the first implementation. It is an internal part of `agent_search` inside `/v1/retrieval/search`.

## Multi-Tenancy

Multi-tenancy is required in the first implementation.

### Tenant Context

Every request must resolve:

- `tenant_id`
- `organization_id`
- `user_id`
- `knowledge_base_id`
- `roles`
- `allowed_scopes`

The first implementation uses API-key based tenant resolution for service-to-service access. Each API key is bound to one tenant, optional organization scope, and allowed knowledge-base scopes. Public API request bodies must not be trusted for tenant identity.

The data model must support complex tenant structures:

- one tenant can contain multiple organizations
- one organization can contain multiple users
- one tenant can contain multiple knowledge bases
- a knowledge base can be shared with multiple roles
- roles can grant read, write, admin, and audit capabilities
- metadata filters can further restrict retrieval within a knowledge base

### Data Isolation

Postgres tables include `tenant_id` and `knowledge_base_id` on all tenant-owned retrieval rows. Queries always filter by tenant and knowledge-base scope unless an internal admin path explicitly opts into cross-tenant access. Repository methods should enforce tenant filters centrally. Postgres row-level security can be added after the repository layer is stable, but application-level tenant filtering is required from the first implementation.

Milvus v1 uses one collection with scalar filters:

- Required scalar fields: `tenant_id`, `knowledge_base_id`, `document_id`, `chunk_id`, `is_active`.
- Retrieval must filter by tenant and knowledge base.

MinIO object keys are namespaced:

```text
tenants/{tenant_id}/knowledge_bases/{knowledge_base_id}/documents/{document_id}/versions/{version}/raw/{filename}
tenants/{tenant_id}/knowledge_bases/{knowledge_base_id}/documents/{document_id}/versions/{version}/parsed/content.md
```

### Versioning And Visibility

Document updates create new versions. Only one version is active for retrieval by default. Old versions remain available for audit until retention cleanup.

Soft delete marks documents and chunks inactive in Postgres, deletes or tombstones vectors in Milvus, and keeps MinIO objects until retention rules remove them.

### Tenant Defaults

Tenant and knowledge-base defaults live in Postgres and `.env` controlled server config:

- default retrieval features
- max upload size
- max chunks per document
- top-k limits
- allowed models
- retention policy

## Configuration

Model and infrastructure configuration comes from `.env` and typed settings loaded at startup.

Examples:

```text
POSTGRES_DSN=
MINIO_ENDPOINT=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
MILVUS_URI=
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=
EMBEDDING_DEVICE=cpu
RERANK_PROVIDER=sentence_transformers
RERANK_MODEL=
RERANK_DEVICE=cpu
QUERY_REWRITE_PROVIDER=openai_compatible
QUERY_REWRITE_MODEL=
LLM_PROVIDER=openai_compatible
LLM_MODEL=
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_API_KEY=
DEFAULT_QUERY_REWRITE_ENABLED=false
DEFAULT_VECTOR_SEARCH_ENABLED=true
DEFAULT_FULL_TEXT_SEARCH_ENABLED=false
DEFAULT_HYBRID_SEARCH_ENABLED=false
DEFAULT_RERANK_ENABLED=false
DEFAULT_AGENT_SEARCH_ENABLED=false
```

API callers may pass retrieval options, but not model paths or credentials.

## API Contracts

### Embed Document

`POST /v1/documents/embed`

Accepts multipart file upload or JSON text input.

Request fields:

- `knowledge_base_id`
- `source_uri`
- `title`
- `metadata`
- `file` or `text`

Response:

```json
{
  "job_id": "job_...",
  "document_id": "doc_...",
  "status": "queued"
}
```

### Update Document

`PATCH /v1/documents/{document_id}`

Supports metadata-only update or content replacement.

Response:

```json
{
  "job_id": "job_...",
  "document_id": "doc_...",
  "version": 2,
  "status": "queued"
}
```

### Retrieval Search

`POST /v1/retrieval/search`

Request:

```json
{
  "knowledge_base_id": "kb_...",
  "query": "问题",
  "options": {
    "query_rewrite": true,
    "vector_search": true,
    "full_text_search": true,
    "hybrid_search": true,
    "rerank": true,
    "agent_search": false,
    "top_k": 20,
    "final_k": 5
  },
  "filters": {
    "document_ids": [],
    "metadata": {}
  }
}
```

Response:

```json
{
  "query_id": "qry_...",
  "rewritten_query": "改写后的问题",
  "chunks": [
    {
      "chunk_id": "chk_...",
      "document_id": "doc_...",
      "text": "...",
      "score": 0.91,
      "retrieval_method": "hybrid_rerank",
      "source": {
        "title": "...",
        "source_uri": "...",
        "page": 3
      },
      "metadata": {}
    }
  ],
  "answer": null,
  "citations": []
}
```

When `options.agent_search=true`, the same endpoint returns generated answer fields:

```json
{
  "query_id": "qry_...",
  "answer": "...",
  "chunks": [
    {
      "chunk_id": "chk_...",
      "document_id": "doc_...",
      "text": "...",
      "score": 0.91,
      "retrieval_method": "hybrid_rerank",
      "source": {
        "title": "...",
        "source_uri": "...",
        "page": 3
      },
      "metadata": {}
    }
  ],
  "citations": [
    {
      "chunk_id": "chk_...",
      "document_id": "doc_...",
      "title": "...",
      "source_uri": "...",
      "page": 3,
      "quote": "..."
    }
  ],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0
  }
}
```

## Database Model

Core tables:

- `tenants`
- `organizations`
- `api_keys`
- `users`
- `user_memberships`
- `knowledge_bases`
- `knowledge_base_acl`
- `documents`
- `document_versions`
- `chunks`
- `chunk_metadata`
- `ingestion_jobs`
- `keyword_terms`
- `keyword_postings`
- `query_logs`
- `retrieval_logs`
- `feedback`

All tenant-owned tables include:

- `tenant_id`
- `created_at`
- `updated_at`

Primary retrieval tables also include:

- `knowledge_base_id`
- `is_active`

## Retrieval Behavior

### Query Rewrite

When enabled, rewrite should produce one canonical query and optionally expansions. The first implementation can use a simple LLM prompt behind an adapter. If rewrite fails, retrieval falls back to the original query and logs the failure.

### Vector Search

Milvus query uses server-configured embedding model and tenant/knowledge-base filters. It returns structured candidates keyed by `chunk_id`.

### Full-Text Search

The first implementation uses Postgres-backed keyword indexing and BM25-style scoring. It is optional. This avoids running OpenSearch before the system needs it.

### Hybrid Search

When vector and full-text search are both enabled and `hybrid_search` is true, merge candidates using RRF. If hybrid is disabled, concatenate unique candidates by configured priority.

### Rerank

When enabled, rerank candidates using a configured rerank adapter. If rerank fails, return the fused candidates and log the error.

### Agent Search

When enabled, agent search converts final retrieved chunks into a bounded context, calls the configured LLM, and maps answer citations back to chunk IDs. If agent search fails after successful retrieval, the endpoint returns a typed LLM failure rather than silently returning only chunks, because callers explicitly requested answer generation.

## Error Handling

Errors should be explicit and typed:

- invalid request
- unauthorized tenant
- forbidden knowledge base
- unsupported file type
- upload too large
- parser failure
- embedding failure
- Milvus failure
- Postgres failure
- MinIO failure
- LLM failure

Ingestion/update failures persist job state with a readable failure reason.

Retrieval and chat endpoints should fail closed on tenant isolation problems. Optional stages can fail open only when the fallback is safe within the resolved tenant context.

## Observability

Log structured events:

- request ID
- tenant ID
- user ID
- knowledge base ID
- document ID
- query ID
- enabled retrieval stages
- stage latency
- candidate counts
- rerank scores
- final citation chunk IDs

Persist query and retrieval logs for evaluation and debugging.

## Testing Strategy

Unit tests:

- settings loading from `.env`
- tenant context resolution
- parser adapters
- chunking behavior
- RRF fusion
- retrieval option gating
- citation mapping

Integration tests:

- Postgres repository behavior
- MinIO object writes
- Milvus adapter with test container or mocked client
- document embed then retrieval
- document update versioning
- tenant isolation across search and chat

Contract tests:

- `/v1/documents/embed`
- `/v1/documents/{document_id}`
- `/v1/retrieval/search`
- `/v1/retrieval/search` with `agent_search=true`

## Initial Implementation Scope

The first build should deliver:

- FastAPI project skeleton.
- Typed `.env` settings.
- Docker Compose for Postgres, MinIO, and Milvus.
- SQL migrations for core multi-tenant tables.
- API-key tenant resolution.
- Document embed API.
- Document update API.
- Retrieval API with optional stages, including `agent_search`.
- Agent search mode with internal context builder and LLM adapter.
- Local parser adapters for `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, and `.webp`.
- Unit and API tests for the critical flow.

## Fixed Provider Defaults

The first implementation uses explicit provider defaults while keeping model values in `.env`:

- Embedding provider: local `sentence_transformers` adapter.
- Rerank provider: local `sentence_transformers` CrossEncoder adapter.
- Query rewrite provider: OpenAI-compatible chat-completions HTTP adapter.
- LLM answer provider: OpenAI-compatible chat-completions HTTP adapter.
- Milvus layout: one collection with scalar tenant and knowledge-base filters.

Tests can use deterministic fake adapters, but production code must load provider settings from `.env` and must not accept model settings from API request bodies.
