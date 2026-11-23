"""Optional parser substrate (tree-sitter).

Extractors must keep working when this package's optional deps are
missing: call sites catch ``ParserUnavailable`` / use ``try_parse`` and
fall back to the existing regex/ast path. Never invent edges from a
partial tree.
"""

from .tree_sitter_support import (
    ParserUnavailable,
    ParsedFile,
    tree_sitter_enabled,
    try_parse,
)

__all__ = [
    "ParserUnavailable",
    "ParsedFile",
    "tree_sitter_enabled",
    "try_parse",
]
