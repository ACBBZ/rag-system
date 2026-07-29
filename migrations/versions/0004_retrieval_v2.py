"""retrieval v2 full text search

Revision ID: 0004_retrieval_v2
Revises: 0003_tenant_vector_collections
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_retrieval_v2"
down_revision = "0003_tenant_vector_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "chunks",
        "metadata",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=False,
        server_default=sa.text("'{}'::jsonb"),
        postgresql_using="metadata::jsonb",
    )
    op.add_column(
        "chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, coalesce(text, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_chunks_search_vector",
        "chunks",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_metadata_gin",
        "chunks",
        ["metadata"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_retrieval_scope",
        "chunks",
        ["tenant_id", "knowledge_base_id", "is_active", "document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_retrieval_scope", table_name="chunks")
    op.drop_index("ix_chunks_metadata_gin", table_name="chunks")
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_column("chunks", "search_vector")
    op.alter_column(
        "chunks",
        "metadata",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=False,
        server_default=sa.text("'{}'::json"),
        postgresql_using="metadata::json",
    )
