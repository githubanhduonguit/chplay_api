"""
Dependencies for the application.

This module exports dependency functions used across the application.
"""

from app.dependencies.auth import get_current_user

__all__ = ["get_current_user"]
