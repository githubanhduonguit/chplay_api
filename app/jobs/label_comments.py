"""Job to label pending comments with aspect-based sentiment (Spark + PhoBERT).

Flow:
1. Create Spark session (optional — used as batch boundary, None is fine).
2. Open async DB session.
3. Fetch pending reviews (type == "review", absa_status == "pending")
   via CommentRepository.
4. Call PhoBERTClient.predict_batch to get labels for all review contents.
5. For each comment:
   a. Set overall_sentiment from the prediction (sentiment or label).
   b. Mark absa_status as 'completed' (or 'failed' on error).
   c. Create CommentAspect rows when the prediction includes aspects.
6. Commit and log a summary.

Only reviews are labeled — comments (user replies and bot replies,
type == "comment") are excluded.
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


def _split_pipe(value: Any) -> list[str]:
    """Split a pipe-separated string into non-empty stripped tokens.

    Args:
        value: Value from the API (expected str like "a|b", may be None).

    Returns:
        List of non-empty tokens.
    """
    if not value:
        return []
    return [t.strip() for t in str(value).split("|") if t.strip()]


def _extract_aspects(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract a normalized list of aspect dicts from a prediction result.

    Primary format (new PhoBERT API):
        {"topic_l1": "account_user|content_features",
         "topic_l2": "signup_issue|feature_bug"}
        → zips L1 and L2 positionally: [(account_user, signup_issue),
          (content_features, feature_bug)]. When topic_l2 is empty,
          each L1 is emitted with topic_l2=None.

    Fallback format (old API):
        {"aspect": [{"aspect": "technical_issue", ...}, ...]}
        → each entry becomes {"topic_l1": aspect_name, "topic_l2": None}.

    Args:
        result: A single prediction dict from the PhoBERT API.

    Returns:
        A list of aspect dicts (empty if none present).
    """
    # Primary: topic_l1 / topic_l2 pipe-separated strings
    if "topic_l1" in result:
        l1_list = _split_pipe(result.get("topic_l1"))
        l2_list = _split_pipe(result.get("topic_l2"))
        aspects: list[dict[str, Any]] = []
        if not l2_list:
            aspects = [{"topic_l1": l1} for l1 in l1_list]
        else:
            aspects = [
                {"topic_l1": l1, "topic_l2": l2}
                for l1, l2 in zip(l1_list, l2_list)
            ]
        return aspects

    # Fallback: old "aspect" list format
    aspect_data = result.get("aspect")
    if isinstance(aspect_data, list):
        out: list[dict[str, Any]] = []
        for a in aspect_data:
            if not isinstance(a, dict):
                continue
            name = a.get("aspect") or a.get("name")
            if not name:
                continue
            item = dict(a)
            item["topic_l1"] = str(name)
            item["topic_l2"] = None
            out.append(item)
        return out
    if isinstance(aspect_data, dict):
        name = aspect_data.get("aspect") or aspect_data.get("name")
        if name:
            item = dict(aspect_data)
            item["topic_l1"] = str(name)
            item["topic_l2"] = None
            return [item]
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
            created_aspects: list[str] = []
            try:
                for aspect in _extract_aspects(result):
                    aspect_l1 = aspect.get("topic_l1")
                    aspect_l2 = aspect.get("topic_l2")
                    aspect_sentiment = aspect.get("sentiment") or aspect.get("label")
                    if not aspect_l1:
                        continue
                    session.add(
                        CommentAspect(
                            comment_id=comment.id,
                            topic_l1=str(aspect_l1),
                            topic_l2=str(aspect_l2) if aspect_l2 else None,
                            sentiment=str(aspect_sentiment or sentiment or "neutral"),
                            confidence_score=_to_float(
                                aspect.get("confidence_score")
                                or aspect.get("confidence")
                                or aspect.get("score")
                            ),
                            model_version=aspect.get("model_version"),
                        )
                    )
                    created_aspects.append(
                        str(aspect_l1) + (f"|{aspect_l2}" if aspect_l2 else "")
                    )
            except Exception as e:
                logger.warning(
                    "Failed to create aspects for comment %s: %s",
                    comment.id,
                    e,
                )

            logger.info(
                "Labeled comment %s: sentiment=%s, aspects=%s",
                comment.id,
                comment.overall_sentiment,
                created_aspects or "(none)",
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
