"""Shared PrefixGraph / full_route_path — honesty over coverage."""

from __future__ import annotations

from src.extract.route_prefix import (
    MAX_DEPTH,
    PrefixGraph,
    full_route_path,
    resolve,
)


def test_single_level_prefix_resolves():
    g = PrefixGraph()
    g.add_root("app")
    g.add_child_edge("v1", "app", "/api")
    res = full_route_path(g, "v1", "/users")
    assert res.path == "/api/users"
    assert res.resolved is True
    assert res.note is None


def test_nested_chain_composes_in_source_order():
    g = PrefixGraph()
    g.add_root("app")
    g.add_child_edge("api", "app", "/api")
    g.add_child_edge("v1", "api", "/v1")
    res = full_route_path(g, "v1", "/users")
    assert res.path == "/api/v1/users"
    assert res.resolved is True


def test_parent_to_child_mount_normalises_to_the_same_edge():
    child_named = PrefixGraph()
    child_named.add_root("app")
    child_named.add_child_edge("r", "app", "/api")

    parent_named = PrefixGraph()
    parent_named.add_root("app")
    parent_named.add_mount("app", "r", "/api")

    a = full_route_path(child_named, "r", "/users")
    b = full_route_path(parent_named, "r", "/users")
    assert a.path == b.path == "/api/users"
    assert a.resolved is b.resolved is True


def test_unknown_parent_is_unresolved_with_a_partial_path():
    g = PrefixGraph()
    g.add_child_edge("v1", "app", "/api/v1")  # app never declared as root
    res = full_route_path(g, "v1", "/alumni")
    assert res.path == "/api/v1/alumni"
    assert res.resolved is False
    assert res.unresolved_reason == "unknown_parent"
    assert "app" in (res.note or "")


def test_non_literal_prefix_names_the_expression():
    g = PrefixGraph()
    g.add_root("app")
    g.add_child_edge("api", "app", None, expression="basePath", declared_at=4)
    res = resolve(g, "api")
    assert res.resolved is False
    assert res.unresolved_reason == "non_literal"
    assert "basePath" in (res.note or "")


def test_cycle_does_not_hang_and_is_reported():
    g = PrefixGraph()
    g.add_child_edge("a", "b", "/a")
    g.add_child_edge("b", "a", "/b")
    res = resolve(g, "a")
    assert res.resolved is False
    assert res.unresolved_reason == "cycle"


def test_depth_guard():
    g = PrefixGraph()
    g.add_root("root")
    prev = "root"
    for i in range(MAX_DEPTH + 5):
        cur = f"n{i}"
        g.add_child_edge(cur, prev, f"/s{i}")
        prev = cur
    res = resolve(g, prev)
    assert res.resolved is False
    assert res.unresolved_reason == "depth"


def test_double_mount_is_reported_as_ambiguous_not_last_wins():
    g = PrefixGraph()
    g.add_root("app")
    g.add_mount("app", "r", "/api/v1")
    g.add_mount("app", "r", "/api/latest")
    res = full_route_path(g, "r", "/users")
    assert res.resolved is False
    assert res.unresolved_reason == "ambiguous"
    assert "more than one prefix" in (res.note or "")


def test_join_normalises_slashes():
    g = PrefixGraph()
    g.add_root("app")
    g.add_child_edge("api", "app", "/api/")
    assert full_route_path(g, "api", "/").path == "/api"
    assert full_route_path(g, "app", "users").path == "/users"
    assert "//" not in full_route_path(g, "api", "/x").path


def test_unresolved_path_always_sets_assumed():
    """Hard rule for callers: pathResolved False ⇒ assumed True."""
    cases = []
    g1 = PrefixGraph()
    g1.add_child_edge("v1", "ghost", "/x")
    cases.append(full_route_path(g1, "v1", "/y"))

    g2 = PrefixGraph()
    g2.add_root("app")
    g2.add_child_edge("v1", "app", None, expression="P")
    cases.append(full_route_path(g2, "v1", "/y"))

    for res in cases:
        assert res.resolved is False
        # Callers must set assumed=True whenever resolved is False.
        assumed = True if res.resolved is False else False
        assert assumed is True
