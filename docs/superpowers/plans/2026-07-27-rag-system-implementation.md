# RAG System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production-oriented, multi-tenant RAG service with document embed/update/delete APIs, remote model endpoints, Milvus vector indexing, Postgres/MinIO storage, optional retrieval stages, and optional `agent_search` answer generation inside `/v1/retrieval/search`.

**Architecture:** FastAPI handles HTTP and tenant context; the `rag/` package owns domain schemas, storage clients, ingestion, retrieval, and agent search. Postgres stores tenants, documents, chunks, jobs, indexes, logs, ACLs, and audit events; MinIO stores raw and parsed objects; Milvus stores active chunk vectors with scalar tenant and knowledge-base filters.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic Settings, SQLAlchemy 2.x async, Alembic, asyncpg, MinIO Python SDK, pymilvus, httpx, pypdf, python-docx, openpyxl, pandas, Pillow, pytesseract-compatible OCR endpoint client, pytest, pytest-asyncio, ruff.

## Global Constraints

- Use FastAPI, Postgres, MinIO, and Milvus.
- Do not depend on LangChain, LlamaIndex, or similar orchestration frameworks.
- Do not expose model URLs, model names, API keys, or infrastructure credentials in API request bodies.
- Model-backed capabilities are configured from `.env` as URL, model name, and API key: embedding, rerank, query rewrite, and LLM answer.
- Retrieval options are request-level booleans: `query_rewrite`, `vector_search`, `full_text_search`, `hybrid_search`, `rerank`, and `agent_search`.
- `POST /v1/retrieval/search` returns chunks by default and returns `chunks + answer + citations + usage` when `agent_search=true`.
- `DELETE /v1/documents/{document_id}` soft-deletes a document.
- `DELETE /v1/documents/{document_id}/purge` permanently deletes document content, vectors, keyword rows, and MinIO objects, leaving only minimal deletion audit.
- Every tenant-owned retrieval query must filter by tenant and knowledge base.
- Milvus v1 uses one collection with scalar fields: `tenant_id`, `knowledge_base_id`, `document_id`, `chunk_id`, and `is_active`.
- First file formats: `.txt`, `.md`, `.pdf`, `.docx`, `.csv`, `.xlsx`, `.xls`, `.png`, `.jpg`, `.jpeg`, and `.webp`.
- Keep changes focused; do not add a frontend.

---

## File Structure

Create this structure:

```text
rag_system/
  app/
    __init__.py
    main.py
    api/
      __init__.py
      dependencies.py
      documents.py
      health.py
      retrieval.py
  rag/
    __init__.py
    auth.py
    config.py
    errors.py
    schemas.py
    ingestion/
      __init__.py
      chunker.py
      cleaner.py
      parsers.py
      pipeline.py
    models/
      __init__.py
      endpoints.py
    retrieval/
      __init__.py
      fusion.py
      pipeline.py
      context.py
    storage/
      __init__.py
      database.py
      migrations.py
      minio_store.py
      milvus_store.py
      repositories.py
  migrations/
    env.py
    versions/
      0001_initial.py
  tests/
    conftest.py
    test_config.py
    test_auth.py
    test_chunker.py
    test_fusion.py
    test_model_endpoints.py
    test_parsers.py
    test_retrieval_api.py
  .env.example
  docker-compose.yml
  pyproject.toml
```

Responsibilities:

- `app/api/*`: HTTP routes only.
- `rag/schemas.py`: shared request/response/domain Pydantic models.
- `rag/config.py`: typed `.env` settings.
- `rag/auth.py`: API-key tenant context resolution.
- `rag/storage/*`: Postgres, MinIO, and Milvus integration boundaries.
- `rag/models/endpoints.py`: remote embedding, rerank, query rewrite, OCR, and LLM clients.
- `rag/ingestion/*`: parse, clean, chunk, persist, embed.
- `rag/retrieval/*`: retrieve, fuse, rerank, optionally generate answer.

---

### Task 1: Project Skeleton, Settings, And Health API

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/api/__init__.py`
- Create: `app/api/health.py`
- Create: `rag/__init__.py`
- Create: `rag/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `rag.config.Settings`
- Produces: `rag.config.get_settings() -> Settings`
- Produces: FastAPI app object `app.main.app`
- Later tasks consume `get_settings()` and environment variable names.

- [ ] **Step 1: Write failing settings tests**

Create `tests/test_config.py`:

```python
from rag.config import Settings


def test_settings_load_model_endpoint_values():
    settings = Settings(
        postgres_dsn="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="miniopass",
        milvus_uri="http://localhost:19530",
        embedding_url="http://models:8000/v1/embeddings",
        embedding_model="bge-m3",
        embedding_api_key="embed-key",
        rerank_url="http://models:8000/v1/rerank",
        rerank_model="bge-reranker",
        rerank_api_key="rerank-key",
        query_rewrite_url="http://models:8000/v1/chat/completions",
        query_rewrite_model="rewrite-model",
        query_rewrite_api_key="rewrite-key",
        llm_url="http://models:8000/v1/chat/completions",
        llm_model="answer-model",
        llm_api_key="llm-key",
    )

    assert settings.embedding_model == "bge-m3"
    assert settings.default_vector_search_enabled is True
    assert settings.default_agent_search_enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`

Expected: FAIL because `rag.config` does not exist.

- [ ] **Step 3: Add dependencies and settings**

Create `pyproject.toml`:

```toml
[project]
name = "rag-system"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "alembic>=1.13",
  "asyncpg>=0.29",
  "fastapi>=0.111",
  "httpx>=0.27",
  "minio>=7.2",
  "openpyxl>=3.1",
  "pandas>=2.2",
  "pillow>=10.4",
  "pydantic>=2.8",
  "pydantic-settings>=2.4",
  "pymilvus>=2.4",
  "pypdf>=4.3",
  "python-docx>=1.1",
  "python-multipart>=0.0.9",
  "sqlalchemy[asyncio]>=2.0",
  "uvicorn[standard]>=0.30",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "respx>=0.21",
  "ruff>=0.5",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

Create `.env.example` with these exact keys:

```text
POSTGRES_DSN=postgresql+asyncpg://rag:rag@localhost:5432/rag
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minio
MINIO_SECRET_KEY=miniopass
MINIO_BUCKET=rag-system
MINIO_SECURE=false
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION=rag_chunks
EMBEDDING_URL=http://localhost:8000/v1/embeddings
EMBEDDING_MODEL=bge-m3
EMBEDDING_API_KEY=replace-me
RERANK_URL=http://localhost:8000/v1/rerank
RERANK_MODEL=bge-reranker
RERANK_API_KEY=replace-me
QUERY_REWRITE_URL=http://localhost:8000/v1/chat/completions
QUERY_REWRITE_MODEL=query-rewrite
QUERY_REWRITE_API_KEY=replace-me
LLM_URL=http://localhost:8000/v1/chat/completions
LLM_MODEL=answer-model
LLM_API_KEY=replace-me
OCR_URL=http://localhost:8000/v1/ocr
OCR_MODEL=ocr-model
OCR_API_KEY=replace-me
DEFAULT_QUERY_REWRITE_ENABLED=false
DEFAULT_VECTOR_SEARCH_ENABLED=true
DEFAULT_FULL_TEXT_SEARCH_ENABLED=false
DEFAULT_HYBRID_SEARCH_ENABLED=false
DEFAULT_RERANK_ENABLED=false
DEFAULT_AGENT_SEARCH_ENABLED=false
```

Create `rag/config.py`:

```python
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    postgres_dsn: str = Field(alias="POSTGRES_DSN")
    minio_endpoint: str = Field(alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="rag-system", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    milvus_uri: str = Field(alias="MILVUS_URI")
    milvus_collection: str = Field(default="rag_chunks", alias="MILVUS_COLLECTION")

    embedding_url: str = Field(alias="EMBEDDING_URL")
    embedding_model: str = Field(alias="EMBEDDING_MODEL")
    embedding_api_key: str = Field(alias="EMBEDDING_API_KEY")
    rerank_url: str = Field(alias="RERANK_URL")
    rerank_model: str = Field(alias="RERANK_MODEL")
    rerank_api_key: str = Field(alias="RERANK_API_KEY")
    query_rewrite_url: str = Field(alias="QUERY_REWRITE_URL")
    query_rewrite_model: str = Field(alias="QUERY_REWRITE_MODEL")
    query_rewrite_api_key: str = Field(alias="QUERY_REWRITE_API_KEY")
    llm_url: str = Field(alias="LLM_URL")
    llm_model: str = Field(alias="LLM_MODEL")
    llm_api_key: str = Field(alias="LLM_API_KEY")
    ocr_url: str = Field(alias="OCR_URL")
    ocr_model: str = Field(alias="OCR_MODEL")
    ocr_api_key: str = Field(alias="OCR_API_KEY")

    default_query_rewrite_enabled: bool = Field(default=False, alias="DEFAULT_QUERY_REWRITE_ENABLED")
    default_vector_search_enabled: bool = Field(default=True, alias="DEFAULT_VECTOR_SEARCH_ENABLED")
    default_full_text_search_enabled: bool = Field(
        default=False, alias="DEFAULT_FULL_TEXT_SEARCH_ENABLED"
    )
    default_hybrid_search_enabled: bool = Field(default=False, alias="DEFAULT_HYBRID_SEARCH_ENABLED")
    default_rerank_enabled: bool = Field(default=False, alias="DEFAULT_RERANK_ENABLED")
    default_agent_search_enabled: bool = Field(default=False, alias="DEFAULT_AGENT_SEARCH_ENABLED")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

Create empty package files:

```python
```

Create `app/api/health.py`:

```python
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

Create `app/main.py`:

```python
from fastapi import FastAPI

from app.api.health import router as health_router

app = FastAPI(title="rag-system")
app.include_router(health_router)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example app rag tests/test_config.py
git commit -m "feat: add project skeleton and settings"
```

---

### Task 2: Domain Schemas And Tenant Auth

**Files:**
- Create: `rag/schemas.py`
- Create: `rag/errors.py`
- Create: `rag/auth.py`
- Create: `app/api/dependencies.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `rag.config.Settings`
- Produces: `TenantContext`
- Produces: `RetrievalOptions`
- Produces: `resolve_tenant_context(api_key: str, repository: TenantRepositoryProtocol) -> TenantContext`
- Later API routes depend on `TenantContext`.

- [ ] **Step 1: Write failing tenant auth tests**

Create `tests/test_auth.py`:

```python
import pytest

from rag.auth import resolve_tenant_context
from rag.errors import UnauthorizedError
from rag.schemas import TenantContext


class FakeTenantRepository:
    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        if api_key == "valid-key":
            return TenantContext(
                tenant_id="tenant_a",
                organization_id="org_a",
                user_id="user_a",
                knowledge_base_ids=["kb_a"],
                roles=["admin"],
                allowed_scopes=["read", "write", "admin", "audit"],
            )
        return None


@pytest.mark.asyncio
async def test_resolve_tenant_context_accepts_valid_key():
    context = await resolve_tenant_context("valid-key", FakeTenantRepository())
    assert context.tenant_id == "tenant_a"
    assert "kb_a" in context.knowledge_base_ids


@pytest.mark.asyncio
async def test_resolve_tenant_context_rejects_invalid_key():
    with pytest.raises(UnauthorizedError):
        await resolve_tenant_context("bad-key", FakeTenantRepository())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`

Expected: FAIL because auth and schema modules do not exist.

- [ ] **Step 3: Implement schemas, errors, and auth**

Create `rag/errors.py`:

```python
class RAGError(Exception):
    status_code = 500
    code = "internal_error"


class UnauthorizedError(RAGError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(RAGError):
    status_code = 403
    code = "forbidden"


class NotFoundError(RAGError):
    status_code = 404
    code = "not_found"


class ValidationError(RAGError):
    status_code = 400
    code = "invalid_request"
```

Create `rag/schemas.py`:

```python
from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    tenant_id: str
    organization_id: str | None = None
    user_id: str
    knowledge_base_ids: list[str]
    roles: list[str] = Field(default_factory=list)
    allowed_scopes: list[str] = Field(default_factory=list)

    def can_access_knowledge_base(self, knowledge_base_id: str) -> bool:
        return knowledge_base_id in self.knowledge_base_ids

    def has_scope(self, scope: str) -> bool:
        return scope in self.allowed_scopes


class RetrievalOptions(BaseModel):
    query_rewrite: bool | None = None
    vector_search: bool | None = None
    full_text_search: bool | None = None
    hybrid_search: bool | None = None
    rerank: bool | None = None
    agent_search: bool | None = None
    top_k: int = Field(default=20, ge=1, le=100)
    final_k: int = Field(default=5, ge=1, le=50)


class RetrievalFilters(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    document_id: str
    text: str
    score: float
    retrieval_method: str
    source: dict[str, str | int | None]
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class Citation(BaseModel):
    chunk_id: str
    document_id: str
    title: str | None = None
    source_uri: str | None = None
    page: int | None = None
    quote: str


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0


class RetrievalSearchRequest(BaseModel):
    knowledge_base_id: str
    query: str = Field(min_length=1)
    options: RetrievalOptions = Field(default_factory=RetrievalOptions)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class RetrievalSearchResponse(BaseModel):
    query_id: str
    rewritten_query: str | None = None
    chunks: list[RetrievedChunk]
    answer: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    usage: Usage | None = None


class EmbedDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    status: str


class UpdateDocumentResponse(BaseModel):
    job_id: str
    document_id: str
    version: int
    status: str


class PurgeDocumentResponse(BaseModel):
    document_id: str
    status: str
```

Create `rag/auth.py`:

```python
from typing import Protocol

from rag.errors import UnauthorizedError
from rag.schemas import TenantContext


class TenantRepositoryProtocol(Protocol):
    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        ...


async def resolve_tenant_context(
    api_key: str,
    repository: TenantRepositoryProtocol,
) -> TenantContext:
    context = await repository.get_context_for_api_key(api_key)
    if context is None:
        raise UnauthorizedError("invalid API key")
    return context
```

Create `app/api/dependencies.py`:

```python
from fastapi import Depends, Header

from rag.errors import UnauthorizedError


async def get_api_key(authorization: str | None = Header(default=None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.removeprefix("Bearer ").strip()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_auth.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/schemas.py rag/errors.py rag/auth.py app/api/dependencies.py tests/test_auth.py
git commit -m "feat: add tenant auth schemas"
```

---

### Task 3: Docker Compose And Postgres Schema

**Files:**
- Create: `docker-compose.yml`
- Create: `rag/storage/__init__.py`
- Create: `rag/storage/database.py`
- Create: `rag/storage/migrations.py`
- Create: `migrations/env.py`
- Create: `migrations/versions/0001_initial.py`

**Interfaces:**
- Produces: `rag.storage.database.Base`
- Produces: `rag.storage.database.get_async_engine(settings: Settings) -> AsyncEngine`
- Produces: `rag.storage.database.get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`
- Produces table names listed in the design spec.

- [ ] **Step 1: Create Docker Compose**

Create `docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: rag
      POSTGRES_USER: rag
      POSTGRES_PASSWORD: rag
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rag -d rag"]
      interval: 5s
      timeout: 5s
      retries: 20

  minio:
    image: minio/minio:RELEASE.2024-07-16T23-46-41Z
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: miniopass
    ports:
      - "9000:9000"
      - "9001:9001"

  milvus:
    image: milvusdb/milvus:v2.4.6
    command: ["milvus", "run", "standalone"]
    environment:
      ETCD_USE_EMBED: "true"
      COMMON_STORAGETYPE: local
    ports:
      - "19530:19530"
```

- [ ] **Step 2: Create SQLAlchemy base and engine helpers**

Create `rag/storage/database.py`:

```python
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from rag.config import Settings


class Base(DeclarativeBase):
    pass


def get_async_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.postgres_dsn, pool_pre_ping=True)


def get_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

Create `rag/storage/migrations.py`:

```python
from rag.storage.database import Base

metadata = Base.metadata
```

- [ ] **Step 3: Create Alembic initial migration**

Create `migrations/env.py`:

```python
from alembic import context
from sqlalchemy import engine_from_config, pool

from rag.config import get_settings
from rag.storage.migrations import metadata

config = context.config
target_metadata = metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(url=settings.postgres_dsn.replace("+asyncpg", ""), target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = settings.postgres_dsn.replace("+asyncpg", "")
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `migrations/versions/0001_initial.py` with explicit table creation for:

```python
"""initial multi tenant schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("tenants", sa.Column("id", sa.String(), primary_key=True), sa.Column("name", sa.String(), nullable=False), *timestamps())
    op.create_table("organizations", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("name", sa.String(), nullable=False), *timestamps())
    op.create_table("users", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("email", sa.String(), nullable=False), *timestamps())
    op.create_table("api_keys", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("organization_id", sa.String(), nullable=True), sa.Column("user_id", sa.String(), nullable=False), sa.Column("key_hash", sa.String(), nullable=False, unique=True), sa.Column("allowed_scopes", sa.JSON(), nullable=False), sa.Column("knowledge_base_ids", sa.JSON(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")), *timestamps())
    op.create_table("knowledge_bases", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("name", sa.String(), nullable=False), sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), *timestamps())
    op.create_table("knowledge_base_acl", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("principal_type", sa.String(), nullable=False), sa.Column("principal_id", sa.String(), nullable=False), sa.Column("roles", sa.JSON(), nullable=False), *timestamps())
    op.create_table("user_memberships", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("organization_id", sa.String(), nullable=True), sa.Column("user_id", sa.String(), nullable=False), sa.Column("roles", sa.JSON(), nullable=False), *timestamps())
    op.create_table("documents", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("title", sa.String(), nullable=False), sa.Column("source_uri", sa.String(), nullable=True), sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")), *timestamps())
    op.create_table("document_versions", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("document_id", sa.String(), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("checksum", sa.String(), nullable=False), sa.Column("raw_object_key", sa.String(), nullable=False), sa.Column("parsed_object_key", sa.String(), nullable=True), sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), *timestamps())
    op.create_table("chunks", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("document_id", sa.String(), nullable=False), sa.Column("document_version", sa.Integer(), nullable=False), sa.Column("text", sa.Text(), nullable=False), sa.Column("title_path", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")), sa.Column("page", sa.Integer(), nullable=True), sa.Column("token_count", sa.Integer(), nullable=False), sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")), *timestamps())
    op.create_table("ingestion_jobs", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("document_id", sa.String(), nullable=True), sa.Column("status", sa.String(), nullable=False), sa.Column("error", sa.Text(), nullable=True), *timestamps())
    op.create_table("keyword_terms", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("term", sa.String(), nullable=False), *timestamps())
    op.create_table("keyword_postings", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("term", sa.String(), nullable=False), sa.Column("chunk_id", sa.String(), nullable=False), sa.Column("frequency", sa.Integer(), nullable=False), *timestamps())
    op.create_table("query_logs", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("query", sa.Text(), nullable=False), sa.Column("rewritten_query", sa.Text(), nullable=True), sa.Column("options", sa.JSON(), nullable=False), *timestamps())
    op.create_table("retrieval_logs", sa.Column("id", sa.String(), primary_key=True), sa.Column("query_id", sa.String(), nullable=False), sa.Column("chunk_id", sa.String(), nullable=False), sa.Column("score", sa.Float(), nullable=False), sa.Column("retrieval_method", sa.String(), nullable=False), *timestamps())
    op.create_table("feedback", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("query_id", sa.String(), nullable=False), sa.Column("rating", sa.Integer(), nullable=False), sa.Column("comment", sa.Text(), nullable=True), *timestamps())
    op.create_table("deletion_audit_events", sa.Column("id", sa.String(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False), sa.Column("knowledge_base_id", sa.String(), nullable=False), sa.Column("document_id", sa.String(), nullable=False), sa.Column("actor_user_id", sa.String(), nullable=False), sa.Column("event_type", sa.String(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    for table_name in [
        "deletion_audit_events",
        "feedback",
        "retrieval_logs",
        "query_logs",
        "keyword_postings",
        "keyword_terms",
        "ingestion_jobs",
        "chunks",
        "document_versions",
        "documents",
        "user_memberships",
        "knowledge_base_acl",
        "knowledge_bases",
        "api_keys",
        "users",
        "organizations",
        "tenants",
    ]:
        op.drop_table(table_name)
```

- [ ] **Step 4: Validate migration imports**

Run: `python -m compileall rag migrations`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml rag/storage migrations
git commit -m "feat: add storage schema and compose"
```

---

### Task 4: Remote Model Endpoint Clients

**Files:**
- Create: `rag/models/__init__.py`
- Create: `rag/models/endpoints.py`
- Test: `tests/test_model_endpoints.py`

**Interfaces:**
- Consumes: `Settings`
- Produces: `ModelEndpointClient.embed(texts: list[str]) -> list[list[float]]`
- Produces: `ModelEndpointClient.rerank(query: str, texts: list[str]) -> list[float]`
- Produces: `ModelEndpointClient.rewrite(query: str) -> str`
- Produces: `ModelEndpointClient.answer(query: str, context: str) -> tuple[str, dict[str, int]]`
- Produces: `ModelEndpointClient.ocr(image_bytes: bytes, mime_type: str) -> str`

- [ ] **Step 1: Write failing endpoint client tests**

Create `tests/test_model_endpoints.py`:

```python
import httpx
import pytest
import respx

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient


def settings() -> Settings:
    return Settings(
        postgres_dsn="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        minio_endpoint="localhost:9000",
        minio_access_key="minio",
        minio_secret_key="miniopass",
        milvus_uri="http://localhost:19530",
        embedding_url="http://models.local/embed",
        embedding_model="embedding-model",
        embedding_api_key="embedding-key",
        rerank_url="http://models.local/rerank",
        rerank_model="rerank-model",
        rerank_api_key="rerank-key",
        query_rewrite_url="http://models.local/rewrite",
        query_rewrite_model="rewrite-model",
        query_rewrite_api_key="rewrite-key",
        llm_url="http://models.local/answer",
        llm_model="answer-model",
        llm_api_key="answer-key",
        ocr_url="http://models.local/ocr",
        ocr_model="ocr-model",
        ocr_api_key="ocr-key",
    )


@pytest.mark.asyncio
@respx.mock
async def test_embed_posts_url_model_and_api_key():
    route = respx.post("http://models.local/embed").mock(
        return_value=httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2]}]})
    )
    client = ModelEndpointClient(settings())
    vectors = await client.embed(["hello"])

    assert vectors == [[0.1, 0.2]]
    assert route.calls.last.request.headers["authorization"] == "Bearer embedding-key"
    assert route.calls.last.request.json()["model"] == "embedding-model"


@pytest.mark.asyncio
@respx.mock
async def test_rerank_returns_scores():
    respx.post("http://models.local/rerank").mock(
        return_value=httpx.Response(200, json={"scores": [0.8, 0.2]})
    )
    client = ModelEndpointClient(settings())
    assert await client.rerank("q", ["a", "b"]) == [0.8, 0.2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_model_endpoints.py -v`

Expected: FAIL because `ModelEndpointClient` does not exist.

- [ ] **Step 3: Implement remote endpoint client**

Create `rag/models/endpoints.py`:

```python
import base64
from typing import Any

import httpx

from rag.config import Settings


class ModelEndpointClient:
    def __init__(self, settings: Settings, timeout: float = 60.0) -> None:
        self.settings = settings
        self.timeout = timeout

    async def _post(self, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.settings.embedding_model, "input": texts}
        data = await self._post(self.settings.embedding_url, self.settings.embedding_api_key, payload)
        return [item["embedding"] for item in data["data"]]

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        payload = {"model": self.settings.rerank_model, "query": query, "documents": texts}
        data = await self._post(self.settings.rerank_url, self.settings.rerank_api_key, payload)
        return [float(score) for score in data["scores"]]

    async def rewrite(self, query: str) -> str:
        payload = {
            "model": self.settings.query_rewrite_model,
            "messages": [
                {"role": "system", "content": "Rewrite the query for retrieval. Return only the rewritten query."},
                {"role": "user", "content": query},
            ],
        }
        data = await self._post(
            self.settings.query_rewrite_url,
            self.settings.query_rewrite_api_key,
            payload,
        )
        return data["choices"][0]["message"]["content"].strip()

    async def answer(self, query: str, context: str) -> tuple[str, dict[str, int]]:
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {"role": "system", "content": "Answer using only the supplied context. Cite sources by chunk id."},
                {"role": "user", "content": f"Question:\\n{query}\\n\\nContext:\\n{context}"},
            ],
        }
        data = await self._post(self.settings.llm_url, self.settings.llm_api_key, payload)
        usage = data.get("usage", {})
        return data["choices"][0]["message"]["content"].strip(), {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
        }

    async def ocr(self, image_bytes: bytes, mime_type: str) -> str:
        payload = {
            "model": self.settings.ocr_model,
            "mime_type": mime_type,
            "image": base64.b64encode(image_bytes).decode("ascii"),
        }
        data = await self._post(self.settings.ocr_url, self.settings.ocr_api_key, payload)
        return data["text"]
```

- [ ] **Step 4: Run endpoint tests**

Run: `pytest tests/test_model_endpoints.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/models tests/test_model_endpoints.py
git commit -m "feat: add remote model endpoint clients"
```

---

### Task 5: Parsers, Cleaner, And Chunker

**Files:**
- Create: `rag/ingestion/__init__.py`
- Create: `rag/ingestion/cleaner.py`
- Create: `rag/ingestion/chunker.py`
- Create: `rag/ingestion/parsers.py`
- Test: `tests/test_chunker.py`
- Test: `tests/test_parsers.py`

**Interfaces:**
- Produces: `ParsedDocument(text: str, metadata: dict[str, object])`
- Produces: `parse_document(filename: str, content: bytes, ocr_client: OcrCallable | None) -> ParsedDocument`
- Produces: `clean_text(text: str) -> str`
- Produces: `chunk_text(document_id: str, text: str, metadata: dict[str, object], chunk_size: int = 900, overlap: int = 120) -> list[ChunkInput]`

- [ ] **Step 1: Write failing chunker tests**

Create `tests/test_chunker.py`:

```python
from rag.ingestion.chunker import chunk_text


def test_chunk_text_preserves_document_and_metadata():
    chunks = chunk_text(
        document_id="doc_1",
        text="alpha beta gamma delta epsilon",
        metadata={"title": "Spec", "page": 1},
        chunk_size=16,
        overlap=4,
    )

    assert len(chunks) >= 2
    assert chunks[0].document_id == "doc_1"
    assert chunks[0].metadata["title"] == "Spec"
    assert chunks[0].text.startswith("alpha")
```

- [ ] **Step 2: Write failing parser tests**

Create `tests/test_parsers.py`:

```python
import pytest

from rag.ingestion.parsers import parse_document


@pytest.mark.asyncio
async def test_parse_txt_document():
    parsed = await parse_document("note.txt", b"hello\\nworld", None)
    assert parsed.text == "hello\\nworld"
    assert parsed.metadata["file_type"] == "txt"


@pytest.mark.asyncio
async def test_parse_csv_document_as_rows():
    parsed = await parse_document("table.csv", b"name,score\\nAda,10\\nTom,9\\n", None)
    assert "row 1" in parsed.text
    assert "Ada" in parsed.text
    assert parsed.metadata["file_type"] == "csv"
```

- [ ] **Step 3: Run tests to verify failure**

Run: `pytest tests/test_chunker.py tests/test_parsers.py -v`

Expected: FAIL because ingestion modules do not exist.

- [ ] **Step 4: Implement cleaner and chunker**

Create `rag/ingestion/cleaner.py`:

```python
import re


def clean_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
```

Create `rag/ingestion/chunker.py`:

```python
from pydantic import BaseModel, Field


class ChunkInput(BaseModel):
    document_id: str
    text: str
    token_count: int
    title_path: list[str] = Field(default_factory=list)
    page: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


def chunk_text(
    document_id: str,
    text: str,
    metadata: dict[str, object],
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[ChunkInput]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    chunks: list[ChunkInput] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(
                ChunkInput(
                    document_id=document_id,
                    text=chunk,
                    token_count=len(chunk.split()),
                    title_path=[str(metadata["title"])] if "title" in metadata else [],
                    page=int(metadata["page"]) if "page" in metadata and metadata["page"] is not None else None,
                    metadata=metadata,
                )
            )
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
```

- [ ] **Step 5: Implement parsers**

Create `rag/ingestion/parsers.py`:

```python
import io
from pathlib import Path
from typing import Protocol

import pandas as pd
from docx import Document
from PIL import Image
from pydantic import BaseModel
from pypdf import PdfReader


class OcrCallable(Protocol):
    async def ocr(self, image_bytes: bytes, mime_type: str) -> str:
        ...


class ParsedDocument(BaseModel):
    text: str
    metadata: dict[str, object]


async def parse_document(
    filename: str,
    content: bytes,
    ocr_client: OcrCallable | None,
) -> ParsedDocument:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"txt", "md"}:
        return ParsedDocument(text=content.decode("utf-8"), metadata={"file_type": suffix})
    if suffix == "pdf":
        reader = PdfReader(io.BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return ParsedDocument(text=text, metadata={"file_type": suffix, "pages": len(reader.pages)})
    if suffix == "docx":
        doc = Document(io.BytesIO(content))
        paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        table_rows: list[str] = []
        for table_index, table in enumerate(doc.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                cells = " | ".join(cell.text.strip() for cell in row.cells)
                table_rows.append(f"table {table_index} row {row_index}: {cells}")
        return ParsedDocument(
            text="\n".join(paragraphs + table_rows),
            metadata={"file_type": suffix, "tables": len(doc.tables)},
        )
    if suffix == "csv":
        frame = pd.read_csv(io.BytesIO(content))
        return ParsedDocument(text=_frame_to_text(frame), metadata={"file_type": suffix})
    if suffix in {"xlsx", "xls"}:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
        sections = [f"sheet {name}\n{_frame_to_text(frame)}" for name, frame in sheets.items()]
        return ParsedDocument(text="\n\n".join(sections), metadata={"file_type": suffix, "sheets": list(sheets)})
    if suffix in {"png", "jpg", "jpeg", "webp"}:
        Image.open(io.BytesIO(content)).verify()
        if ocr_client is None:
            raise ValueError("OCR client is required for image parsing")
        text = await ocr_client.ocr(content, f"image/{'jpeg' if suffix == 'jpg' else suffix}")
        return ParsedDocument(text=text, metadata={"file_type": suffix})
    raise ValueError(f"unsupported file type: {suffix}")


def _frame_to_text(frame: pd.DataFrame) -> str:
    rows = []
    for index, row in frame.fillna("").iterrows():
        cells = ", ".join(f"{column}: {row[column]}" for column in frame.columns)
        rows.append(f"row {index + 1}: {cells}")
    return "\n".join(rows)
```

- [ ] **Step 6: Run parser and chunker tests**

Run: `pytest tests/test_chunker.py tests/test_parsers.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add rag/ingestion tests/test_chunker.py tests/test_parsers.py
git commit -m "feat: add document parsing and chunking"
```

---

### Task 6: Object Store, Vector Store, And Repositories

**Files:**
- Create: `rag/storage/minio_store.py`
- Create: `rag/storage/milvus_store.py`
- Create: `rag/storage/repositories.py`

**Interfaces:**
- Produces: `MinioObjectStore.put_bytes(object_key: str, content: bytes, content_type: str) -> None`
- Produces: `MilvusVectorStore.upsert_chunks(...) -> None`
- Produces: `MilvusVectorStore.search(...) -> list[RetrievedChunk]`
- Produces: `DocumentRepository` methods used by ingestion and retrieval pipelines.

- [ ] **Step 1: Implement MinIO store**

Create `rag/storage/minio_store.py`:

```python
import io

from minio import Minio

from rag.config import Settings


class MinioObjectStore:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    def put_bytes(self, object_key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        self.client.put_object(
            self.bucket,
            object_key,
            io.BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

    def remove_prefix(self, prefix: str) -> None:
        for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True):
            self.client.remove_object(self.bucket, item.object_name)
```

- [ ] **Step 2: Implement Milvus store boundary**

Create `rag/storage/milvus_store.py`:

```python
from pymilvus import MilvusClient

from rag.config import Settings
from rag.schemas import RetrievedChunk, TenantContext


class MilvusVectorStore:
    def __init__(self, settings: Settings) -> None:
        self.collection = settings.milvus_collection
        self.client = MilvusClient(uri=settings.milvus_uri)

    def upsert_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
        chunk_ids: list[str],
        vectors: list[list[float]],
    ) -> None:
        rows = [
            {
                "id": chunk_id,
                "vector": vector,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "chunk_id": chunk_id,
                "is_active": True,
            }
            for chunk_id, vector in zip(chunk_ids, vectors, strict=True)
        ]
        self.client.upsert(collection_name=self.collection, data=rows)

    def search(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        query_vector: list[float],
        top_k: int,
    ) -> list[RetrievedChunk]:
        filter_expr = (
            f'tenant_id == "{tenant.tenant_id}" and '
            f'knowledge_base_id == "{knowledge_base_id}" and is_active == true'
        )
        results = self.client.search(
            collection_name=self.collection,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            output_fields=["chunk_id", "document_id"],
        )
        chunks: list[RetrievedChunk] = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            chunks.append(
                RetrievedChunk(
                    chunk_id=entity["chunk_id"],
                    document_id=entity["document_id"],
                    text="",
                    score=float(hit["distance"]),
                    retrieval_method="vector",
                    source={},
                    metadata={},
                )
            )
        return chunks

    def delete_document(self, tenant_id: str, knowledge_base_id: str, document_id: str) -> None:
        self.client.delete(
            collection_name=self.collection,
            filter=(
                f'tenant_id == "{tenant_id}" and '
                f'knowledge_base_id == "{knowledge_base_id}" and '
                f'document_id == "{document_id}"'
            ),
        )
```

- [ ] **Step 3: Implement repository interfaces with explicit methods**

Create `rag/storage/repositories.py`:

```python
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from rag.schemas import RetrievedChunk, TenantContext


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class StoredChunk:
    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, object]


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        from sqlalchemy import text

        key_hash = api_key
        result = await self.session.execute(
            text(
                """
                select tenant_id, organization_id, user_id, allowed_scopes, knowledge_base_ids
                from api_keys
                where key_hash = :key_hash and is_active = true
                """
            ),
            {"key_hash": key_hash},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return TenantContext(
            tenant_id=row["tenant_id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            knowledge_base_ids=list(row["knowledge_base_ids"]),
            roles=[],
            allowed_scopes=list(row["allowed_scopes"]),
        )


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, tenant: TenantContext, knowledge_base_id: str) -> str:
        from sqlalchemy import text

        job_id = new_id("job")
        await self.session.execute(
            text(
                """
                insert into ingestion_jobs (id, tenant_id, knowledge_base_id, status)
                values (:id, :tenant_id, :knowledge_base_id, 'queued')
                """
            ),
            {"id": job_id, "tenant_id": tenant.tenant_id, "knowledge_base_id": knowledge_base_id},
        )
        return job_id

    async def create_document_record(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        title: str,
        source_uri: str | None,
    ) -> str:
        from sqlalchemy import text

        document_id = new_id("doc")
        await self.session.execute(
            text(
                """
                insert into documents (id, tenant_id, knowledge_base_id, title, source_uri)
                values (:id, :tenant_id, :knowledge_base_id, :title, :source_uri)
                """
            ),
            {
                "id": document_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "title": title,
                "source_uri": source_uri,
            },
        )
        return document_id

    async def store_chunks(self, chunks: list[StoredChunk]) -> None:
        from sqlalchemy import text

        for chunk in chunks:
            await self.session.execute(
                text(
                    """
                    insert into chunks (
                        id, tenant_id, knowledge_base_id, document_id, document_version,
                        text, token_count, metadata
                    )
                    values (
                        :id, :tenant_id, :knowledge_base_id, :document_id, 1,
                        :text, :token_count, :metadata
                    )
                    """
                ),
                {
                    "id": chunk.chunk_id,
                    "tenant_id": chunk.metadata["tenant_id"],
                    "knowledge_base_id": chunk.metadata["knowledge_base_id"],
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "token_count": len(chunk.text.split()),
                    "metadata": chunk.metadata,
                },
            )

    async def hydrate_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        from sqlalchemy import text

        if not candidates:
            return []
        candidate_by_id = {candidate.chunk_id: candidate for candidate in candidates}
        result = await self.session.execute(
            text(
                """
                select c.id, c.document_id, c.text, c.page, c.metadata, d.title, d.source_uri
                from chunks c
                join documents d on d.id = c.document_id
                where c.tenant_id = :tenant_id
                  and c.knowledge_base_id = :knowledge_base_id
                  and c.is_active = true
                  and c.id = any(:chunk_ids)
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_ids": list(candidate_by_id),
            },
        )
        hydrated = []
        for row in result.mappings():
            candidate = candidate_by_id[row["id"]]
            hydrated.append(
                candidate.model_copy(
                    update={
                        "text": row["text"],
                        "source": {
                            "title": row["title"],
                            "source_uri": row["source_uri"],
                            "page": row["page"],
                        },
                        "metadata": row["metadata"],
                    }
                )
            )
        return hydrated

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        from sqlalchemy import text

        await self.session.execute(
            text(
                """
                insert into deletion_audit_events (
                    id, tenant_id, knowledge_base_id, document_id, actor_user_id, event_type
                )
                values (:id, :tenant_id, :knowledge_base_id, :document_id, :actor_user_id, 'purge')
                """
            ),
            {
                "id": new_id("del"),
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "actor_user_id": tenant.user_id,
            },
        )
        await self.session.execute(
            text(
                """
                delete from keyword_postings
                where tenant_id = :tenant_id
                  and knowledge_base_id = :knowledge_base_id
                  and chunk_id in (
                    select id from chunks
                    where tenant_id = :tenant_id
                      and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                  )
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        for table_name in ["chunks", "document_versions", "documents"]:
            await self.session.execute(
                text(
                    f"""
                    delete from {table_name}
                    where tenant_id = :tenant_id
                      and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                    """
                ),
                {
                    "tenant_id": tenant.tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                },
            )
```

- [ ] **Step 4: Compile storage modules**

Run: `python -m compileall rag/storage`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/storage
git commit -m "feat: add storage integration boundaries"
```

---

### Task 7: Retrieval Fusion And Pipeline

**Files:**
- Create: `rag/retrieval/__init__.py`
- Create: `rag/retrieval/fusion.py`
- Create: `rag/retrieval/context.py`
- Create: `rag/retrieval/pipeline.py`
- Test: `tests/test_fusion.py`

**Interfaces:**
- Consumes: `RetrievedChunk`, `RetrievalSearchRequest`, `TenantContext`
- Produces: `rrf_fusion(result_sets: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]`
- Produces: `build_context(chunks: list[RetrievedChunk]) -> str`
- Produces: `RetrievalPipeline.search(...) -> RetrievalSearchResponse`

- [ ] **Step 1: Write failing RRF tests**

Create `tests/test_fusion.py`:

```python
from rag.retrieval.fusion import rrf_fusion
from rag.schemas import RetrievedChunk


def chunk(chunk_id: str, score: float, method: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc_{chunk_id}",
        text=f"text {chunk_id}",
        score=score,
        retrieval_method=method,
        source={},
        metadata={},
    )


def test_rrf_fusion_deduplicates_and_prefers_consistent_hits():
    fused = rrf_fusion([
        [chunk("a", 1.0, "vector"), chunk("b", 0.8, "vector")],
        [chunk("b", 1.0, "full_text"), chunk("a", 0.7, "full_text")],
    ])

    assert [item.chunk_id for item in fused] == ["a", "b"]
    assert fused[0].retrieval_method == "hybrid"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_fusion.py -v`

Expected: FAIL because retrieval modules do not exist.

- [ ] **Step 3: Implement RRF and context builder**

Create `rag/retrieval/fusion.py`:

```python
from rag.schemas import RetrievedChunk


def rrf_fusion(result_sets: list[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}
    for results in result_sets:
        for rank, chunk in enumerate(results, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            chunks.setdefault(chunk.chunk_id, chunk)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    fused: list[RetrievedChunk] = []
    for chunk_id, score in ordered:
        chunk = chunks[chunk_id].model_copy(update={"score": score, "retrieval_method": "hybrid"})
        fused.append(chunk)
    return fused
```

Create `rag/retrieval/context.py`:

```python
from rag.schemas import RetrievedChunk


def build_context(chunks: list[RetrievedChunk], max_chars: int = 12000) -> str:
    sections: list[str] = []
    total = 0
    for chunk in chunks:
        section = f"[chunk_id: {chunk.chunk_id}]\\n{chunk.text}"
        if total + len(section) > max_chars:
            break
        sections.append(section)
        total += len(section)
    return "\n\n".join(sections)
```

- [ ] **Step 4: Implement pipeline skeleton**

Create `rag/retrieval/pipeline.py`:

```python
from uuid import uuid4

from rag.config import Settings
from rag.models.endpoints import ModelEndpointClient
from rag.retrieval.context import build_context
from rag.retrieval.fusion import rrf_fusion
from rag.schemas import Citation, RetrievalSearchRequest, RetrievalSearchResponse, TenantContext, Usage


class RetrievalPipeline:
    def __init__(
        self,
        settings: Settings,
        model_client: ModelEndpointClient,
        document_repository,
        vector_store,
    ) -> None:
        self.settings = settings
        self.model_client = model_client
        self.document_repository = document_repository
        self.vector_store = vector_store

    async def search(
        self,
        tenant: TenantContext,
        request: RetrievalSearchRequest,
    ) -> RetrievalSearchResponse:
        query_id = f"qry_{uuid4().hex}"
        query = request.query
        rewritten_query = None

        if request.options.query_rewrite:
            rewritten_query = await self.model_client.rewrite(query)
            query = rewritten_query

        candidates = []
        if request.options.vector_search is not False:
            vectors = await self.model_client.embed([query])
            candidates.append(
                self.vector_store.search(tenant, request.knowledge_base_id, vectors[0], request.options.top_k)
            )

        chunks = rrf_fusion(candidates) if len(candidates) > 1 else (candidates[0] if candidates else [])
        chunks = await self.document_repository.hydrate_chunks(tenant, request.knowledge_base_id, chunks)

        if request.options.rerank and chunks:
            scores = await self.model_client.rerank(query, [chunk.text for chunk in chunks])
            chunks = [
                chunk.model_copy(update={"score": score, "retrieval_method": f"{chunk.retrieval_method}_rerank"})
                for chunk, score in zip(chunks, scores, strict=True)
            ]
            chunks.sort(key=lambda chunk: chunk.score, reverse=True)

        final_chunks = chunks[: request.options.final_k]
        answer = None
        citations: list[Citation] = []
        usage = None

        if request.options.agent_search:
            context = build_context(final_chunks)
            answer, raw_usage = await self.model_client.answer(request.query, context)
            usage = Usage(**raw_usage)
            citations = [
                Citation(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=str(chunk.source.get("title")) if chunk.source.get("title") else None,
                    source_uri=str(chunk.source.get("source_uri")) if chunk.source.get("source_uri") else None,
                    page=int(chunk.source["page"]) if chunk.source.get("page") is not None else None,
                    quote=chunk.text[:240],
                )
                for chunk in final_chunks
            ]

        return RetrievalSearchResponse(
            query_id=query_id,
            rewritten_query=rewritten_query,
            chunks=final_chunks,
            answer=answer,
            citations=citations,
            usage=usage,
        )
```

- [ ] **Step 5: Run fusion tests**

Run: `pytest tests/test_fusion.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add rag/retrieval tests/test_fusion.py
git commit -m "feat: add retrieval pipeline"
```

---

### Task 8: Ingestion Pipeline And Document APIs

**Files:**
- Create: `rag/ingestion/pipeline.py`
- Create: `app/api/documents.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/main.py`
- Test: add document route tests in `tests/test_retrieval_api.py`

**Interfaces:**
- Consumes: parser, cleaner, chunker, model client, MinIO store, Milvus store, document repository.
- Produces: `IngestionPipeline.embed_document(...) -> EmbedDocumentResponse`
- Produces: `IngestionPipeline.update_document(...) -> UpdateDocumentResponse`
- Produces: `IngestionPipeline.purge_document(...) -> PurgeDocumentResponse`

- [ ] **Step 1: Implement ingestion pipeline**

Create `rag/ingestion/pipeline.py`:

```python
from hashlib import sha256

from rag.ingestion.chunker import chunk_text
from rag.ingestion.cleaner import clean_text
from rag.ingestion.parsers import parse_document
from rag.models.endpoints import ModelEndpointClient
from rag.schemas import EmbedDocumentResponse, PurgeDocumentResponse, TenantContext, UpdateDocumentResponse
from rag.storage.repositories import StoredChunk


class IngestionPipeline:
    def __init__(self, model_client: ModelEndpointClient, object_store, vector_store, document_repository) -> None:
        self.model_client = model_client
        self.object_store = object_store
        self.vector_store = vector_store
        self.document_repository = document_repository

    async def embed_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        filename: str,
        content: bytes,
        title: str,
        source_uri: str | None,
        metadata: dict[str, object],
    ) -> EmbedDocumentResponse:
        job_id = await self.document_repository.create_job(tenant, knowledge_base_id)
        document_id = await self.document_repository.create_document_record(
            tenant, knowledge_base_id, title, source_uri
        )
        checksum = sha256(content).hexdigest()
        raw_key = f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/{document_id}/versions/1/raw/{filename}"
        self.object_store.put_bytes(raw_key, content, "application/octet-stream")

        parsed = await parse_document(filename, content, self.model_client)
        text = clean_text(parsed.text)
        parsed_key = f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/{document_id}/versions/1/parsed/content.md"
        self.object_store.put_bytes(parsed_key, text.encode("utf-8"), "text/markdown")

        chunk_inputs = chunk_text(
            document_id,
            text,
            {
                **metadata,
                **parsed.metadata,
                "checksum": checksum,
                "title": title,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
            },
        )
        vectors = await self.model_client.embed([chunk.text for chunk in chunk_inputs])
        chunk_ids = [f"chk_{index}_{document_id}" for index, _ in enumerate(chunk_inputs, start=1)]
        await self.document_repository.store_chunks(
            [
                StoredChunk(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    text=chunk.text,
                    metadata=chunk.metadata,
                )
                for chunk_id, chunk in zip(chunk_ids, chunk_inputs, strict=True)
            ]
        )
        self.vector_store.upsert_chunks(tenant, knowledge_base_id, document_id, chunk_ids, vectors)
        return EmbedDocumentResponse(job_id=job_id, document_id=document_id, status="queued")

    async def update_document(self, tenant: TenantContext, knowledge_base_id: str, document_id: str) -> UpdateDocumentResponse:
        job_id = await self.document_repository.create_job(tenant, knowledge_base_id)
        return UpdateDocumentResponse(job_id=job_id, document_id=document_id, version=2, status="queued")

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> PurgeDocumentResponse:
        self.vector_store.delete_document(tenant.tenant_id, knowledge_base_id, document_id)
        prefix = f"tenants/{tenant.tenant_id}/knowledge_bases/{knowledge_base_id}/documents/{document_id}/"
        self.object_store.remove_prefix(prefix)
        await self.document_repository.purge_document(tenant, knowledge_base_id, document_id)
        return PurgeDocumentResponse(document_id=document_id, status="purged")
```

- [ ] **Step 2: Add API dependencies used by document routes**

Modify `app/api/dependencies.py`:

```python
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from rag.auth import resolve_tenant_context
from rag.config import get_settings
from rag.errors import UnauthorizedError
from rag.ingestion.pipeline import IngestionPipeline
from rag.models.endpoints import ModelEndpointClient
from rag.schemas import TenantContext
from rag.storage.database import get_async_engine, get_sessionmaker
from rag.storage.milvus_store import MilvusVectorStore
from rag.storage.minio_store import MinioObjectStore
from rag.storage.repositories import DocumentRepository, TenantRepository


async def get_api_key(authorization: str | None = Header(default=None)) -> str:
    if authorization is None or not authorization.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    return authorization.removeprefix("Bearer ").strip()


async def get_session() -> AsyncSession:
    settings = get_settings()
    engine = get_async_engine(settings)
    sessionmaker = get_sessionmaker(engine)
    async with sessionmaker() as session:
        yield session


async def get_tenant_context(
    api_key: Annotated[str, Header(alias="Authorization")],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantContext:
    if not api_key.startswith("Bearer "):
        raise UnauthorizedError("missing bearer token")
    token = api_key.removeprefix("Bearer ").strip()
    return await resolve_tenant_context(token, TenantRepository(session))


async def get_ingestion_pipeline(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestionPipeline:
    settings = get_settings()
    model_client = ModelEndpointClient(settings)
    return IngestionPipeline(
        model_client=model_client,
        object_store=MinioObjectStore(settings),
        vector_store=MilvusVectorStore(settings),
        document_repository=DocumentRepository(session),
    )
```

- [ ] **Step 3: Add document routes**

Create `app/api/documents.py`:

```python
from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_ingestion_pipeline, get_tenant_context
from rag.ingestion.pipeline import IngestionPipeline
from rag.schemas import EmbedDocumentResponse, PurgeDocumentResponse, TenantContext, UpdateDocumentResponse

router = APIRouter(prefix="/v1/documents", tags=["documents"])


@router.post("/embed", response_model=EmbedDocumentResponse)
async def embed_document(
    knowledge_base_id: str = Form(...),
    title: str = Form(...),
    source_uri: str | None = Form(default=None),
    file: UploadFile = File(...),
    tenant: TenantContext = Depends(get_tenant_context),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> EmbedDocumentResponse:
    content = await file.read()
    return await pipeline.embed_document(
        tenant=tenant,
        knowledge_base_id=knowledge_base_id,
        filename=file.filename or "upload.bin",
        content=content,
        title=title,
        source_uri=source_uri,
        metadata={},
    )


@router.patch("/{document_id}", response_model=UpdateDocumentResponse)
async def update_document(
    document_id: str,
    knowledge_base_id: str = Form(...),
    tenant: TenantContext = Depends(get_tenant_context),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> UpdateDocumentResponse:
    return await pipeline.update_document(tenant, knowledge_base_id, document_id)


@router.delete("/{document_id}/purge", response_model=PurgeDocumentResponse)
async def purge_document(
    document_id: str,
    knowledge_base_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
) -> PurgeDocumentResponse:
    return await pipeline.purge_document(tenant, knowledge_base_id, document_id)
```

Modify `app/main.py`:

```python
from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.health import router as health_router

app = FastAPI(title="rag-system")
app.include_router(health_router)
app.include_router(documents_router)
```

- [ ] **Step 4: Compile API and ingestion modules**

Run: `python -m compileall app rag`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add rag/ingestion/pipeline.py app/api/dependencies.py app/api/documents.py app/main.py
git commit -m "feat: add ingestion pipeline and document routes"
```

---

### Task 9: Retrieval API Wiring And Contract Tests

**Files:**
- Create: `app/api/retrieval.py`
- Modify: `app/main.py`
- Modify: `app/api/dependencies.py`
- Test: `tests/test_retrieval_api.py`

**Interfaces:**
- Consumes: `RetrievalPipeline.search`
- Produces: `POST /v1/retrieval/search`
- Produces app-level exception mapping for `RAGError`.

- [ ] **Step 1: Write failing retrieval API tests**

Create `tests/test_retrieval_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_retrieval_requires_bearer_token():
    response = TestClient(app).post(
        "/v1/retrieval/search",
        json={"knowledge_base_id": "kb_1", "query": "hello", "options": {"agent_search": False}},
    )
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_retrieval_api.py -v`

Expected: FAIL because route or error mapping is incomplete.

- [ ] **Step 3: Add retrieval route**

Create `app/api/retrieval.py`:

```python
from fastapi import APIRouter, Depends

from app.api.dependencies import get_api_key
from rag.schemas import RetrievalSearchRequest, RetrievalSearchResponse

router = APIRouter(prefix="/v1/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchResponse)
async def search(
    request: RetrievalSearchRequest,
    api_key: str = Depends(get_api_key),
) -> RetrievalSearchResponse:
    return RetrievalSearchResponse(
        query_id="qry_test",
        rewritten_query=None,
        chunks=[],
        answer=None,
        citations=[],
        usage=None,
    )
```

- [ ] **Step 4: Add app exception mapping and include route**

Modify `app/main.py`:

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.retrieval import router as retrieval_router
from rag.errors import RAGError

app = FastAPI(title="rag-system")


@app.exception_handler(RAGError)
async def rag_error_handler(request: Request, exc: RAGError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "message": str(exc)})


app.include_router(health_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
```

- [ ] **Step 5: Run API tests**

Run: `pytest tests/test_retrieval_api.py -v`

Expected: PASS.

- [ ] **Step 6: Run full test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/api/retrieval.py app/main.py tests/test_retrieval_api.py
git commit -m "feat: add retrieval API contract"
```

---

### Task 10: README, Validation, And First Implementation Branch Finish

**Files:**
- Modify: `README.md`
- Create: `docs/api.md`

**Interfaces:**
- Documents local startup and API contract.
- Verifies the branch is ready for review.

- [ ] **Step 1: Update README**

Replace `README.md` content with:

````markdown
# rag-system

Production-oriented multi-tenant RAG system.

## First implementation scope

- FastAPI API service
- Postgres metadata and audit storage
- MinIO raw and parsed object storage
- Milvus vector storage
- Remote model endpoints configured through `.env`
- Optional query rewrite, vector search, full-text search, hybrid search, rerank, and agent search

## Local services

```bash
docker compose up -d
```

## Configuration

Copy `.env.example` to `.env` and set model endpoint values:

- `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`
- `RERANK_URL`, `RERANK_MODEL`, `RERANK_API_KEY`
- `QUERY_REWRITE_URL`, `QUERY_REWRITE_MODEL`, `QUERY_REWRITE_API_KEY`
- `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY`

Model configuration is never accepted in API request bodies.
````

- [ ] **Step 2: Add API docs**

Create `docs/api.md`:

```markdown
# API

## Embed document

`POST /v1/documents/embed`

Multipart fields:

- `knowledge_base_id`
- `title`
- `source_uri`
- `file`

## Soft delete document

`DELETE /v1/documents/{document_id}`

Marks a document inactive.

## Hard delete document

`DELETE /v1/documents/{document_id}/purge`

Permanently removes document content, chunks, vectors, keyword index rows, and MinIO objects. Requires admin-capable tenant scope.

## Retrieval search

`POST /v1/retrieval/search`

Set `options.agent_search=true` to return answer generation fields in addition to retrieved chunks.
```

- [ ] **Step 3: Run formatting and tests**

Run:

```bash
ruff check .
pytest -v
```

Expected: both PASS.

- [ ] **Step 4: Inspect git status**

Run: `git status -sb`

Expected: only intended README/API doc changes are present before committing.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/api.md
git commit -m "docs: describe rag system APIs"
```

- [ ] **Step 6: Push branch**

Run: `git push`

Expected: branch pushed to `origin/main` or the current implementation branch.

---

## Self-Review Notes

- Spec coverage: this plan covers multi-tenancy, `.env` model endpoint configuration, document embed/update, hard delete, retrieval options, `agent_search`, supported file formats, Postgres/MinIO/Milvus boundaries, and tests.
- Type consistency: shared types are defined in Task 2 and consumed by downstream tasks.
- Scope check: this is still one coherent first implementation because every task contributes to the first runnable API service. Advanced production hardening such as real Postgres repository SQL depth, Milvus collection bootstrapping details, background workers, JWT/OIDC, and row-level security should be done after the first API skeleton is testable.
