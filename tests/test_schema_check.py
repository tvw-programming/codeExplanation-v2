from src.validate.schema_check import validate_record, validate_records


def _valid_record(**overrides):
    record = {
        "chunkId": "x-1",
        "filePath": "src/x.ts",
        "featureName": "X",
        "projectType": {"frontend": "react"},
        "language": "TypeScript",
        "lineRange": [1, 10],
        "frameworkOrLibrary": ["React"],
        "featureMapping": [],
        "confidence": 0.9,
        "confidenceLevel": "high",
        "contentHash": "abc123",
        "lastUpdated": "2026-01-01T00:00:00Z",
        "pullRequest": None,
    }
    record.update(overrides)
    return record


def test_valid_record_has_no_problems():
    assert validate_record(_valid_record()) == []


def test_missing_required_field_is_reported():
    record = _valid_record()
    del record["language"]
    problems = validate_record(record)
    assert any("language" in p for p in problems)


def test_missing_storage_key_entirely_is_reported_even_if_other_is_null():
    record = _valid_record()
    del record["pullRequest"]
    problems = validate_record(record)
    assert any("pullRequest" in p for p in problems)


def test_pull_request_present_but_null_is_fine():
    record = _valid_record(pullRequest=None)
    assert validate_record(record) == []


def test_invalid_line_range_start_after_end_is_reported():
    record = _valid_record(lineRange=[10, 1])
    problems = validate_record(record)
    assert any("lineRange" in p for p in problems)


def test_confidence_out_of_range_is_reported():
    record = _valid_record(confidence=1.5)
    problems = validate_record(record)
    assert any("confidence" in p for p in problems)


def test_invalid_confidence_level_is_reported():
    record = _valid_record(confidenceLevel="super-high")
    problems = validate_record(record)
    assert any("confidenceLevel" in p for p in problems)


def test_feature_mapping_not_a_list_is_reported():
    record = _valid_record(featureMapping="not-a-list")
    problems = validate_record(record)
    assert any("featureMapping" in p for p in problems)


def test_validate_records_summarizes_valid_and_invalid_counts():
    records = [_valid_record(chunkId="a"), _valid_record(chunkId="b", language=None)]
    result = validate_records(records)
    assert result["total"] == 2
    assert result["validCount"] == 1
    assert result["invalidCount"] == 1
    assert "b" in result["problems"]
    assert "a" not in result["problems"]


def test_validate_records_placeholder_stack_record_fails_honestly():
    # Phase 3's honest placeholder for an unimplemented stack — missing
    # almost everything required. Must be reported, not swallowed.
    placeholder = {
        "chunkId": "py-agent-1",
        "filePath": "agent/main.py",
        "featureName": "Agent",
        "projectType": {},
        "notes": "Extraction for stack 'python' is not yet implemented in Phase 3.",
        "confidence": 0,
        "confidenceLevel": "low",
    }
    result = validate_records([placeholder])
    assert result["invalidCount"] == 1
    assert len(result["problems"]["py-agent-1"]) > 0
