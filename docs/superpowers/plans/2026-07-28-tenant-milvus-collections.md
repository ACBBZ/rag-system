# Tenant Milvus Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route each new tenant to a stable Milvus alias backed by a versioned physical collection while preserving the shared collection for unmigrated tenants.

**Architecture:** Postgres stores tenant vector-resource state. Tenant provisioning creates a pending database record, creates the Milvus collection and alias, then activates the resource and issues the initial API key. Request authentication loads the active vector route into `TenantContext`; `MilvusVectorStore` resolves either the tenant alias or the legacy shared collection and keeps tenant and knowledge-base filters as defense in depth.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy asyncio, Alembic, PyMilvus `MilvusClient`, Pytest, Ruff.

## Global Constraints

- Modify `main` directly as explicitly requested.
- Keep existing tenants on `MILVUS_LEGACY_COLLECTION` unless a ready tenant resource is active.
- New tenant collection names and aliases are server-generated and contain no tenant names or slugs.
- API clients cannot submit collection names.
- Keep `tenant_id` and `knowledge_base_id` in every vector row and filter.
- Initial owner API keys are issued only after vector provisioning succeeds.
- Milvus failures leave a retryable database state and do not activate the tenant.
- Collection and alias operations are idempotent.

---

### Task 1: Configuration and database resource model

**Files:**
- Create: `migrations/versions/0003_tenant_vector_collections.py`
- Modify: `rag/config.py`
- Modify: `.env.example`
- Modify: `rag/schemas.py`
- Modify: `rag/errors.py`
- Test: `tests/test_tenant_collection_routing.py`

**Interfaces:**
- Produces `TenantVectorRoute`, `VectorResourceSummary`, and configuration fields for collection prefix, legacy collection, dimension, metric, index, search params, and schema version.

- [ ] Add failing tests for deterministic names, environment configuration defaults, and unavailable-route errors.
- [ ] Confirm the tests fail because the routing types and configuration do not exist.
- [ ] Add the Alembic resource and migration-progress tables and schema/configuration models.
- [ ] Run focused tests and Ruff.
- [ ] Commit the database and configuration phase.

### Task 2: Collection lifecycle manager

**Files:**
- Create: `rag/storage/milvus_schema.py`
- Create: `rag/storage/milvus_collection_manager.py`
- Test: `tests/test_milvus_collection_manager.py`

**Interfaces:**
- Produces `build_collection_names(tenant_id, prefix, schema_version)`, `schema_fingerprint(settings)`, and `MilvusCollectionManager.ensure_collection(resource)`.

- [ ] Add failing fake-client tests for deterministic names, idempotent collection creation, alias creation, alias reassignment, and schema mismatch rejection.
- [ ] Confirm failures are caused by missing lifecycle implementation.
- [ ] Implement schema, index parameters, collection validation, and alias management using `MilvusClient` APIs.
- [ ] Run focused tests and Ruff.
- [ ] Commit the Collection Manager phase.

### Task 3: Vector resource repository and tenant provisioning

**Files:**
- Create: `rag/storage/vector_resources.py`
- Create: `rag/tenants/provisioning.py`
- Modify: `rag/storage/repositories.py`
- Modify: `app/api/platform.py`
- Modify: `app/api/dependencies.py`
- Modify: `rag/schemas.py`
- Test: `tests/test_tenant_vector_provisioning.py`

**Interfaces:**
- Produces `VectorResourceRepository`, `TenantProvisioningService.create_tenant()`, `retry_vector_resource()`, and platform status/retry endpoints.

- [ ] Add failing tests proving initial keys are not issued before Milvus readiness and failures are recorded as retryable.
- [ ] Confirm the tests fail against the current single-transaction tenant creation path.
- [ ] Split database bootstrap from vector provisioning, create/activate resource records, and issue the key only after successful alias activation.
- [ ] Add `GET /v1/platform/tenants/{tenant_id}/vector-resource` and `POST /v1/platform/tenants/{tenant_id}/vector-resource/retry`.
- [ ] Run focused tests and Ruff.
- [ ] Commit the provisioning phase.

### Task 4: Request routing and vector operations

**Files:**
- Modify: `rag/schemas.py`
- Modify: `rag/storage/identity_repository.py`
- Create: `rag/storage/tenant_collection_resolver.py`
- Modify: `rag/storage/milvus_store.py`
- Modify: `rag/ingestion/pipeline.py`
- Modify: `rag/retrieval/pipeline.py`
- Test: `tests/test_tenant_collection_routing.py`
- Test: `tests/test_tenant_isolation_v2.py`

**Interfaces:**
- Produces `TenantCollectionResolver.resolve(tenant)` and asynchronous `MilvusVectorStore.upsert_chunks/search/delete_document` operations.

- [ ] Add failing tests proving new tenants use only their alias, legacy tenants use the shared collection, and client input cannot select a collection.
- [ ] Confirm tests fail because the store still uses one fixed collection.
- [ ] Load active vector-resource routing during authentication, resolve the server-controlled collection, and retain tenant/knowledge-base filters.
- [ ] Await vector operations in ingestion and retrieval pipelines.
- [ ] Run focused tests, existing API tests, and Ruff.
- [ ] Commit the runtime routing phase.

### Task 5: Shared-collection migration support and verification

**Files:**
- Create: `rag/storage/vector_migration.py`
- Modify: `app/api/platform.py`
- Modify: `rag/schemas.py`
- Modify: `docs/authorization-v2-api.md`
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_vector_migration.py`

**Interfaces:**
- Produces `TenantVectorMigrationService.backfill_tenant()` and platform migration status/start endpoints. Backfill uses `query_iterator`, preserves primary keys and vectors, and updates progress after each batch.

- [ ] Add failing fake-client tests for tenant-filtered backfill, resumable progress, idempotent upsert, and activation only after successful copy.
- [ ] Confirm failures are due to the missing migration service.
- [ ] Implement migration records, batch iteration, destination upsert, progress persistence, and route activation.
- [ ] Document deployment, migration, rollback, and environment variables.
- [ ] Run `ruff check .` and `pytest -v`; inspect GitHub Actions status after the final commit.
- [ ] Commit the migration and verification phase.
