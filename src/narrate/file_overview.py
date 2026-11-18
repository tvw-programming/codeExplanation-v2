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

import re
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


# Packages that are the framework a file is built on, as opposed to a
# library it merely uses. Matched as substrings of the dependency string
# so versioned Go module paths ("github.com/gofiber/fiber/v2") and
# scoped npm names both land.
_FRAMEWORK_MARKERS: list[tuple[str, str]] = [
    ("gofiber/fiber", "Fiber"),
    ("gin-gonic/gin", "Gin"),
    ("labstack/echo", "Echo"),
    ("net/http", "net/http"),
    ("react", "React"),
    ("@angular", "Angular"),
    ("vue", "Vue"),
    ("svelte", "Svelte"),
    ("next", "Next.js"),
    ("express", "Express"),
    ("fastapi", "FastAPI"),
    ("django", "Django"),
    ("flask", "Flask"),
    ("spring", "Spring"),
]

# Imports that mean this file is doing agent/LLM work rather than
# ordinary frontend or backend work.
_AGENTIC_MARKERS = (
    "langchain", "langgraph", "openai", "anthropic", "llama_index", "llamaindex",
    "modelcontextprotocol", "/mcp", "mcp-", "autogen", "crewai", "semantic-kernel",
    "transformers", "ollama",
)

LAYER_FRONTEND = "Frontend"
LAYER_BACKEND = "Backend"
LAYER_TESTING = "Testing"
LAYER_AGENTIC = "Agentic"
LAYER_CONFIG = "Configuration"


# Path segments that identify no package on their own: taking the last
# segment of "firebase.google.com/go/v4" would label it "go".
_GENERIC_SEGMENTS = {"go", "pkg", "src", "lib", "internal", "api", "v1", "client"}
_CODE_HOSTS = {"github", "gitlab", "bitbucket", "codeberg", "sr"}


def _is_version_segment(part: str) -> bool:
    return len(part) > 1 and part[0] == "v" and part[1:].isdigit()


def _pretty_package(name: str) -> str:
    """A readable name for a dependency. Go module paths are domain
    qualified and version suffixed, so the last segment is usually
    meaningless — "firebase.google.com/go/v4/auth" is the Firebase auth
    package, not a package called "auth"."""
    cleaned = name.strip().rstrip("/")
    parts = [p for p in cleaned.split("/") if p and not _is_version_segment(p)]
    if not parts:
        return name

    if cleaned.startswith("@"):
        return "/".join(parts[:2])

    if "." in parts[0]:
        host = parts[0].split(".")[0]
        if host in _CODE_HOSTS and len(parts) >= 3:
            return parts[2]
        tail = [p for p in parts[1:] if p.lower() not in _GENERIC_SEGMENTS]
        if not tail or tail[-1].lower() == host.lower():
            return host
        return f"{host}/{tail[-1]}"

    return parts[0]


def split_frameworks_and_libraries(packages: list[str]) -> tuple[list[str], list[str]]:
    """Which of a file's packages is the framework it is built on, and
    which are libraries it uses."""
    frameworks: list[str] = []
    libraries: list[str] = []
    for package in packages:
        lowered = package.lower()
        # Match on whole path segments, not bare substrings: otherwise
        # "@tanstack/react-query" reads as the React framework rather
        # than as a library, and "next-auth" as Next.js.
        segments = {part for part in lowered.split("/") if part}
        matched = None
        for marker, label in _FRAMEWORK_MARKERS:
            hit = marker in lowered if "/" in marker else marker in segments
            if hit:
                matched = label
                break
        if matched:
            if matched not in frameworks:
                frameworks.append(matched)
        else:
            pretty = _pretty_package(package)
            if pretty not in libraries:
                libraries.append(pretty)
    return frameworks, libraries


def classify_layer(file_path: str, record: dict) -> str:
    """Which part of the system this file belongs to. Derived from the
    path, the language and what it imports — the repository does not
    state this anywhere, so it is a reading of the evidence rather than
    a fact the code declares."""
    path = file_path.lower()
    name = Path(file_path).name.lower()

    if name.endswith(("_test.go", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
        return LAYER_TESTING
    if "/test" in path or path.startswith("test"):
        return LAYER_TESTING

    packages = [
        *(record.get("frameworkOrLibrary") or []),
        *[d.get("path", "") for d in record.get("dependencies") or []],
    ]
    blob = " ".join(packages).lower()
    if any(marker in blob for marker in _AGENTIC_MARKERS):
        return LAYER_AGENTIC

    if (
        name.endswith((".json", ".yaml", ".yml", ".toml", ".ini"))
        or "/config" in path
        # Build/tool config lives at the repo root as <tool>.config.ts
        # (vite.config.ts, jest.config.js, tailwind.config.ts).
        or ".config." in name
        or name in {"dockerfile", "makefile", "go.mod", "package.json"}
    ):
        return LAYER_CONFIG

    if file_path.endswith(".go") or record.get("routes"):
        return LAYER_BACKEND
    if file_path.endswith((".tsx", ".jsx", ".css", ".scss", ".html")):
        return LAYER_FRONTEND
    if file_path.endswith(".ts"):
        # A .ts file under an api/ or server/ directory is backend code.
        if any(fragment in path for fragment in ("/server/", "/backend/", "/api/server")):
            return LAYER_BACKEND
        return LAYER_FRONTEND
    if file_path.endswith(".py"):
        return LAYER_BACKEND
    return LAYER_BACKEND if record.get("language") == "Go" else LAYER_FRONTEND


# How much of a file's header comment the card shows and reads aloud.
# A package doc can run several paragraphs; at that length the card
# becomes a wall of text and its narration runs close to half a minute
# before the walkthrough has even started.
CARD_PURPOSE_CHARS = 280

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def summarize_purpose(text: str, max_chars: int = CARD_PURPOSE_CHARS) -> str:
    """The opening of a purpose, cut at a sentence boundary.

    Ending mid-word on an ellipsis reads as missing information. Whole
    sentences read as a complete thought, which is what this is: the
    rest of the file's documentation is covered by the walkthrough that
    follows the card.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return text

    kept: list[str] = []
    length = 0
    for sentence in _SENTENCE_SPLIT.split(text):
        if kept and length + len(sentence) + 1 > max_chars:
            break
        kept.append(sentence)
        length += len(sentence) + 1

    joined = " ".join(kept).strip()
    if joined and len(joined) <= max_chars:
        return joined
    # One sentence longer than the whole budget (or no sentence
    # boundaries at all): cut at a word instead.
    return text[:max_chars].rsplit(" ", 1)[0].rstrip(",;:") + "."


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

    functions = record.get("importantFunctions") or []
    exported_names = [
        fn.get("name") for fn in functions if fn.get("exported") and fn.get("name")
    ]

    packages = [
        *(record.get("frameworkOrLibrary") or []),
        *[d.get("path", "") for d in record.get("dependencies") or []
          if not (d.get("path", "").startswith((".", "~", "@/")))],
    ]
    frameworks, libraries = split_frameworks_and_libraries(packages)

    routes = [
        f"{r.get('method', '')} {r.get('path', '')}".strip()
        for r in record.get("routes") or []
    ]
    outbound = [
        f"{c.get('method', '')} {c.get('url', '')}".strip()
        for c in record.get("apiCalls") or []
    ]
    side_effects = sorted({
        effect.get("kind") for effect in record.get("sideEffects") or []
        if isinstance(effect, dict) and effect.get("kind")
    })

    # Counts of what the file actually holds — a quick sense of how much
    # file this is, before the walkthrough starts.
    contains: list[str] = []
    if functions:
        contains.append(f"{len(functions)} function(s)")
    if exported_names:
        contains.append(f"{len(exported_names)} exported")
    if record.get("eventHandlers"):
        contains.append(f"{len(record['eventHandlers'])} handler(s)")
    if routes:
        contains.append(f"{len(routes)} route(s)")
    if record.get("dataModels"):
        contains.append(f"{len(record['dataModels'])} model(s)")

    return {
        "fileName": Path(file_path).name,
        "filePath": file_path,
        "purpose": summarize_purpose(purpose) if purpose else None,
        "purposeFull": purpose,
        "fileType": classify_file_type(file_path, record),
        "layer": classify_layer(file_path, record),
        "feature": record.get("featureName"),
        "callers": links["callers"],
        "callees": links["callees"],
        "language": record.get("language"),
        "frameworks": frameworks,
        "libraries": libraries,
        "exports": exported_names,
        "contains": contains,
        "routes": routes,
        "outboundCalls": outbound,
        "sideEffects": side_effects,
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
