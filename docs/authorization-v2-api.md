# Authorization V2 and Tenant Vector API Guide

## Required configuration

Set `API_KEY_PEPPER` to a long random secret and `PLATFORM_API_KEY` to a separate platform-control credential. Apply Alembic revisions through `0003_tenant_vector_collections` before creating or migrating tenants.

Configure Milvus with:

```env
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION_PREFIX=rag_prod
MILVUS_LEGACY_COLLECTION=rag_chunks
MILVUS_SCHEMA_VERSION=1
MILVUS_VECTOR_DIMENSION=1024
MILVUS_METRIC_TYPE=COSINE
MILVUS_INDEX_TYPE=HNSW
MILVUS_INDEX_M=16
MILVUS_INDEX_EF_CONSTRUCTION=200
MILVUS_SEARCH_EF=64
MILVUS_MIGRATION_BATCH_SIZE=500
```

`MILVUS_VECTOR_DIMENSION` must match the output dimension of `EMBEDDING_MODEL`. Changing the embedding model or dimension requires a new schema version and physical collection.

## Tenant collections

Each newly created tenant receives:

- a server-generated stable alias such as `rag_prod_t_<digest>_current`;
- a versioned physical collection such as `rag_prod_t_<digest>_v1`;
- a `tenant_vector_resources` database record containing the schema, model, index, lifecycle status, and current read mode.

Tenant names and slugs are not used in Milvus names. Application clients cannot submit or override collection names.

A tenant collection contains all of that tenant's knowledge bases. Vector rows and filters still include `tenant_id` and `knowledge_base_id` as defense in depth.

## Create a tenant

`POST /v1/platform/tenants` with `Authorization: Bearer $PLATFORM_API_KEY`.

The platform service creates the database tenant in `provisioning` state, creates and validates the Milvus physical collection, creates the stable alias, activates the tenant, and only then issues the initial owner API key. The response contains that plaintext key exactly once.

If Milvus provisioning fails, the tenant remains non-active, the vector resource is marked `failed`, and no initial API key is issued. Use the tenant ID from the error message to inspect and retry:

```text
GET  /v1/platform/tenants/{tenant_id}/vector-resource
POST /v1/platform/tenants/{tenant_id}/vector-resource/retry
```

Collection and alias creation are idempotent, so retrying does not duplicate resources.

## Migrate an existing tenant

Existing tenants without a ready vector resource continue to use `MILVUS_LEGACY_COLLECTION`.

Start a tenant migration:

```text
POST /v1/platform/tenants/{tenant_id}/vector-migration
```

Read migration status:

```text
GET /v1/platform/tenants/{tenant_id}/vector-migration
```

Migration behavior:

1. Create and validate the tenant physical collection and alias.
2. Mark the tenant vector resource `migrating` with shared read mode.
3. Read only rows matching the authenticated tenant ID from the shared collection.
4. Copy rows in batches using idempotent upsert and persist `last_chunk_id` progress.
5. While migration is running, retrieval continues against the shared collection, while new upserts and deletes are applied to both shared and tenant collections.
6. After a successful copy, mark the migration completed and switch request routing to the stable alias.
7. On failure, keep shared read mode, preserve progress, record the error, and allow the same endpoint to resume.

Do not drop `MILVUS_LEGACY_COLLECTION` until every historical tenant has a completed migration and the rollback retention period has passed.

## Collection upgrades and rollback

For an embedding or schema upgrade:

1. Increase `MILVUS_SCHEMA_VERSION` and configure the new model and dimension.
2. Create the new physical collection for each tenant.
3. Backfill or re-embed data.
4. Validate counts and retrieval quality.
5. Reassign the stable alias to the new physical collection.
6. Keep the previous physical collection during a rollback window.

Rolling back is performed by moving the stable alias back to the previous physical collection. Application routes do not change because they use the alias.

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

Every V2 request reloads tenant status, user status, membership, direct grants, knowledge-base ACLs, API-key limits, and the active tenant vector route. Permission and collection-route changes therefore affect existing keys on the next request.
