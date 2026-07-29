# RAG V2 Retrieval and RAGAS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every retrieval capability declared by the API execute real behavior, add deterministic and RAGAS evaluation, and keep the existing multi-tenant FastAPI/PostgreSQL/Milvus architecture compatible.

**Architecture:** Resolve request options into a non-null effective configuration, run vector and PostgreSQL full-text retrievers independently, filter and hydrate through PostgreSQL, fuse hybrid candidates with weighted RRF, optionally rerank and generate an answer, and expose effective diagnostics. Evaluation calls the real HTTP API and computes deterministic retrieval metrics plus optional RAGAS metrics.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL full-text search, Milvus, Pydantic v2, pytest, RAGAS 0.4.3.

## Global Constraints

- Preserve `/v1/retrieval/search` compatibility.
- Never silently ignore an explicitly enabled retrieval capability.
- Keep trusted tenant and knowledge-base filters on every retrieval path.
- Metadata filters use scalar equality with AND semantics.
- RAGAS remains an optional dependency and never runs in the production request path.
- All behavior changes receive tests before implementation.

---

### Task 1: Effective Retrieval Options

**Files:**
- Create: `rag/retrieval/options.py`
- Modify: `rag/schemas.py`
- Test: `tests/test_retrieval_options.py`

**Interfaces:**
- Produces: `resolve_retrieval_options(settings, options) -> EffectiveRetrievalOptions`.

- [ ] Write tests for environment defaults, explicit overrides, hybrid normalization, invalid disabled retrievers, and `final_k <= top_k`.
- [ ] Run the focused tests and confirm missing implementation failures.
- [ ] Add effective option models and resolver.
- [ ] Run focused tests and the schema tests.

### Task 2: Filtered Full-Text Retrieval

**Files:**
- Create: `rag/retrieval/lexical.py`
- Modify: `rag/storage/repositories.py`
- Create: `migrations/versions/0004_retrieval_v2.py`
- Test: `tests/test_lexical_retrieval.py`

**Interfaces:**
- Produces: `DocumentRepository.full_text_search(...) -> list[RetrievedChunk]`.
- Produces: filtered `hydrate_chunks(..., document_ids, metadata)` preserving candidate order.

- [ ] Write repository tests for tenant/KB scope, document filters, metadata filters, and stable hydration order.
- [ ] Add generated `search_vector`, GIN and JSONB indexes in migration 0004.
- [ ] Implement parameterized PostgreSQL full-text search and filtered hydration.
- [ ] Run focused repository tests.

### Task 3: Vector Filters and Hybrid Orchestration

**Files:**
- Modify: `rag/storage/milvus_store.py`
- Modify: `rag/retrieval/pipeline.py`
- Modify: `rag/retrieval/fusion.py`
- Test: `tests/test_retrieval_pipeline.py`
- Test: `tests/test_fusion.py`

**Interfaces:**
- Consumes: effective options and repository full-text retrieval.
- Produces: real vector, full-text, and hybrid execution with weighted RRF.

- [ ] Write failing tests proving each mode invokes the expected retriever, filters reach both paths, and hybrid results are fused.
- [ ] Add document ID filtering to Milvus and filtered PostgreSQL hydration for metadata.
- [ ] Implement parallel hybrid retrieval and weighted RRF.
- [ ] Preserve per-stage scores and apply reranking after fusion.
- [ ] Run focused and existing retrieval tests.

### Task 4: Transaction and Capability Errors

**Files:**
- Modify: `app/api/dependencies.py`
- Modify: `rag/errors.py`
- Test: `tests/test_database_session.py`

**Interfaces:**
- Produces: request-scoped commit on success and rollback on exception.

- [ ] Write failing tests for commit and rollback behavior.
- [ ] Implement transaction lifecycle.
- [ ] Add explicit invalid-option and unavailable-capability errors.
- [ ] Run focused tests.

### Task 5: Deterministic Evaluation and RAGAS

**Files:**
- Create: `rag/evaluation/__init__.py`
- Create: `rag/evaluation/deterministic_metrics.py`
- Create: `rag/evaluation/client.py`
- Create: `rag/evaluation/runner.py`
- Create: `evals/datasets/smoke.jsonl`
- Modify: `pyproject.toml`
- Test: `tests/test_evaluation_metrics.py`

**Interfaces:**
- Produces: Hit Rate@K, Precision@K, Recall@K, MRR and an optional RAGAS runner using the real API.

- [ ] Write failing deterministic metric tests.
- [ ] Implement deterministic metrics.
- [ ] Add HTTP evaluation client and JSONL runner.
- [ ] Add optional `eval` dependencies with `ragas==0.4.3`.
- [ ] Run evaluation tests without requiring RAGAS installation.

### Task 6: CI and Documentation

**Files:**
- Create: `.github/workflows/rag-eval.yml`
- Modify: `README.md`
- Modify: `.env.example`

- [ ] Add an opt-in/manual evaluation workflow with API and evaluator secrets.
- [ ] Document exact behavior of vector, full-text, hybrid, filters, and RAGAS commands.
- [ ] Run Ruff and the complete test suite in GitHub Actions.

### Task 7: Verification and Pull Request

- [ ] Inspect the complete branch diff for accidental unrelated changes.
- [ ] Confirm CI status for the branch commit.
- [ ] Open a draft pull request to `main` with architecture, migration, test, and deployment notes.
- [ ] Report any verification limitations honestly.