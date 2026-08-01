"""Rename review_id to review_parent_id in comments table.

Revision ID: 20260717_rename_review_parent_id
Revises:
Create Date: 2026-07-17 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260717_rename_review_parent_id"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename review_id column to review_parent_id."""
    op.alter_column(
        "comments",
        "review_id",
        new_column_name="review_parent_id",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    """Rename review_parent_id column back to review_id."""
    op.alter_column(
        "comments",
        "review_parent_id",
        new_column_name="review_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
