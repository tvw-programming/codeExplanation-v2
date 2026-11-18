import subprocess

import pytest

from src.detect.source_resolver import (
    SourceResolutionError,
    _looks_like_git_url,
    _slug_from_url,
    resolve_source,
)


def test_local_path_is_resolved_as_local_path(tmp_path):
    repo = tmp_path / "myrepo"
    repo.mkdir()
    resolved = resolve_source(str(repo), tmp_path / "clones")
    assert resolved.kind == "local_path"
    assert resolved.local_root == repo.resolve()


def test_https_github_url_is_recognized():
    assert _looks_like_git_url("https://github.com/tvw-programming/Alumni-web")


def test_https_dot_git_url_is_recognized():
    assert _looks_like_git_url("https://example.com/org/repo.git")


def test_ssh_git_url_is_recognized():
    assert _looks_like_git_url("git@github.com:org/repo.git")


def test_random_string_is_not_a_git_url():
    assert not _looks_like_git_url("just some text")


def test_lookalike_subdomain_is_not_accepted_as_github():
    # Regression: "github.com" in netloc used to be a bare substring
    # check, so "github.com.attacker.net" was wrongly accepted.
    assert not _looks_like_git_url("https://github.com.attacker.net/org/repo")


def test_resolve_source_clones_a_recognized_git_url(tmp_path, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # Simulate a successful clone by creating the destination dir.
        dest = cmd[-1]
        import os
        os.makedirs(dest, exist_ok=True)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    resolved = resolve_source("https://github.com/org/repo.git", tmp_path / "clones")
    assert resolved.kind == "git"
    assert resolved.local_root == (tmp_path / "clones" / "repo").resolve()
    # The real repo URL is still passed through untouched, with a "--"
    # separator added ahead of it for defense in depth.
    assert "https://github.com/org/repo.git" in calls[0]
    assert "--" in calls[0]


def test_resolve_source_rejects_path_traversal_slug(tmp_path):
    # Regression: "https://github.com/org/.." used to resolve to the
    # workdir's PARENT directory and silently skip cloning.
    workdir = tmp_path / "clones"
    with pytest.raises(SourceResolutionError):
        resolve_source("https://github.com/org/..", workdir)


def test_resolve_source_rejects_dot_slug(tmp_path):
    workdir = tmp_path / "clones"
    with pytest.raises(SourceResolutionError):
        resolve_source("https://github.com/org/.", workdir)


def test_slug_from_url_strips_git_suffix():
    assert _slug_from_url("https://github.com/org/repo.git") == "repo"


def test_unresolvable_value_raises():
    with pytest.raises(SourceResolutionError):
        resolve_source("not a path and not a url", "/tmp/does-not-matter")
