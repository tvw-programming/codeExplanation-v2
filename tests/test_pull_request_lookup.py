import json
import subprocess

from src.storage.pull_request_lookup import find_last_pull_request_url


def _fake_run(responses):
    """Returns a fake subprocess.run that serves canned JSON responses
    keyed by the exact `gh api <path>` argument passed."""
    def run(cmd, **kwargs):
        path = cmd[2]
        payload = responses.get(path)
        if payload is None:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not found")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
    return run


def test_file_path_is_url_encoded_before_the_api_call(monkeypatch):
    # Regression: file_path used to be interpolated raw into the query
    # string, so "&" in a path would silently inject a bogus parameter.
    seen_paths = []

    def fake_run(cmd, **kwargs):
        seen_paths.append(cmd[2])
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    find_last_pull_request_url("org", "repo", "src/A&B.tsx")

    assert seen_paths, "expected at least one gh api call"
    assert "A%26B.tsx" in seen_paths[0]
    assert "A&B.tsx" not in seen_paths[0]


def test_returns_pr_url_when_commit_and_pr_are_found(monkeypatch):
    responses = {
        "repos/org/repo/commits?path=src/App.tsx&per_page=1": [{"sha": "abc123"}],
        "repos/org/repo/commits/abc123/pulls": [{"html_url": "https://github.com/org/repo/pull/5"}],
    }
    monkeypatch.setattr(subprocess, "run", _fake_run(responses))

    result = find_last_pull_request_url("org", "repo", "src/App.tsx")
    assert result == "https://github.com/org/repo/pull/5"


def test_returns_none_when_no_commits_found(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake_run({}))
    assert find_last_pull_request_url("org", "repo", "src/App.tsx") is None


def test_returns_none_when_commit_has_no_linked_pr(monkeypatch):
    responses = {
        "repos/org/repo/commits?path=README.md&per_page=1": [{"sha": "abc123"}],
        "repos/org/repo/commits/abc123/pulls": [],
    }
    monkeypatch.setattr(subprocess, "run", _fake_run(responses))

    assert find_last_pull_request_url("org", "repo", "README.md") is None


def test_never_raises_when_gh_binary_is_missing(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("gh not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert find_last_pull_request_url("org", "repo", "README.md") is None
