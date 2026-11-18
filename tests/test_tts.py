import shutil

import pytest

import src.render.tts as tts_module
from src.render.tts import synthesize, TTSError, PIPER_ENGINE_ID, ESPEAK_ENGINE_ID

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None, reason="espeak-ng not installed in this environment"
)


@requires_espeak
def test_synthesize_produces_a_real_nonempty_wav_file(tmp_path):
    result = synthesize("Hello from the test suite.", tmp_path / "out.wav")
    assert result.path.is_file()
    assert result.path.stat().st_size > 0
    assert result.engine  # honestly records which engine actually ran


@requires_espeak
def test_synthesize_creates_parent_directories(tmp_path):
    result = synthesize("Nested path check.", tmp_path / "nested" / "dir" / "out.wav")
    assert result.path.is_file()


def test_synthesize_raises_tts_error_when_binary_missing(tmp_path, monkeypatch):
    import subprocess as subprocess_module

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("espeak-ng not found")

    monkeypatch.setattr(subprocess_module, "run", fake_run)
    with pytest.raises(TTSError):
        synthesize("text", tmp_path / "out.wav")


def test_synthesize_falls_back_to_espeak_when_piper_voice_not_downloaded(tmp_path, monkeypatch):
    """The common case in this dev environment (and CI): the ~64MB
    Piper model hasn't been downloaded, so synthesis must silently use
    espeak-ng rather than erroring."""
    monkeypatch.setattr(tts_module, "piper_voice_available", lambda: False)

    calls = []

    def fake_espeak(text, out_path, *a, **kw):
        calls.append(text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF....")
        return out_path

    monkeypatch.setattr(tts_module, "_synthesize_espeak", fake_espeak)
    result = synthesize("text", tmp_path / "out.wav")
    assert result.engine == ESPEAK_ENGINE_ID
    assert calls == ["text"]


def test_synthesize_prefers_piper_when_voice_is_available(tmp_path, monkeypatch):
    monkeypatch.setattr(tts_module, "piper_voice_available", lambda: True)

    def fake_piper(text, out_path):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF....")
        return out_path

    def fail_if_called_espeak(*a, **kw):
        raise AssertionError("should not fall back to espeak-ng when piper succeeds")

    monkeypatch.setattr(tts_module, "_synthesize_piper", fake_piper)
    monkeypatch.setattr(tts_module, "_synthesize_espeak", fail_if_called_espeak)
    result = synthesize("text", tmp_path / "out.wav")
    assert result.engine == PIPER_ENGINE_ID


def test_synthesize_falls_back_to_espeak_when_piper_itself_fails(tmp_path, monkeypatch):
    """Piper's model files exist but synthesis fails for some other
    reason (corrupt model, unsupported text, ...) — must not take the
    whole chunk down with it; fall back rather than erroring."""
    monkeypatch.setattr(tts_module, "piper_voice_available", lambda: True)

    def failing_piper(text, out_path):
        raise TTSError("piper failed (exit 1): something went wrong")

    def fake_espeak(text, out_path, *a, **kw):
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF....")
        return out_path

    monkeypatch.setattr(tts_module, "_synthesize_piper", failing_piper)
    monkeypatch.setattr(tts_module, "_synthesize_espeak", fake_espeak)
    result = synthesize("text", tmp_path / "out.wav")
    assert result.engine == ESPEAK_ENGINE_ID
