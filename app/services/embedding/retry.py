"""
Retry and timeout utilities for embedding service.

Provides configurable retry strategies and timeout handling
using tenacity for resilience against transient failures.
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar
from asyncio import timeout as async_timeout

from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.stop import stop_never

import logging

from app.core.config import settings
from app.core.exceptions import EmbeddingError, EmbeddingTimeoutError

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# ── Tenacity Retry Strategies ────────────────────────────────────────


def default_retry_strategy() -> AsyncRetrying:
    """Default retry strategy for embedding API calls.

    Uses exponential backoff with jitter, retrying only on
    transient errors (network issues, 5xx responses).
    Retries up to RETRY_ATTEMPTS times from global settings.

    Returns:
        An AsyncRetrying instance configured with the default strategy.
    """
    return AsyncRetrying(
        stop=stop_after_attempt(settings.EMBEDDING_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(
            (
                ConnectionError,
                TimeoutError,
                EmbeddingTimeoutError,
            ),
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


def aggressive_retry_strategy() -> AsyncRetrying:
    """More aggressive retry for critical background embedding jobs.

    Retries indefinitely with exponential backoff up to 60s.
    Suitable for Spark batch jobs or scheduled index builds.

    Returns:
        An AsyncRetrying instance with more retries and longer waits.
    """
    return AsyncRetrying(
        stop=stop_never,
        wait=wait_exponential(multiplier=2, min=2, max=60),
        retry=retry_if_exception_type(
            (
                ConnectionError,
                TimeoutError,
                EmbeddingTimeoutError,
            ),
        ),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )


# ── Timeout Decorator ────────────────────────────────────────────────


def with_timeout(custom_timeout: int | None = None) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator that wraps an async function with a timeout.

    Args:
        custom_timeout: Override the default timeout from settings.

    Returns:
        A decorator that applies the timeout to the async function.
    """
    timeout_seconds = custom_timeout or settings.EMBEDDING_TIMEOUT

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                async with async_timeout(timeout_seconds):
                    return await func(*args, **kwargs)
            except TimeoutError as e:
                raise EmbeddingTimeoutError(timeout=timeout_seconds) from e

        return wrapper

    return decorator
