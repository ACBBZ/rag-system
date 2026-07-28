# rag-system

Production-oriented multi-tenant RAG system.

## First implementation scope

- FastAPI API service
- Postgres metadata and audit storage
- MinIO raw and parsed object storage
- Milvus vector storage
- Remote model endpoints configured through `.env`
- Optional query rewrite, vector search, full-text search, hybrid search, rerank, and agent search

## Local services

```bash
docker compose up -d
```

## Configuration

Copy `.env.example` to `.env` and set model endpoint values:

- `EMBEDDING_URL`, `EMBEDDING_MODEL`, `EMBEDDING_API_KEY`
- `RERANK_URL`, `RERANK_MODEL`, `RERANK_API_KEY`
- `QUERY_REWRITE_URL`, `QUERY_REWRITE_MODEL`, `QUERY_REWRITE_API_KEY`
- `LLM_URL`, `LLM_MODEL`, `LLM_API_KEY`

Model configuration is never accepted in API request bodies.
