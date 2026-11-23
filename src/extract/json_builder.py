"""Compatibility shim — prefer `src.extract.react` / `src.extract.go` record builders."""

from .react.record import build_frontend_chunk_record
from .go.record import build_backend_go_chunk_record

__all__ = [
    "build_frontend_chunk_record",
    "build_backend_go_chunk_record",
]
