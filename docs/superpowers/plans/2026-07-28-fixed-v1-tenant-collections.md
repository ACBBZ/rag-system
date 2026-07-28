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

- [x] Replace shared and dual-write tests with tests that require a ready authenticated route.
- [x] Require all upsert, search, and delete calls to use the stable alias.
- [x] Require search and delete filters to contain authenticated `tenant_id` and authorized `knowledge_base_id`.
- [x] Require Collection Manager to reject an alias pointing at another physical collection rather than reassigning it.
- [x] Keep provisioning ordering and failure tests.

### Task 2: Simplify database and configuration

- [x] Remove migration table and `read_mode`.
- [x] Add unique constraints for tenant, alias, and physical Collection.
- [x] Remove legacy Collection, schema-version, and migration-batch environment settings.
- [x] Store metric, index, and search configuration in the resource route.

### Task 3: Simplify runtime routing and platform APIs

- [x] Remove shared/dual-write modes and migration endpoints.
- [x] Load exactly one ready resource by tenant ID.
- [x] Use resource metric/index/search parameters during search.
- [x] Reject unexpected Alias targets.
- [x] Keep idempotent provisioning and retry.

### Task 4: Update public documentation

- [x] Update `README.md` for the fixed V1 architecture.
- [x] Update `docs/authorization-v2-api.md`.
- [x] Create `docs/vector-collection-v2-roadmap.md`.
- [x] Explicitly list all V2 features that are not implemented.
- [x] Document future re-embedding and Alias-switch requirements.

### Task 5: Verification

- [x] Parse the changed Python modules successfully.
- [x] Run the three focused fixed-V1 test modules in a reconstructed local environment: 12 passed.
- [x] Remove the vector migration service, migration test, and multi-version Alembic revision.
- [ ] Run complete repository `ruff check .` in a network-capable checkout.
- [ ] Run complete repository `pytest -v` with the real PyMilvus dependency.
- [ ] Confirm the final GitHub Actions result.

Local checkout verification is partially blocked because the execution environment cannot resolve `github.com`, and `pymilvus` is not installed locally. Focused tests used the repository Fake Milvus clients plus a minimal SDK schema stub.
