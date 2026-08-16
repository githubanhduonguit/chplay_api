"""Split comment_aspects.aspect into topic_l1 and topic_l2.

Revision ID: 20260812_split_comment_aspects
Revises: 20260811_add_document_tables
Create Date: 2026-08-12 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260812_split_comment_aspects"
down_revision: Union[str, None] = "20260811_add_document_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Replace the single-level ``aspect`` column with topic_l1/topic_l2.

    Old seed data in ``aspect`` is intentionally dropped (per requirement):
    it used a different label set than the PhoBERT model's topic_l1/topic_l2.
    """
    op.execute("DELETE FROM comment_aspects")
    op.drop_index("idx_comment_aspects_aspect", table_name="comment_aspects")
    op.drop_index("idx_comment_aspects_sentiment", table_name="comment_aspects")
    op.drop_constraint(
        "comment_aspects_comment_id_aspect_key",
        "comment_aspects",
        type_="unique",
    )
    op.drop_column("comment_aspects", "aspect")

    op.add_column(
        "comment_aspects",
        sa.Column("topic_l1", sa.String(256), nullable=False, server_default=""),
    )
    op.add_column(
        "comment_aspects",
        sa.Column("topic_l2", sa.String(256), nullable=True),
    )
    op.create_index(
        "ix_comment_aspects_topic_l1",
        "comment_aspects",
        ["topic_l1"],
    )
    op.create_index(
        "ix_comment_aspects_topic_l2",
        "comment_aspects",
        ["topic_l2"],
    )
    # Remove the temporary server_default so new inserts must set topic_l1
    op.alter_column("comment_aspects", "topic_l1", server_default=None)


def downgrade() -> None:
    """Restore the single ``aspect`` column (nullable to accept existing rows)."""
    op.drop_index("ix_comment_aspects_topic_l2", table_name="comment_aspects")
    op.drop_index("ix_comment_aspects_topic_l1", table_name="comment_aspects")
    op.drop_column("comment_aspects", "topic_l2")
    op.drop_column("comment_aspects", "topic_l1")

    op.add_column(
        "comment_aspects",
        sa.Column("aspect", sa.String(256), nullable=True),
    )
    op.create_unique_constraint(
        "comment_aspects_comment_id_aspect_key",
        "comment_aspects",
        ["comment_id", "aspect"],
    )
    op.create_index("idx_comment_aspects_aspect", "comment_aspects", ["aspect"])
    op.create_index(
        "idx_comment_aspects_sentiment",
        "comment_aspects",
        ["aspect", "sentiment"],
    )
