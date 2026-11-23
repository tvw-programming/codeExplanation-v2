"""Phase 4 — storage and reuse.

Per the locked rule: chunk JSON files are saved in a dummy folder that
mirrors the client repo's structure, keyed by the chunk's primary file
path. On a later run, the stored contentHash is compared against the
current file's hash; a match means the stored JSON is reused with no
re-analysis, and a mismatch (or no stored record at all) means that one
chunk is re-extracted. Nothing else is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.extract.common import content_hash

# Bumped whenever the extractors start producing materially different
# records for unchanged source — new fields, better line ranges, fixed
# detection. The stored record carries the version it was written with,
# and a mismatch forces re-analysis.
#
# Without this, reuse is keyed on the source file's content alone, so an
# improvement to the extractor would never reach any chunk already in a
# user's store: their files haven't changed, so every chunk is reused
# and the improvement silently does nothing.
#
# History:
#   1 - original: contentHash-only reuse.
#   2 - eventHandlers carry a lineRange, so the narration can highlight
#       the handler line it is talking about.
#   3 - importantFunctions carry doc comments, call graph and body
#       facts, so the narration can describe a function instead of
#       only naming it.
#   4 - records carry the file's own header comment, for the card that
#       introduces each file in the video.
#   5 - fidelity + visualAvailability envelope; refuse blank visuals.
#   6 - visualGraph component_tree + lifecycleFlows for React; jsxMounts /
#       hooks / callback outputs on frontend records.
#   7 - Go Fiber route_tree + ordered middleware lifecycle; middleware /
#       routeGroups / usesFiber on backend Go records.
#   8 - Multi-stack visuals: Python ast, Express detect+routes, Spring DI,
#       Angular dedicated extractor, Vue/Solid/Qwik/JS/Rust extract+graphs.
#   9 - Extractor hardening: per-stack packages; honesty fixes (APIRouter
#       prefix, Spring methods/Lombok, Express route chains, Angular
#       signal I/O, Rust methods); React/Go/FE layout migrate.
#  10 - Angular project selector index → template child mount edges
#       (unmatched tags skipped; duplicates skipped; attribute assumed).
#  11 - Django urlpatterns path()/re_path()/url() literals; include()
#       mounts assumed (not joined cross-file); method UNKNOWN.
#  12 - Spring honesty: bare @RequestMapping → ALL (not silent GET);
#       multi method=/path arrays; ${}/#{} assumed; setter/@Inject DI;
#       multi-ctor assumed; Spring Data repo interfaces (no Impl invent).
#  13 - Go Fiber honesty: generics on funcs/structs/interfaces;
#       interface method sets (no Impl edges); fiber.Handler factories;
#       All()/literal Add() routes; Route() closures still skipped.
#  14 - Express honesty: nested literal mounts compose; path arrays;
#       regex routes assumed (no URL invent); per-route METHOD middleware;
#       use(prefix, non-router) is path-scoped middleware not a mount;
#       non-literal mount prefixes assumed.
#  15 - Python honesty: in-file Django view/CBV HTTP methods; Flask
#       Blueprint(url_prefix=); in-file include_router/register_blueprint
#       literal mounts; non-literal mounts → assumed.
#  17 - Shared route-prefix resolver (PrefixGraph); FastAPI include_router
#       + Django include() cross-file join on unique literal resolution;
#       Go Fiber groups via shared resolver (no assumed "app" root);
#       routes may carry pathResolved / prefixChain.
#  18 - Rust honesty: real handlers, qualified axum::routing::*, chained
#       MethodRouter methods, in-file .nest compose; no Express-style
#       .get("/path"); unresolved nest invents no children.
#  19 - Express/Flask PrefixGraph cross-file mounts (unique require /
#       register_blueprint); Spring cross-file mounts deferred.
#  20 - React JSX brace/memo/HOC/hook honesty; Go brace-scoped Route()
#       + explicit var _ interface assertions; Angular templateUrl
#       class+html bundle chunking.
EXTRACTOR_VERSION = 20


def output_path_for(output_root: Path, file_path: str) -> Path:
    """The stored JSON for a chunk lives at <output_root>/<filePath>.json —
    mirroring the client repo's own directory structure, with .json
    appended so it never collides with the real source file."""
    return output_root / f"{file_path}.json"


def read_stored(output_root: Path, file_path: str) -> dict | None:
    path = output_path_for(output_root, file_path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_stored(output_root: Path, file_path: str, record: dict) -> Path:
    path = output_path_for(output_root, file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def needs_reanalysis(output_root: Path, source_root: Path, file_path: str) -> tuple[bool, str]:
    """Returns (should_reanalyze, current_content_hash).

    True (needs re-analysis) when there is no stored record yet, the
    stored record has no contentHash to compare against, the hashes
    differ, or the record was written by an older extractor version.
    False only when a stored record exists, its contentHash exactly
    matches the file's current content, and it was produced by the
    current extractor.
    """
    current_hash = content_hash(source_root, file_path)
    stored = read_stored(output_root, file_path)
    if stored is None:
        return True, current_hash
    stored_hash = stored.get("contentHash")
    if not stored_hash or stored_hash != current_hash:
        return True, current_hash
    # Records written before this field existed are version 1.
    if stored.get("extractorVersion", 1) != EXTRACTOR_VERSION:
        return True, current_hash
    return False, current_hash
