from typing import Protocol

from rag.errors import UnauthorizedError
from rag.schemas import TenantContext


class TenantRepositoryProtocol(Protocol):
    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        ...


async def resolve_tenant_context(
    api_key: str,
    repository: TenantRepositoryProtocol,
) -> TenantContext:
    context = await repository.get_context_for_api_key(api_key)
    if context is None:
        raise UnauthorizedError("invalid API key")
    return context

