"""Controller tests: state transitions, background jobs and error surfaces."""

from __future__ import annotations

import threading
from pathlib import Path


from deepl_ofm.controller import AppController
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.services.translation import (
    TranslationCancelled,
    TranslationError,
    TranslationOutput,
)



def wait_until(predicate, timeout: float = 3.0, step: float = 0.01) -> bool:
    import time

    from PySide6.QtWidgets import QApplication

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(step)
    return predicate()


def _controller(tmp_path: Path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.model = "hy-mt2:7b"
    history = HistoryStore(path=tmp_path / "history.json")
    controller = AppController(settings=settings, history=history)
    controller.settings.auto_translate = False
    return controller


def test_translate_success(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    calls = []

    def fake_translate(text, **kwargs):
        calls.append(text)
        kwargs["on_progress"](1, 1)
        return TranslationOutput(text="Привіт, світ!", warnings=0, duration_ms=42, tokens_per_second=12.5)

    monkeypatch.setattr(controller.translator, "translate", fake_translate)
    controller.set_source_text("Hello, world!")
    controller.translate(force=True)

    assert wait_until(lambda: controller.translated_text != "", timeout=3)
    assert controller.translated_text == "Привіт, світ!"
    assert controller.is_translating is False
    assert controller.last_duration_ms == 42
    assert controller.tokens_per_second == 12.5
    assert calls == ["Hello, world!"]
    assert len(controller.history.entries) == 1
    assert controller.history.entries[0].translated_text == "Привіт, світ!"


def test_translate_error_is_localised(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    errors = []
    controller.errorRaised.connect(errors.append)

    def failing(text, **kwargs):
        raise TranslationError("connection", detail="http://127.0.0.1:11434")

    monkeypatch.setattr(controller.translator, "translate", failing)
    controller.set_source_text("Hello")
    controller.translate(force=True)

    assert wait_until(lambda: bool(errors), timeout=3)
    assert not controller.is_translating
    assert controller.translated_text == ""


def test_cancel_marks_not_translating(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    release = threading.Event()

    def slow(text, **kwargs):
        kwargs["on_progress"](0, 3)
        release.wait(2)
        raise TranslationCancelled()

    monkeypatch.setattr(controller.translator, "translate", slow)
    controller.set_source_text("Hello")
    controller.translate(force=True)
    assert wait_until(lambda: controller.is_translating, timeout=2)

    controller.cancel()
    assert controller.is_translating is False
    release.set()


def test_style_and_tone_persist(qapp, tmp_path):
    controller = _controller(tmp_path)
    controller.set_style("natural")
    controller.set_tone("formal")
    assert controller.settings.last_style.value == "natural"

    reloaded = AppSettings(path=tmp_path / "settings.json")
    assert reloaded.last_style.value == "natural"
    assert reloaded.last_tone.value == "formal"


def test_swap_languages_resolves_auto(qapp, tmp_path):
    controller = _controller(tmp_path)
    controller.set_source_language("auto")
    controller.set_target_language("uk")
    controller.set_source_text("The quick brown fox jumps over the lazy dog.")
    controller._run_detection()

    controller.swap_languages()
    assert controller.source_language.code == "uk"
    assert controller.target_language.code == "en"


def test_interface_language_switch(qapp, tmp_path):
    controller = _controller(tmp_path)
    from deepl_ofm.i18n import t

    assert t("Settings", "en") == "Settings"
    controller.set_interface_language("uk")
    assert controller.settings.interface_language.value == "uk"
    assert t("Settings") == "Налаштування"


def test_file_job_reports_failure(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    source = tmp_path / "note.txt"
    source.write_text("Hello there.", encoding="utf-8", newline="")

    from deepl_ofm.services.documents import DocumentError

    def broken_read(path):
        raise DocumentError("unreadable")

    monkeypatch.setattr("deepl_ofm.controller.DocumentTranslator.read", broken_read)
    controller.start_file_translation(source)
    assert wait_until(lambda: (controller.file_job or {}).get("state") == "failed", timeout=3)
    assert controller.file_job["message"]


def test_history_entry_loaded_on_request(qapp, tmp_path):
    controller = _controller(tmp_path)
    from deepl_ofm.services.history import HistoryEntry

    entry = HistoryEntry(
        source_text="Hello",
        translated_text="Привіт",
        source_code="en",
        target_code="uk",
        style="auto",
        tone="standard",
        engine="test",
        duration_ms=10,
    )
    controller.history.add(entry)
    controller.load_history_entry(entry.id)
    assert controller.source_text == "Hello"
    assert controller.translated_text == "Привіт"
    assert controller.target_language.code == "uk"
