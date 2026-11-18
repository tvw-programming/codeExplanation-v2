"""Phase 3 — frontend-to-backend featureMapping: match API calls to
routes by URL, per the locked rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PARAM_RE = re.compile(r"\$\{[^}]+\}|:[\w]+")


def normalize_path(path: str) -> str:
    """Strip dynamic segments (${id} on the frontend, :id on the Fiber
    side) to a comparable template, e.g. '/alumni/${id}' and
    '/api/v1/alumni/:id' both become 'alumni/{}' once the base is removed
    by the caller — this function only normalizes params, the caller
    handles the base URL."""
    normalized = PARAM_RE.sub("{}", path)
    return normalized.strip("/")


@dataclass
class MatchedLink:
    frontend_chunk_id: str
    backend_chunk_id: str
    method: str
    frontend_url: str
    backend_path: str
    assumed: bool


def match_calls_to_routes(
    frontend_calls: list[tuple[str, str, str, bool]],   # (chunk_id, method, url, url_is_template)
    backend_routes: list[tuple[str, str, str, bool]],    # (chunk_id, method, path, route_assumed)
    base_url: str | None,
) -> list[MatchedLink]:
    """Match each frontend API call to a backend route by method + URL,
    accounting for the frontend axios client's baseURL prefix."""
    base = (base_url or "").strip("/")

    # Index backend routes by (method, normalized_path).
    backend_index: dict[tuple[str, str], list[tuple[str, str, bool]]] = {}
    for chunk_id, method, path, route_assumed in backend_routes:
        key = (method.upper(), normalize_path(path))
        backend_index.setdefault(key, []).append((chunk_id, path, route_assumed))

    links: list[MatchedLink] = []
    for chunk_id, method, url, url_is_template in frontend_calls:
        combined = (base + "/" + url.lstrip("/")) if base else url
        key = (method.upper(), normalize_path(combined))
        for backend_chunk_id, backend_path, route_assumed in backend_index.get(key, []):
            links.append(MatchedLink(
                frontend_chunk_id=chunk_id,
                backend_chunk_id=backend_chunk_id,
                method=method.upper(),
                frontend_url=url,
                backend_path=backend_path,
                assumed=url_is_template or route_assumed,
            ))
    return links
