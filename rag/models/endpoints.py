import base64
from typing import Any

import httpx

from rag.config import Settings


class ModelEndpointClient:
    def __init__(self, settings: Settings, timeout: float = 60.0) -> None:
        self.settings = settings
        self.timeout = timeout

    async def _post(self, url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        payload = {"model": self.settings.embedding_model, "input": texts}
        data = await self._post(
            self.settings.embedding_url,
            self.settings.embedding_api_key,
            payload,
        )
        return [item["embedding"] for item in data["data"]]

    async def rerank(self, query: str, texts: list[str]) -> list[float]:
        payload = {"model": self.settings.rerank_model, "query": query, "documents": texts}
        data = await self._post(self.settings.rerank_url, self.settings.rerank_api_key, payload)
        return [float(score) for score in data["scores"]]

    async def rewrite(self, query: str) -> str:
        payload = {
            "model": self.settings.query_rewrite_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Rewrite the query for retrieval. Return only the rewritten query.",
                },
                {"role": "user", "content": query},
            ],
        }
        data = await self._post(
            self.settings.query_rewrite_url,
            self.settings.query_rewrite_api_key,
            payload,
        )
        return data["choices"][0]["message"]["content"].strip()

    async def answer(self, query: str, context: str) -> tuple[str, dict[str, int]]:
        payload = {
            "model": self.settings.llm_model,
            "messages": [
                {
                    "role": "system",
                    "content": "Answer using only the supplied context. Cite sources by chunk id.",
                },
                {"role": "user", "content": f"Question:\n{query}\n\nContext:\n{context}"},
            ],
        }
        data = await self._post(self.settings.llm_url, self.settings.llm_api_key, payload)
        usage = data.get("usage", {})
        return data["choices"][0]["message"]["content"].strip(), {
            "prompt_tokens": int(usage.get("prompt_tokens", 0)),
            "completion_tokens": int(usage.get("completion_tokens", 0)),
        }

    async def ocr(self, image_bytes: bytes, mime_type: str) -> str:
        payload = {
            "model": self.settings.ocr_model,
            "mime_type": mime_type,
            "image": base64.b64encode(image_bytes).decode("ascii"),
        }
        data = await self._post(self.settings.ocr_url, self.settings.ocr_api_key, payload)
        return data["text"]
