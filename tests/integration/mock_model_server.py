from __future__ import annotations

import hashlib

from fastapi import FastAPI

app = FastAPI()


@app.post("/v1/embeddings")
async def embeddings(payload: dict):
    vectors = []
    for text in payload.get("input", []):
        digest = hashlib.sha256(str(text).encode("utf-8")).digest()
        vector = [
            ((digest[index % len(digest)] / 255.0) * 2) - 1
            for index in range(8)
        ]
        vectors.append({"embedding": vector})
    return {"data": vectors}


@app.post("/v1/rerank")
async def rerank(payload: dict):
    query = str(payload.get("query", "")).casefold()
    scores = [
        sum(token in str(document).casefold() for token in query.split())
        for document in payload.get("documents", [])
    ]
    return {"scores": scores}


@app.post("/v1/chat/completions")
async def chat(payload: dict):
    messages = payload.get("messages", [])
    system = str(messages[0].get("content", "")) if messages else ""
    if "Rewrite the query" in system:
        content = str(messages[-1].get("content", ""))
    else:
        content = (
            '{"answer":"The fixture says employees receive fifteen days of '
            'paid leave.","cited_chunk_ids":[],"abstained":false,'
            '"abstention_reason":null}'
        )
    return {
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }


@app.post("/v1/ocr")
async def ocr(payload: dict):
    return {"text": "fixture OCR text"}
