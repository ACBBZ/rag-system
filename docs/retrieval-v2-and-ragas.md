# Retrieval V2 and RAGAS Evaluation

## Retrieval modes

`POST /v1/retrieval/search` now supports a preferred `retrieval_mode` option:

- `vector`: Milvus vector search only.
- `full_text`: PostgreSQL full-text search only.
- `hybrid`: vector and full-text search run concurrently and are merged with weighted Reciprocal Rank Fusion.
- `auto`: resolve the mode from the legacy boolean fields and environment defaults.

The legacy fields remain supported. Request values override environment defaults. A request that disables every retriever returns an explicit validation error.

```json
{
  "knowledge_base_id": "kb_123",
  "query": "What is the annual leave policy?",
  "options": {
    "retrieval_mode": "hybrid",
    "query_rewrite": true,
    "rerank": true,
    "agent_search": true,
    "top_k": 30,
    "final_k": 6
  },
  "filters": {
    "document_ids": ["doc_123"],
    "metadata": {
      "department": "hr",
      "language": "en"
    }
  }
}
```

Document filters are applied in Milvus and PostgreSQL. Metadata filters are applied by PostgreSQL full-text search and by the PostgreSQL hydration stage for vector results. When a metadata filter is present, vector retrieval over-fetches candidates before hydration to reduce recall loss caused by post-filtering.

The response includes `effective_options` so callers can inspect the actual mode and feature switches used for the request. Each chunk also retains per-stage scores in `scores` and retrieval stages in `retrieval_methods`.

## Database migration

Apply migration `0004_retrieval_v2` before enabling full-text or hybrid search:

```bash
alembic upgrade head
```

The migration:

- converts `chunks.metadata` to `jsonb`;
- adds a generated `search_vector` column;
- creates a GIN index for full-text search;
- creates a GIN index for metadata filters;
- creates a tenant/knowledge-base retrieval scope index.

`full_text` and `hybrid` modes require this migration. Vector-only mode remains compatible with the existing Milvus V1 collection schema.

## Environment defaults

```env
DEFAULT_QUERY_REWRITE_ENABLED=false
DEFAULT_VECTOR_SEARCH_ENABLED=true
DEFAULT_FULL_TEXT_SEARCH_ENABLED=false
DEFAULT_HYBRID_SEARCH_ENABLED=false
DEFAULT_RERANK_ENABLED=false
DEFAULT_AGENT_SEARCH_ENABLED=false
```

A request option set to `null` inherits the corresponding environment value. An explicit `true` or `false` overrides it.

## Deterministic evaluation

Install development dependencies and run:

```bash
pytest tests/test_evaluation_metrics.py -v
```

The evaluation package provides:

- Hit Rate@K;
- Precision@K;
- Recall@K;
- Mean Reciprocal Rank.

Run the real HTTP API against a JSONL dataset:

```bash
export RAG_EVAL_BASE_URL=http://localhost:8000
export RAG_EVAL_API_KEY=rag_live_example.secret

python -m rag.evaluation.runner \
  --dataset evals/datasets/smoke.jsonl \
  --output evals/reports/results.jsonl
```

The bundled smoke dataset is a template. Replace its knowledge-base, reference answer, and reference chunk IDs with stable fixture data before using it as a quality gate.

## RAGAS

Install the optional evaluation dependencies:

```bash
python -m pip install -e '.[eval]'
```

Configure an OpenAI-compatible evaluator:

```env
RAGAS_EVALUATOR_BASE_URL=https://api.openai.com/v1
RAGAS_EVALUATOR_API_KEY=replace-me
RAGAS_EVALUATOR_MODEL=gpt-4o-mini
RAGAS_EVALUATOR_EMBEDDING_MODEL=text-embedding-3-small
```

Run:

```bash
python -m rag.evaluation.runner \
  --dataset evals/datasets/smoke.jsonl \
  --output evals/reports/results.jsonl \
  --ragas
```

The runner uses the RAGAS 0.4 collections API and records:

- Faithfulness;
- Answer Relevancy;
- Context Precision;
- Context Recall;
- Factual Correctness.

RAGAS is never imported by the production API path. The GitHub Actions `RAG Evaluation` workflow can run the same evaluation manually or on a schedule after its secrets and evaluator variables are configured.

## Current metadata-filter limitation

The fixed Milvus V1 collection does not contain a generic metadata JSON field. Therefore metadata filtering for vector results is enforced during PostgreSQL hydration after an over-fetched Milvus search. This is correct with respect to returned results, but highly selective metadata filters can reduce recall.

A future Milvus V2 collection should store approved filterable metadata fields and apply the same filter before approximate nearest-neighbor search. Until that migration is deployed, quality tests should include representative selective metadata-filter cases.
