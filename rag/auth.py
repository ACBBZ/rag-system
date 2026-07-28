from typing import Protocol

from rag.errors import ForbiddenError, UnauthorizedError
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


def authorize_knowledge_base(
    tenant: TenantContext,
    knowledge_base_id: str,
    required_scope: str,
) -> None:
    if not tenant.can_access_knowledge_base(knowledge_base_id):
        raise ForbiddenError("knowledge base access denied")
    if not tenant.has_scope(required_scope):
        raise ForbiddenError(f"missing scope: {required_scope}")
