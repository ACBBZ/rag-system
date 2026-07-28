from pydantic import BaseModel, Field


class ChunkInput(BaseModel):
    document_id: str
    text: str
    token_count: int
    title_path: list[str] = Field(default_factory=list)
    page: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


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

    chunks: list[ChunkInput] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(
                ChunkInput(
                    document_id=document_id,
                    text=chunk,
                    token_count=len(chunk.split()),
                    title_path=[str(metadata["title"])] if "title" in metadata else [],
                    page=(
                        int(metadata["page"])
                        if "page" in metadata and metadata["page"] is not None
                        else None
                    ),
                    metadata=metadata,
                )
            )
        if end == len(text):
            break
        start = max(0, end - overlap)
    return chunks
