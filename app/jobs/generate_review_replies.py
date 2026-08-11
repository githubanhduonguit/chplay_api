"""Job to generate bot replies for pending reviews.

Flow:
1. Create Spark session.
2. Open async DB session.
3. Fetch pending reviews via CommentRepository.
4. For each review:
   a. Mark as 'processing'.
   b. Call ReviewReplyAgent to generate reply.
   c. If success: create bot reply comment, mark review as 'completed'.
   d. If failure: log error, mark review as 'failed'.
5. Log summary.

Each review is processed in its own transaction for isolation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.core.config import settings
from app.db.session import async_session_factory
from app.db.repository.comment import CommentRepository
from app.services.agents.review_reply_agent import ReviewReplyAgent
from app.services.llm.glm import GLMReviewReplyService
from app.services.spark.session import get_spark_session

logger = logging.getLogger(__name__)


@dataclass
class JobResult:
    """Result of a job run."""

    success: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


async def process_single_review(
    repo: CommentRepository,
    agent: ReviewReplyAgent,
    review_id: int,
) -> tuple[bool, str | None]:
    """Process a single review: generate reply and save bot comment.

    Args:
        repo: The CommentRepository instance.
        agent: The ReviewReplyAgent instance.
        review_id: The ID of the review to process.

    Returns:
        A tuple of (success: bool, error_message: str | None).
    """
    try:
        # Re-fetch review within current session to get fresh object
        review = await repo.get(review_id)
        if review is None:
            return False, f"Review {review_id} not found in current session."

        # Check if still pending or processing (idempotency)
        if review.bot_reply_status not in ("pending", "processing"):
            return False, (
                f"Review {review_id} has status '{review.bot_reply_status}', "
                f"expected 'pending' or 'processing'. Skipping."
            )

        # Check for existing bot reply (avoid duplicates)
        has_reply = await repo.has_bot_reply_for_review(review.id)
        if has_reply:
            logger.warning("Review %s already has a bot reply. Skipping.", review.id)
            return False, "Bot reply already exists."

        # Generate reply
        result = await agent.run(review)
        if not result.success or not result.reply:
            return False, result.error or "Agent returned no reply."

        # Save bot reply
        await repo.create_bot_reply(review, result.reply)

        # Mark review as completed
        await repo.update_bot_reply_status(review.id, "completed")

        await repo.session.commit()
        logger.info("Successfully processed review %s.", review.id)
        return True, None

    except Exception as e:
        await repo.session.rollback()
        error_msg = f"Error processing review {review_id}: {str(e)}"
        logger.error(error_msg, exc_info=True)

        # Mark review as failed in a new transaction
        try:
            await repo.update_bot_reply_status(review_id, "failed")
            await repo.session.commit()
        except Exception as commit_e:
            await repo.session.rollback()
            logger.error(
                "Failed to mark review %s as failed: %s",
                review_id,
                str(commit_e),
            )

        return False, error_msg


async def run_generate_review_replies(
    limit: int | None = None,
) -> JobResult:
    """Main job function: process pending reviews and generate bot replies.

    Args:
        limit: Maximum number of reviews to process in this run.
            Defaults to settings.REVIEW_REPLY_BATCH_SIZE.

    Returns:
        A JobResult with counts of success/failed/skipped.
    """
    if limit is None:
        limit = settings.REVIEW_REPLY_BATCH_SIZE
    job_result = JobResult()
    start_time = time.monotonic()

    logger.info("Starting generate_review_replies job with limit=%s.", limit)

    # Create Spark session (optional — used as batch boundary for future scaling)
    spark = get_spark_session(app_name="generate-review-replies")
    if spark is not None:
        logger.info("Spark session created: %s", spark.sparkContext.appName)
    else:
        logger.info("Running without Spark session.")

    # Process reviews using async DB
    async with async_session_factory() as session:
        repo = CommentRepository(session)
        agent = ReviewReplyAgent(
            llm_service=GLMReviewReplyService(),
        )

        # Get pending reviews
        pending_reviews = await repo.get_pending_bot_reply_reviews(limit=limit)
        job_result.total = len(pending_reviews)
        logger.info("Found %s pending reviews to process.", job_result.total)

        for review in pending_reviews:
            # Mark as processing first
            try:
                await repo.update_bot_reply_status(review.id, "processing")
                await session.flush()
            except Exception as e:
                logger.error(
                    "Failed to mark review %s as processing: %s",
                    review.id,
                    str(e),
                )
                job_result.skipped += 1
                continue

            # Process the review
            success, error = await process_single_review(repo, agent, review.id)

            if success:
                job_result.success += 1
            else:
                job_result.failed += 1
                if error:
                    job_result.errors.append(error)

    duration = time.monotonic() - start_time
    job_result.duration_seconds = round(duration, 2)

    logger.info(
        "Job finished. Success=%s, Failed=%s, Skipped=%s, "
        "Total=%s, Duration=%ss.",
        job_result.success,
        job_result.failed,
        job_result.skipped,
        job_result.total,
        job_result.duration_seconds,
    )

    if job_result.errors:
        logger.warning("Errors encountered:")
        for err in job_result.errors:
            logger.warning("  - %s", err)

    return job_result


def _parse_args() -> int:
    """Parse CLI arguments. Lazy import to avoid side effects on module load."""
    from argparse import ArgumentParser

    parser = ArgumentParser(
        description="Generate bot replies for pending reviews."
    )
    from app.core.config import settings

    parser.add_argument(
        "--limit",
        type=int,
        default=settings.REVIEW_REPLY_BATCH_SIZE,
        help=f"Maximum number of reviews to process (default: {settings.REVIEW_REPLY_BATCH_SIZE}).",
    )
    args = parser.parse_args()
    return args.limit


async def main() -> None:
    """CLI entrypoint for running the job."""
    limit = _parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = await run_generate_review_replies(limit=limit)

    print("\n=== Job Result ===")
    print(f"  Success:  {result.success}")
    print(f"  Failed:   {result.failed}")
    print(f"  Skipped:  {result.skipped}")
    print(f"  Total:    {result.total}")
    print(f"  Duration: {result.duration_seconds}s")
    if result.errors:
        print("\n  Errors:")
        for err in result.errors:
            print(f"    - {err}")


if __name__ == "__main__":
    asyncio.run(main())
