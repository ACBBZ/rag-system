"""authorization v2

Revision ID: 0002_authorization_v2
Revises: 0001_initial
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_authorization_v2"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("slug", sa.String(), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "tenants",
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.add_column(
        "tenants",
        sa.Column("authz_version", sa.BigInteger(), nullable=False, server_default="1"),
    )
    op.create_unique_constraint("uq_tenants_slug", "tenants", ["slug"])

    op.add_column("users", sa.Column("normalized_email", sa.String(), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column("users", sa.Column("external_subject", sa.String(), nullable=True))
    op.add_column("users", sa.Column("created_by_user_id", sa.String(), nullable=True))
    op.create_unique_constraint(
        "uq_users_tenant_email", "users", ["tenant_id", "normalized_email"]
    )

    op.add_column("user_memberships", sa.Column("role", sa.String(), nullable=True))
    op.add_column(
        "user_memberships",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "user_memberships",
        sa.Column("authz_version", sa.BigInteger(), nullable=False, server_default="1"),
    )
    op.create_unique_constraint(
        "uq_membership_tenant_user", "user_memberships", ["tenant_id", "user_id"]
    )

    op.create_table(
        "membership_scope_grants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("granted_by_user_id", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "permission", name="uq_user_permission"
        ),
    )

    op.add_column("knowledge_bases", sa.Column("description", sa.Text(), nullable=True))
    op.add_column(
        "knowledge_bases",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column("knowledge_bases", sa.Column("created_by_user_id", sa.String(), nullable=True))
    op.create_unique_constraint(
        "uq_knowledge_bases_tenant_id", "knowledge_bases", ["tenant_id", "id"]
    )

    op.add_column("knowledge_base_acl", sa.Column("user_id", sa.String(), nullable=True))
    op.add_column("knowledge_base_acl", sa.Column("role", sa.String(), nullable=True))
    op.add_column("knowledge_base_acl", sa.Column("granted_by_user_id", sa.String(), nullable=True))
    op.create_unique_constraint(
        "uq_kb_acl_user",
        "knowledge_base_acl",
        ["tenant_id", "knowledge_base_id", "user_id"],
    )

    op.add_column("api_keys", sa.Column("name", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("key_prefix", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("secret_hash", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("scope_limit", sa.JSON(), nullable=True))
    op.add_column("api_keys", sa.Column("knowledge_base_limit", sa.JSON(), nullable=True))
    op.add_column("api_keys", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("api_keys", sa.Column("created_by_user_id", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("revoked_by_user_id", sa.String(), nullable=True))
    op.add_column("api_keys", sa.Column("revocation_reason", sa.String(), nullable=True))

    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("actor_user_id", sa.String(), nullable=True),
        sa.Column("actor_api_key_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=False),
        sa.Column("target_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_tenant_created", "audit_events", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_tenant_created", table_name="audit_events")
    op.drop_table("audit_events")
    for column in [
        "revocation_reason", "revoked_by_user_id", "created_by_user_id", "last_used_at",
        "revoked_at", "expires_at", "knowledge_base_limit", "scope_limit", "secret_hash",
        "key_prefix", "name",
    ]:
        op.drop_column("api_keys", column)
    op.drop_constraint("uq_kb_acl_user", "knowledge_base_acl", type_="unique")
    for column in ["granted_by_user_id", "role", "user_id"]:
        op.drop_column("knowledge_base_acl", column)
    op.drop_constraint("uq_knowledge_bases_tenant_id", "knowledge_bases", type_="unique")
    for column in ["created_by_user_id", "status", "description"]:
        op.drop_column("knowledge_bases", column)
    op.drop_table("membership_scope_grants")
    op.drop_constraint("uq_membership_tenant_user", "user_memberships", type_="unique")
    for column in ["authz_version", "status", "role"]:
        op.drop_column("user_memberships", column)
    op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    for column in ["created_by_user_id", "external_subject", "status", "display_name", "normalized_email"]:
        op.drop_column("users", column)
    op.drop_constraint("uq_tenants_slug", "tenants", type_="unique")
    for column in ["authz_version", "settings", "status", "slug"]:
        op.drop_column("tenants", column)
