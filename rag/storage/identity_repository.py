from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.authz import parse_api_key, validate_key_lifecycle, verify_api_key_secret
from rag.config import Settings
from rag.schemas import TenantContext, TenantVectorRoute
from rag.storage.milvus_schema import schema_fingerprint


class DynamicTenantRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        if not api_key.startswith("rag_live_") or "." not in api_key:
            return await self._get_legacy_context(api_key)

        key_id, secret = parse_api_key(api_key)
        result = await self.session.execute(
            text(
                """
                select k.id as api_key_id, k.tenant_id, k.organization_id, k.user_id,
                       k.secret_hash, k.scope_limit, k.knowledge_base_limit,
                       k.is_active, k.revoked_at, k.expires_at,
                       t.status as tenant_status,
                       u.status as user_status,
                       m.role as tenant_role,
                       m.status as membership_status,
                       coalesce(array_agg(g.permission) filter (
                           where g.permission is not null
                             and (g.expires_at is null or g.expires_at > now())
                       ), '{}') as direct_permissions
                from api_keys k
                join tenants t on t.id = k.tenant_id
                join users u on u.id = k.user_id and u.tenant_id = k.tenant_id
                join user_memberships m on m.user_id = k.user_id and m.tenant_id = k.tenant_id
                left join membership_scope_grants g
                  on g.user_id = k.user_id and g.tenant_id = k.tenant_id
                where k.id = :key_id
                group by k.id, t.status, u.status, m.role, m.status
                """
            ),
            {"key_id": key_id},
        )
        row = result.mappings().first()
        if row is None or not row["secret_hash"]:
            return None
        if not verify_api_key_secret(secret, row["secret_hash"], self.settings.api_key_pepper):
            return None
        validate_key_lifecycle(
            is_active=row["is_active"],
            revoked_at=row["revoked_at"],
            expires_at=row["expires_at"],
        )
        if row["tenant_status"] != "active" or row["user_status"] != "active":
            return None
        if row["membership_status"] != "active":
            return None

        acl_result = await self.session.execute(
            text(
                """
                select kb.id as knowledge_base_id, a.role
                from knowledge_bases kb
                left join knowledge_base_acl a
                  on a.tenant_id = kb.tenant_id
                 and a.knowledge_base_id = kb.id
                 and a.user_id = :user_id
                where kb.tenant_id = :tenant_id
                  and kb.status = 'active'
                  and (:is_admin or a.user_id is not null)
                """
            ),
            {
                "tenant_id": row["tenant_id"],
                "user_id": row["user_id"],
                "is_admin": row["tenant_role"] in {"tenant_owner", "tenant_admin"},
            },
        )
        acl_rows = list(acl_result.mappings())
        vector_route = await self._get_vector_route(row["tenant_id"])
        await self.session.execute(
            text("update api_keys set last_used_at = now() where id = :key_id"),
            {"key_id": key_id},
        )
        return TenantContext(
            tenant_id=row["tenant_id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            api_key_id=row["api_key_id"],
            tenant_role=row["tenant_role"] or "member",
            direct_permissions=list(row["direct_permissions"] or []),
            scope_limit=list(row["scope_limit"]) if row["scope_limit"] is not None else None,
            knowledge_base_limit=(
                list(row["knowledge_base_limit"])
                if row["knowledge_base_limit"] is not None
                else None
            ),
            knowledge_base_ids=[item["knowledge_base_id"] for item in acl_rows],
            roles=[
                f"kb:{item['knowledge_base_id']}:{item['role']}"
                for item in acl_rows
                if item["role"]
            ],
            vector_route=vector_route,
        )

    async def _get_legacy_context(self, api_key: str) -> TenantContext | None:
        result = await self.session.execute(
            text(
                """
                select tenant_id, organization_id, user_id, allowed_scopes, knowledge_base_ids
                from api_keys
                where key_hash = :key_hash and is_active = true
                """
            ),
            {"key_hash": api_key},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return TenantContext(
            tenant_id=row["tenant_id"],
            organization_id=row["organization_id"],
            user_id=row["user_id"],
            knowledge_base_ids=list(row["knowledge_base_ids"]),
            allowed_scopes=list(row["allowed_scopes"]),
            direct_permissions=list(row["allowed_scopes"]),
            scope_limit=list(row["allowed_scopes"]),
            knowledge_base_limit=list(row["knowledge_base_ids"]),
            vector_route=await self._get_vector_route(row["tenant_id"]),
        )

    async def _get_vector_route(self, tenant_id: str) -> TenantVectorRoute | None:
        result = await self.session.execute(
            text(
                """
                select logical_alias, physical_collection, embedding_model,
                       embedding_dimension, metric_type, index_type, search_params,
                       schema_fingerprint
                from tenant_vector_resources
                where tenant_id = :tenant_id and status = 'ready'
                limit 1
                """
            ),
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()
        if row is None or row["schema_fingerprint"] != schema_fingerprint(self.settings):
            return None
        return TenantVectorRoute(
            collection_alias=row["logical_alias"],
            physical_collection=row["physical_collection"],
            embedding_model=row["embedding_model"],
            embedding_dimension=int(row["embedding_dimension"]),
            metric_type=row["metric_type"],
            index_type=row["index_type"],
            search_params=dict(row["search_params"] or {}),
        )
