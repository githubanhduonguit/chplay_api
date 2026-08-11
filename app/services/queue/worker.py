"""Worker that consumes review jobs from the in-app queue.

The worker runs as a background asyncio task started in the FastAPI
lifespan. For each job it opens a fresh DB session and reuses
``process_single_review`` from ``app/jobs/generate_review_replies.py``
to generate the bot reply and persist it.
"""

from __future__ import annotations

import logging

from app.db.repository.comment import CommentRepository
from app.db.session import async_session_factory
from app.jobs.generate_review_replies import process_single_review
from app.services.agents.review_reply_agent import ReviewReplyAgent
from app.services.llm.glm import GLMReviewReplyService
from app.services.queue.queue import ReviewJobQueue
from app.services.queue.schemas import ReviewJob

logger = logging.getLogger(__name__)


class ReviewQueueWorker:
    """Consume ``ReviewJob`` items from the queue and process them.

    Args:
        queue: The ReviewJobQueue instance to consume jobs from.
    """

    def __init__(self, queue: ReviewJobQueue) -> None:
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
                    "Unhandled error processing job for review %s: %s",
                    job.review_id,
                    str(e),
                    exc_info=True,
                )

    async def _process(self, job: ReviewJob) -> None:
        """Process a single review job: generate reply and save bot comment.

        Args:
            job: The review job to process.
        """
        async with async_session_factory() as session:
            repo = CommentRepository(session)
            agent = ReviewReplyAgent(llm_service=GLMReviewReplyService())
            success, error = await process_single_review(
                repo, agent, job.review_id
            )
            if success:
                logger.info(
                    "Queue worker processed review %s successfully.",
                    job.review_id,
                )
            else:
                logger.warning(
                    "Queue worker failed to process review %s: %s",
                    job.review_id,
                    error,
                )

    async def stop(self) -> None:
        """Signal the worker to stop after the current job finishes."""
        self._running = False
