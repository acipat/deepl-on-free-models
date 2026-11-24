"""Regression tests for the behaviour fixed after the macOS↔Windows parity audit."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication

from deepl_ofm.controller import AppController
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.services.translation import TranslationOutput


def _controller(tmp_path: Path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.auto_translate = False
    settings.last_source_code = "en"
    settings.last_target_code = "uk"
    controller = AppController(settings=settings, history=HistoryStore(path=tmp_path / "history.json"))
    return controller


def _pump(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        from PySide6.QtWidgets import QApplication

        QApplication.processEvents()
        time.sleep(0.01)
    return predicate()


def test_selection_is_captured_before_the_window_appears(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    order: list[str] = []

    monkeypatch.setattr("deepl_ofm.support.selection.is_supported", lambda: True)
    monkeypatch.setattr(
        "deepl_ofm.support.selection.capture_selection",
        lambda **_: (order.append("capture"), "Selected sentence")[1],
    )
    monkeypatch.setattr(controller, "translate", lambda force=False: order.append("translate"))
    controller.windowRequested.connect(lambda: order.append("window"))

    controller.translate_selection()

    assert order == ["capture", "window", "translate"]
    assert controller.source_text == "Selected sentence"


def test_selection_failure_is_reported(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    monkeypatch.setattr("deepl_ofm.support.selection.is_supported", lambda: True)
    monkeypatch.setattr("deepl_ofm.support.selection.capture_selection", lambda **_: "")

    controller.translate_selection()

    assert errors and "administrator" in errors[-1]


def test_copy_follows_the_result_view_mode(qapp, tmp_path):
    controller = _controller(tmp_path)
    controller.translated_text = "**Hello** world\n\n# Heading"

    controller.set_result_view("text")
    controller.copy_translation()
    clipboard = QGuiApplication.clipboard()
    assert "**" not in clipboard.text()
    assert not clipboard.mimeData().hasHtml()

    controller.set_result_view("markdown")
    controller.copy_translation()
    assert clipboard.text() == "**Hello** world\n\n# Heading"

    controller.set_result_view("preview")
    controller.copy_translation()
    assert clipboard.mimeData().hasHtml()
    assert "**" not in clipboard.text()


def test_swap_languages_swaps_the_panes(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    monkeypatch.setattr(controller, "translate", lambda force=False: None)
    controller.set_source_text("Hello")
    controller.translated_text = "Привіт"

    controller.swap_languages()

    assert controller.source_text == "Привіт"
    assert controller.translated_text == "Hello"
    assert controller.source_language.code == "uk"
    assert controller.target_language.code == "en"


def test_style_change_retranslates_when_auto_translate_is_off(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    calls: list[str] = []

    def fake_translate(text, **kwargs):
        calls.append(text)
        return TranslationOutput(text="Готово", duration_ms=5)

    monkeypatch.setattr(controller.translator, "translate", fake_translate)
    controller.set_source_text("Hello")
    controller.translate(force=True)
    assert _pump(lambda: controller.translated_text == "Готово")

    controller.set_style("literal")
    assert _pump(lambda: len(calls) == 2)


def test_clear_resets_every_metric(qapp, tmp_path):
    controller = _controller(tmp_path)
    controller.set_source_text("Hello")
    controller.tokens_per_second = 12.0
    controller.last_duration_ms = 900
    controller.using_fallback = True
    controller.detected_language = controller.target_language

    controller.clear_source()

    assert controller.source_text == ""
    assert controller.translated_text == ""
    assert controller.tokens_per_second is None
    assert controller.last_duration_ms is None
    assert controller.using_fallback is False
    assert controller.detected_language is None


def test_clipboard_hotkey_converts_html_to_markdown(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(controller, "translate", lambda force=False: calls.append("translate"))

    mime = QMimeData()
    mime.setHtml("<h2>Title</h2><p>Hello <b>world</b></p>")
    mime.setText("Title\n\nHello world")
    QGuiApplication.clipboard().setMimeData(mime)

    controller.translate_clipboard()

    assert "## Title" in controller.source_text
    assert "**world**" in controller.source_text
    assert calls == ["translate"]
