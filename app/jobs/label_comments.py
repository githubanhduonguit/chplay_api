"""Job to label pending comments with aspect-based sentiment (Spark + PhoBERT).

Flow:
1. Create Spark session (optional — used as batch boundary, None is fine).
2. Open async DB session.
3. Fetch pending comments (absa_status == "pending") via CommentRepository.
4. Call PhoBERTClient.predict_batch to get labels for all comment contents.
5. For each comment:
   a. Set overall_sentiment from the prediction (sentiment or label).
   b. Mark absa_status as 'completed' (or 'failed' on error).
   c. Create CommentAspect rows when the prediction includes aspects.
6. Commit and log a summary.

This job only assigns labels — it does NOT generate bot replies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.core.exceptions import PhoBERTError
from app.db.models.comment_aspect import CommentAspect
from app.db.session import async_session_factory
from app.db.repository.comment import CommentRepository
from app.services.phobert.client import PhoBERTClient
from app.services.spark.session import get_spark_session

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 100


@dataclass
class LabelJobResult:
    """Result of a label job run."""

    labeled: int = 0
    failed: int = 0
    total: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


def _extract_aspects(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a normalized list of aspect dicts from a prediction result.

    Supports either a single aspect dict or a list of aspect dicts
    under the "aspect" key.

    Args:
        result: A single prediction dict from the PhoBERT API.

    Returns:
        A list of aspect dicts (empty if none present).
    """
    aspect_data = result.get("aspect")
    if isinstance(aspect_data, list):
        return [a for a in aspect_data if isinstance(a, dict)]
    if isinstance(aspect_data, dict):
        return [aspect_data]
    return []


def _to_float(value: Any) -> float | None:
    """Safely convert a value to float, or None if it cannot be converted.

    Args:
        value: The value to convert (e.g. confidence score from the API).

    Returns:
        The float value, or None when unparseable/missing.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def run_label_comments(limit: int | None = None) -> LabelJobResult:
    """Main job function: label pending comments via the PhoBERT API.

    Args:
        limit: Maximum number of comments to label in this run.
            Defaults to 100 when None.

    Returns:
        A LabelJobResult with counts of labeled/failed comments.
    """
    if limit is None:
        limit = DEFAULT_LIMIT
    job_result = LabelJobResult()
    start_time = time.monotonic()

    logger.info("Starting label_comments job with limit=%s.", limit)

    # Create Spark session (optional — used as batch boundary for future scaling)
    spark = get_spark_session(app_name="label-comments")
    if spark is not None:
        logger.info("Spark session created: %s", spark.sparkContext.appName)
    else:
        logger.info("Running without Spark session.")

    async with async_session_factory() as session:
        repo = CommentRepository(session)

        # Get pending comments
        comments = await repo.get_pending_label_comments(limit=limit)
        job_result.total = len(comments)
        logger.info("Found %s comments pending labeling.", job_result.total)

        if not comments:
            logger.info("No comments to label.")
            job_result.duration_seconds = round(time.monotonic() - start_time, 2)
            return job_result

        # Predict labels via PhoBERT (client splits into batches internally)
        client = PhoBERTClient()
        try:
            results = await client.predict_batch([c.content for c in comments])
        except PhoBERTError as e:
            logger.warning(
                "PhoBERT labeling skipped (PHOBERT_API_URL not configured or API error): %s",
                e,
            )
            job_result.duration_seconds = round(time.monotonic() - start_time, 2)
            return job_result

        if len(results) != len(comments):
            logger.warning(
                "PhoBERT returned %d results for %d comments; processing aligned pairs only.",
                len(results),
                len(comments),
            )

        for comment, result in zip(comments, results):
            try:
                sentiment = result.get("sentiment") or result.get("label")
                if sentiment:
                    comment.overall_sentiment = str(sentiment)
                comment.absa_status = "completed"
                job_result.labeled += 1
            except Exception as e:
                comment.absa_status = "failed"
                job_result.failed += 1
                error_msg = f"Failed to label comment {comment.id}: {e}"
                job_result.errors.append(error_msg)
                logger.error(error_msg)
                continue

            # Create CommentAspect rows if the prediction includes aspects
            try:
                for aspect in _extract_aspects(result):
                    aspect_name = aspect.get("aspect") or aspect.get("name")
                    aspect_sentiment = aspect.get("sentiment") or aspect.get("label")
                    if not aspect_name or not aspect_sentiment:
                        continue
                    session.add(
                        CommentAspect(
                            comment_id=comment.id,
                            aspect=str(aspect_name),
                            sentiment=str(aspect_sentiment),
                            confidence_score=_to_float(
                                aspect.get("confidence_score")
                                or aspect.get("confidence")
                                or aspect.get("score")
                            ),
                            model_version=aspect.get("model_version"),
                        )
                    )
            except Exception as e:
                logger.warning(
                    "Failed to create aspects for comment %s: %s",
                    comment.id,
                    e,
                )

        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Failed to commit label results: %s", e)
            job_result.errors.append(f"Commit failed: {e}")

    job_result.duration_seconds = round(time.monotonic() - start_time, 2)

    logger.info(
        "Label job finished. Labeled=%s, Failed=%s, Total=%s, Duration=%ss.",
        job_result.labeled,
        job_result.failed,
        job_result.total,
        job_result.duration_seconds,
    )

    if job_result.errors:
        logger.warning("Label job errors encountered:")
        for err in job_result.errors:
            logger.warning("  - %s", err)

    return job_result


async def main() -> None:
    """CLI entrypoint for manually running the label job."""
    from argparse import ArgumentParser

    parser = ArgumentParser(description="Label pending comments via PhoBERT.")
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Maximum number of comments to label (default: {DEFAULT_LIMIT}).",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = await run_label_comments(limit=args.limit)

    print("\n=== Label Job Result ===")
    print(f"  Labeled:  {result.labeled}")
    print(f"  Failed:   {result.failed}")
    print(f"  Total:    {result.total}")
    print(f"  Duration: {result.duration_seconds}s")
    if result.errors:
        print("\n  Errors:")
        for err in result.errors:
            print(f"    - {err}")


if __name__ == "__main__":
    asyncio.run(main())
