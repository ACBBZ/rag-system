# Authorization V2 and Fixed V1 Tenant Collections

## Required configuration

Set `API_KEY_PEPPER` to a long random secret and `PLATFORM_API_KEY` to a separate platform-control credential. Apply Alembic revisions through `0003_tenant_vector_collections` before creating tenants.

Configure Milvus with:

```env
MILVUS_URI=http://localhost:19530
MILVUS_COLLECTION_PREFIX=rag_prod
MILVUS_VECTOR_DIMENSION=1024
MILVUS_METRIC_TYPE=COSINE
MILVUS_INDEX_TYPE=HNSW
MILVUS_INDEX_M=16
MILVUS_INDEX_EF_CONSTRUCTION=200
MILVUS_SEARCH_EF=64
```

`MILVUS_VECTOR_DIMENSION` must exactly match the output dimension of `EMBEDDING_MODEL`.

After the first tenant Collection is created, treat the embedding model, vector dimension, metric, index settings, search settings, and field schema as immutable for V1. A configuration fingerprint mismatch makes the tenant vector route unavailable instead of querying incompatible vectors.

## Tenant Collection model

Each tenant receives exactly one database vector resource:

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

Tenant names and slugs are never included in Milvus names. API clients cannot submit or override Collection names.

A tenant Collection contains all of that tenant's knowledge bases. Every vector row still contains `tenant_id` and `knowledge_base_id`, and search/delete filters retain those values as defense in depth.

The current database enforces:

- one vector resource per tenant;
- one tenant per logical Alias;
- one tenant per physical Collection;
- `schema_version = 1`.

## Create a tenant

Call:

```text
POST /v1/platform/tenants
Authorization: Bearer $PLATFORM_API_KEY
```

The platform service performs these steps:

1. Create the tenant in `provisioning` state.
2. Create the initial Owner and membership.
3. Optionally create the default knowledge base.
4. Insert the pending tenant vector resource.
5. Create and validate the V1 physical Collection.
6. Create or validate the stable Alias.
7. Mark the vector resource `ready`.
8. Activate the tenant.
9. Issue the initial Owner API key.

The plaintext initial API key is returned exactly once.

If Milvus provisioning fails, the tenant remains non-active, the vector resource is marked `failed`, and no initial API key is issued.

Inspect and retry provisioning with:

```text
GET  /v1/platform/tenants/{tenant_id}/vector-resource
POST /v1/platform/tenants/{tenant_id}/vector-resource/retry
```

Provisioning is idempotent. An existing Collection must have the expected vector dimension and required fields. An existing Alias must already point to the tenant's V1 physical Collection; the application does not silently reassign an unexpected Alias.

## Runtime vector routing

Every authenticated request resolves the API key from PostgreSQL and obtains a trusted `tenant_id`. The service then loads the single `ready` vector resource for that tenant and stores its route in `TenantContext`.

Vector operations never read a tenant ID or Collection name from the request body.

If no compatible ready resource exists, vector operations return `503 vector_store_unavailable`. There is no shared Collection fallback.

Runtime route data includes:

- logical Alias;
- physical Collection name for administration and diagnostics;
- embedding model and dimension;
- metric type;
- index type;
- search parameters.

Upsert, search, and delete always target the logical Alias. Search parameters come from the tenant resource, not from a separate runtime guess.

## Defense in depth

Vector writes include:

```text
tenant_id
knowledge_base_id
document_id
chunk_id
document_version
is_active
```

Search filters include:

```text
tenant_id == authenticated tenant
AND knowledge_base_id == authorized knowledge base
AND is_active == true
```

Delete filters include:

```text
tenant_id == authenticated tenant
AND knowledge_base_id == authorized knowledge base
AND document_id == requested document
```

This preserves tenant isolation even if a Collection route is configured incorrectly.

## Users and administrators

- `POST /v1/users` creates a tenant user.
- `PATCH /v1/users/{user_id}/role` changes `member`, `tenant_admin`, or `tenant_owner` according to delegation rules.
- `PUT /v1/users/{user_id}/scope-grants` grants a direct permission.
- `DELETE /v1/users/{user_id}/scope-grants/{permission}` revokes it.

A tenant administrator can create and manage members. Tenant owners can create and manage administrators and additional owners. The last active owner cannot be removed.

## Knowledge bases

`POST /v1/knowledge-bases` requires `knowledge_bases:create`. The creator automatically receives `kb_admin`.

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

Every V2 request reloads tenant status, user status, membership, direct grants, knowledge-base ACLs, API-key limits, and the compatible ready vector route.

## Deferred V2 upgrade work

The current release does not implement:

- a shared Collection;
- Collection data migration;
- multiple physical Collection versions;
- hot embedding-model upgrades;
- online vector-dimension upgrades;
- dual-write;
- Alias canary switching;
- Collection rollback;
- migration progress tables;
- migration management APIs.

See `docs/vector-collection-v2-roadmap.md` for the future design boundary. A future model upgrade must create a new physical Collection, regenerate vectors from canonical PostgreSQL chunk text, validate the new Collection, and only then switch the stable Alias.
