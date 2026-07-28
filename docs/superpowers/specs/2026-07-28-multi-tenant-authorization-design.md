# Multi-Tenant Authorization V2 Design

## Goal

Build a production-oriented authorization model where tenants are the isolation boundary, tenant administrators are roles inside a tenant, knowledge-base creation is controlled by an independent permission, user permissions are resolved dynamically from membership and knowledge-base ACL records, and API keys only authenticate and narrow permissions.

## Core model

- A deployment contains multiple tenants.
- Each user row belongs to exactly one tenant.
- Tenant roles are `tenant_owner`, `tenant_admin`, and `member`.
- Knowledge-base roles are `kb_admin`, `editor`, and `viewer`.
- Direct grants can give a member tenant-level permissions such as `knowledge_bases:create`.
- API keys contain optional `scope_limit` and `knowledge_base_limit`; they never grant permissions the user does not currently hold.
- Effective permissions are the union of tenant-role permissions, direct grants, and the target knowledge-base ACL, intersected with API-key limits.

## Tenant provisioning

A platform administrator creates a tenant through a platform-only API. One transaction creates the tenant, initial owner, owner membership, optional default knowledge base, owner ACL, initial API key, and audit event. Platform authentication is separate from tenant API-key authentication.

## Dynamic authorization

Every tenant request performs:

1. Parse and verify the API key.
2. Reject revoked or expired keys.
3. Load tenant, user, and membership status.
4. Load current tenant role and direct permission grants.
5. For knowledge-base operations, verify the knowledge base belongs to the authenticated tenant and load its ACL.
6. Intersect dynamic permissions with API-key limits.
7. Authorize the requested fine-grained permission.

Cross-tenant resource lookups return 404 to avoid existence disclosure.

## Permission model

Tenant permissions include user management, API-key management, knowledge-base creation, audit access, and tenant configuration. Knowledge-base permissions include member management, document creation/update/delete, and retrieval.

Tenant owners can manage owners and administrators. Tenant administrators can manage ordinary members but cannot alter owners or remove the last active owner. A non-admin member can create knowledge bases when granted `knowledge_bases:create`; the creator automatically receives `kb_admin` on the new knowledge base.

## API-key security

New keys use `rag_live_<key_id>.<secret>`. The database stores the key ID, prefix, and an HMAC-SHA-256 digest of the secret using a server-side pepper. Plaintext is returned only once. Keys support expiry, revocation, and last-used metadata.

## Storage isolation

Postgres repositories always accept and filter by `tenant_id`; knowledge-base resources also filter by `knowledge_base_id`. Milvus rows and filters include tenant and knowledge-base identifiers. MinIO object keys are generated under tenant and knowledge-base prefixes. All identifiers used in Milvus filter expressions are validated or escaped.

## Audit

Tenant provisioning, user creation and disablement, role changes, direct grant changes, knowledge-base creation and membership changes, API-key issuance/revocation, and destructive document operations produce audit events. API-key plaintext and complete hashes are never logged.

## Compatibility

The migration retains legacy API-key columns during transition. New keys use the V2 format and dynamic authorization. Legacy keys can be accepted temporarily while operators rotate them, but new management APIs never issue legacy keys.

## Acceptance criteria

- Multiple tenants can be created through an API.
- Each tenant can have multiple owners, administrators, and members.
- Administrators can create members and change permitted roles.
- Members with `knowledge_bases:create` can create a knowledge base and become its `kb_admin`.
- ACL and membership changes affect existing API keys on the next request.
- API-key limits can only reduce effective permissions.
- Cross-tenant document and knowledge-base access is denied.
- Revoked, expired, disabled-user, and suspended-tenant credentials are rejected.
- Automated tests cover authorization boundaries and tenant isolation.
