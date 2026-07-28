from rag.ingestion.chunker import chunk_text


def test_chunk_text_preserves_document_and_metadata():
    chunks = chunk_text(
        document_id="doc_1",
        text="alpha beta gamma delta epsilon",
        metadata={"title": "Spec", "page": 1},
        chunk_size=16,
        overlap=4,
    )

    assert len(chunks) >= 2
    assert chunks[0].document_id == "doc_1"
    assert chunks[0].metadata["title"] == "Spec"
    assert chunks[0].text.startswith("alpha")
