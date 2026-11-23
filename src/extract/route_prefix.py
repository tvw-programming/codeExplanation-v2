"""Shared route-prefix resolution.

One dataflow pass, many stacks. Every framework in this project composes a
route's real URL out of facts that are NOT on the route's own line: a Fiber
group chain, an Express app.use mount in another file, a Spring class-level
@RequestMapping, a FastAPI include_router prefix, a Flask url_prefix, a
Django include() mount. The shape of the problem is identical every time —
a directed graph of (symbol → parent symbol, literal prefix segment) edges
whose roots carry no prefix — so it is solved once here and each extractor
only has to produce the edges.

Honesty contract: this module NEVER returns a bare string. It returns the
path it could build AND whether that path is complete, because a confidently
wrong URL is the worst output this pipeline can produce (a viewer cannot
falsify it) and a half-built path reported as complete is exactly that.

Hard rule for callers: ``pathResolved is False`` ⇒ ``assumed is True``.
Never invent joins; prefer assumed / skip when a parent or segment is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Opaque to this module; chosen by the extractor. Within one file a bare
# local name is enough ("v1"). Across files it must be qualified, e.g.
# ("src/routes/birds.js", "<module>"), so two files that both call their
# router `router` do not collide. Any hashable value works.
SymbolId = object

MAX_DEPTH = 32  # real mount chains are 2–4 deep; this is a runaway guard


@dataclass(frozen=True)
class PrefixEdge:
    """``child`` inherits ``parent``'s prefix, and adds ``segment`` to it.

    ``segment is None`` when the extractor saw a prefix it could not read as
    a literal — ``app.Group(basePath)``, ``url_prefix=PREFIX``,
    ``include_router(r, prefix=settings.API_V1)``. Carrying None rather than
    ``""`` is the whole point: ``""`` claims the prefix is empty; None admits
    it is unknown.
    """

    child: SymbolId
    parent: SymbolId | None  # None == this symbol is itself a root
    segment: str | None  # literal path segment, or None if non-literal
    declared_at: int | None = None  # 1-indexed line, for the note and for cues
    expression: str | None = None  # verbatim source of a non-literal prefix


@dataclass(frozen=True)
class Resolution:
    """What came back. ``path`` is always safe to show; ``resolved`` says
    whether it is the whole truth."""

    path: str
    resolved: bool
    note: str | None
    chain: tuple[SymbolId, ...]  # child → … → root, for debugging
    unresolved_reason: str | None = None  # unknown_parent|non_literal|cycle|depth|ambiguous


@dataclass
class PrefixGraph:
    edges: dict[SymbolId, PrefixEdge] = field(default_factory=dict)
    roots: set[SymbolId] = field(default_factory=set)

    def add_child_edge(
        self,
        child: SymbolId,
        parent: SymbolId | None,
        segment: str | None,
        *,
        declared_at: int | None = None,
        expression: str | None = None,
    ) -> None:
        """Fiber groups, FastAPI nested routers: the CHILD names its parent."""
        self.edges[child] = PrefixEdge(child, parent, segment, declared_at, expression)

    def add_mount(
        self,
        parent: SymbolId,
        child: SymbolId,
        segment: str | None,
        *,
        declared_at: int | None = None,
        expression: str | None = None,
    ) -> None:
        """Express app.use / Flask register_blueprint / FastAPI include_router /
        Django include(): the PARENT names the child. Normalised to the same
        edge so the resolver only ever sees one direction.

        A second mount of the same child at a different prefix is a real
        pattern (same router mounted twice) and is NOT silently last-wins —
        the edge becomes non-literal / ambiguous.
        """
        existing = self.edges.get(child)
        if existing is not None and (existing.parent, existing.segment) != (parent, segment):
            self.edges[child] = PrefixEdge(
                child,
                parent,
                None,
                declared_at,
                expression="<mounted at more than one prefix>",
            )
            return
        self.edges[child] = PrefixEdge(child, parent, segment, declared_at, expression)

    def add_root(
        self,
        symbol: SymbolId,
        segment: str | None = None,
        *,
        declared_at: int | None = None,
    ) -> None:
        """fiber.New(), Express ``app``, Spring class, FastAPI app, etc."""
        self.roots.add(symbol)
        if segment:
            self.edges[symbol] = PrefixEdge(symbol, None, segment, declared_at)


def _join(segments_child_first: list[str]) -> str:
    """Segments arrive child-first (walked upward); reverse, strip, rebuild.

    Empty stays ``""`` rather than becoming ``/``, so a rootless route is
    visibly rootless.
    """
    parts = [s.strip("/") for s in reversed(segments_child_first)]
    parts = [p for p in parts if p]
    return ("/" + "/".join(parts)) if parts else ""


def resolve(graph: PrefixGraph, symbol: SymbolId) -> Resolution:
    """Walk ``symbol`` up to a root, collecting prefix segments.

    Terminates on four conditions, three of which mean "assumed":
      - reached a declared root            → resolved
      - hit a symbol with no edge          → unknown_parent
      - hit an edge with segment is None   → non_literal (or ambiguous)
      - revisited a symbol / exceeded      → cycle / depth
        MAX_DEPTH

    In every unresolved case the segments gathered so far are still returned
    (a partial prefix is useful to a reviewer) but ``resolved`` is False and
    the note names what is missing.
    """
    segments: list[str] = []
    chain: list[SymbolId] = []
    seen: set[SymbolId] = set()
    current: SymbolId = symbol
    reason: str | None = None
    detail: str | None = None

    for _ in range(MAX_DEPTH):
        chain.append(current)
        if current in seen:
            reason, detail = "cycle", f"prefix chain revisits {current!r}"
            break
        seen.add(current)

        edge = graph.edges.get(current)
        if edge is None:
            if current in graph.roots:
                return Resolution(_join(segments), True, None, tuple(chain))
            reason = "unknown_parent"
            detail = (
                f"{current!r} is never given a prefix in the files that were "
                f"analysed; its prefix is set at a call site elsewhere"
            )
            break

        if edge.segment is None:
            if edge.expression == "<mounted at more than one prefix>":
                reason = "ambiguous"
                detail = (
                    f"{current!r} is mounted at more than one prefix; "
                    f"refusing to invent a single URL"
                )
            else:
                reason = "non_literal"
                detail = (
                    f"the prefix for {current!r} is "
                    f"{edge.expression or 'a non-literal expression'}"
                    f"{f' at line {edge.declared_at}' if edge.declared_at else ''}, "
                    f"which static analysis cannot evaluate"
                )
            break

        segments.append(edge.segment)

        if edge.parent is None or (
            edge.parent in graph.roots and edge.parent not in graph.edges
        ):
            if edge.parent is not None:
                chain.append(edge.parent)
            return Resolution(
                _join(segments),
                True,
                None,
                tuple(c for c in chain if c is not None),
            )

        current = edge.parent
    else:
        reason = "depth"
        detail = f"prefix chain exceeded {MAX_DEPTH} levels"

    note = (
        f"Route prefix could not be fully resolved: {detail}. "
        f"The path shown is built from the {len(segments)} segment(s) that were "
        f"resolvable and may be missing a leading prefix — verify against the "
        f"application's route registration before relying on it."
    )
    return Resolution(
        _join(segments),
        False,
        note,
        tuple(c for c in chain if c is not None),
        unresolved_reason=reason,
    )


def full_route_path(graph: PrefixGraph, symbol: SymbolId, route_path: str) -> Resolution:
    """Resolve the registering symbol's prefix and append this route's own path."""
    prefix = resolve(graph, symbol)
    tail = (route_path or "").strip()
    if tail and not tail.startswith("/") and not tail.startswith("^"):
        tail = "/" + tail
    if prefix.path and tail.startswith("^"):
        # Never invent a join of a resolved prefix onto a regex route.
        return Resolution(
            tail,
            False,
            (
                "Route prefix could not be fully resolved: refusing to join a "
                "prefix onto a regex route pattern. "
                f"Showing the local pattern only."
            ),
            prefix.chain,
            unresolved_reason="non_literal",
        )
    # A route path of "/" under a non-empty prefix is the prefix itself
    # (Fiber/Express treat trailing slash on the join as insignificant).
    if prefix.path and tail in ("", "/"):
        path = prefix.path.rstrip("/") or "/"
    else:
        path = (prefix.path + tail) or "/"
    # '/api' + '/' must not become '/api//'.
    if path != "//":
        while "//" in path:
            path = path.replace("//", "/")
    else:
        path = "/"
    return Resolution(
        path,
        prefix.resolved,
        prefix.note,
        prefix.chain,
        prefix.unresolved_reason,
    )


def chain_as_strings(chain: tuple[SymbolId, ...]) -> list[str]:
    """Operator-facing prefixChain: stringify opaque symbol ids."""
    out: list[str] = []
    for item in chain:
        if isinstance(item, tuple) and len(item) == 2:
            out.append(f"{item[0]}::{item[1]}")
        else:
            out.append(str(item))
    return out
