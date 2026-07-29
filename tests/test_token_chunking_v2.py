from rag.ingestion.chunker import ChunkingConfig, chunk_document
from rag.ingestion.parsers import ParsedBlock, ParsedDocument
from rag.ingestion.tokenizer import TokenCounter


def test_token_counter_counts_chinese_without_spaces():
    counter = TokenCounter()
    assert counter.count("正式员工每年享有十五天带薪年假") > 5


def test_chunk_document_preserves_structure_and_stable_ids():
    parsed = ParsedDocument(
        blocks=[
            ParsedBlock(
                block_type="heading",
                text="休假制度",
                page=1,
                title_path=["员工手册"],
                position=0,
                metadata={},
            ),
            ParsedBlock(
                block_type="paragraph",
                text="正式员工每年享有十五天带薪年假。" * 20,
                page=1,
                title_path=["员工手册", "休假制度"],
                position=1,
                metadata={},
            ),
        ],
        metadata={"file_type": "pdf"},
    )
    config = ChunkingConfig(target_tokens=60, max_tokens=80, overlap_tokens=10)
    first = chunk_document("doc_1", 1, parsed, {}, config=config)
    second = chunk_document("doc_1", 1, parsed, {}, config=config)

    assert first
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.token_count <= 80 for chunk in first)
    assert all(chunk.page_start == 1 for chunk in first)
    assert any("休假制度" in chunk.title_path for chunk in first)
