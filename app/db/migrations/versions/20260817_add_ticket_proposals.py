"""Add ticket_proposals table.

Revision ID: 20260817_add_ticket_proposals
Revises: 20260812_split_comment_aspects
Create Date: 2026-08-17 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260817_add_ticket_proposals"
down_revision: Union[str, None] = "20260812_split_comment_aspects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the ticket_proposals table with its indexes."""
    op.create_table(
        "ticket_proposals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("app_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("topic_l1", sa.String(length=256), nullable=True),
        sa.Column("topic_l2", sa.String(length=256), nullable=True),
        sa.Column("review_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("batch_date", sa.Date(), nullable=True),
        sa.Column("ticket_id", sa.String(length=256), nullable=True),
        sa.Column("ticket_url", sa.String(length=1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["app_id"], ["apps.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticket_proposals_app_id", "ticket_proposals", ["app_id"])
    op.create_index("ix_ticket_proposals_status", "ticket_proposals", ["status"])
    op.create_index("ix_ticket_proposals_topic_l1", "ticket_proposals", ["topic_l1"])
    op.create_index("ix_ticket_proposals_batch_date", "ticket_proposals", ["batch_date"])


def downgrade() -> None:
    """Drop the ticket_proposals table and its indexes."""
    op.drop_index("ix_ticket_proposals_batch_date", table_name="ticket_proposals")
    op.drop_index("ix_ticket_proposals_topic_l1", table_name="ticket_proposals")
    op.drop_index("ix_ticket_proposals_status", table_name="ticket_proposals")
    op.drop_index("ix_ticket_proposals_app_id", table_name="ticket_proposals")
    op.drop_table("ticket_proposals")
