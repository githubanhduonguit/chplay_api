"""
Background scheduler for periodic jobs.

Uses APScheduler to run background jobs on a schedule:
- Daily index rebuild (BM25 + re-index documents)
- Sync external data (placeholder for future use)
- Cleanup old versions and expired data
- Retry failed processing jobs
- Label comments with Spark + PhoBERT

Runs as a separate process (started via CLI command).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import settings
from app.db.session import async_session_factory

logger = logging.getLogger(__name__)

# ── Job lock ─────────────────────────────────────────────────────────
# Simple in-memory lock to prevent overlapping runs of the same job
_job_locks: dict[str, bool] = {}


def _acquire_lock(job_id: str) -> bool:
    """Try to acquire a lock for a job.

    Args:
        job_id: Unique job identifier.

    Returns:
        True if the lock was acquired, False if already locked.
    """
    if _job_locks.get(job_id, False):
        logger.warning("Job '%s' is already running, skipping.", job_id)
        return False
    _job_locks[job_id] = True
    return True


def _release_lock(job_id: str) -> None:
    """Release a job lock.

    Args:
        job_id: Unique job identifier.
    """
    _job_locks[job_id] = False


# ── Job implementations ──────────────────────────────────────────────


async def job_daily_rebuild_index() -> None:
    """Rebuild BM25 and vector indices daily.

    Process:
    1. Fetch all documents with status 'uploaded' or 'failed'
    2. Run the chunking pipeline for each
    3. Rebuild BM25 index from all chunk texts
    4. Log summary
    """
    job_id = "daily_rebuild_index"
    if not _acquire_lock(job_id):
        return

    start_time = datetime.now(timezone.utc)
    logger.info("Job '%s' started at %s", job_id, start_time.isoformat())

    try:
        from app.db.repository.document import DocumentRepository
        from app.services.chunking.chunker import ChunkingService
        from app.services.chunking.cleaner import TextCleanerService
        from app.services.chunking.extractor import TextExtractorService

        async with async_session_factory() as session:
            doc_repo = DocumentRepository(session)
            chunker = ChunkingService()

            # Get documents that need processing
            pending_docs = await doc_repo.get_by_status("uploaded")
            failed_docs = await doc_repo.get_by_status("failed")
            docs_to_process = pending_docs + failed_docs

            logger.info("Found %d documents to process", len(docs_to_process))

            success_count = 0
            fail_count = 0

            for doc in docs_to_process:
                try:
                    await chunker.process_document(doc, session)
                    await session.commit()
                    success_count += 1
                except Exception as e:
                    await session.rollback()
                    logger.error("Failed to process document %s: %s", doc.id, e)
                    fail_count += 1

            logger.info(
                "Daily index rebuild: %d succeeded, %d failed out of %d",
                success_count,
                fail_count,
                len(docs_to_process),
            )

    except Exception as e:
        logger.error("Daily index rebuild failed: %s", e, exc_info=True)
    finally:
        _release_lock(job_id)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("Job '%s' finished in %.2fs", job_id, duration)


async def job_sync_external_data() -> None:
    """Sync external data (placeholder for future use).

    This job can be extended to:
    - Fetch reviews from CH Play API
    - Sync with external databases
    - Update app metadata
    """
    job_id = "sync_external_data"
    if not _acquire_lock(job_id):
        return

    start_time = datetime.now(timezone.utc)
    logger.info("Job '%s' started at %s (placeholder)", job_id, start_time.isoformat())

    try:
        # Placeholder: implement actual sync logic here
        logger.info("External data sync completed (no-op placeholder).")
    except Exception as e:
        logger.error("External data sync failed: %s", e, exc_info=True)
    finally:
        _release_lock(job_id)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("Job '%s' finished in %.2fs", job_id, duration)


async def job_cleanup_old_versions() -> None:
    """Clean up old versions and expired data.

    Process:
    1. Identify documents with failed status older than 7 days
    2. Soft-delete or mark for cleanup
    3. Remove expired sessions / temporary files
    4. Log cleanup summary
    """
    job_id = "cleanup_old_versions"
    if not _acquire_lock(job_id):
        return

    start_time = datetime.now(timezone.utc)
    logger.info("Job '%s' started at %s", job_id, start_time.isoformat())

    try:
        from app.db.repository.document import DocumentRepository

        async with async_session_factory() as session:
            doc_repo = DocumentRepository(session)

            # Get failed documents older than 7 days
            failed_docs = await doc_repo.get_by_status("failed")

            # Placeholder: cleanup logic
            # For now, just log the count
            logger.info(
                "Cleanup: found %d failed documents (older items would be cleaned here)",
                len(failed_docs),
            )

    except Exception as e:
        logger.error("Cleanup job failed: %s", e, exc_info=True)
    finally:
        _release_lock(job_id)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("Job '%s' finished in %.2fs", job_id, duration)


async def job_retry_failed_jobs() -> None:
    """Retry failed processing jobs.

    Process:
    1. Fetch documents with status 'failed'
    2. Attempt to re-process them through the chunking pipeline
    3. Log retry results
    """
    job_id = "retry_failed_jobs"
    if not _acquire_lock(job_id):
        return

    start_time = datetime.now(timezone.utc)
    logger.info("Job '%s' started at %s", job_id, start_time.isoformat())

    try:
        from app.db.repository.document import DocumentRepository
        from app.services.chunking.chunker import ChunkingService

        async with async_session_factory() as session:
            doc_repo = DocumentRepository(session)
            chunker = ChunkingService()

            failed_docs = await doc_repo.get_by_status("failed")
            logger.info("Retry: found %d failed documents", len(failed_docs))

            success_count = 0
            fail_count = 0

            for doc in failed_docs:
                try:
                    await chunker.process_document(doc, session)
                    await session.commit()
                    success_count += 1
                except Exception as e:
                    await session.rollback()
                    logger.error("Retry failed for document %s: %s", doc.id, e)
                    fail_count += 1

            logger.info(
                "Retry failed jobs: %d succeeded, %d still failed",
                success_count,
                fail_count,
            )

    except Exception as e:
        logger.error("Retry failed jobs failed: %s", e, exc_info=True)
    finally:
        _release_lock(job_id)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("Job '%s' finished in %.2fs", job_id, duration)


async def job_label_comments() -> None:
    """Label pending comments with Spark + PhoBERT.

    Process:
    1. Fetch comments with absa_status == 'pending'
    2. Predict labels via the PhoBERT API
    3. Update overall_sentiment / absa_status and create aspect rows
    4. Log summary
    """
    job_id = "label_comments"
    if not _acquire_lock(job_id):
        return

    start_time = datetime.now(timezone.utc)
    logger.info("Job '%s' started at %s", job_id, start_time.isoformat())

    try:
        from app.jobs.label_comments import run_label_comments

        await run_label_comments()
    except Exception as e:
        logger.error("Label comments job failed: %s", e, exc_info=True)
    finally:
        _release_lock(job_id)
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info("Job '%s' finished in %.2fs", job_id, duration)


# ── Scheduler ────────────────────────────────────────────────────────


class BackgroundScheduler:
    """APScheduler wrapper for managing periodic background jobs.

    Usage:
        scheduler = BackgroundScheduler()
        scheduler.start()
        # ... application runs ...
        scheduler.stop()
    """

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
        self._jobs_registered: bool = False

    def register_jobs(self) -> None:
        """Register all periodic jobs with the scheduler.

        Jobs and their schedules:
        - Daily index rebuild: every day at 02:00 AM
        - Sync external data: every hour
        - Cleanup old versions: every day at 03:00 AM
        - Retry failed jobs: every 30 minutes
        - Label comments: every 30 seconds
        """
        if self._jobs_registered:
            logger.warning("Jobs already registered, skipping.")
            return

        # Daily index rebuild at 02:00
        self.scheduler.add_job(
            job_daily_rebuild_index,
            CronTrigger(hour=2, minute=0, timezone=settings.SCHEDULER_TIMEZONE),
            id="daily_rebuild_index",
            name="Daily index rebuild",
            coalesce=True,
            max_instances=1,
        )

        # Sync external data every hour
        self.scheduler.add_job(
            job_sync_external_data,
            IntervalTrigger(hours=1),
            id="sync_external_data",
            name="Sync external data",
            coalesce=True,
            max_instances=1,
        )

        # Cleanup old versions at 03:00 daily
        self.scheduler.add_job(
            job_cleanup_old_versions,
            CronTrigger(hour=3, minute=0, timezone=settings.SCHEDULER_TIMEZONE),
            id="cleanup_old_versions",
            name="Cleanup old versions",
            coalesce=True,
            max_instances=1,
        )

        # Retry failed jobs every 30 minutes
        self.scheduler.add_job(
            job_retry_failed_jobs,
            IntervalTrigger(minutes=30),
            id="retry_failed_jobs",
            name="Retry failed jobs",
            coalesce=True,
            max_instances=1,
        )

        # Label comments every 30 seconds (Spark + PhoBERT)
        self.scheduler.add_job(
            job_label_comments,
            IntervalTrigger(seconds=30),
            id="label_comments",
            name="Label comments (Spark + PhoBERT)",
            coalesce=True,
            max_instances=1,
        )

        self._jobs_registered = True
        logger.info("Registered %d periodic jobs", len(self.scheduler.get_jobs()))

    def start(self) -> None:
        """Start the scheduler.

        Registers jobs if not already registered, then starts the scheduler.
        """
        if not self._jobs_registered:
            self.register_jobs()

        if not self.scheduler.running:
            self.scheduler.start()
            logger.info(
                "Background scheduler started (timezone: %s)",
                settings.SCHEDULER_TIMEZONE,
            )
        else:
            logger.warning("Scheduler is already running.")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Background scheduler stopped.")

    @property
    def running(self) -> bool:
        """Check if the scheduler is currently running."""
        return self.scheduler.running

    def get_jobs_info(self) -> list[dict[str, Any]]:
        """Get information about all registered jobs.

        Returns:
            A list of dicts with job info (id, name, next_run_time, trigger).
        """
        jobs = self.scheduler.get_jobs()
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ]


# ── Main entry point ─────────────────────────────────────────────────

def run_scheduler() -> None:
    """Run the scheduler as a standalone process.

    This is the entry point for running the scheduler separately
    from the API process. Usage:
        python -m app.workers.scheduler
    """
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    scheduler = BackgroundScheduler()
    scheduler.start()

    logger.info("Scheduler started. Press Ctrl+C to stop.")

    try:
        # Keep the process alive
        import signal

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Handle shutdown signals
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: loop.stop())
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                pass

        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.stop()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    run_scheduler()
