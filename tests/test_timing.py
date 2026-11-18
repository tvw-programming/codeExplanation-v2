from src.render.timing import align_cues_to_words, ms_to_frame, TranscriptWord
from src.narrate.visual_cues import VisualCue


def _cue(cue_id="cue-1", label="validateProfile", line_range=(10, 20)):
    return VisualCue(id=cue_id, token=f"VISUAL[HIGHLIGHT:{cue_id}]", line_range=list(line_range),
                      label=label, source_field="importantFunctions")


def test_ms_to_frame_rounds_to_nearest_frame():
    assert ms_to_frame(1000, 30) == 30
    assert ms_to_frame(500, 30) == 15
    assert ms_to_frame(16, 30) == 0  # rounds down, not up, at .48 frames


def test_align_exact_match_within_transcript_is_not_assumed():
    cues = [_cue()]
    cue_word_index = {"cue-1": 2}
    words = [
        TranscriptWord("The", 0, 200),
        TranscriptWord("function", 200, 500),
        TranscriptWord("runs", 500, 800),
        TranscriptWord("next", 800, 1100),
    ]
    timed = align_cues_to_words(cues, cue_word_index, words)
    assert len(timed) == 1
    assert timed[0].assumed is False
    assert timed[0].start_ms == 500
    assert timed[0].end_ms == 800


def test_align_index_past_transcript_falls_back_and_widens_and_marks_assumed():
    cues = [_cue()]
    cue_word_index = {"cue-1": 50}  # way past the 4-word transcript
    words = [
        TranscriptWord("The", 0, 200),
        TranscriptWord("function", 200, 500),
        TranscriptWord("runs", 500, 800),
        TranscriptWord("next", 800, 1100),
    ]
    timed = align_cues_to_words(cues, cue_word_index, words)
    assert timed[0].assumed is True
    assert timed[0].start_ms == 800 - 200
    assert timed[0].end_ms == 1100 + 200
    assert timed[0].note is not None


def test_align_no_transcript_words_marks_assumed_with_zeroed_times():
    cues = [_cue()]
    timed = align_cues_to_words(cues, {"cue-1": 0}, [])
    assert timed[0].assumed is True
    assert timed[0].start_ms == 0 and timed[0].end_ms == 0


def test_align_missing_cue_index_marks_assumed():
    cues = [_cue()]
    timed = align_cues_to_words(cues, {}, [TranscriptWord("Hello", 0, 100)])
    assert timed[0].assumed is True


def test_align_widened_start_never_goes_negative():
    cues = [_cue()]
    words = [TranscriptWord("Hi", 0, 100)]
    timed = align_cues_to_words(cues, {"cue-1": 5}, words)
    assert timed[0].start_ms == 0  # would be -100 without the floor
