"""In-app queue package for processing review jobs.

Provides:
- ReviewJob: dataclass describing a review job.
- ReviewJobQueue: typed wrapper around asyncio.Queue.
- review_job_queue: module-level singleton queue.
- ReviewQueueWorker: background consumer loop for processing jobs.
"""

from app.services.queue.queue import ReviewJobQueue, review_job_queue
from app.services.queue.schemas import ReviewJob
from app.services.queue.worker import ReviewQueueWorker

__all__ = [
    "ReviewJob",
    "ReviewJobQueue",
    "review_job_queue",
    "ReviewQueueWorker",
]
