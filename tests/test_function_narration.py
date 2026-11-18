from src.narrate.function_narration import (
    MAX_PAUSE_MS,
    MAX_SPOKEN_DOC_CHARS,
    MIN_PAUSE_MS,
    build_function_narration,
    build_function_summary,
    pause_after_ms,
    speakable,
)


def fn(**overrides) -> dict:
    base = {
        "name": "requireAuth",
        "signature": "function requireAuth() {",
        "lineRange": [48, 56],
        "lineCount": 9,
        "description": None,
        "exported": False,
        "calledBy": [],
        "calls": [],
        "params": [],
        "raisesError": False,
        "isAsync": False,
        "reactHooks": [],
        "apiCalls": [],
        "sideEffects": [],
    }
    base.update(overrides)
    return base


def test_pause_grows_with_function_length_within_bounds():
    assert pause_after_ms(1) == MIN_PAUSE_MS + round((MAX_PAUSE_MS - MIN_PAUSE_MS) / 40)
    assert pause_after_ms(0) == MIN_PAUSE_MS
    assert pause_after_ms(40) == MAX_PAUSE_MS
    assert pause_after_ms(500) == MAX_PAUSE_MS, "a huge function must not pause forever"
    assert MIN_PAUSE_MS <= pause_after_ms(12) <= MAX_PAUSE_MS


def test_narration_names_the_function_and_its_lines():
    spoken = build_function_narration(fn())
    assert "requireAuth" in spoken
    assert "48" in spoken and "56" in spoken


def test_doc_comment_is_attributed_not_asserted():
    """The comment is the author's claim about the code, not something
    the extractor checked, so it must not be spoken as verified fact."""
    spoken = build_function_narration(fn(description="Returns the signed-in user's token."))
    assert "documentation says" in spoken
    assert "Returns the signed-in user's token." in spoken


def test_narration_says_who_calls_it():
    spoken = build_function_narration(fn(calledBy=["signInWith", "currentIdToken"]))
    assert "signInWith and currentIdToken" in spoken
    assert "2 callers" in spoken


def test_exported_function_admits_callers_are_not_visible():
    """Claiming nothing calls it would be wrong — the chunk just can't see."""
    spoken = build_function_narration(fn(exported=True))
    assert "exported" in spoken
    assert "not visible from this chunk" in spoken


def test_unused_unexported_function_is_described_as_such():
    spoken = build_function_narration(fn(exported=False, calledBy=[]))
    assert "not exported" in spoken


def test_behaviour_facts_are_spoken_when_present():
    spoken = build_function_narration(fn(
        params=["provider"],
        raisesError=True,
        apiCalls=[{"method": "POST", "url": "/api/login"}],
        sideEffects=["navigation"],
        reactHooks=["useCallback"],
    ))
    assert "It takes provider." in spoken
    assert "POST" in spoken and "/api/login" in spoken
    assert "raises an error" in spoken
    assert "navigation" in spoken
    assert "memoised" in spoken


def test_no_undocumented_filler_sentence():
    """It would repeat on nearly every function and says nothing."""
    spoken = build_function_narration(fn(description=None))
    assert "no documentation" not in spoken.lower()


def test_summary_leads_with_the_doc_comment_when_there_is_one():
    summary = build_function_summary(fn(description="Guards every call that needs auth. More detail here."))
    assert summary.startswith("requireAuth — ")
    assert "Guards every call that needs auth." in summary
    assert "More detail here." not in summary, "summary is one sentence"


def test_summary_falls_back_to_derived_facts_without_a_doc_comment():
    summary = build_function_summary(fn(exported=True, raisesError=True))
    assert "requireAuth" in summary
    assert "exported" in summary


def test_speakable_strips_markup_that_would_be_read_aloud():
    assert speakable("Use `getIdToken(true)` to *force* a refresh") == (
        "Use getIdToken(true) to force a refresh"
    )


def test_speakable_trims_a_very_long_comment_at_a_sentence_boundary():
    long_doc = ("This sentence is here to pad the comment out. " * 30).strip()
    result = speakable(long_doc)
    assert len(result) <= MAX_SPOKEN_DOC_CHARS
    assert result.endswith(".")
