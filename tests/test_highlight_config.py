from src.render.highlight_config import MIN_HIGHLIGHT_SECONDS, build_highlight_config
from src.render.timing import TimedCue


def cue(id_, start_ms, end_ms, line_range=(1, 2), assumed=False, note=None):
    return TimedCue(id=id_, token=f"VISUAL[HIGHLIGHT:{id_}]", line_range=list(line_range),
                    label=id_, start_ms=start_ms, end_ms=end_ms, assumed=assumed, note=note)


def test_builds_frame_range_from_ms_at_given_fps():
    config = build_highlight_config([cue("a", 1000, 2000, (10, 20))], fps=30)
    entry = config[0]
    assert entry["id"] == "a"
    assert entry["lineRange"] == [10, 20]
    # The aligned anchor is reported unchanged.
    assert entry["fromFrame"] == 30
    assert entry["toFrame"] == 60
    assert entry["assumed"] is False
    assert entry["note"] is None


def test_preserves_assumed_flag_and_note():
    config = build_highlight_config([cue("a", 0, 500, assumed=True, note="widened fallback")], fps=24)
    assert config[0]["assumed"] is True
    assert config[0]["note"] == "widened fallback"


def test_empty_input_returns_empty_list():
    assert build_highlight_config([], fps=30) == []


def test_first_cue_is_held_from_the_start_of_the_chunk():
    """Otherwise the opening beats play over unmarked code."""
    config = build_highlight_config([cue("a", 5000, 5400)], fps=30, duration_ms=20000)
    assert config[0]["displayFromFrame"] == 0
    assert config[0]["displayShifted"] is True


def test_last_cue_is_held_to_the_end_of_the_chunk():
    config = build_highlight_config([cue("a", 1000, 1400)], fps=30, duration_ms=20000)
    assert config[0]["displayToFrame"] >= 600


def test_each_cue_holds_until_the_next_one_starts_leaving_no_gaps():
    cues = [cue("a", 2000, 2400), cue("b", 9000, 9400), cue("c", 16000, 16400)]
    config = build_highlight_config(cues, fps=30, duration_ms=24000)
    windows = [(c["displayFromFrame"], c["displayToFrame"]) for c in config]
    assert windows[0][0] == 0
    for (_, end), (next_start, _) in zip(windows, windows[1:]):
        assert end == next_start, f"gap or overlap between {windows}"
    assert windows[-1][1] >= 720


def test_every_cue_gets_the_readable_minimum_when_there_is_room():
    """Anchors a third of a second apart must not produce flashes."""
    cues = [cue("a", 1000, 1300), cue("b", 1300, 1600), cue("c", 1600, 1900)]
    config = build_highlight_config(cues, fps=30, duration_ms=60000)
    min_frames = MIN_HIGHLIGHT_SECONDS * 30
    for entry in config:
        held = entry["displayToFrame"] - entry["displayFromFrame"]
        assert held >= min_frames, f"{entry['id']} only held {held} frames"


def test_display_windows_stay_inside_a_chunk_too_short_for_the_full_minimum():
    """Nine cues in three seconds can't each get two seconds; they share
    the time instead of running off the end of the chunk."""
    cues = [cue(str(i), i * 300, i * 300 + 200) for i in range(9)]
    config = build_highlight_config(cues, fps=30, duration_ms=3000)
    total_frames = 90
    assert all(c["displayFromFrame"] < total_frames for c in config)
    starts = [c["displayFromFrame"] for c in config]
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts), "cues must not collapse onto one frame"


def test_cues_are_ordered_by_anchor_even_when_passed_out_of_order():
    cues = [cue("late", 9000, 9400), cue("early", 1000, 1400)]
    config = build_highlight_config(cues, fps=30, duration_ms=20000)
    assert [c["id"] for c in config] == ["early", "late"]
