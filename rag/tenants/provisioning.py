from __future__ import annotations

import asyncio
from dataclasses import dataclass

from rag.errors import NotFoundError, ServiceUnavailableError
from rag.storage.vector_resources import TenantVectorResource


@dataclass(frozen=True)
class TenantProvisioningResult:
    tenant: dict[str, object]
    owner: dict[str, object]
    knowledge_base_id: str | None
    api_key: dict[str, object] | None
    vector_resource: TenantVectorResource


class TenantProvisioningService:
    def __init__(
        self,
        *,
        session,
        management_repository,
        vector_repository,
        collection_manager,
    ) -> None:
        self.session = session
        self.management_repository = management_repository
        self.vector_repository = vector_repository
        self.collection_manager = collection_manager

    async def create_tenant(
        self,
        *,
        name: str,
        slug: str,
        owner_email: str,
        owner_display_name: str | None,
        default_knowledge_base_name: str | None,
    ) -> TenantProvisioningResult:
        tenant, owner, knowledge_base_id = (
            await self.management_repository.create_tenant_bootstrap(
                name=name,
                slug=slug,
                owner_email=owner_email,
                owner_display_name=owner_display_name,
                default_knowledge_base_name=default_knowledge_base_name,
            )
        )
        resource = await self.vector_repository.create_pending(str(tenant["id"]))
        await self.session.commit()
        return await self._provision(
            tenant=tenant,
            owner=owner,
            knowledge_base_id=knowledge_base_id,
            resource=resource,
            issue_initial_key=True,
        )

    async def retry_vector_resource(self, tenant_id: str) -> TenantProvisioningResult:
        context = await self.management_repository.get_bootstrap_context(tenant_id)
        if context is None:
            raise NotFoundError("tenant not found")
        tenant, owner, knowledge_base_id = context
        resource = await self.vector_repository.get(tenant_id)
        if resource is None:
            resource = await self.vector_repository.create_pending(tenant_id)
            await self.session.commit()
        if resource.status == "ready" and tenant["status"] == "active":
            return TenantProvisioningResult(
                tenant=tenant,
                owner=owner,
                knowledge_base_id=knowledge_base_id,
                api_key=None,
                vector_resource=resource,
            )
        return await self._provision(
            tenant=tenant,
            owner=owner,
            knowledge_base_id=knowledge_base_id,
            resource=resource,
            issue_initial_key=True,
        )

    async def _provision(
        self,
        *,
        tenant: dict[str, object],
        owner: dict[str, object],
        knowledge_base_id: str | None,
        resource: TenantVectorResource,
        issue_initial_key: bool,
    ) -> TenantProvisioningResult:
        tenant_id = str(tenant["id"])
        try:
            await self.vector_repository.mark_creating(resource.id)
            await self.session.commit()
            await asyncio.to_thread(self.collection_manager.ensure_collection, resource)
            await self.vector_repository.mark_ready(resource.id)
            await self.management_repository.activate_tenant(tenant_id)
            api_key = None
            if issue_initial_key:
                api_key = await self.management_repository.issue_api_key(
                    tenant_id=tenant_id,
                    user_id=str(owner["id"]),
                    name="Initial owner key",
                    scope_limit=None,
                    knowledge_base_limit=None,
                    expires_at=None,
                    created_by_user_id=str(owner["id"]),
                )
            await self.management_repository.audit(
                tenant_id=tenant_id,
                actor_user_id=str(owner["id"]),
                actor_api_key_id=api_key["id"] if api_key else None,
                action="tenant.created",
                target_type="tenant",
                target_id=tenant_id,
                after_state={"vector_collection": resource.logical_alias},
            )
            await self.session.commit()
        except Exception as exc:
            await self.session.rollback()
            await self.vector_repository.mark_failed(resource.id, str(exc))
            await self.session.commit()
            raise ServiceUnavailableError(
                f"tenant {tenant_id} vector collection provisioning failed"
            ) from exc

        refreshed = await self.vector_repository.get(tenant_id)
        if refreshed is None:
            raise ServiceUnavailableError(
                f"tenant {tenant_id} vector collection provisioning failed"
            )
        active_tenant = {**tenant, "status": "active"}
        return TenantProvisioningResult(
            tenant=active_tenant,
            owner=owner,
            knowledge_base_id=knowledge_base_id,
            api_key=api_key,
            vector_resource=refreshed,
        )
