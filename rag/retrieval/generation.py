from rag.schemas import GeneratedAnswer


def normalize_generated_answer(value: GeneratedAnswer | str) -> GeneratedAnswer:
    if isinstance(value, GeneratedAnswer):
        return value
    return GeneratedAnswer(
        answer=value,
        cited_chunk_ids=[],
        abstained=not bool(value.strip()),
        abstention_reason="empty_answer" if not value.strip() else None,
    )
