"""Go stack extractor package (Fiber regex)."""

from .extract import *  # noqa: F403
from .record import build_backend_go_chunk_record

__all__ = [
    "build_backend_go_chunk_record",
]
