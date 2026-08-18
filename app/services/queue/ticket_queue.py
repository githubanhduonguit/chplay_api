"""In-app async queue for ticket proposal jobs.

A thin typed wrapper around ``asyncio.Queue`` used to decouple admin
approval (HITL) from external ticket creation (Trello / IT Helpdesk).
The queue lives inside the application process — no external
infrastructure (Celery/Redis/RQ). Mirrors ``ReviewJobQueue``.
"""

from __future__ import annotations

import asyncio

from app.services.queue.schemas import TicketProposalJob


class TicketProposalJobQueue:
    """Async queue for ``TicketProposalJob`` items.

    Args:
        maxsize: Maximum number of jobs the queue can hold before
            ``enqueue`` blocks. Defaults to 1000.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._queue: asyncio.Queue[TicketProposalJob] = asyncio.Queue(
            maxsize=maxsize
        )

    async def enqueue(self, job: TicketProposalJob) -> None:
        """Put a job into the queue.

        Args:
            job: The TicketProposalJob to enqueue.
        """
        await self._queue.put(job)

    async def dequeue(self) -> TicketProposalJob:
        """Get the next job from the queue, blocking until one is available.

        Returns:
            The next TicketProposalJob.
        """
        return await self._queue.get()

    def size(self) -> int:
        """Get the current number of jobs in the queue.

        Returns:
            The current queue size.
        """
        return self._queue.qsize()


# Module-level singleton queue shared across the application.
ticket_proposal_queue = TicketProposalJobQueue()
