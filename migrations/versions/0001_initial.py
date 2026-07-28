"""initial multi tenant schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    ]


def tenant_columns(include_knowledge_base: bool = False) -> list[sa.Column]:
    columns = [sa.Column("tenant_id", sa.String(), nullable=False)]
    if include_knowledge_base:
        columns.append(sa.Column("knowledge_base_id", sa.String(), nullable=False))
    return columns


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("name", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("email", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("key_hash", sa.String(), nullable=False, unique=True),
        sa.Column("allowed_scopes", sa.JSON(), nullable=False),
        sa.Column("knowledge_base_ids", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
    )
    op.create_table(
        "knowledge_base_acl",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("principal_type", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "user_memberships",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("organization_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("source_uri", sa.String(), nullable=True),
        sa.Column("active_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )
    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(), nullable=False),
        sa.Column("raw_object_key", sa.String(), nullable=False),
        sa.Column("parsed_object_key", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        *timestamps(),
    )
    op.create_table(
        "chunks",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("document_version", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("title_path", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        *timestamps(),
    )
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "keyword_terms",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("term", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "keyword_postings",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("term", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "query_logs",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("rewritten_query", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "retrieval_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("query_id", sa.String(), nullable=False),
        sa.Column("chunk_id", sa.String(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("retrieval_method", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(),
        sa.Column("query_id", sa.String(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_table(
        "deletion_audit_events",
        sa.Column("id", sa.String(), primary_key=True),
        *tenant_columns(include_knowledge_base=True),
        sa.Column("document_id", sa.String(), nullable=False),
        sa.Column("actor_user_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    for table_name in [
        "deletion_audit_events",
        "feedback",
        "retrieval_logs",
        "query_logs",
        "keyword_postings",
        "keyword_terms",
        "ingestion_jobs",
        "chunks",
        "document_versions",
        "documents",
        "user_memberships",
        "knowledge_base_acl",
        "knowledge_bases",
        "api_keys",
        "users",
        "organizations",
        "tenants",
    ]:
        op.drop_table(table_name)
