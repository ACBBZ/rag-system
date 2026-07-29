from __future__ import annotations

from rag.schemas import Citation, GeneratedAnswer, RetrievedChunk


class CitationValidationError(ValueError):
    pass


def validate_citations(
    generated: GeneratedAnswer,
    chunks: list[RetrievedChunk],
) -> list[Citation]:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    unknown = [
        chunk_id
        for chunk_id in generated.cited_chunk_ids
        if chunk_id not in by_id
    ]
    if unknown:
        raise CitationValidationError(
            "generated answer cited unknown chunk IDs: "
            + ", ".join(sorted(set(unknown)))
        )
    citations: list[Citation] = []
    seen: set[str] = set()
    for chunk_id in generated.cited_chunk_ids:
        if chunk_id in seen:
            continue
        seen.add(chunk_id)
        chunk = by_id[chunk_id]
        citations.append(
            Citation(
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=(
                    str(chunk.source.get("title"))
                    if chunk.source.get("title")
                    else None
                ),
                source_uri=(
                    str(chunk.source.get("source_uri"))
                    if chunk.source.get("source_uri")
                    else None
                ),
                page=(
                    int(chunk.source["page"])
                    if chunk.source.get("page") is not None
                    else None
                ),
                quote=chunk.text[:240],
            )
        )
    return citations
