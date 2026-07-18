"""Spark session helper.

Provides a factory function for creating SparkSession instances
using settings from the application configuration.
Spark is optional — if Java is not installed, the helper gracefully
returns None so the caller can continue without Spark.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)


def get_spark_session(
    app_name: str | None = None,
    additional_config: dict[str, Any] | None = None,
) -> SparkSession | None:
    """Create or get a SparkSession, or None if Spark is unavailable.

    Wraps PySpark import and session creation in a try/except so the
    caller does not crash when Java or PySpark is not installed.

    Args:
        app_name: Optional override for the Spark application name.
            Defaults to settings.SPARK_APP_NAME.
        additional_config: Optional dict of additional Spark config
            key-value pairs to set on the session builder.

    Returns:
        A SparkSession instance, or None if unavailable.
    """
    try:
        from pyspark.sql import SparkSession

        builder = (
            SparkSession.builder
            .appName(app_name or settings.SPARK_APP_NAME)
            .master(settings.SPARK_MASTER)
        )

        if additional_config:
            for key, value in additional_config.items():
                builder = builder.config(key, value)

        spark = builder.getOrCreate()

        logger.info(
            "Spark session created: app_name=%s, master=%s",
            spark.sparkContext.appName,
            spark.sparkContext.master,
        )

        return spark

    except Exception:
        logger.warning(
            "Spark could not be started (Java not installed?). "
            "Continuing without Spark.",
        )
        return None
