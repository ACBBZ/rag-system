"""Milvus V2 metadata and lexical search normalization

Revision ID: 0006_retrieval_v3
Revises: 0005_ingestion_v2
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_retrieval_v3"
down_revision = "0005_ingestion_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_tenant_vector_resource_schema_v1",
        "tenant_vector_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tenant_vector_resource_schema_supported",
        "tenant_vector_resources",
        "schema_version in (1, 2)",
    )
    op.alter_column(
        "tenant_vector_resources",
        "schema_version",
        existing_type=sa.Integer(),
        server_default="2",
    )
    op.add_column(
        "tenant_vector_resources",
        sa.Column("previous_physical_collection", sa.String(), nullable=True),
    )
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_column("chunks", "search_vector")
    op.add_column(
        "chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple'::regconfig, coalesce(title_path::text, '')), 'A') || "
                "setweight(to_tsvector('simple'::regconfig, coalesce(lexical_text, text, '')), 'B')",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_chunks_search_vector", table_name="chunks")
    op.drop_column("chunks", "search_vector")
    op.add_column(
        "chunks",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, coalesce(text, ''))", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_search_vector", "chunks", ["search_vector"], postgresql_using="gin")
    op.drop_column("tenant_vector_resources", "previous_physical_collection")
    op.drop_constraint(
        "ck_tenant_vector_resource_schema_supported",
        "tenant_vector_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_tenant_vector_resource_schema_v1",
        "tenant_vector_resources",
        "schema_version = 1",
    )
    op.alter_column(
        "tenant_vector_resources",
        "schema_version",
        existing_type=sa.Integer(),
        server_default="1",
    )
