from typing import Any, Self

import httpx


class RAGApiClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout)

    async def search(
        self,
        *,
        knowledge_base_id: str,
        query: str,
        options: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self.client.post(
            f"{self.base_url}/v1/retrieval/search",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "knowledge_base_id": knowledge_base_id,
                "query": query,
                "options": options or {},
                "filters": filters or {},
            },
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self.close()
