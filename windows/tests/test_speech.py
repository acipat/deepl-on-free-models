"""Tests for ``deepl_ofm.services.speech`` (port of Speaker.swift)."""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from deepl_ofm.services import speech as speech_module  # noqa: E402
from deepl_ofm.services.speech import Speaker  # noqa: E402

_APP = None


def _ensure_app() -> QApplication:
    global _APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _APP = app
    return _APP


@pytest.fixture(scope="module", autouse=True)
def qapp() -> QApplication:
    return _ensure_app()


class _FakeLocale:
    def __init__(self, name: str) -> None:
        self._name = name

    def name(self) -> str:
        return self._name


class _FakeVoice:
    def __init__(self, name: str, locale: str) -> None:
        self._name = name
        self._locale = _FakeLocale(locale)

    def name(self) -> str:
        return self._name

    def locale(self) -> _FakeLocale:
        return self._locale


def test_construction_offscreen_does_not_raise() -> None:
    speaker = Speaker()
    assert speaker.is_speaking() is False
    # Forces the engine path (or its absence) without raising.
    assert isinstance(speaker.is_available(), bool)


def test_voices_returns_list_of_pairs() -> None:
    speaker = Speaker()
    voices = speaker.voices()
    assert isinstance(voices, list)
    for voice_id, label in voices:
        assert isinstance(voice_id, str)
        assert isinstance(label, str)


def test_speak_without_engine_is_a_noop(monkeypatch) -> None:
    monkeypatch.setattr(speech_module, "_QT_SPEECH_AVAILABLE", False)
    monkeypatch.setattr(speech_module, "QTextToSpeech", None)
    speaker = Speaker()
    started: list[str] = []
    finished: list[str] = []
    speaker.started.connect(started.append)
    speaker.finished.connect(finished.append)

    assert speaker.is_available() is False
    assert speaker.voices() == []
    speaker.speak("Hello", target="translation")
    speaker.speak("Привіт", voice_id="any", target="source")
    speaker.stop()

    assert started == []
    assert finished == []
    assert speaker.is_speaking() is False


def test_empty_text_is_ignored() -> None:
    speaker = Speaker()
    started: list[str] = []
    speaker.started.connect(started.append)
    speaker.speak("   ", target="translation")
    speaker.speak("", target="source")
    assert started == []


def test_stop_and_is_speaking_are_safe_without_speech() -> None:
    speaker = Speaker()
    speaker.stop()
    assert speaker.is_speaking() is False


def test_voice_id_helper() -> None:
    assert speech_module._voice_id(_FakeVoice("Zosia", "pl_PL")) == "pl_PL::Zosia"
    assert speech_module._voice_id(_FakeVoice("", "")) == "::"


def test_max_chars_matches_the_swift_truncation() -> None:
    assert Speaker.MAX_CHARS == 4000


class _FakeState:
    Ready = "ready"
    Speaking = "speaking"
    Synthesizing = "synthesizing"
    Paused = "paused"
    Error = "error"


class _FakeSignal:
    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def emit(self, value) -> None:
        for slot in list(self._slots):
            slot(value)


class _FakeEngine:
    """Just enough of QTextToSpeech to exercise the non-no-op path."""

    State = _FakeState

    def __init__(self) -> None:
        self._state = _FakeState.Ready
        self._voices = [_FakeVoice("Bob", "en_US"), _FakeVoice("Zosia", "pl_PL")]
        self.stateChanged = _FakeSignal()
        self.errorOccurred = _FakeSignal()
        self.spoken: list[str] = []
        self.voice = None
        self.locale = None

    @staticmethod
    def availableEngines() -> list[str]:
        return ["fake"]

    def availableVoices(self) -> list:
        return list(self._voices)

    def availableLocales(self) -> list:
        return [voice.locale() for voice in self._voices]

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        self._state = state
        self.stateChanged.emit(state)

    def say(self, text: str) -> None:
        self.spoken.append(text)
        self.set_state(_FakeState.Speaking)

    def stop(self) -> None:
        self.set_state(_FakeState.Ready)

    def setVoice(self, voice) -> None:
        self.voice = voice

    def setLocale(self, locale) -> None:
        self.locale = locale


def test_speak_with_a_fake_engine(monkeypatch) -> None:
    monkeypatch.setattr(speech_module, "_QT_SPEECH_AVAILABLE", True)
    monkeypatch.setattr(speech_module, "QTextToSpeech", _FakeEngine)
    speaker = Speaker()
    started: list[str] = []
    finished: list[str] = []
    speaker.started.connect(started.append)
    speaker.finished.connect(finished.append)

    assert speaker.is_available() is True
    assert [label for _, label in speaker.voices()] == ["Bob", "Zosia"]

    speaker.speak("Hello", "en_US::Bob", "translation", language_code="en")
    engine = speaker._engine
    assert started == ["translation"]
    assert engine.spoken == ["Hello"]
    assert engine.voice is not None and engine.voice.name() == "Bob"
    assert speaker.is_speaking() is True

    engine.set_state(_FakeState.Ready)
    assert finished == ["translation"]
    assert speaker.is_speaking() is False


def test_speak_picks_a_voice_by_language(monkeypatch) -> None:
    monkeypatch.setattr(speech_module, "_QT_SPEECH_AVAILABLE", True)
    monkeypatch.setattr(speech_module, "QTextToSpeech", _FakeEngine)
    speaker = Speaker()
    speaker.speak("Dzień dobry", target="translation", language_code="pl")

    engine = speaker._engine
    assert engine.voice is not None and engine.voice.name() == "Zosia"
