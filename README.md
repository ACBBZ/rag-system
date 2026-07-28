# rag-system

Production-oriented multi-tenant RAG API built with FastAPI, PostgreSQL, MinIO, Milvus, and remote model endpoints.

## Features

- FastAPI API service
- PostgreSQL metadata, authorization, tenant resource, and audit storage
- MinIO/S3-compatible raw and parsed object storage
- One isolated Milvus Collection per tenant
- Tenant users, roles, direct permissions, knowledge-base ACLs, and scoped API keys
- Remote embedding, rerank, query-rewrite, LLM, and OCR endpoints configured through environment variables
- Optional query rewrite, vector search, full-text search, hybrid search, rerank, and agent search
- File support for `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, and `.webp`

Model and infrastructure configuration is loaded from environment variables and is never accepted in API request bodies.

## Current Milvus architecture

The current release uses a deliberately simple fixed V1 model:

```text
one tenant
→ one stable logical Alias
→ one fixed V1 physical Collection
```

Example:

```text
Alias:    rag_prod_t_<tenant-digest>_current
Physical: rag_prod_t_<tenant-digest>_v1
```

Collection names are generated from a SHA-256 digest of the database `tenant_id`. Tenant names and slugs are not included.

Every vector row still stores:

- `tenant_id`
- `knowledge_base_id`
- `document_id`
- `chunk_id`
- `document_version`
- `is_active`

Search and delete operations continue to filter by the authenticated `tenant_id` and authorized `knowledge_base_id` as defense in depth.

There is no shared Collection fallback, migration mode, or dual-write path in V1.

## Requirements

- Python 3.11+
- Docker and Docker Compose
- PostgreSQL
- MinIO or another S3-compatible object store
- Milvus
- Remote model-compatible endpoints for enabled embedding, rerank, query rewrite, LLM, and OCR capabilities

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

### Infrastructure

Required infrastructure settings include:

```env
POSTGRES_DSN=postgresql+asyncpg://rag:rag@localhost:5432/rag

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=miniopass
MINIO_BUCKET=rag-system
MINIO_SECURE=false

MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION_PREFIX=rag_dev
```

Use different Collection prefixes for development, test, and production environments.

### Fixed V1 vector configuration

```env
MILVUS_VECTOR_DIMENSION=1024
MILVUS_METRIC_TYPE=COSINE
MILVUS_INDEX_TYPE=HNSW
MILVUS_INDEX_M=16
MILVUS_INDEX_EF_CONSTRUCTION=200
MILVUS_SEARCH_EF=64
```

`MILVUS_VECTOR_DIMENSION` must exactly match the output dimension of `EMBEDDING_MODEL`.

After the first tenant Collection is created, treat the embedding model, vector dimension, metric, index configuration, search configuration, and Milvus field schema as immutable for V1. The application stores a configuration fingerprint with each tenant resource and refuses to provide a vector route when the current configuration is incompatible.

### Authorization secrets

```env
API_KEY_PEPPER=replace-with-a-long-random-secret
PLATFORM_API_KEY=replace-with-a-separate-platform-admin-key
```

- `API_KEY_PEPPER` is used to HMAC-hash tenant API-key secrets. Changing it invalidates existing V2 keys.
- `PLATFORM_API_KEY` protects `/v1/platform/*` control-plane endpoints and must not be distributed to tenant users.

### Model endpoints

Configure:

- `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`
- `RERANK_URL`, `RERANK_MODEL`, `RERANK_API_KEY`
- `QUERY_REWRITE_URL`, `QUERY_REWRITE_MODEL`, `QUERY_REWRITE_API_KEY`
- `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY`
- `OCR_URL`, `OCR_MODEL`, `OCR_API_KEY`

Retrieval defaults are controlled by:

- `DEFAULT_QUERY_REWRITE_ENABLED`
- `DEFAULT_VECTOR_SEARCH_ENABLED`
- `DEFAULT_FULL_TEXT_SEARCH_ENABLED`
- `DEFAULT_HYBRID_SEARCH_ENABLED`
- `DEFAULT_RERANK_ENABLED`
- `DEFAULT_AGENT_SEARCH_ENABLED`

## Local infrastructure

Start PostgreSQL, MinIO, and Milvus:

```bash
docker compose up -d
```

The MinIO console is available at `http://localhost:9001` with the credentials from `docker-compose.yml`.

## Database

The migration chain is:

```text
0001_initial
→ 0002_authorization_v2
→ 0003_tenant_vector_collections
```

The repository contains Alembic migration files but does not currently include a deployment-specific `alembic.ini`. Add the configuration for the target environment, then run:

```bash
alembic upgrade head
```

`0003_tenant_vector_collections` creates exactly one vector-resource row per tenant and enforces:

- unique `tenant_id`;
- unique logical Alias;
- unique physical Collection;
- fixed `schema_version = 1`.

## Create the first tenant

Tenant creation is a platform control-plane operation:

```http
POST /v1/platform/tenants
Authorization: Bearer <PLATFORM_API_KEY>
Content-Type: application/json
```

Example:

```bash
curl -X POST http://localhost:8000/v1/platform/tenants \
  -H "Authorization: Bearer $PLATFORM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme",
    "slug": "acme",
    "owner_email": "owner@example.com",
    "owner_display_name": "Acme Owner",
    "default_knowledge_base_name": "Default"
  }'
```

Provisioning performs:

1. Create the tenant in `provisioning` state.
2. Create the initial Owner and membership.
3. Create the default knowledge base and ACL when requested.
4. Insert the pending tenant vector resource.
5. Create and validate the tenant V1 physical Collection.
6. Create or validate the stable Alias.
7. Mark the vector resource `ready`.
8. Activate the tenant.
9. Issue the initial Owner API key.

The plaintext initial API key is returned exactly once.

If Milvus provisioning fails, the tenant remains non-active, the resource is marked `failed`, and no initial key is issued.

Inspect or retry provisioning with:

```text
GET  /v1/platform/tenants/{tenant_id}/vector-resource
POST /v1/platform/tenants/{tenant_id}/vector-resource/retry
```

## Runtime authentication and isolation

Protected tenant endpoints require:

```http
Authorization: Bearer <tenant-api-key>
```

The runtime flow is:

1. Resolve and verify the API key from PostgreSQL.
2. Load the trusted `tenant_id`, user, membership, permissions, key limits, and knowledge-base ACLs.
3. Load the single compatible `ready` vector resource for that `tenant_id`.
4. Put the tenant Alias and vector settings into `TenantContext`.
5. Validate access to the requested knowledge base.
6. Use the Alias for Milvus upsert, search, and delete.
7. Keep `tenant_id` and `knowledge_base_id` scalar filters on Milvus operations.

Clients never submit `tenant_id`, Collection names, model URLs, model names, infrastructure credentials, or platform secrets in business API bodies.

When no compatible ready vector resource exists, vector operations return `503 vector_store_unavailable`. The service does not fall back to a global Collection.

## Start the API

Development:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Production-style single process:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

OpenAPI is available at `http://localhost:8000/docs`.

## Main APIs

### Platform

- `POST /v1/platform/tenants`
- `GET /v1/platform/tenants/{tenant_id}/vector-resource`
- `POST /v1/platform/tenants/{tenant_id}/vector-resource/retry`

### Tenant management

- `POST /v1/users`
- `PATCH /v1/users/{user_id}/role`
- `PUT /v1/users/{user_id}/scope-grants`
- `DELETE /v1/users/{user_id}/scope-grants/{permission}`
- `POST /v1/api-keys`
- `POST /v1/users/{user_id}/api-keys`
- `DELETE /v1/api-keys/{api_key_id}`

### Knowledge bases

- `POST /v1/knowledge-bases`
- `PUT /v1/knowledge-bases/{knowledge_base_id}/members/{user_id}`

### Documents

- `POST /v1/documents/embed`
- `PATCH /v1/documents/{document_id}`
- `DELETE /v1/documents/{document_id}/purge`

### Retrieval

- `POST /v1/retrieval/search`

See `docs/authorization-v2-api.md` for permissions, key behavior, provisioning details, and tenant vector routing.

## Current V1 non-goals

The current release does not implement:

- a shared Collection;
- Collection data migration;
- multiple physical Collection versions;
- hot embedding-model upgrades;
- online vector-dimension upgrades;
- dual-write;
- Alias canary or gradual switching;
- Collection rollback;
- migration progress tables;
- migration management APIs.

These features are intentionally deferred because the project has not deployed PostgreSQL or Milvus and has no historical vector data to preserve.

Future upgrades are documented in `docs/vector-collection-v2-roadmap.md`. A future embedding-model upgrade must create a new physical Collection, regenerate vectors from canonical PostgreSQL chunk text, validate the new Collection, and only then switch the stable Alias.

## Validate

```bash
ruff check .
pytest -v
```
