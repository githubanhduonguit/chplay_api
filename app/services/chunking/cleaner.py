"""
Text cleaning service.

Normalizes and cleans raw text before chunking:
- Normalizes whitespace (tabs → spaces, multiple spaces → single space)
- Removes unwanted control characters
- Strips leading/trailing whitespace per line
- Removes empty lines
- Optionally normalizes Unicode characters
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

logger = logging.getLogger(__name__)

# Control characters to remove (keep newlines, tabs, carriage returns)
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Multiple whitespace pattern (excluding newlines)
_MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")

# Multiple blank lines pattern
_MULTI_BLANK_LINE_PATTERN = re.compile(r"\n{3,}")

# URL pattern
_URL_PATTERN = re.compile(r"https?://\S+")

# Email pattern
_EMAIL_PATTERN = re.compile(r"\S+@\S+\.\S+")


class TextCleanerService:
    """Service for cleaning and normalizing raw text before chunking.

    Applies configurable cleaning operations to prepare text
    for consistent chunking and embedding.
    """

    def __init__(self, config: dict[str, bool] | None = None) -> None:
        """
        Args:
            config: Dict of cleaning options. Defaults to all enabled.
                Keys:
                - normalize_unicode: Normalize Unicode (NFKC). Default True.
                - remove_control_chars: Remove control characters. Default True.
                - normalize_whitespace: Collapse multiple spaces. Default True.
                - strip_lines: Strip leading/trailing whitespace per line. Default True.
                - remove_empty_lines: Remove entirely blank lines. Default True.
                - collapse_newlines: Collapse 3+ newlines to 2. Default True.
                - remove_urls: Remove URLs from text. Default False.
                - remove_emails: Remove email addresses. Default False.
                - max_line_length: Truncate lines longer than this. Default 0 (disabled).
        """
        self.config = {
            "normalize_unicode": True,
            "remove_control_chars": True,
            "normalize_whitespace": True,
            "strip_lines": True,
            "remove_empty_lines": True,
            "collapse_newlines": True,
            "remove_urls": False,
            "remove_emails": False,
            "max_line_length": 0,
        }
        if config:
            self.config.update(config)

    # ── Public API ───────────────────────────────────────────────────

    def clean(self, text: str) -> str:
        """Clean and normalize raw text.

        Args:
            text: Raw input text.

        Returns:
            Cleaned text ready for chunking.
        """
        if not text:
            return ""

        result = text

        if self.config["normalize_unicode"]:
            result = self._normalize_unicode(result)

        if self.config["remove_control_chars"]:
            result = self._remove_control_chars(result)

        if self.config["remove_urls"]:
            result = _URL_PATTERN.sub("", result)

        if self.config["remove_emails"]:
            result = _EMAIL_PATTERN.sub("", result)

        if self.config["strip_lines"]:
            result = self._strip_lines(result)

        if self.config["normalize_whitespace"]:
            result = self._normalize_whitespace(result)

        if self.config["remove_empty_lines"]:
            result = self._remove_empty_lines(result)

        if self.config["collapse_newlines"]:
            result = _MULTI_BLANK_LINE_PATTERN.sub(r"\n\n", result)

        if self.config["max_line_length"] > 0:
            result = self._truncate_long_lines(result, self.config["max_line_length"])

        return result.strip()

    def clean_lines(self, lines: list[str]) -> list[str]:
        """Clean a list of lines.

        Args:
            lines: List of text lines.

        Returns:
            List of cleaned, non-empty lines.
        """
        return [line for line in (self.clean(line) for line in lines) if line]

    # ── Internal cleaning methods ────────────────────────────────────

    @staticmethod
    def _normalize_unicode(text: str) -> str:
        """Normalize Unicode characters to NFKC form.

        Converts compatibility characters (e.g., ﬁ → fi, ⁵ → 5).

        Args:
            text: Input text.

        Returns:
            NFKC-normalized text.
        """
        return unicodedata.normalize("NFKC", text)

    @staticmethod
    def _remove_control_chars(text: str) -> str:
        """Remove unwanted control characters.

        Preserves newlines (\\n), carriage returns (\\r), and tabs (\\t).

        Args:
            text: Input text.

        Returns:
            Text with control characters removed.
        """
        return _CONTROL_CHARS_PATTERN.sub("", text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Normalize whitespace within lines.

        Replaces tabs with spaces and collapses multiple spaces.

        Args:
            text: Input text.

        Returns:
            Text with normalized whitespace.
        """
        return _MULTI_SPACE_PATTERN.sub(" ", text)

    @staticmethod
    def _strip_lines(text: str) -> str:
        """Strip leading/trailing whitespace from each line.

        Args:
            text: Input text.

        Returns:
            Text with stripped lines.
        """
        lines = text.split("\n")
        stripped = [line.strip() for line in lines]
        return "\n".join(stripped)

    @staticmethod
    def _remove_empty_lines(text: str) -> str:
        """Remove entirely blank lines.

        Args:
            text: Input text.

        Returns:
            Text with empty lines removed.
        """
        lines = text.split("\n")
        non_empty = [line for line in lines if line.strip()]
        return "\n".join(non_empty)

    @staticmethod
    def _truncate_long_lines(text: str, max_length: int) -> str:
        """Truncate lines that exceed a maximum length.

        Args:
            text: Input text.
            max_length: Maximum characters per line.

        Returns:
            Text with long lines truncated.
        """
        lines = text.split("\n")
        truncated = [line[:max_length] if len(line) > max_length else line for line in lines]
        return "\n".join(truncated)

    def describe(self) -> dict[str, Any]:
        """Return the current cleaning configuration.

        Returns:
            Dict of cleaning options with their current values.
        """
        return dict(self.config)
