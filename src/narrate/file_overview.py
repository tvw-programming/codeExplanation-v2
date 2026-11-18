"""Phase 5 — the summary card that introduces each file in the video.

Before the walkthrough of a file starts, the viewer sees the file on
its own for a few seconds: what it is, where it sits, what calls it and
what it calls. This builds that card's contents.

Every field is read from the extraction or from the record set as a
whole. Fields the repository genuinely cannot answer are left out
rather than filled with a plausible-looking value — a card that states
an owning team no CODEOWNERS file names, or a last-modified date taken
from a shallow clone where every file shares one commit, would be
inventing facts about someone's codebase in a form that looks
authoritative. `unavailable` records why each of those was skipped so
the gap is visible instead of silent.

Caller/callee resolution is honest about its own limits too: imports
are matched to other chunks by module stem, because the aliases a
project uses ("~/features/...", "@/types/...") are resolved by its
bundler config rather than by anything in the file. That catches the
real relationships in practice but cannot see calls made through
dynamic imports or dependency injection, so the card says "from the
imports in this repository" rather than claiming completeness.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# (path fragment or suffix, label) — first match wins, so the more
# specific entries come first.
_FILE_TYPE_RULES: list[tuple[str, str]] = [
    ("/cmd/", "Program entry point"),
    ("/handler/", "HTTP handler"),
    ("/repository/", "Data access (repository)"),
    ("/middleware", "Middleware"),
    ("/migrate", "Database migration"),
    ("/moderation/", "Service"),
    ("/storage/", "Service"),
    ("/mocks/", "Test fixtures / mocks"),
    ("/types/", "Type definitions"),
    ("/hooks/", "React hook"),
    ("/components/", "UI component"),
    ("/features/", "Feature screen"),
    ("/api/", "API client"),
    ("/lib/", "Shared library / setup"),
    ("/config", "Configuration"),
]

_FILE_NAME_RULES: list[tuple[str, str]] = [
    ("main.tsx", "Application entry point"),
    ("main.go", "Program entry point"),
    ("index.tsx", "Application entry point"),
    ("client.ts", "API client"),
]


def classify_file_type(file_path: str, record: dict) -> str:
    """A label derived from where the file sits and what it exports.
    Presented on the card as derived, not as a declaration the repo
    makes about itself."""
    path = file_path.lower()
    name = Path(file_path).name.lower()

    for suffix, label in _FILE_NAME_RULES:
        if name == suffix:
            return label
    if name.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")) or name.endswith("_test.go"):
        return "Test file"
    if name.endswith(".d.ts"):
        return "Type definitions"
    if name.endswith((".json", ".yaml", ".yml")):
        return "Configuration"

    for fragment, label in _FILE_TYPE_RULES:
        if fragment in path:
            return label

    if record.get("routes"):
        return "HTTP handler"
    if record.get("dataModels") and not record.get("importantFunctions"):
        return "Type definitions"
    if file_path.endswith(".tsx"):
        return "UI component"
    if file_path.endswith(".go"):
        return "Go source file"
    return f"{record.get('language') or 'Source'} file"


def _stem(module_path: str) -> str:
    cleaned = module_path.rstrip("/")
    return Path(cleaned).stem.lower()


def _build_stem_index(records: list[dict]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for record in records:
        file_path = record.get("filePath") or ""
        if not file_path:
            continue
        index.setdefault(Path(file_path).stem.lower(), []).append(file_path)
    return index


def resolve_relationships(records: list[dict]) -> dict[str, dict[str, list[str]]]:
    """Which files each file imports, and which import it.

    Matching is by module stem because alias prefixes are a bundler
    concern, not something the source states.
    """
    stem_index = _build_stem_index(records)
    callees: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}

    for record in records:
        file_path = record.get("filePath") or ""
        if not file_path:
            continue
        callees.setdefault(file_path, [])
        resolved: list[str] = []
        for dependency in record.get("dependencies") or []:
            target_stem = _stem(dependency.get("path") or "")
            for candidate in stem_index.get(target_stem, []):
                if candidate != file_path and candidate not in resolved:
                    resolved.append(candidate)
        callees[file_path] = resolved
        for target in resolved:
            callers.setdefault(target, [])
            if file_path not in callers[target]:
                callers[target].append(file_path)

    return {
        path: {"callers": callers.get(path, []), "callees": callees.get(path, [])}
        for path in callees
    }


def _git_last_modified(repo_root: Path, file_path: str) -> tuple[str | None, str | None]:
    """(iso_date, reason_it_is_missing). A shallow clone carries one
    commit, so every file in it reports that commit's date — reporting
    that as "last modified" would tell the viewer all 22 files changed
    at the same instant, which is false."""
    try:
        shallow = subprocess.run(
            ["git", "rev-parse", "--is-shallow-repository"],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30, check=False,
        )
        if shallow.stdout.strip() == "true":
            return None, "the repository was cloned shallow, so per-file dates are not available"
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", file_path],
            cwd=str(repo_root), capture_output=True, text=True, timeout=30, check=False,
        )
        date = result.stdout.strip()
        return (date, None) if date else (None, "no commit touches this file")
    except (OSError, subprocess.SubprocessError):
        return None, "git history could not be read"


def _code_owner(repo_root: Path) -> tuple[str | None, str | None]:
    for candidate in (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS"):
        if (repo_root / candidate).is_file():
            return None, "a CODEOWNERS file exists but per-path owners are not resolved yet"
    return None, "the repository has no CODEOWNERS file"


def _test_references(records: list[dict], file_path: str) -> tuple[list[str], str | None]:
    stem = Path(file_path).stem.lower()
    hits: list[str] = []
    saw_test_file = False
    for record in records:
        other = record.get("filePath") or ""
        name = Path(other).name.lower()
        is_test = (
            name.endswith(("_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        )
        if not is_test:
            continue
        saw_test_file = True
        for dependency in record.get("dependencies") or []:
            if _stem(dependency.get("path") or "") == stem:
                hits.append(other)
                break
    if hits:
        return hits, None
    if not saw_test_file:
        return [], "no test files were found in this repository"
    return [], "no test file imports this one"


def build_file_overview(
    record: dict,
    relationships: dict[str, dict[str, list[str]]],
    records: list[dict],
    repo_root: Path | None = None,
) -> dict:
    file_path = record.get("filePath") or ""
    links = relationships.get(file_path, {"callers": [], "callees": []})
    unavailable: dict[str, str] = {}

    purpose = record.get("fileDescription")
    if not purpose:
        exported = [
            fn.get("name") for fn in record.get("importantFunctions") or []
            if fn.get("exported") and fn.get("name")
        ]
        if exported:
            purpose = "Provides " + ", ".join(exported[:4]) + "."
        else:
            unavailable["purpose"] = "the file has no header comment and exports nothing named"

    last_modified = None
    if repo_root is not None:
        last_modified, reason = _git_last_modified(Path(repo_root), file_path)
        if reason:
            unavailable["lastModified"] = reason
        owner, owner_reason = _code_owner(Path(repo_root))
        if owner_reason:
            unavailable["owner"] = owner_reason
    else:
        unavailable["lastModified"] = "the repository was not available when this was built"

    tests, tests_reason = _test_references(records, file_path)
    if tests_reason:
        unavailable["tests"] = tests_reason

    risks: list[str] = []
    if any(fn.get("secretsRedacted") for fn in record.get("importantFunctions") or []):
        risks.append("a possible secret was redacted from this file's snippets")
    if any(fn.get("truncated") for fn in record.get("importantFunctions") or []):
        risks.append("long definitions were trimmed in the extraction")
    assumed = sum(
        1 for group in ("eventHandlers", "apiCalls", "routes")
        for item in record.get(group) or [] if item.get("assumed")
    )
    if assumed:
        risks.append(f"{assumed} claim(s) could not be verified and are marked assumed")
    if (record.get("confidenceLevel") or "") in {"low", "medium"}:
        risks.append(f"extraction confidence is {record.get('confidenceLevel')}")

    exported_names = [
        fn.get("name") for fn in record.get("importantFunctions") or []
        if fn.get("exported") and fn.get("name")
    ]

    return {
        "fileName": Path(file_path).name,
        "filePath": file_path,
        "purpose": purpose,
        "fileType": classify_file_type(file_path, record),
        "callers": links["callers"],
        "callees": links["callees"],
        "language": record.get("language"),
        "frameworks": record.get("frameworkOrLibrary") or [],
        "exports": exported_names,
        "lineCount": (record.get("lineRange") or [1, 1])[1],
        "lastModified": last_modified,
        "tests": tests,
        "risks": risks,
        # Why a field above is empty, so the omission is visible rather
        # than looking like the extractor simply forgot.
        "unavailable": unavailable,
    }


def build_file_overviews(records: list[dict], repo_root: Path | None = None) -> dict[str, dict]:
    relationships = resolve_relationships(records)
    return {
        record["chunkId"]: build_file_overview(record, relationships, records, repo_root)
        for record in records if record.get("chunkId")
    }
