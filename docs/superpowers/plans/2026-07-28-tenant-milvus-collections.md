# Tenant Milvus Collections Implementation Plan — Superseded

This plan described shared-Collection compatibility, migration, dual-write, and multiple physical Collection versions.

The project has not deployed PostgreSQL or Milvus and has no historical vector data, so that complexity is not part of the current release.

Use these documents instead:

- Current fixed V1 implementation plan: `docs/superpowers/plans/2026-07-28-fixed-v1-tenant-collections.md`
- Current API and provisioning guide: `docs/authorization-v2-api.md`
- Future multi-version and embedding-upgrade roadmap: `docs/vector-collection-v2-roadmap.md`

The current architecture is:

```text
one tenant
→ one stable logical Alias
→ one fixed V1 physical Collection
```

Shared Collections, migration, multi-version routing, dual-write, Alias switching, and rollback are explicitly deferred to a future V2 design.
