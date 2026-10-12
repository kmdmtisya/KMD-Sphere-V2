"""ai conversations, messages and tool calls (P10-T07)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[sa.UUID]:
    return sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _now(name: str) -> sa.Column[sa.DateTime]:
    return sa.Column(
        name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        _id(),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("portfolio_id", sa.UUID(), nullable=True),
        _now("created_at"),
        _now("updated_at"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_conversations_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolios.id"],
            name=op.f("fk_ai_conversations_portfolio_id_portfolios"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_conversations")),
    )
    op.create_index(
        "ix_ai_conversations_user_id_updated_at", "ai_conversations", ["user_id", "updated_at"]
    )
    op.create_index("ix_ai_conversations_updated_at", "ai_conversations", ["updated_at"])

    op.create_table(
        "ai_messages",
        _id(),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=9), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("provider", sa.String(length=20), nullable=True),
        _now("created_at"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=op.f("ck_ai_messages_role")),
        sa.CheckConstraint("length(content) <= 20000", name=op.f("ck_ai_messages_content_length")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ai_conversations.id"],
            name=op.f("fk_ai_messages_conversation_id_ai_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_messages_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_messages")),
        sa.UniqueConstraint(
            "conversation_id", "position", name="uq_ai_messages_conversation_position"
        ),
    )
    op.create_index("ix_ai_messages_user_id", "ai_messages", ["user_id"])

    op.create_table(
        "ai_tool_calls",
        _id(),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("arguments_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=5), nullable=False),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        _now("created_at"),
        sa.CheckConstraint("status IN ('ok', 'error')", name=op.f("ck_ai_tool_calls_status")),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["ai_conversations.id"],
            name=op.f("fk_ai_tool_calls_conversation_id_ai_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["ai_messages.id"],
            name=op.f("fk_ai_tool_calls_message_id_ai_messages"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_tool_calls_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_tool_calls")),
    )
    op.create_index("ix_ai_tool_calls_user_id", "ai_tool_calls", ["user_id"])
    op.create_index("ix_ai_tool_calls_conversation_id", "ai_tool_calls", ["conversation_id"])


def downgrade() -> None:
    op.drop_table("ai_tool_calls")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
