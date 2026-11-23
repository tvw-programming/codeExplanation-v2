"""React stack extractor package (TS/JSX regex)."""

from .extract import *  # noqa: F403
from .record import build_frontend_chunk_record

__all__ = [
    "build_frontend_chunk_record",
]
