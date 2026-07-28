from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.authz import hash_api_key_secret, parse_api_key, validate_key_lifecycle, verify_api_key_secret
from rag.config import Settings
from rag.schemas import RetrievedChunk, TenantContext


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


@dataclass
class StoredChunk:
    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, object]


class TenantRepository:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings

    async def get_context_for_api_key(self, api_key: str) -> TenantContext | None:
        if api_key.startswith("rag_live_") and "." in api_key:
            if self.settings is None:
                return None
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
            )

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
            roles=[],
            allowed_scopes=list(row["allowed_scopes"]),
            tenant_role="member",
            direct_permissions=list(row["allowed_scopes"]),
            scope_limit=list(row["allowed_scopes"]),
            knowledge_base_limit=list(row["knowledge_base_ids"]),
        )


class AuthorizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_knowledge_base_role(
        self, tenant_id: str, user_id: str, knowledge_base_id: str
    ) -> str | None:
        result = await self.session.execute(
            text(
                """
                select a.role
                from knowledge_bases kb
                left join knowledge_base_acl a
                  on a.tenant_id = kb.tenant_id
                 and a.knowledge_base_id = kb.id
                 and a.user_id = :user_id
                where kb.id = :knowledge_base_id
                  and kb.tenant_id = :tenant_id
                  and kb.status = 'active'
                """
            ),
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
            },
        )
        row = result.mappings().first()
        if row is None:
            return None
        return row["role"]

    async def knowledge_base_exists(self, tenant_id: str, knowledge_base_id: str) -> bool:
        result = await self.session.execute(
            text(
                """
                select 1 from knowledge_bases
                where id = :knowledge_base_id and tenant_id = :tenant_id and status = 'active'
                """
            ),
            {"tenant_id": tenant_id, "knowledge_base_id": knowledge_base_id},
        )
        return result.first() is not None


class ManagementRepository:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def create_tenant(
        self,
        *,
        name: str,
        slug: str,
        owner_email: str,
        owner_display_name: str | None,
        default_knowledge_base_name: str | None,
    ) -> tuple[dict[str, object], dict[str, object], str | None, dict[str, object]]:
        tenant_id = new_id("ten")
        owner_id = new_id("usr")
        membership_id = new_id("mem")
        await self.session.execute(
            text(
                """
                insert into tenants (id, slug, name, status, settings, authz_version)
                values (:id, :slug, :name, 'active', '{}', 1)
                """
            ),
            {"id": tenant_id, "slug": slug, "name": name},
        )
        normalized_email = owner_email.strip().lower()
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
                "normalized_email": normalized_email,
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
            {"id": membership_id, "tenant_id": tenant_id, "user_id": owner_id},
        )
        knowledge_base_id = None
        if default_knowledge_base_name:
            knowledge_base_id = await self.create_knowledge_base(
                tenant_id=tenant_id,
                user_id=owner_id,
                name=default_knowledge_base_name,
                description=None,
            )
        key = await self.issue_api_key(
            tenant_id=tenant_id,
            user_id=owner_id,
            name="Initial owner key",
            scope_limit=None,
            knowledge_base_limit=None,
            expires_at=None,
            created_by_user_id=owner_id,
        )
        await self.audit(
            tenant_id=tenant_id,
            actor_user_id=owner_id,
            actor_api_key_id=key["id"],
            action="tenant.created",
            target_type="tenant",
            target_id=tenant_id,
        )
        return (
            {"id": tenant_id, "slug": slug, "name": name, "status": "active"},
            {
                "id": owner_id,
                "tenant_id": tenant_id,
                "email": owner_email,
                "display_name": owner_display_name,
                "status": "active",
                "role": "tenant_owner",
            },
            knowledge_base_id,
            key,
        )

    async def create_user(
        self,
        *,
        tenant_id: str,
        email: str,
        display_name: str | None,
        role: str,
        actor_user_id: str,
    ) -> dict[str, object]:
        user_id = new_id("usr")
        await self.session.execute(
            text(
                """
                insert into users (
                    id, tenant_id, email, normalized_email, display_name, status, created_by_user_id
                ) values (
                    :id, :tenant_id, :email, :normalized_email, :display_name, 'active', :actor
                )
                """
            ),
            {
                "id": user_id,
                "tenant_id": tenant_id,
                "email": email,
                "normalized_email": email.strip().lower(),
                "display_name": display_name,
                "actor": actor_user_id,
            },
        )
        await self.session.execute(
            text(
                """
                insert into user_memberships (
                    id, tenant_id, user_id, organization_id, roles, role, status, authz_version
                ) values (:id, :tenant_id, :user_id, null, :roles, :role, 'active', 1)
                """
            ),
            {
                "id": new_id("mem"),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "roles": [role],
                "role": role,
            },
        )
        await self.audit(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="user.created",
            target_type="user",
            target_id=user_id,
        )
        return {
            "id": user_id,
            "tenant_id": tenant_id,
            "email": email,
            "display_name": display_name,
            "status": "active",
            "role": role,
        }

    async def update_user_role(
        self, *, tenant_id: str, user_id: str, role: str, actor_user_id: str
    ) -> None:
        result = await self.session.execute(
            text(
                """
                select role from user_memberships
                where tenant_id = :tenant_id and user_id = :user_id
                for update
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id},
        )
        row = result.mappings().first()
        if row is None:
            raise LookupError("user not found")
        if row["role"] == "tenant_owner" and role != "tenant_owner":
            count = await self.session.execute(
                text(
                    """
                    select count(*) from user_memberships
                    where tenant_id = :tenant_id and role = 'tenant_owner' and status = 'active'
                    """
                ),
                {"tenant_id": tenant_id},
            )
            if int(count.scalar_one()) <= 1:
                raise ValueError("cannot remove the last tenant owner")
        await self.session.execute(
            text(
                """
                update user_memberships
                set role = :role, roles = :roles, authz_version = authz_version + 1,
                    updated_at = now()
                where tenant_id = :tenant_id and user_id = :user_id
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id, "role": role, "roles": [role]},
        )
        await self.audit(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action="user.role_updated",
            target_type="user",
            target_id=user_id,
            after_state={"role": role},
        )

    async def grant_permission(
        self,
        *,
        tenant_id: str,
        user_id: str,
        permission: str,
        actor_user_id: str,
        expires_at: datetime | None,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into membership_scope_grants (
                    id, tenant_id, user_id, permission, granted_by_user_id, expires_at
                ) values (:id, :tenant_id, :user_id, :permission, :actor, :expires_at)
                on conflict (tenant_id, user_id, permission)
                do update set granted_by_user_id = excluded.granted_by_user_id,
                              expires_at = excluded.expires_at
                """
            ),
            {
                "id": new_id("grt"),
                "tenant_id": tenant_id,
                "user_id": user_id,
                "permission": permission,
                "actor": actor_user_id,
                "expires_at": expires_at,
            },
        )

    async def revoke_permission(self, tenant_id: str, user_id: str, permission: str) -> None:
        await self.session.execute(
            text(
                """
                delete from membership_scope_grants
                where tenant_id = :tenant_id and user_id = :user_id and permission = :permission
                """
            ),
            {"tenant_id": tenant_id, "user_id": user_id, "permission": permission},
        )

    async def issue_api_key(
        self,
        *,
        tenant_id: str,
        user_id: str,
        name: str,
        scope_limit: list[str] | None,
        knowledge_base_limit: list[str] | None,
        expires_at: datetime | None,
        created_by_user_id: str,
    ) -> dict[str, object]:
        from rag.authz import generate_api_key

        key_id = new_id("key")
        raw_key, secret = generate_api_key(key_id)
        digest = hash_api_key_secret(secret, self.settings.api_key_pepper)
        prefix = raw_key.split(".", 1)[0]
        await self.session.execute(
            text(
                """
                insert into api_keys (
                    id, tenant_id, organization_id, user_id, key_hash,
                    allowed_scopes, knowledge_base_ids, is_active,
                    name, key_prefix, secret_hash, scope_limit, knowledge_base_limit,
                    expires_at, created_by_user_id
                ) values (
                    :id, :tenant_id, null, :user_id, :legacy_hash,
                    '[]', '[]', true,
                    :name, :prefix, :secret_hash, :scope_limit, :knowledge_base_limit,
                    :expires_at, :created_by_user_id
                )
                """
            ),
            {
                "id": key_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "legacy_hash": f"v2:{key_id}",
                "name": name,
                "prefix": prefix,
                "secret_hash": digest,
                "scope_limit": scope_limit,
                "knowledge_base_limit": knowledge_base_limit,
                "expires_at": expires_at,
                "created_by_user_id": created_by_user_id,
            },
        )
        return {"id": key_id, "prefix": prefix, "api_key": raw_key, "expires_at": expires_at}

    async def revoke_api_key(
        self, *, tenant_id: str, api_key_id: str, actor_user_id: str, reason: str | None = None
    ) -> bool:
        result = await self.session.execute(
            text(
                """
                update api_keys
                set is_active = false, revoked_at = now(), revoked_by_user_id = :actor,
                    revocation_reason = :reason
                where id = :id and tenant_id = :tenant_id and revoked_at is null
                """
            ),
            {
                "id": api_key_id,
                "tenant_id": tenant_id,
                "actor": actor_user_id,
                "reason": reason,
            },
        )
        return bool(result.rowcount)

    async def create_knowledge_base(
        self,
        *,
        tenant_id: str,
        user_id: str,
        name: str,
        description: str | None,
    ) -> str:
        knowledge_base_id = new_id("kb")
        await self.session.execute(
            text(
                """
                insert into knowledge_bases (
                    id, tenant_id, name, description, status, settings, created_by_user_id
                ) values (:id, :tenant_id, :name, :description, 'active', '{}', :user_id)
                """
            ),
            {
                "id": knowledge_base_id,
                "tenant_id": tenant_id,
                "name": name,
                "description": description,
                "user_id": user_id,
            },
        )
        await self.set_knowledge_base_member(
            tenant_id=tenant_id,
            knowledge_base_id=knowledge_base_id,
            user_id=user_id,
            role="kb_admin",
            actor_user_id=user_id,
        )
        return knowledge_base_id

    async def set_knowledge_base_member(
        self,
        *,
        tenant_id: str,
        knowledge_base_id: str,
        user_id: str,
        role: str,
        actor_user_id: str,
    ) -> None:
        user_exists = await self.session.execute(
            text("select 1 from users where id = :user_id and tenant_id = :tenant_id"),
            {"user_id": user_id, "tenant_id": tenant_id},
        )
        if user_exists.first() is None:
            raise LookupError("user not found")
        await self.session.execute(
            text(
                """
                insert into knowledge_base_acl (
                    id, tenant_id, knowledge_base_id, principal_type, principal_id,
                    roles, user_id, role, granted_by_user_id
                ) values (
                    :id, :tenant_id, :knowledge_base_id, 'user', :user_id,
                    :roles, :user_id, :role, :actor
                )
                on conflict (tenant_id, knowledge_base_id, user_id)
                do update set role = excluded.role, roles = excluded.roles,
                              granted_by_user_id = excluded.granted_by_user_id,
                              updated_at = now()
                """
            ),
            {
                "id": new_id("acl"),
                "tenant_id": tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "user_id": user_id,
                "roles": [role],
                "role": role,
                "actor": actor_user_id,
            },
        )

    async def audit(
        self,
        *,
        tenant_id: str | None,
        actor_user_id: str | None,
        action: str,
        target_type: str,
        target_id: str,
        actor_api_key_id: str | None = None,
        before_state: dict[str, object] | None = None,
        after_state: dict[str, object] | None = None,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into audit_events (
                    id, tenant_id, actor_user_id, actor_api_key_id, action,
                    target_type, target_id, before_state, after_state, metadata
                ) values (
                    :id, :tenant_id, :actor_user_id, :actor_api_key_id, :action,
                    :target_type, :target_id, :before_state, :after_state, '{}'
                )
                """
            ),
            {
                "id": new_id("aud"),
                "tenant_id": tenant_id,
                "actor_user_id": actor_user_id,
                "actor_api_key_id": actor_api_key_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "before_state": before_state,
                "after_state": after_state,
            },
        )


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, tenant: TenantContext, knowledge_base_id: str) -> str:
        job_id = new_id("job")
        await self.session.execute(
            text(
                """
                insert into ingestion_jobs (id, tenant_id, knowledge_base_id, status)
                values (:id, :tenant_id, :knowledge_base_id, 'queued')
                """
            ),
            {"id": job_id, "tenant_id": tenant.tenant_id, "knowledge_base_id": knowledge_base_id},
        )
        return job_id

    async def create_document_record(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        title: str,
        source_uri: str | None,
    ) -> str:
        document_id = new_id("doc")
        await self.session.execute(
            text(
                """
                insert into documents (id, tenant_id, knowledge_base_id, title, source_uri)
                values (:id, :tenant_id, :knowledge_base_id, :title, :source_uri)
                """
            ),
            {
                "id": document_id,
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "title": title,
                "source_uri": source_uri,
            },
        )
        return document_id

    async def store_chunks(self, chunks: list[StoredChunk]) -> None:
        for chunk in chunks:
            await self.session.execute(
                text(
                    """
                    insert into chunks (
                        id, tenant_id, knowledge_base_id, document_id, document_version,
                        text, token_count, metadata
                    ) values (
                        :id, :tenant_id, :knowledge_base_id, :document_id, 1,
                        :text, :token_count, :metadata
                    )
                    """
                ),
                {
                    "id": chunk.chunk_id,
                    "tenant_id": chunk.metadata["tenant_id"],
                    "knowledge_base_id": chunk.metadata["knowledge_base_id"],
                    "document_id": chunk.document_id,
                    "text": chunk.text,
                    "token_count": len(chunk.text.split()),
                    "metadata": chunk.metadata,
                },
            )

    async def hydrate_chunks(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        candidates: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []
        candidate_by_id = {candidate.chunk_id: candidate for candidate in candidates}
        result = await self.session.execute(
            text(
                """
                select c.id, c.document_id, c.text, c.page, c.metadata, d.title, d.source_uri
                from chunks c
                join documents d
                  on d.id = c.document_id
                 and d.tenant_id = c.tenant_id
                 and d.knowledge_base_id = c.knowledge_base_id
                where c.tenant_id = :tenant_id
                  and c.knowledge_base_id = :knowledge_base_id
                  and c.is_active = true
                  and c.id = any(:chunk_ids)
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "chunk_ids": list(candidate_by_id),
            },
        )
        hydrated = []
        for row in result.mappings():
            candidate = candidate_by_id[row["id"]]
            hydrated.append(
                candidate.model_copy(
                    update={
                        "text": row["text"],
                        "source": {
                            "title": row["title"],
                            "source_uri": row["source_uri"],
                            "page": row["page"],
                        },
                        "metadata": row["metadata"],
                    }
                )
            )
        return hydrated

    async def document_exists(
        self, tenant: TenantContext, knowledge_base_id: str, document_id: str
    ) -> bool:
        result = await self.session.execute(
            text(
                """
                select 1 from documents
                where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                  and id = :document_id and is_active = true
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        return result.first() is not None

    async def purge_document(
        self,
        tenant: TenantContext,
        knowledge_base_id: str,
        document_id: str,
    ) -> None:
        await self.session.execute(
            text(
                """
                insert into deletion_audit_events (
                    id, tenant_id, knowledge_base_id, document_id, actor_user_id, event_type
                ) values (:id, :tenant_id, :knowledge_base_id, :document_id, :actor_user_id, 'purge')
                """
            ),
            {
                "id": new_id("del"),
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
                "actor_user_id": tenant.user_id,
            },
        )
        await self.session.execute(
            text(
                """
                delete from keyword_postings
                where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                  and chunk_id in (
                    select id from chunks
                    where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                  )
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
        for table_name in ["chunks", "document_versions"]:
            await self.session.execute(
                text(
                    f"""
                    delete from {table_name}
                    where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                      and document_id = :document_id
                    """
                ),
                {
                    "tenant_id": tenant.tenant_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_id": document_id,
                },
            )
        await self.session.execute(
            text(
                """
                delete from documents
                where tenant_id = :tenant_id and knowledge_base_id = :knowledge_base_id
                  and id = :document_id
                """
            ),
            {
                "tenant_id": tenant.tenant_id,
                "knowledge_base_id": knowledge_base_id,
                "document_id": document_id,
            },
        )
