"""Express.js in-file route / middleware extraction (regex).

Cross-file mount prefixes are marked assumed — never silently wrong.
Supports app.get/post and router.route(path).get().post() chains.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


ROUTE_RE = re.compile(
    r"""(?P<var>\w+)\.(?P<method>get|post|put|delete|patch|all|use)\(\s*(?P<quote>['"`])(?P<path>[^'"`]*)(?P=quote)""",
    re.IGNORECASE,
)
ROUTE_CHAIN_RE = re.compile(
    r"""(?P<var>\w+)\.route\(\s*(?P<quote>['"`])(?P<path>[^'"`]*)(?P=quote)\s*\)(?P<chain>(?:\s*\.\s*(?:get|post|put|delete|patch|all)\s*\([^;]*)+)""",
    re.IGNORECASE,
)
CHAIN_METHOD_RE = re.compile(
    r"""\.\s*(?P<method>get|post|put|delete|patch|all)\s*\(\s*(?P<handler>[A-Za-z_][\w.]*)?""",
    re.IGNORECASE,
)
ROUTER_RE = re.compile(r"""(?:const|let|var)\s+(?P<var>\w+)\s*=\s*(?:express\.)?Router\s*\(""")
USE_MOUNT_RE = re.compile(
    r"""(?P<var>\w+)\.use\(\s*(?P<quote>['"`])(?P<prefix>[^'"`]*)(?P=quote)\s*,\s*(?P<target>\w+)""",
    re.IGNORECASE,
)
MW_USE_RE = re.compile(
    r"""(?P<var>\w+)\.use\(\s*(?P<call>[^)]+)\)""",
    re.IGNORECASE,
)


@dataclass
class ExpressRoute:
    method: str
    path: str
    router_var: str
    line: int
    assumed: bool
    handler: str
    note: str | None = None


@dataclass
class ExpressMiddleware:
    router_var: str
    name: str
    order: int
    line: int
    is_auth: bool
    assumed: bool = True


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _mw_name(call: str) -> str:
    call = call.strip()
    m = re.match(r"([\w.]+)", call)
    return m.group(1) if m else call[:40]


def _full_path(prefix: str, path: str) -> str:
    full = (prefix.rstrip("/") + "/" + path.lstrip("/")) if prefix else path
    if not full.startswith("/"):
        full = "/" + full
    return full


def extract_express(text: str) -> tuple[list[ExpressRoute], list[ExpressMiddleware], dict[str, str]]:
    """Return routes, middleware, and local mount prefixes (var→prefix)."""
    routers = {m.group("var") for m in ROUTER_RE.finditer(text)}
    routers.add("app")

    mounts: dict[str, str] = {}
    for m in USE_MOUNT_RE.finditer(text):
        mounts[m.group("target")] = m.group("prefix")

    middleware: list[ExpressMiddleware] = []
    order = 0
    for m in MW_USE_RE.finditer(text):
        call = m.group("call").strip()
        if re.match(r"""['"`][^'"`]+['"`]\s*,\s*\w+\s*$""", call):
            continue
        name = _mw_name(call.split(",")[-1] if "," in call else call)
        if name in mounts or name in routers and "," in call:
            if not re.search(r"[\w.]+\s*\(|^\w+$", call):
                continue
        is_auth = bool(re.search(r"(?i)auth|jwt|passport|session", call))
        middleware.append(ExpressMiddleware(
            router_var=m.group("var"),
            name=name,
            order=order,
            line=_line_of(text, m.start()),
            is_auth=is_auth,
        ))
        order += 1

    routes: list[ExpressRoute] = []
    seen: set[tuple[str, str, int]] = set()

    def _add_route(var: str, method: str, path: str, line: int, handler: str) -> None:
        method = method.upper()
        if method == "USE":
            return
        if method == "ALL":
            method = "ALL"
        prefix = mounts.get(var, "")
        assumed = var not in routers and var != "app"
        full = _full_path(prefix, path)
        note = None
        if var not in routers and var != "app":
            assumed = True
            note = "Router variable not declared in this file; path prefix may be incomplete."
        key = (method, full, line)
        if key in seen:
            return
        seen.add(key)
        routes.append(ExpressRoute(
            method=method,
            path=full,
            router_var=var,
            line=line,
            assumed=assumed,
            handler=handler,
            note=note,
        ))

    for m in ROUTE_CHAIN_RE.finditer(text):
        var = m.group("var")
        path = m.group("path")
        line = _line_of(text, m.start())
        for cm in CHAIN_METHOD_RE.finditer(m.group("chain")):
            handler = cm.group("handler") or f"inline_L{line}"
            if handler in ("async", "function"):
                handler = f"inline_L{line}"
            _add_route(var, cm.group("method"), path, line, handler)

    for m in ROUTE_RE.finditer(text):
        method = m.group("method")
        if method.lower() == "use":
            continue
        var = m.group("var")
        path = m.group("path")
        line = _line_of(text, m.start())
        rest = text[m.end():m.end() + 80]
        hm = re.search(r",\s*([A-Za-z_][\w.]*)", rest)
        handler = hm.group(1) if hm else "handler"
        if handler in ("async", "function"):
            handler = f"inline_L{line}"
        _add_route(var, method, path, line, handler)

    return routes, middleware, mounts
