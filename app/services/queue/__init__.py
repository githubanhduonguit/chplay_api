"""In-app queue package for processing review and ticket proposal jobs.

Provides:
- ReviewJob / TicketProposalJob: dataclasses describing queue jobs.
- ReviewJobQueue / TicketProposalJobQueue: typed asyncio.Queue wrappers.
- review_job_queue / ticket_proposal_queue: module-level singletons.
- ReviewQueueWorker / TicketProposalQueueWorker: background consumers.
"""

from app.services.queue.queue import ReviewJobQueue, review_job_queue
from app.services.queue.schemas import ReviewJob, TicketProposalJob
from app.services.queue.ticket_queue import (
    TicketProposalJobQueue,
    ticket_proposal_queue,
)
from app.services.queue.ticket_worker import TicketProposalQueueWorker
from app.services.queue.worker import ReviewQueueWorker

__all__ = [
    "ReviewJob",
    "ReviewJobQueue",
    "review_job_queue",
    "ReviewQueueWorker",
    "TicketProposalJob",
    "TicketProposalJobQueue",
    "ticket_proposal_queue",
    "TicketProposalQueueWorker",
]
