import shutil

import pytest

from src.render.tts import synthesize, TTSError

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None, reason="espeak-ng not installed in this environment"
)


@requires_espeak
def test_synthesize_produces_a_real_nonempty_wav_file(tmp_path):
    out = synthesize("Hello from the test suite.", tmp_path / "out.wav")
    assert out.is_file()
    assert out.stat().st_size > 0


@requires_espeak
def test_synthesize_creates_parent_directories(tmp_path):
    out = synthesize("Nested path check.", tmp_path / "nested" / "dir" / "out.wav")
    assert out.is_file()


def test_synthesize_raises_tts_error_when_binary_missing(tmp_path, monkeypatch):
    import subprocess as subprocess_module

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("espeak-ng not found")

    monkeypatch.setattr(subprocess_module, "run", fake_run)
    with pytest.raises(TTSError):
        synthesize("text", tmp_path / "out.wav")
