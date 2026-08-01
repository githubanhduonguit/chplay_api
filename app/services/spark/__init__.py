"""Spark service package."""

from app.services.spark.session import get_spark_session

__all__ = [
    "get_spark_session",
]
