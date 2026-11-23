"""Angular stack extractor package."""

from .extract import (
    AngularComponent,
    AngularMount,
    SelectorEntry,
    build_selector_index,
    extract_angular_component,
    extract_template_mounts,
    load_template_sibling,
    parse_selector_fragments,
)
from .record import build_angular_chunk_record

__all__ = [
    "AngularComponent",
    "AngularMount",
    "SelectorEntry",
    "build_angular_chunk_record",
    "build_selector_index",
    "extract_angular_component",
    "extract_template_mounts",
    "load_template_sibling",
    "parse_selector_fragments",
]
