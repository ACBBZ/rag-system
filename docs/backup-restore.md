# Backup and Restore

## PostgreSQL

Use daily encrypted logical or physical backups with point-in-time recovery. Restore into an isolated environment, run `alembic current`, and verify document/version/chunk counts before reconnecting external stores.

## MinIO

Enable object versioning and replication for the RAG bucket. Raw objects are canonical ingestion inputs; parsed objects may be regenerated. Preserve tenant and knowledge-base prefixes during restore.

## Milvus

Milvus vectors are reproducible from active PostgreSQL chunks and the recorded embedding model. Back up collection metadata and alias targets, but treat PostgreSQL chunk text plus model fingerprint as the authoritative rebuild source.

## Recovery sequence

1. Restore PostgreSQL.
2. Restore or verify MinIO raw objects.
3. Recreate tenant collections from recorded schema fingerprints.
4. Re-embed active chunks in batches.
5. Validate chunk ID and vector counts.
6. Switch tenant aliases.
7. Run deterministic retrieval and leakage gates.
8. Re-enable traffic.
