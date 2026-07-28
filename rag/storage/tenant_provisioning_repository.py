from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.config import Settings
from rag.storage.repositories import ManagementRepository, new_id


class TenantProvisioningRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.management = ManagementRepository(session, settings)

    async def create_tenant_bootstrap(
        self,
        *,
        name: str,
        slug: str,
        owner_email: str,
        owner_display_name: str | None,
        default_knowledge_base_name: str | None,
    ) -> tuple[dict[str, object], dict[str, object], str | None]:
        tenant_id = new_id("ten")
        owner_id = new_id("usr")
        await self.session.execute(
            text(
                """
                insert into tenants (id, slug, name, status, settings, authz_version)
                values (:id, :slug, :name, 'provisioning', '{}', 1)
                """
            ),
            {"id": tenant_id, "slug": slug, "name": name},
        )
        await self.session.execute(
            text(
                """
                insert into users (
                    id, tenant_id, email, normalized_email, display_name, status
                ) values (
                    :id, :tenant_id, :email, :normalized_email, :display_name, 'active'
                )
                """
            ),
            {
                "id": owner_id,
                "tenant_id": tenant_id,
                "email": owner_email,
                "normalized_email": owner_email.strip().lower(),
                "display_name": owner_display_name,
            },
        )
        await self.session.execute(
            text(
                """
                insert into user_memberships (
                    id, tenant_id, user_id, organization_id, roles, role, status, authz_version
                ) values (
                    :id, :tenant_id, :user_id, null, '["tenant_owner"]',
                    'tenant_owner', 'active', 1
                )
                """
            ),
            {"id": new_id("mem"), "tenant_id": tenant_id, "user_id": owner_id},
        )
        knowledge_base_id = None
        if default_knowledge_base_name:
            knowledge_base_id = await self.management.create_knowledge_base(
                tenant_id=tenant_id,
                user_id=owner_id,
                name=default_knowledge_base_name,
                description=None,
            )
        await self.management.audit(
            tenant_id=tenant_id,
            actor_user_id=owner_id,
            action="tenant.provisioning_started",
            target_type="tenant",
            target_id=tenant_id,
        )
        return (
            {"id": tenant_id, "slug": slug, "name": name, "status": "provisioning"},
            {
                "id": owner_id,
                "tenant_id": tenant_id,
                "email": owner_email,
                "display_name": owner_display_name,
                "status": "active",
                "role": "tenant_owner",
            },
            knowledge_base_id,
        )

    async def activate_tenant(self, tenant_id: str) -> None:
        await self.session.execute(
            text(
                """
                update tenants
                set status = 'active', updated_at = now()
                where id = :tenant_id and status in ('provisioning', 'active')
                """
            ),
            {"tenant_id": tenant_id},
        )

    async def issue_api_key(self, **kwargs):
        return await self.management.issue_api_key(**kwargs)

    async def audit(self, **kwargs) -> None:
        await self.management.audit(**kwargs)

    async def get_bootstrap_context(
        self,
        tenant_id: str,
    ) -> tuple[dict[str, object], dict[str, object], str | None] | None:
        tenant_result = await self.session.execute(
            text("select id, slug, name, status from tenants where id = :tenant_id"),
            {"tenant_id": tenant_id},
        )
        tenant = tenant_result.mappings().first()
        if tenant is None:
            return None
        owner_result = await self.session.execute(
            text(
                """
                select u.id, u.tenant_id, u.email, u.display_name, u.status, m.role
                from users u
                join user_memberships m
                  on m.tenant_id = u.tenant_id and m.user_id = u.id
                where u.tenant_id = :tenant_id and m.role = 'tenant_owner'
                  and m.status = 'active'
                order by u.created_at asc
                limit 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        owner = owner_result.mappings().first()
        if owner is None:
            return None
        kb_result = await self.session.execute(
            text(
                """
                select id from knowledge_bases
                where tenant_id = :tenant_id and created_by_user_id = :owner_id
                  and status = 'active'
                order by created_at asc
                limit 1
                """
            ),
            {"tenant_id": tenant_id, "owner_id": owner["id"]},
        )
        knowledge_base_id = kb_result.scalar_one_or_none()
        return dict(tenant), dict(owner), knowledge_base_id
