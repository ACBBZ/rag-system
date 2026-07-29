# Production Runbook

## Deployment order

1. Back up PostgreSQL and record every tenant Milvus alias target.
2. Deploy migrations with `alembic upgrade head`.
3. Deploy the API and verify `/health/live`.
4. Verify `/health/ready` reports PostgreSQL, MinIO, and Milvus as ready.
5. Deploy at least one `rag-worker` process.
6. Run ingestion reconciliation and the deterministic smoke evaluation.
7. Migrate tenant vector resources from schema V1 to V2 before enabling selective metadata filters.

## Incident triage

- API unavailable: inspect process health, database pool saturation, and dependency readiness.
- Retrieval empty: compare PostgreSQL active chunks to Milvus active vectors and inspect query traces.
- Ingestion stuck: inspect `heartbeat_at`, reset stale jobs, and retry only after confirming idempotent staging data.
- Citation failure: retain trace and query IDs, inspect structured model output, and do not return unvalidated citations.
- Quality regression: disable the changed retrieval option at knowledge-base scope and restore the last evaluation baseline.

## Rollback

Application code may be rolled back while keeping additive migrations. Do not downgrade a migration while workers are active. Milvus V2 rollback is an alias switch to `previous_physical_collection`; validate row counts and embedding fingerprints before switching.

## Reconciliation

Run hourly and alert on any non-empty result:

- active PostgreSQL chunks without Milvus vectors;
- Milvus vectors without active PostgreSQL chunks;
- missing MinIO raw or parsed objects;
- stale processing jobs;
- staging versions older than the configured retention period.
