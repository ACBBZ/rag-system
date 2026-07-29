"""durable ingestion jobs and structured chunks

Revision ID: 0005_ingestion_v2
Revises: 0004_retrieval_v2
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ingestion_v2"
down_revision = "0004_retrieval_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "document_versions",
        "metadata",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        postgresql_using="metadata::jsonb",
    )
    op.add_column(
        "document_versions",
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
    )
    op.add_column(
        "document_versions",
        sa.Column("filename", sa.String(), nullable=False, server_default="upload.bin"),
    )
    op.create_unique_constraint(
        "uq_document_versions_scope_version",
        "document_versions",
        ["tenant_id", "knowledge_base_id", "document_id", "version"],
    )
    op.alter_column(
        "chunks",
        "title_path",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=sa.text("'[]'::jsonb"),
        postgresql_using="title_path::jsonb",
    )
    op.add_column("chunks", sa.Column("ordinal", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("chunks", sa.Column("content_hash", sa.String(), nullable=False, server_default=""))
    op.add_column("chunks", sa.Column("context_key", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("parent_chunk_id", sa.String(), nullable=True))
    op.add_column("chunks", sa.Column("page_start", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("page_end", sa.Integer(), nullable=True))
    op.add_column("chunks", sa.Column("language", sa.String(), nullable=False, server_default="und"))
    op.add_column("chunks", sa.Column("parser_version", sa.String(), nullable=False, server_default="v1"))
    op.add_column("chunks", sa.Column("chunker_version", sa.String(), nullable=False, server_default="v1"))
    op.add_column("chunks", sa.Column("lexical_text", sa.Text(), nullable=False, server_default=""))
    op.create_unique_constraint(
        "uq_chunks_scope_ordinal",
        "chunks",
        ["tenant_id", "knowledge_base_id", "document_id", "document_version", "ordinal"],
    )
    op.create_index("uq_chunks_context_key", "chunks", ["context_key"], unique=True)
    job_columns = [
        sa.Column("document_version", sa.Integer(), nullable=True),
        sa.Column("stage", sa.String(), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", sa.String(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("raw_object_key", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    ]
    for column in job_columns:
        op.add_column("ingestion_jobs", column)
    op.create_unique_constraint(
        "uq_ingestion_job_idempotency",
        "ingestion_jobs",
        ["tenant_id", "knowledge_base_id", "idempotency_key"],
    )
    op.create_index(
        "ix_ingestion_jobs_claim",
        "ingestion_jobs",
        ["status", "available_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_jobs_claim", table_name="ingestion_jobs")
    op.drop_constraint("uq_ingestion_job_idempotency", "ingestion_jobs", type_="unique")
    for name in [
        "metadata", "filename", "raw_object_key", "idempotency_key", "error_details",
        "error_message", "error_code", "worker_id", "heartbeat_at", "completed_at",
        "started_at", "available_at", "max_attempts", "attempt", "progress", "stage",
        "document_version",
    ]:
        op.drop_column("ingestion_jobs", name)
    op.drop_index("uq_chunks_context_key", table_name="chunks")
    op.drop_constraint("uq_chunks_scope_ordinal", "chunks", type_="unique")
    for name in [
        "lexical_text", "chunker_version", "parser_version", "language", "page_end",
        "page_start", "parent_chunk_id", "context_key", "content_hash", "ordinal",
    ]:
        op.drop_column("chunks", name)
    op.alter_column(
        "chunks",
        "title_path",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=False,
        server_default=sa.text("'[]'::json"),
        postgresql_using="title_path::json",
    )
    op.drop_constraint("uq_document_versions_scope_version", "document_versions", type_="unique")
    op.drop_column("document_versions", "filename")
    op.drop_column("document_versions", "status")
    op.alter_column(
        "document_versions",
        "metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=False,
        server_default=sa.text("'{}'::json"),
        postgresql_using="metadata::json",
    )
