# Authorization V2 API Guide

## Required configuration

Set `API_KEY_PEPPER` to a long random secret and `PLATFORM_API_KEY` to a separate platform-control credential. Apply Alembic revisions `0001_initial` and `0002_authorization_v2` before using V2 APIs.

## Create a tenant

`POST /v1/platform/tenants` with `Authorization: Bearer $PLATFORM_API_KEY`.

The response contains the initial owner API key exactly once. Store it securely.

## Create users and administrators

- `POST /v1/users` creates a tenant user.
- `PATCH /v1/users/{user_id}/role` changes `member`, `tenant_admin`, or `tenant_owner` according to delegation rules.
- `PUT /v1/users/{user_id}/scope-grants` grants a direct permission.
- `DELETE /v1/users/{user_id}/scope-grants/{permission}` revokes it.

A tenant administrator can create and manage members. Tenant owners can create and manage administrators and additional owners. The last active owner cannot be removed.

## Create knowledge bases

`POST /v1/knowledge-bases` requires `knowledge_bases:create`. The caller does not need to be a tenant administrator. The creator automatically receives `kb_admin`.

`PUT /v1/knowledge-bases/{knowledge_base_id}/members/{user_id}` assigns `kb_admin`, `editor`, or `viewer`.

## API keys

- `POST /v1/api-keys` creates a key for the current user.
- `POST /v1/users/{user_id}/api-keys` lets an authorized administrator create a key for a tenant user.
- `DELETE /v1/api-keys/{api_key_id}` revokes a key.

V2 keys use `rag_live_<key_id>.<secret>`. Plaintext is returned once. `scope_limit` and `knowledge_base_limit` only reduce the user's live membership and ACL permissions.

## Document and retrieval permissions

- Embed requires `documents:create`.
- Update requires `documents:update`.
- Purge requires `documents:delete`.
- Retrieval requires `retrieval:read`.

Every V2 request reloads tenant status, user status, membership, direct grants, knowledge-base ACLs, and API-key limits. Permission changes therefore affect existing keys on the next request.
