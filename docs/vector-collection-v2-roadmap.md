# Vector Collection V2 Roadmap

## Status

This document describes a future upgrade path. None of the capabilities below are implemented in the current fixed V1 release.

The current release intentionally supports:

```text
one tenant
→ one stable logical Alias
→ one fixed V1 physical Collection
```

## Not implemented in V1

The current version does not implement:

- a shared Collection;
- Collection data migration;
- multiple physical Collection versions per tenant;
- hot embedding-model upgrades;
- online vector-dimension upgrades;
- dual-write;
- Alias canary or gradual switching;
- Collection rollback;
- migration progress tables;
- migration management APIs.

These features must not be inferred from the `_v1` physical Collection suffix. The suffix is only a fixed schema identifier in the current release.

## Why this is deferred

The project has not yet deployed PostgreSQL or Milvus and has no historical vector data to preserve. Implementing migration and multi-version state now would add runtime branches, failure states, tests, and operational procedures for data that does not exist.

The V1 implementation therefore treats the following settings as immutable after the first tenant Collection is created:

- `EMBEDDING_MODEL`;
- `MILVUS_VECTOR_DIMENSION`;
- `MILVUS_METRIC_TYPE`;
- `MILVUS_INDEX_TYPE`;
- `MILVUS_INDEX_M`;
- `MILVUS_INDEX_EF_CONSTRUCTION`;
- `MILVUS_SEARCH_EF`;
- the Milvus field schema.

If the configured fingerprint differs from a ready tenant resource, the runtime does not provide a vector route for that tenant.

## Future V2 design trigger

Design V2 only when at least one of these requirements becomes real:

- change the embedding model;
- change vector dimensions;
- change the Milvus field schema;
- change metrics or index strategy;
- perform a zero-downtime vector upgrade;
- provide rollback to a previous physical Collection;
- move existing tenants between Milvus clusters.

## Expected V2 architecture

A future V2 should preserve the stable logical Alias while adding versioned physical Collections:

```text
stable tenant Alias
├── current physical Collection V1
└── prepared physical Collection V2
```

The upgrade flow should be designed separately and should include:

1. Create the V2 physical Collection without changing the live Alias.
2. Read canonical chunk text and metadata from PostgreSQL.
3. Generate new vectors using the V2 embedding model.
4. Write the new vectors into V2 with `tenant_id` and `knowledge_base_id` fields.
5. Validate document counts, chunk counts, dimensions, filters, and retrieval quality.
6. Keep live reads on V1 until validation succeeds.
7. Switch the stable Alias to V2 in one controlled operation.
8. Retain V1 for a defined rollback window.
9. Remove V1 only after the rollback window and operational approval.

Old vectors must not be copied into V2 when the embedding model or its semantics change. V2 vectors must be regenerated from canonical chunk text.

## Required V2 components

A future implementation may introduce:

- an explicit active-resource pointer per tenant;
- multiple physical resource records per tenant;
- provisioning and backfill state machines;
- source and target write routing;
- migration progress and retry records;
- validation reports;
- Alias switch and rollback APIs restricted to the platform control plane;
- metrics and audit events for every upgrade stage.

Those components are deliberately absent from V1.
