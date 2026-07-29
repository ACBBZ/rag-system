# Production RAG Phases 0–6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the current retrieval-capable RAG service to a production-oriented system with shared runtime resources, durable asynchronous ingestion, versioned structured documents, Milvus V2 metadata filtering, validated answers and citations, observability, quality gates, integration tests, and operational hardening.

**Architecture:** Keep a modular FastAPI application. Application lifespan owns shared PostgreSQL, HTTP, MinIO, and Milvus clients. API requests enqueue durable ingestion jobs; a separate worker claims jobs with PostgreSQL `FOR UPDATE SKIP LOCKED`, writes staging data, validates cross-store consistency, and activates document versions. Retrieval uses PostgreSQL lexical search and Milvus V2 vector search, then builds token-budgeted context and validates structured model output. Evaluation calls the real API and compares deterministic and RAGAS metrics against versioned baselines.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL 16, MinIO, Milvus 2.4+, httpx, Pydantic v2, tiktoken, Prometheus, OpenTelemetry, pytest, RAGAS 0.4.3.

## Global Constraints

- Preserve existing `/v1/retrieval/search` fields and legacy retrieval booleans.
- Keep tenant and knowledge-base constraints in every PostgreSQL and Milvus operation.
- Never silently ignore an explicitly enabled capability.
- Use deterministic identifiers for ingestion retries and evaluation fixtures.
- Keep RAGAS outside the production request path.
- Every externally visible behavior must have a focused test.
- All new migrations must have a downgrade path.
- Direct main updates are explicitly authorized for this implementation.

---

### Task 1: Runtime lifecycle, resilience, and health

**Files:**
- Create: `rag/runtime.py`
- Create: `rag/observability.py`
- Modify: `app/main.py`
- Modify: `app/api/dependencies.py`
- Modify: `app/api/health.py`
- Modify: `rag/models/endpoints.py`
- Modify: `rag/storage/database.py`
- Modify: `rag/storage/minio_store.py`
- Modify: `rag/config.py`
- Test: `tests/test_runtime_and_health.py`
- Test: `tests/test_model_client_resilience.py`

**Interfaces:**
- `create_runtime(settings) -> RuntimeResources`
- `close_runtime(runtime) -> None`
- `ModelEndpointClient(settings, http_client)`
- `/health/live` and `/health/ready`

- [ ] Add tests proving one runtime reuses clients, health distinguishes liveness/readiness, model calls retry retryable failures, and malformed embeddings are rejected.
- [ ] Implement FastAPI lifespan and application state resources.
- [ ] Implement shared HTTP client, granular timeouts, bounded retry/backoff, and response validation.
- [ ] Add upload and resource limit settings.
- [ ] Run runtime/model tests and the existing suite.

### Task 2: Durable asynchronous ingestion and document versions

**Files:**
- Create: `rag/ingestion/jobs.py`
- Create: `rag/ingestion/worker.py`
- Create: `rag/ingestion/reconciliation.py`
- Modify: `rag/ingestion/pipeline.py`
- Modify: `rag/storage/repositories.py`
- Modify: `rag/storage/minio_store.py`
- Modify: `app/api/documents.py`
- Create: `app/api/ingestion_jobs.py`
- Create: `migrations/versions/0005_ingestion_v2.py`
- Test: `tests/test_ingestion_jobs.py`
- Test: `tests/test_ingestion_worker.py`

**Interfaces:**
- `IngestionPipeline.enqueue_document(...) -> EmbedDocumentResponse`
- `IngestionWorker.run_once() -> bool`
- `DocumentRepository.claim_next_job(worker_id)`
- `GET /v1/ingestion-jobs/{job_id}`
- `POST /v1/ingestion-jobs/{job_id}/retry`

- [ ] Add tests for true queued responses, job state transitions, retries, idempotency, version activation, and failed-stage compensation.
- [ ] Add job/version/staging database fields and constraints.
- [ ] Change upload/update APIs to persist raw content and enqueue work only.
- [ ] Implement worker claim, heartbeat, parsing, chunking, embedding, indexing, validation, activation, and failure updates.
- [ ] Implement reconciliation checks for PostgreSQL, MinIO, and Milvus.
- [ ] Run ingestion tests and the full suite.

### Task 3: Structured parsing, token-aware chunking, and stable context keys

**Files:**
- Create: `rag/ingestion/tokenizer.py`
- Modify: `rag/ingestion/parsers.py`
- Modify: `rag/ingestion/chunker.py`
- Modify: `rag/ingestion/cleaner.py`
- Test: `tests/test_structured_parsing.py`
- Test: `tests/test_token_chunking.py`

**Interfaces:**
- `ParsedBlock`, `ParsedDocument.blocks`
- `TokenCounter.count(text)`
- `chunk_document(document_id, version, parsed, metadata, config)`

- [ ] Add tests for PDF pages, DOCX headings/tables, spreadsheet row ranges, Chinese token counts, semantic boundaries, and stable chunk IDs.
- [ ] Return structured blocks with page/title/position metadata.
- [ ] Implement tokenizer-based target/max/overlap limits.
- [ ] Generate stable content hashes, context keys, parent IDs, and chunk IDs.
- [ ] Run parser/chunker tests and the full suite.

### Task 4: Milvus V2, lexical quality, and retrieval controls

**Files:**
- Modify: `rag/storage/milvus_schema.py`
- Modify: `rag/storage/milvus_collection_manager.py`
- Modify: `rag/storage/milvus_store.py`
- Create: `rag/storage/vector_migration.py`
- Modify: `rag/retrieval/options.py`
- Modify: `rag/retrieval/pipeline.py`
- Modify: `rag/retrieval/fusion.py`
- Modify: `rag/retrieval/postgres_store.py`
- Create: `rag/retrieval/lexical.py`
- Create: `migrations/versions/0006_retrieval_v3.py`
- Test: `tests/test_milvus_v2_filters.py`
- Test: `tests/test_retrieval_controls.py`

**Interfaces:**
- Milvus V2 fields include `metadata`, `language`, `page_start`, `page_end`.
- `compile_milvus_metadata_filter(metadata) -> str`
- Effective options include RRF weights, thresholds, rerank pool, and per-document limits.

- [ ] Add tests for safe metadata filter compilation, V2 schema, score normalization, thresholds, document diversity, and configurable RRF.
- [ ] Add V2 collection schema and a reindex/alias migration service.
- [ ] Store filterable metadata in Milvus and execute filters before ANN search.
- [ ] Add language-aware lexical normalization and weighted vectors.
- [ ] Add score semantics, candidate thresholds, per-document caps, and configurable fusion.
- [ ] Run retrieval tests and the full suite.

### Task 5: Token-budgeted generation, abstention, and verified citations

**Files:**
- Modify: `rag/retrieval/context.py`
- Create: `rag/retrieval/generation.py`
- Create: `rag/retrieval/citations.py`
- Modify: `rag/models/endpoints.py`
- Modify: `rag/retrieval/pipeline.py`
- Modify: `rag/schemas.py`
- Test: `tests/test_context_budget.py`
- Test: `tests/test_citation_validation.py`

**Interfaces:**
- `GeneratedAnswer(answer, cited_chunk_ids, abstained, abstention_reason)`
- `build_context(chunks, token_counter, budget)`
- `validate_citations(generated, chunks)`

- [ ] Add tests for token budgets, source boundaries, unknown citation IDs, abstention, and prompt-injection-resistant instructions.
- [ ] Request JSON-schema-compatible model output.
- [ ] Validate citation IDs and retry one malformed response.
- [ ] Add answer status, trace ID, timings, and final score semantics to responses.
- [ ] Run generation tests and the full suite.

### Task 6: Observability and evaluation gates

**Files:**
- Modify: `rag/observability.py`
- Modify: `rag/retrieval/postgres_store.py`
- Modify: `rag/retrieval/pipeline.py`
- Modify: `rag/evaluation/deterministic_metrics.py`
- Modify: `rag/evaluation/runner.py`
- Create: `rag/evaluation/gates.py`
- Create: `evals/datasets/golden.jsonl`
- Create: `evals/datasets/adversarial.jsonl`
- Modify: `.github/workflows/rag-eval.yml`
- Create: `migrations/versions/0007_observability.py`
- Test: `tests/test_evaluation_gates.py`
- Test: `tests/test_query_logging.py`

**Interfaces:**
- Query/retrieval logs record trace, stage scores, selection, citation, models, usage, and latency.
- Evaluation supports nDCG, filter accuracy, leakage, duplicate rate, abstention accuracy, baseline comparison, and nonzero exit on gate failure.

- [ ] Add tests for new deterministic metrics, baseline comparison, tag grouping, leakage hard gates, and query log payloads.
- [ ] Add Prometheus metrics and OpenTelemetry spans.
- [ ] Persist query and retrieval stage records.
- [ ] Add versioned fixture datasets and gate configuration.
- [ ] Update CI to run deterministic smoke gates and nightly RAGAS.
- [ ] Run evaluation tests and the full suite.

### Task 7: Integration, security, load, and operations

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/security.yml`
- Create: `tests/integration/test_end_to_end.py`
- Create: `tests/integration/test_failure_recovery.py`
- Create: `tests/integration/mock_model_server.py`
- Create: `load/locustfile.py`
- Create: `Dockerfile`
- Create: `docs/runbook.md`
- Create: `docs/slo.md`
- Create: `docs/backup-restore.md`

**Interfaces:**
- CI runs migration, service integration, security scans, and evaluation smoke gates.
- Operational documentation defines recovery, SLOs, and deployment checks.

- [ ] Add integration tests for upload, worker completion, hybrid retrieval, update, purge, isolation, and injected failures.
- [ ] Add dependency audit, static security scan, and artifact/SBOM generation.
- [ ] Add load scenario and production container.
- [ ] Document migration, rollback, backup, restore, reconciliation, alerting, and incident response.
- [ ] Run all available CI workflows and record remaining environment-dependent checks.
