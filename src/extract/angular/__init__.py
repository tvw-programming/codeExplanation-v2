"""Angular stack extractor package."""

from .extract import (
    AngularComponent,
    AngularMount,
    SelectorEntry,
    build_selector_index,
    extract_angular_component,
    extract_template_mounts,
    load_template_sibling,
    pair_angular_template_bundles,
    parse_selector_fragments,
    resolve_template_url_sibling,
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
    "pair_angular_template_bundles",
    "parse_selector_fragments",
    "resolve_template_url_sibling",
]
