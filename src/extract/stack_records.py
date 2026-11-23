"""Thin re-exports of per-stack record builders.

Hardened stacks live under `src/extract/<stack>/` (extract.py + record.py).
React / Go builders also live in packages; `json_builder` remains a shim.
"""

from __future__ import annotations

from .python import build_python_chunk_record
from .angular import build_angular_chunk_record
from .spring import build_spring_chunk_record
from .express import build_express_chunk_record
from .rust import build_rust_chunk_record
from .vue import build_vue_chunk_record
from .solid import build_solid_chunk_record
from .qwik import build_qwik_chunk_record
from .javascript import build_javascript_chunk_record
from .react import build_frontend_chunk_record
from .go import build_backend_go_chunk_record

__all__ = [
    "build_python_chunk_record",
    "build_angular_chunk_record",
    "build_spring_chunk_record",
    "build_express_chunk_record",
    "build_rust_chunk_record",
    "build_vue_chunk_record",
    "build_solid_chunk_record",
    "build_qwik_chunk_record",
    "build_javascript_chunk_record",
    "build_frontend_chunk_record",
    "build_backend_go_chunk_record",
]
