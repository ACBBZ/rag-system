import pytest

from rag.ingestion.parsers import parse_document


@pytest.mark.asyncio
async def test_parse_txt_document():
    parsed = await parse_document("note.txt", b"hello\nworld", None)
    assert parsed.text == "hello\nworld"
    assert parsed.metadata["file_type"] == "txt"


@pytest.mark.asyncio
async def test_parse_csv_document_as_rows():
    parsed = await parse_document("table.csv", b"name,score\nAda,10\nTom,9\n", None)
    assert "row 1" in parsed.text
    assert "Ada" in parsed.text
    assert parsed.metadata["file_type"] == "csv"
