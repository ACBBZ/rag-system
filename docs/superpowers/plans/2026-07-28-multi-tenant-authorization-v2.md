# Multi-Tenant Authorization V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add multi-tenant provisioning, dynamic membership/ACL authorization, secure API-key issuance, tenant management APIs, and cross-tenant tests.

**Architecture:** Keep FastAPI and SQLAlchemy boundaries, add a V2 migration and focused identity/authorization repositories. Tenant and knowledge-base permissions are resolved from current database records on every request and intersected with API-key limits. Existing document and retrieval pipelines continue receiving a trusted tenant context.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, Postgres, pytest.

## Global Constraints

- Tenant IDs are server-derived for tenant APIs.
- Cross-tenant resource lookup returns 404.
- API-key plaintext is returned once and never stored.
- API-key limits only reduce dynamic user permissions.
- Existing document and retrieval API paths remain compatible.

---

### Task 1: Database migration

- Add tenant/user status and authorization version fields.
- Normalize memberships to one tenant role.
- Add direct permission grants.
- Expand knowledge-base ACL with user and role fields.
- Add API-key V2 lifecycle and limit fields.
- Add audit events and database constraints.
- Add migration-shape tests.

### Task 2: Authentication refactor

- Add permission and role enums.
- Add API-key generation, parsing, HMAC hashing, expiry and revocation validation.
- Resolve principal context from current tenant, user, membership, grants and key limits.
- Add unit tests for key security and permission intersection.

### Task 3: Management APIs

- Add platform tenant provisioning guarded by `PLATFORM_API_KEY`.
- Add tenant user creation, role updates, direct grants and API-key issuance/revocation.
- Protect last-owner and administrator delegation boundaries.
- Add API tests for provisioning and user management.

### Task 4: Knowledge-base ACL

- Add knowledge-base creation and member management APIs.
- Permit non-admin creation through `knowledge_bases:create`.
- Automatically grant the creator `kb_admin`.
- Replace document and retrieval authorization with fine-grained dynamic permission dependencies.
- Add ACL behavior tests.

### Task 5: Cross-tenant tests and verification

- Add two-tenant authorization tests.
- Test cross-tenant knowledge-base and document denial.
- Test permission changes against existing API keys.
- Run `ruff check .` and `pytest -v`.
