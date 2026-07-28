import io
from pathlib import Path
from typing import Protocol

import pandas as pd
from docx import Document
from PIL import Image
from pydantic import BaseModel
from pypdf import PdfReader


class OcrCallable(Protocol):
    async def ocr(self, image_bytes: bytes, mime_type: str) -> str:
        ...


class ParsedDocument(BaseModel):
    text: str
    metadata: dict[str, object]


async def parse_document(
    filename: str,
    content: bytes,
    ocr_client: OcrCallable | None,
) -> ParsedDocument:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix in {"txt", "md"}:
        return ParsedDocument(text=content.decode("utf-8"), metadata={"file_type": suffix})
    if suffix == "pdf":
        reader = PdfReader(io.BytesIO(content))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        return ParsedDocument(text=text, metadata={"file_type": suffix, "pages": len(reader.pages)})
    if suffix == "docx":
        doc = Document(io.BytesIO(content))
        paragraphs = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
        table_rows: list[str] = []
        for table_index, table in enumerate(doc.tables, start=1):
            for row_index, row in enumerate(table.rows, start=1):
                cells = " | ".join(cell.text.strip() for cell in row.cells)
                table_rows.append(f"table {table_index} row {row_index}: {cells}")
        return ParsedDocument(
            text="\n".join(paragraphs + table_rows),
            metadata={"file_type": suffix, "tables": len(doc.tables)},
        )
    if suffix == "csv":
        frame = pd.read_csv(io.BytesIO(content))
        return ParsedDocument(text=_frame_to_text(frame), metadata={"file_type": suffix})
    if suffix in {"xlsx", "xls"}:
        sheets = pd.read_excel(io.BytesIO(content), sheet_name=None)
        sections = [f"sheet {name}\n{_frame_to_text(frame)}" for name, frame in sheets.items()]
        return ParsedDocument(
            text="\n\n".join(sections),
            metadata={"file_type": suffix, "sheets": list(sheets)},
        )
    if suffix in {"png", "jpg", "jpeg", "webp"}:
        Image.open(io.BytesIO(content)).verify()
        if ocr_client is None:
            raise ValueError("OCR client is required for image parsing")
        text = await ocr_client.ocr(content, f"image/{'jpeg' if suffix == 'jpg' else suffix}")
        return ParsedDocument(text=text, metadata={"file_type": suffix})
    raise ValueError(f"unsupported file type: {suffix}")


def _frame_to_text(frame: pd.DataFrame) -> str:
    rows = []
    for index, row in frame.fillna("").iterrows():
        cells = ", ".join(f"{column}: {row[column]}" for column in frame.columns)
        rows.append(f"row {index + 1}: {cells}")
    return "\n".join(rows)
