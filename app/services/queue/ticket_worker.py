"""Worker that consumes ticket proposal jobs from the in-app queue.

The worker runs as a background asyncio task started in the FastAPI
lifespan. For each job it opens a fresh DB session and calls
``TicketProposalService.process_approved_proposal`` to create the
external ticket (Trello / IT Helpdesk) asynchronously right after an
admin approves the proposal — no polling/interval scheduler needed.
"""

from __future__ import annotations

import logging

from app.db.session import async_session_factory
from app.services.queue.schemas import TicketProposalJob
from app.services.queue.ticket_queue import TicketProposalJobQueue

logger = logging.getLogger(__name__)


class TicketProposalQueueWorker:
    """Consume ``TicketProposalJob`` items from the queue and process them.

    Args:
        queue: The TicketProposalJobQueue instance to consume jobs from.
    """

    def __init__(self, queue: TicketProposalJobQueue) -> None:
        self.queue = queue
        self._running = False

    async def start(self) -> None:
        """Run the consume loop until ``stop()`` is called.

        Each job is processed in isolation so a single failure does not
        kill the worker.
        """
        self._running = True
        while self._running:
            job = await self.queue.dequeue()
            try:
                await self._process(job)
            except Exception as e:
                logger.error(
                    "Unhandled error processing job for proposal %s: %s",
                    job.proposal_id,
                    str(e),
                    exc_info=True,
                )

    async def _process(self, job: TicketProposalJob) -> None:
        """Process a single ticket proposal job: create the external ticket.

        The proposal must already be committed as APPROVED by the time the
        job runs (``approve()`` commits before enqueueing), otherwise the
        policy check in ``process_approved_proposal`` rejects it.

        Args:
            job: The ticket proposal job to process.
        """
        # Lazy import to avoid a circular import: this worker is imported
        # from app.services.* while app.services.ticket_service may still
        # be initializing (it enqueues into the same queue).
        from app.services.ticket_service import TicketProposalService

        async with async_session_factory() as session:
            service = TicketProposalService(session)
            proposal = await service.process_approved_proposal(job.proposal_id)
            await session.commit()
            if proposal.status == "CREATED":
                logger.info(
                    "Ticket worker created ticket for proposal %s "
                    "(ticket_id=%s, url=%s)",
                    job.proposal_id,
                    proposal.ticket_id,
                    proposal.ticket_url,
                )
            else:
                logger.warning(
                    "Ticket worker: proposal %s ended with status '%s' "
                    "(not CREATED)",
                    job.proposal_id,
                    proposal.status,
                )

    async def stop(self) -> None:
        """Signal the worker to stop after the current job finishes."""
        self._running = False
