from pathlib import Path

from src.narrate.file_overview import (
    LAYER_AGENTIC,
    LAYER_BACKEND,
    LAYER_CONFIG,
    LAYER_FRONTEND,
    LAYER_TESTING,
    _pretty_package,
    build_file_overview,
    build_file_overviews,
    classify_file_type,
    classify_layer,
    resolve_relationships,
    split_frameworks_and_libraries,
    summarize_purpose,
    CARD_PURPOSE_CHARS,
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


def test_framework_is_separated_from_libraries():
    frameworks, libraries = split_frameworks_and_libraries([
        "github.com/gofiber/fiber/v2",
        "firebase.google.com/go/v4/auth",
        "google.golang.org/api/option",
    ])
    assert frameworks == ["Fiber"]
    assert libraries == ["firebase/auth", "google/option"]


def test_a_library_whose_name_contains_a_framework_name_stays_a_library():
    """Substring matching made "@tanstack/react-query" read as React."""
    frameworks, libraries = split_frameworks_and_libraries(
        ["react", "@tanstack/react-query", "next-auth"],
    )
    assert frameworks == ["React"]
    assert "@tanstack/react-query" in libraries
    assert "next-auth" in libraries


def test_go_module_paths_get_a_meaningful_name_not_their_last_segment():
    """"firebase.google.com/go/v4" is Firebase, not a package named "go"."""
    assert _pretty_package("firebase.google.com/go/v4") == "firebase"
    assert _pretty_package("github.com/lib/pq") == "pq"
    assert _pretty_package("gorm.io/gorm") == "gorm"
    assert _pretty_package("@mui/material") == "@mui/material"
    assert _pretty_package("axios") == "axios"


def test_layer_classification_covers_the_four_kinds_of_work():
    assert classify_layer("api/internal/handler/a.go", record("x")) == LAYER_BACKEND
    assert classify_layer("src/features/alumni/Page.tsx", record("x")) == LAYER_FRONTEND
    assert classify_layer("api/internal/a_test.go", record("x")) == LAYER_TESTING
    assert classify_layer("src/a.test.ts", record("x")) == LAYER_TESTING
    assert classify_layer("vite.config.ts", record("x")) == LAYER_CONFIG


def test_agentic_work_is_recognised_from_its_imports():
    agent = record("src/agents/planner.ts", dependencies=[
        {"path": "@langchain/core"}, {"path": "openai"},
    ])
    assert classify_layer("src/agents/planner.ts", agent) == LAYER_AGENTIC


def test_contains_counts_what_the_file_actually_holds():
    rec = record(
        "api/internal/handler/a.go",
        importantFunctions=[{"name": "A", "exported": True}, {"name": "b"}],
        routes=[{"method": "GET", "path": "/alumni"}],
        dataModels=[{"name": "Alumni"}],
    )
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    joined = " ".join(overview["contains"])
    assert "2 function(s)" in joined
    assert "1 exported" in joined
    assert "1 route(s)" in joined
    assert "1 model(s)" in joined
    assert overview["routes"] == ["GET /alumni"]


def test_card_purpose_is_cut_at_a_sentence_not_mid_word():
    """An ellipsis mid-word reads as missing information; whole
    sentences read as a complete thought."""
    long_purpose = (
        "Package firebaseauth validates Firebase ID tokens on the API edge. "
        "The rule this package exists to enforce: the browser never tells us who it is. "
        "It presents a token signed by Google, we verify the signature against Google's "
        "rotating public keys, and the uid we act on comes out of that verification. "
        "A uid in a request body is ignored entirely by every handler in this service."
    )
    summary = summarize_purpose(long_purpose)
    assert len(summary) <= CARD_PURPOSE_CHARS
    assert not summary.endswith("...")
    assert summary.endswith((".", "!", "?"))
    assert summary.startswith("Package firebaseauth validates")


def test_a_short_purpose_is_left_exactly_as_it_is():
    assert summarize_purpose("Entry point for the app.") == "Entry point for the app."


def test_a_single_enormous_sentence_still_gets_cut_cleanly():
    monster = "This one sentence just keeps going and going " * 20
    summary = summarize_purpose(monster)
    assert len(summary) <= CARD_PURPOSE_CHARS + 1
    assert not summary.endswith(" .")


def test_overview_keeps_the_full_purpose_alongside_the_card_version():
    long_purpose = "First sentence here. " + ("Padding sentence. " * 40)
    rec = record("src/a.ts", fileDescription=long_purpose)
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    assert len(overview["purpose"]) <= CARD_PURPOSE_CHARS
    assert overview["purposeFull"] == long_purpose


def test_side_effects_are_read_under_the_name_the_record_actually_uses():
    """json_builder serialises these as "type"; reading "kind" meant the
    card's side effects were silently always empty."""
    rec = record("src/a.ts", sideEffects=[
        {"type": "navigation", "description": "Detected at line 10"},
        {"type": "storage", "description": "Detected at line 20"},
    ])
    overview = build_file_overview(rec, resolve_relationships([rec]), [rec])
    assert overview["sideEffects"] == ["navigation", "storage"]


def test_server_side_languages_are_not_labelled_frontend():
    """A .java file fell through to the Frontend fallback."""
    for path in ("src/main/java/com/example/UserService.java", "app/models/user.rb",
                 "src/main.rs", "api/Service.cs"):
        assert classify_layer(path, record("x")) == LAYER_BACKEND
