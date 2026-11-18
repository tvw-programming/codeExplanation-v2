from src.render.highlight_config import build_highlight_config
from src.render.timing import TimedCue


def test_builds_frame_range_from_ms_at_given_fps():
    cues = [TimedCue(id="a", token="VISUAL[HIGHLIGHT:a]", line_range=[10, 20], label="fn",
                      start_ms=1000, end_ms=2000, assumed=False)]
    config = build_highlight_config(cues, fps=30)
    assert config == [{"id": "a", "lineRange": [10, 20], "fromFrame": 30, "toFrame": 60,
                        "assumed": False, "note": None}]


def test_preserves_assumed_flag_and_note():
    cues = [TimedCue(id="a", token="VISUAL[HIGHLIGHT:a]", line_range=[1, 2], label="fn",
                      start_ms=0, end_ms=500, assumed=True, note="widened fallback")]
    config = build_highlight_config(cues, fps=24)
    assert config[0]["assumed"] is True
    assert config[0]["note"] == "widened fallback"


def test_empty_input_returns_empty_list():
    assert build_highlight_config([], fps=30) == []
