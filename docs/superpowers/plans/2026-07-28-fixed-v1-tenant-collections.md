# Fixed V1 Tenant Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify Milvus tenancy to one stable alias and one fixed V1 physical collection per tenant, with no shared collection, migration, dual-write, or multi-version runtime behavior.

**Architecture:** Tenant provisioning creates one database vector resource, one Milvus physical collection, and one stable alias. API-key authentication loads the ready resource by authenticated `tenant_id`; vector operations always use the alias and retain `tenant_id` plus `knowledge_base_id` filters as defense in depth.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL, Alembic, PyMilvus, Pytest.

## Global Constraints

- Modify `main` directly as explicitly requested.
- There is no deployed PostgreSQL or Milvus state, so migration history may be simplified before first deployment.
- The current implementation supports only schema version 1.
- Do not implement shared Collection fallback, data migration, multiple Collection versions, hot embedding upgrades, online dimension upgrades, dual-write, alias canary switching, rollback, migration progress, or migration APIs.
- Preserve `tenant_id` and `knowledge_base_id` Milvus filters.
- Document future V2 upgrades separately.

---

### Task 1: Define fixed V1 behavior with tests

**Files:**
- Modify: `tests/test_tenant_collection_routing.py`
- Modify: `tests/test_milvus_collection_manager.py`
- Modify: `tests/test_tenant_vector_provisioning.py`
- Delete: `tests/test_vector_migration.py`

**Interfaces:**
- Produces: `TenantVectorRoute` with alias, physical collection, embedding dimension, metric, index type, and search parameters.
- Produces: `build_collection_names(tenant_id, prefix)` fixed to `_v1`.

- [ ] Replace shared and dual-write tests with tests that require a ready authenticated route.
- [ ] Require all upsert, search, and delete calls to use the stable alias.
- [ ] Require search and delete filters to contain authenticated `tenant_id` and authorized `knowledge_base_id`.
- [ ] Require Collection Manager to reject an alias pointing at another physical collection rather than reassigning it.
- [ ] Keep provisioning ordering and failure tests.

### Task 2: Simplify database and configuration

**Files:**
- Modify: `migrations/versions/0003_tenant_vector_collections.py`
- Delete: `migrations/versions/0004_vector_alias_versions.py`
- Modify: `rag/config.py`
- Modify: `.env.example`
- Modify: `rag/storage/milvus_schema.py`
- Modify: `rag/storage/vector_resources.py`

**Interfaces:**
- Produces: one `tenant_vector_resources` row per tenant.
- Produces: fixed `schema_version = 1`.

- [ ] Remove migration table and `read_mode`.
- [ ] Add unique constraints for tenant, alias, and physical Collection.
- [ ] Remove legacy Collection, schema-version, and migration-batch environment settings.
- [ ] Store metric, index, and search configuration in the resource route.

### Task 3: Simplify runtime routing and platform APIs

**Files:**
- Modify: `rag/schemas.py`
- Modify: `rag/storage/identity_repository.py`
- Modify: `rag/storage/tenant_collection_resolver.py`
- Modify: `rag/storage/milvus_store.py`
- Modify: `rag/storage/milvus_collection_manager.py`
- Modify: `rag/tenants/provisioning.py`
- Modify: `app/api/platform.py`
- Delete: `rag/storage/vector_migration.py`

**Interfaces:**
- Consumes: ready vector resource loaded from authenticated `tenant_id`.
- Produces: alias-only vector operations and 503 when no ready resource exists.

- [ ] Remove shared/dual-write modes and migration endpoints.
- [ ] Load exactly one ready resource by tenant ID.
- [ ] Use resource metric/index/search parameters during search.
- [ ] Reject unexpected Alias targets.
- [ ] Keep idempotent provisioning and retry.

### Task 4: Update public documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/authorization-v2-api.md`
- Create: `docs/vector-collection-v2-roadmap.md`

- [ ] Document the fixed V1 one-tenant-one-Collection architecture.
- [ ] Document required environment variables and provisioning APIs.
- [ ] Explicitly list all V2 features that are not implemented.
- [ ] Explain that future model upgrades require a new Collection, re-embedding from PostgreSQL chunk text, validation, and Alias switching.

### Task 5: Verification

- [ ] Run `ruff check .`.
- [ ] Run `pytest -v`.
- [ ] Confirm no references remain to migration APIs, legacy Collection settings, `dual_write`, or `read_mode`.
- [ ] Confirm current GitHub Actions status for the final commit.
