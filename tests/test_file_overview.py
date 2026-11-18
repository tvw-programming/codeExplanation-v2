from pathlib import Path

from src.narrate.file_overview import (
    build_file_overview,
    build_file_overviews,
    classify_file_type,
    resolve_relationships,
)


def record(file_path, **overrides):
    base = {
        "chunkId": file_path.replace("/", "-"),
        "filePath": file_path,
        "language": "TypeScript",
        "lineRange": [1, 40],
        "dependencies": [],
        "importantFunctions": [],
        "confidenceLevel": "high",
    }
    base.update(overrides)
    return base


def test_imports_resolve_into_caller_and_callee_links_across_chunks():
    """Alias prefixes are a bundler concern, so matching is by stem."""
    records = [
        record("src/features/alumni/ProfilePage.tsx", dependencies=[
            {"path": "~/features/alumni/educationFormSchema"},
            {"path": "@mui/material"},
        ]),
        record("src/features/alumni/educationFormSchema.ts"),
    ]
    links = resolve_relationships(records)
    page = links["src/features/alumni/ProfilePage.tsx"]
    schema = links["src/features/alumni/educationFormSchema.ts"]

    assert page["callees"] == ["src/features/alumni/educationFormSchema.ts"]
    assert schema["callers"] == ["src/features/alumni/ProfilePage.tsx"]
    assert page["callers"] == []


def test_a_file_never_links_to_itself():
    records = [record("src/lib/firebase.ts", dependencies=[{"path": "./firebase"}])]
    links = resolve_relationships(records)
    assert links["src/lib/firebase.ts"]["callees"] == []


def test_file_type_comes_from_path_then_falls_back_to_language():
    assert classify_file_type("api/cmd/server/main.go", record("x")) == "Program entry point"
    assert classify_file_type("api/internal/handler/a.go", record("x")) == "HTTP handler"
    assert classify_file_type("api/internal/repository/a.go", record("x")) == "Data access (repository)"
    assert classify_file_type("src/main.tsx", record("x")) == "Application entry point"
    assert classify_file_type("src/components/Button.tsx", record("x")) == "UI component"
    assert classify_file_type("src/types/api.d.ts", record("x")) == "Type definitions"
    assert classify_file_type("src/a_test.go", record("x")) == "Test file"
    assert classify_file_type("src/a.test.ts", record("x")) == "Test file"
    assert classify_file_type("src/plain.go", record("x")) == "Go source file"


def test_purpose_uses_the_file_header_comment_when_there_is_one():
    rec = record("src/lib/firebase.ts", fileDescription="Firebase client: social login.")
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    assert overview["purpose"] == "Firebase client: social login."


def test_purpose_falls_back_to_exported_names():
    rec = record("src/lib/a.ts", importantFunctions=[
        {"name": "signIn", "exported": True},
        {"name": "helper", "exported": False},
    ])
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    assert overview["purpose"] == "Provides signIn."
    assert overview["exports"] == ["signIn"]


def test_missing_fields_record_why_rather_than_being_filled_in(tmp_path):
    """A card stating an owner no CODEOWNERS file names, or a date taken
    from a shallow clone, would invent facts about someone's codebase."""
    rec = record("src/lib/a.ts")
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec], repo_root=tmp_path)

    assert overview["lastModified"] is None
    assert "owner" in overview["unavailable"]
    assert "CODEOWNERS" in overview["unavailable"]["owner"]
    assert "tests" in overview["unavailable"]
    assert overview["tests"] == []


def test_shallow_clone_does_not_report_a_last_modified_date(tmp_path, monkeypatch):
    import subprocess as subprocess_module

    class Result:
        def __init__(self, stdout):
            self.stdout = stdout

    def fake_run(cmd, **kwargs):
        if "--is-shallow-repository" in cmd:
            return Result("true\n")
        return Result("2026-09-23T17:34:20+05:30\n")

    monkeypatch.setattr(subprocess_module, "run", fake_run)
    rec = record("src/lib/a.ts")
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec], repo_root=tmp_path)
    assert overview["lastModified"] is None
    assert "shallow" in overview["unavailable"]["lastModified"]


def test_risks_come_from_real_extraction_signals():
    rec = record(
        "src/lib/a.ts",
        confidenceLevel="medium",
        importantFunctions=[{"name": "a", "secretsRedacted": True, "truncated": True}],
        eventHandlers=[{"name": "h", "assumed": True}],
    )
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    joined = " ".join(overview["risks"])
    assert "secret" in joined
    assert "trimmed" in joined
    assert "assumed" in joined
    assert "medium" in joined


def test_a_clean_high_confidence_file_lists_no_risks():
    rec = record("src/lib/a.ts", confidenceLevel="high")
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    assert overview["risks"] == []


def test_overviews_are_keyed_by_chunk_id():
    records = [record("src/a.ts"), record("src/b.ts")]
    overviews = build_file_overviews(records)
    assert set(overviews) == {"src-a.ts", "src-b.ts"}
    assert overviews["src-a.ts"]["fileName"] == "a.ts"


def test_test_files_that_import_a_file_are_counted_as_coverage():
    records = [
        record("src/lib/a.ts"),
        record("src/lib/a.test.ts", dependencies=[{"path": "./a"}]),
    ]
    overview = build_file_overview(records[0], resolve_relationships(records), records)
    assert overview["tests"] == ["src/lib/a.test.ts"]
    assert "tests" not in overview["unavailable"]
