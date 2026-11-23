"""Vanilla JavaScript stack extractor package."""

from .extract import JsModuleFacts, extract_javascript
from .record import build_javascript_chunk_record

__all__ = [
    "JsModuleFacts",
    "extract_javascript",
    "build_javascript_chunk_record",
]
