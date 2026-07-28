"""fixed v1 tenant vector collections

Revision ID: 0003_tenant_vector_collections
Revises: 0002_authorization_v2
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_tenant_vector_collections"
down_revision = "0002_authorization_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_vector_resources",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(), nullable=False, server_default="milvus"),
        sa.Column("cluster_key", sa.String(), nullable=False, server_default="default"),
        sa.Column("logical_alias", sa.String(), nullable=False),
        sa.Column("physical_collection", sa.String(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(), nullable=False),
        sa.Column("index_type", sa.String(), nullable=False),
        sa.Column(
            "index_params",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "search_params",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("schema_fingerprint", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "schema_version = 1",
            name="ck_tenant_vector_resource_schema_v1",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            name="uq_tenant_vector_resource_tenant",
        ),
        sa.UniqueConstraint(
            "logical_alias",
            name="uq_tenant_vector_resource_alias",
        ),
        sa.UniqueConstraint(
            "physical_collection",
            name="uq_tenant_vector_resource_collection",
        ),
    )
    op.create_index(
        "ix_tenant_vector_resources_tenant_status",
        "tenant_vector_resources",
        ["tenant_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_vector_resources_tenant_status",
        table_name="tenant_vector_resources",
    )
    op.drop_table("tenant_vector_resources")
