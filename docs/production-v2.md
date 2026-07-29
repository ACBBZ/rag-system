# Production RAG V2

The production architecture uses FastAPI lifespan resources, a durable PostgreSQL ingestion queue, structured token-aware parsing, document-version activation, Milvus schema V2, validated structured answers, Prometheus metrics, OpenTelemetry spans, and deterministic/RAGAS quality gates.

## Required deployment commands

```bash
python -m pip install -e '.[dev,eval,security]'
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
rag-worker
```

Run API and worker as separate processes. At least one worker is required for queued documents to become searchable.

## Migration notes

Migration `0005_ingestion_v2` makes document ingestion asynchronous and adds version/job fields. Migration `0006_retrieval_v3` enables Milvus schema version 2 and weighted lexical text. Existing V1 tenant collections require reindexing with `MilvusV2Migrator`; do not simply change the database row without creating and validating the new collection. Migration `0007_observability` adds query/retrieval trace fields.

## API changes

- `POST /v1/documents/embed` returns HTTP 202 with a real queued job.
- `PATCH /v1/documents/{document_id}` accepts an optional replacement file; without a file it reprocesses the active raw object as a new version.
- `GET /v1/ingestion-jobs/{job_id}` returns status and progress.
- `POST /v1/ingestion-jobs/{job_id}/retry` retries eligible failures.
- Retrieval responses include trace ID, answer status, abstention reason, timings, final score type, and validated citations.
- `/health/live`, `/health/ready`, and `/metrics` are available for operations.

## Evaluation

The repository includes smoke, golden, and adversarial dataset seeds. Replace fixture knowledge-base IDs with the deployed fixture KB and populate stable `reference_context_keys` after fixture ingestion. Quality gates always require zero tenant/knowledge-base leakage and zero unknown citation IDs.
