from src.narrate.pipeline import generate_narration_for_repo


def _records():
    return [
        {
            "chunkId": "admin-grid-a1",
            "featureName": "Alumni Admin Grid",
            "frameworkOrLibrary": ["React"],
            "eventHandlers": [{"name": "handleSave", "eventType": "user action", "assumed": False}],
            "apiCalls": [{"method": "GET", "url": "/alumni", "assumed": False}],
            "featureMapping": ["alumni-repo-b2"],
            "notes": "internal reviewer note that must never be spoken",
        },
        {
            "chunkId": "alumni-repo-b2",
            "featureName": "Alumni Repository",
            "frameworkOrLibrary": ["Go Fiber"],
            "routes": [{"method": "GET", "path": "/alumni", "assumed": False}],
            "featureMapping": ["admin-grid-a1"],
        },
    ]


def test_every_record_gets_a_script_and_pronunciation_table():
    results = generate_narration_for_repo(_records())
    assert set(results.keys()) == {"admin-grid-a1", "alumni-repo-b2"}
    for entry in results.values():
        assert entry["script"] is not None
        assert isinstance(entry["pronunciationTable"], dict)


def test_dependency_processed_first_gets_a_back_reference_from_the_other():
    results = generate_narration_for_repo(_records())
    # Whichever of the two is processed second should reference the
    # first one as a back-reference (they link to each other, so one
    # direction must resolve as "earlier").
    connections_texts = [results[cid]["script"].connections for cid in results]
    assert any("covered earlier" in text for text in connections_texts)


def test_notes_field_never_appears_in_generated_scripts():
    results = generate_narration_for_repo(_records())
    for entry in results.values():
        script = entry["script"]
        full_text = " ".join([script.purpose, script.connections, *script.flow, script.recap])
        assert "internal reviewer note" not in full_text


def test_pronunciation_table_covers_identifiers_used_in_the_script():
    results = generate_narration_for_repo(_records())
    table = results["admin-grid-a1"]["pronunciationTable"]
    assert "handleSave" in table
    assert table["handleSave"] == "handle Save"


def test_isolated_chunk_with_no_links_gets_standalone_connections_beat():
    records = _records() + [{
        "chunkId": "isolated-c3",
        "featureName": "Isolated Util",
        "frameworkOrLibrary": ["Python"],
        "featureMapping": [],
    }]
    results = generate_narration_for_repo(records)
    assert "stands on its own" in results["isolated-c3"]["script"].connections
