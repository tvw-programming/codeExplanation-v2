"""Angular stack extractor package."""

from .extract import AngularComponent, extract_angular_component, load_template_sibling
from .record import build_angular_chunk_record

__all__ = [
    "AngularComponent",
    "extract_angular_component",
    "load_template_sibling",
    "build_angular_chunk_record",
]
