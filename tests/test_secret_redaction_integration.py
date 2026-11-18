"""Regression test for the code-review finding: secret_scan() existed
and was unit-tested in isolation, but was never wired into the real
extraction pipeline, so a hardcoded secret in a source file was copied
verbatim into the output JSON. This test reproduces that exact scenario
end to end through extract_repo(), not just through guardrails.py
directly — an integration test is what should have caught the gap in
the first place.
"""

import json

from src.detect.project_type import detect_project_type
from src.extract.extractor import extract_repo
from src.security.guardrails import REDACTION_PLACEHOLDER

# NOT a real key shape (GitHub push protection flags sk_live_-style strings
# even in test fixtures) — this only needs to satisfy our own conservative
# apiKey="..." pattern in guardrails._SECRET_PATTERNS, which just checks
# for a 16+ char quoted value assigned to a key/secret-named variable.
LEAKED_SECRET = "FAKE-TEST-ONLY-CREDENTIAL-VALUE-0000000000"


def _build_repo_with_secret(root):
    (root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
    feature_dir = root / "src" / "features" / "auth"
    feature_dir.mkdir(parents=True)
    (feature_dir / "AuthConfig.tsx").write_text(
        "export function configureAuth() {\n"
        f'  const apiKey = "{LEAKED_SECRET}";\n'
        "  console.log(apiKey);\n"
        "  return apiKey;\n"
        "}\n"
    )


def test_hardcoded_secret_is_redacted_before_it_reaches_the_output_record(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _build_repo_with_secret(repo)

    project_type = detect_project_type(repo)
    records = extract_repo(repo, project_type)

    full_output = json.dumps(records)
    assert LEAKED_SECRET not in full_output, "the raw secret must never reach the output JSON"
    assert REDACTION_PLACEHOLDER in full_output, "the redaction placeholder should be visible in its place"

    # The affected record should also honestly flag itself for review
    # rather than silently redacting and moving on.
    auth_record = next(r for r in records if r["featureName"] == "auth")
    assert "secret" in auth_record["notes"].lower()
    assert auth_record["confidence"] <= 0.5


def test_clean_code_with_no_secrets_is_unaffected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(json.dumps({"dependencies": {"react": "^19.0.0"}}))
    feature_dir = repo / "src" / "features" / "widgets"
    feature_dir.mkdir(parents=True)
    (feature_dir / "WidgetList.tsx").write_text(
        "export default function WidgetList() {\n"
        "  return <div>widgets</div>;\n"
        "}\n"
    )

    project_type = detect_project_type(repo)
    records = extract_repo(repo, project_type)
    record = records[0]

    assert record["notes"] is None or "secret" not in record["notes"].lower()
    assert all(not fn["secretsRedacted"] for fn in record["importantFunctions"])
