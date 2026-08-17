"""
TicketProposal database model.

Represents an AI-generated issue proposal that is created from clustered
negative reviews and goes through a Human-In-The-Loop approval flow
(PROPOSED → APPROVED → CREATING → CREATED / REJECTED / FAILED) before a
ticket is created at the external provider (IT Helpdesk / Trello).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BaseMixin

if TYPE_CHECKING:
    from app.db.models.app import App


class TicketProposal(BaseMixin, Base):
    """Represents an issue proposal created by the AI agent.

    Attributes:
        app_id: Foreign key to the associated app.
        title: Short summary of the issue.
        description: Detailed description (reviews excerpts, count...).
        status: PROPOSED / APPROVED / REJECTED / CREATING / CREATED / FAILED.
        source: Who created it (default "ai_agent").
        topic_l1: Coarse topic from PhoBERT aspects (used for clustering/dedup).
        topic_l2: Finer topic (optional).
        review_ids: List of comment ids grouped into this proposal.
        batch_date: Ngày của review được tổng hợp (vd hôm qua). Mỗi sáng là 1 batch riêng.
        ticket_id: External ticket id returned by the provider.
        ticket_url: External ticket URL for the admin to open.
        error_message: Last failure reason when status == FAILED.
        app: Relationship to the associated App.
    """

    __tablename__ = "ticket_proposals"

    app_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("apps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="PROPOSED", nullable=False, index=True
    )
    source: Mapped[str] = mapped_column(String(64), default="ai_agent", nullable=False)
    topic_l1: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    topic_l2: Mapped[str | None] = mapped_column(String(256), nullable=True)
    review_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    batch_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    ticket_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ticket_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    app: Mapped[App] = relationship("App", back_populates="ticket_proposals")

    def __repr__(self) -> str:
        return (
            f"<TicketProposal id={self.id} app_id={self.app_id} "
            f"status='{self.status}' topic_l1='{self.topic_l1}'>"
        )
