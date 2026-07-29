from __future__ import annotations

from hashlib import sha256

from pydantic import BaseModel, Field

from rag.ingestion.parsers import ParsedDocument
from rag.ingestion.tokenizer import TokenCounter


class ChunkingConfig(BaseModel):
    target_tokens: int = Field(default=450, ge=16)
    max_tokens: int = Field(default=600, ge=32)
    overlap_tokens: int = Field(default=60, ge=0)


class ChunkInput(BaseModel):
    chunk_id: str
    context_key: str
    document_id: str
    document_version: int
    ordinal: int
    text: str
    token_count: int
    content_hash: str
    parent_chunk_id: str | None = None
    title_path: list[str] = Field(default_factory=list)
    page: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    language: str = "und"
    metadata: dict[str, object] = Field(default_factory=dict)


def chunk_document(
    document_id: str,
    version: int,
    parsed: ParsedDocument,
    metadata: dict[str, object],
    *,
    config: ChunkingConfig | None = None,
    token_counter: TokenCounter | None = None,
) -> list[ChunkInput]:
    active_config = config or ChunkingConfig()
    if active_config.target_tokens > active_config.max_tokens:
        raise ValueError("target_tokens cannot exceed max_tokens")
    if active_config.overlap_tokens >= active_config.max_tokens:
        raise ValueError("overlap_tokens must be smaller than max_tokens")
    counter = token_counter or TokenCounter()
    chunks: list[ChunkInput] = []
    ordinal = 0
    for block in parsed.blocks:
        text = block.text.strip()
        if not text or block.block_type == "heading":
            continue
        tokens = counter.encode(text)
        start = 0
        while start < len(tokens):
            end = min(start + active_config.max_tokens, len(tokens))
            piece_tokens = tokens[start:end]
            piece = counter.decode(piece_tokens).strip()
            if piece:
                ordinal += 1
                content_hash = sha256(piece.encode("utf-8")).hexdigest()
                source_key = str(
                    metadata.get("source_key")
                    or metadata.get("source_uri")
                    or metadata.get("title")
                    or document_id
                )
                context_key = (
                    f"{source_key}:v{version}:p{block.page or 0}:b{block.position}:c{ordinal}:"
                    f"{content_hash[:16]}"
                )
                chunk_id = f"chk_{sha256(context_key.encode('utf-8')).hexdigest()[:32]}"
                language = str(metadata.get("language") or block.metadata.get("language") or "und")
                chunks.append(
                    ChunkInput(
                        chunk_id=chunk_id,
                        context_key=context_key,
                        document_id=document_id,
                        document_version=version,
                        ordinal=ordinal,
                        text=piece,
                        token_count=len(piece_tokens),
                        content_hash=content_hash,
                        title_path=list(block.title_path),
                        page=block.page,
                        page_start=block.page,
                        page_end=block.page,
                        language=language,
                        metadata={**metadata, **block.metadata},
                    )
                )
            if end >= len(tokens):
                break
            start = max(0, end - active_config.overlap_tokens)
    return chunks


def chunk_text(
    document_id: str,
    text: str,
    metadata: dict[str, object],
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[ChunkInput]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")
    counter = TokenCounter()
    chunks: list[ChunkInput] = []
    start = 0
    ordinal = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            ordinal += 1
            content_hash = sha256(piece.encode("utf-8")).hexdigest()
            context_key = f"{document_id}:v1:c{ordinal}:{content_hash[:16]}"
            chunks.append(
                ChunkInput(
                    chunk_id=f"chk_{sha256(context_key.encode()).hexdigest()[:32]}",
                    context_key=context_key,
                    document_id=document_id,
                    document_version=1,
                    ordinal=ordinal,
                    text=piece,
                    token_count=counter.count(piece),
                    content_hash=content_hash,
                    title_path=[str(metadata["title"])] if metadata.get("title") else [],
                    page=int(metadata["page"]) if metadata.get("page") is not None else None,
                    page_start=int(metadata["page"]) if metadata.get("page") is not None else None,
                    page_end=int(metadata["page"]) if metadata.get("page") is not None else None,
                    language=str(metadata.get("language") or "und"),
                    metadata=metadata,
                )
            )
        if end == len(text):
            break
        start = end - overlap
    return chunks
