"""allow stable aliases across tenant collection versions

Revision ID: 0004_vector_alias_versions
Revises: 0003_tenant_vector_collections
Create Date: 2026-07-28
"""

from alembic import op

revision = "0004_vector_alias_versions"
down_revision = "0003_tenant_vector_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A tenant keeps one stable alias while physical collections are versioned.
    # Multiple resource rows for the same tenant therefore intentionally share
    # logical_alias and differ by schema_version/physical_collection.
    op.drop_constraint(
        "uq_vector_resource_alias",
        "tenant_vector_resources",
        type_="unique",
    )
    op.create_index(
        "ix_tenant_vector_resources_alias",
        "tenant_vector_resources",
        ["logical_alias"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tenant_vector_resources_alias",
        table_name="tenant_vector_resources",
    )
    op.create_unique_constraint(
        "uq_vector_resource_alias",
        "tenant_vector_resources",
        ["logical_alias"],
    )
