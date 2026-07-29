import os

import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_deployed_stack_is_live_and_ready():
    base_url = os.environ.get("RAG_INTEGRATION_BASE_URL")
    if not base_url:
        pytest.skip("RAG_INTEGRATION_BASE_URL is not configured")
    async with httpx.AsyncClient(base_url=base_url, timeout=30) as client:
        live = await client.get("/health/live")
        ready = await client.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code == 200, ready.text
