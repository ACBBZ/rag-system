from rag.schemas import RetrievedChunk


def build_context(chunks: list[RetrievedChunk], max_chars: int = 12000) -> str:
    sections: list[str] = []
    total = 0
    for chunk in chunks:
        section = f"[chunk_id: {chunk.chunk_id}]\n{chunk.text}"
        if total + len(section) > max_chars:
            break
        sections.append(section)
        total += len(section)
    return "\n\n".join(sections)
