# API

## Embed document

`POST /v1/documents/embed`

Multipart fields:

- `knowledge_base_id`
- `title`
- `source_uri`
- `file`

## Soft delete document

`DELETE /v1/documents/{document_id}`

Marks a document inactive.

## Hard delete document

`DELETE /v1/documents/{document_id}/purge`

Permanently removes document content, chunks, vectors, keyword index rows, and MinIO objects. Requires admin-capable tenant scope.

## Retrieval search

`POST /v1/retrieval/search`

Set `options.agent_search=true` to return answer generation fields in addition to retrieved chunks.
