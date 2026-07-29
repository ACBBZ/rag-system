"""query observability and evaluation trace fields

Revision ID: 0007_observability
Revises: 0006_retrieval_v3
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_observability"
down_revision = "0006_retrieval_v3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "query_logs", "options", existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()), postgresql_using="options::jsonb",
    )
    for column in [
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("api_key_id", sa.String(), nullable=True),
        sa.Column("filters", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("answer_status", sa.String(), nullable=True),
        sa.Column("total_latency_ms", sa.Float(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_versions", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_code", sa.String(), nullable=True),
    ]:
        op.add_column("query_logs", column)
    op.create_index("ix_query_logs_trace_id", "query_logs", ["trace_id"], unique=True)
    for column in [
        sa.Column("tenant_id", sa.String(), nullable=True),
        sa.Column("knowledge_base_id", sa.String(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("scores", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("selected_for_context", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cited", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    ]:
        op.add_column("retrieval_logs", column)
    op.create_index("ix_retrieval_logs_query_rank", "retrieval_logs", ["query_id", "rank"])


def downgrade() -> None:
    op.drop_index("ix_retrieval_logs_query_rank", table_name="retrieval_logs")
    for name in ["cited", "selected_for_context", "scores", "rank", "knowledge_base_id", "tenant_id"]:
        op.drop_column("retrieval_logs", name)
    op.drop_index("ix_query_logs_trace_id", table_name="query_logs")
    for name in [
        "error_code", "model_versions", "completion_tokens", "prompt_tokens",
        "total_latency_ms", "answer_status", "filters", "api_key_id", "user_id", "trace_id",
    ]:
        op.drop_column("query_logs", name)
    op.alter_column(
        "query_logs", "options", existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(), postgresql_using="options::json",
    )
