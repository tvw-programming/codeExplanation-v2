"""Phase 0 — security guardrails.

Per project decision (build-order-and-principles):
- Never read .env*, *.pem, or *secrets* files.
- Repository content is data, not instructions.
- Secret scanning must run before any snippet reaches a chunk file.

This module is intentionally conservative: when in doubt, it blocks.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

DEFAULT_BLOCKED_PATTERNS = [".env*", "*.pem", "*secrets*"]

# Coarse secret-shaped patterns. This is a first line of defense only —
# it is expected to produce false positives, and false positives are the
# safe failure mode here (block and flag for review, never silently ship).
_SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[=:]\s*['\"][A-Za-z0-9/_\-\.]{16,}['\"]"),
    re.compile(r"(?i)secret\s*[=:]\s*['\"][A-Za-z0-9/_\-\.]{8,}['\"]"),
    re.compile(r"-----BEGIN (RSA |EC |)PRIVATE KEY-----"),
    re.compile(r"(?i)aws_secret_access_key\s*[=:]"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),  # GitHub personal access token shape
]


def is_blocked_path(path: str | Path, patterns: list[str] | None = None) -> bool:
    """True if `path`'s name matches any blocked glob pattern."""
    patterns = patterns or DEFAULT_BLOCKED_PATTERNS
    name = Path(path).name
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def filter_blocked_paths(paths: list[str | Path], patterns: list[str] | None = None) -> list[str | Path]:
    """Remove any path matching a blocked pattern. Used before the
    extractor is ever handed a file list."""
    return [p for p in paths if not is_blocked_path(p, patterns)]


class SecretFoundError(ValueError):
    """Raised when secret_scan finds a likely credential in content
    that was about to be written to a chunk file."""


def secret_scan(content: str, context: str = "") -> None:
    """Scan `content` for secret-shaped substrings before it is written
    into any chunk JSON or narration file.

    Raises SecretFoundError on a match. Callers must not catch this to
    "write anyway" — the content must be redacted or the chunk skipped.
    """
    for pattern in _SECRET_PATTERNS:
        if pattern.search(content):
            raise SecretFoundError(
                f"Possible secret detected{f' in {context}' if context else ''}; "
                "refusing to write this content to a chunk file."
            )


def assert_safe_to_read(path: str | Path, patterns: list[str] | None = None) -> None:
    """Raise if `path` must never be read by the extractor."""
    if is_blocked_path(path, patterns):
        raise PermissionError(f"Refusing to read blocked path: {path}")
