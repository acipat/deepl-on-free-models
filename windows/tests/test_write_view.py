"""Write tab: local copy, busy cycle polling, error state and retranslation."""

from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language, t
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.theme import Theme
from deepl_ofm.ui.write_view import WriteView


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def controller(qapp, tmp_path: Path):
    Theme.apply(qapp, dark=False)
    set_language(AppLanguage.EN)
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.interface_language = AppLanguage.EN
    settings.auto_translate = False
    controller = AppController(
        settings=settings, history=HistoryStore(path=tmp_path / "history.json")
    )
    yield controller
    set_language(AppLanguage.EN)
    controller.deleteLater()
    qapp.processEvents()


@pytest.fixture
def view(qapp, controller):
    widget = WriteView(controller)
    widget.resize(1180, 760)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.deleteLater()
    qapp.processEvents()


def _busy_writer(controller, calls: list[tuple[str, str]]):
    def fake(text: str, target_code: str) -> None:
        calls.append((text, target_code))
        controller.write_in_progress = True

    return fake


def test_initial_state(qapp, view, controller):
    assert view.heading.text() == t("Improve text")
    assert view.editor.placeholderText() == t("Type or paste text to improve")
    assert view.placeholder.isVisible()
    assert not view.result_view.isVisible()
    assert view.language_combo.include_auto() is False
    assert view.language_combo.code() == controller.target_language.code
    assert not view.improve_button.isEnabled()
    assert view.improve_button.text() == t("Improve text")
    assert not view.copy_button.isEnabled()
    assert not view.cancel_button.isVisible()
    assert view._poll_timer.interval() == 120


def test_improve_captures_text_and_target(qapp, view, controller, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(controller, "write_text", _busy_writer(controller, calls))

    view.editor.setPlainText("  Hello world  ")
    view.improve_button.click()

    # Without an explicit choice the text is improved in its own language:
    # the controller receives "auto" and detects it (macOS WriteStore behaviour).
    assert calls == [("  Hello world  ", "auto")]
    assert view.improve_button.text() == t("Improving…")
    assert not view.improve_button.isEnabled()
    assert view.cancel_button.isVisible()
    assert view._poll_timer.isActive()
    assert view.editor.toPlainText() == "  Hello world  "

    # Let the fixture tear down without a live poll timer.
    controller.write_in_progress = False
    view._poll_timer.stop()


def test_busy_cycle_restores_button_and_shows_result(qapp, view, controller, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(controller, "write_text", _busy_writer(controller, calls))

    view.editor.setPlainText("The app is very good.")
    view.improve_button.click()
    assert not view.improve_button.isEnabled()

    controller.write_output = "The app works very well."
    controller.write_warning_count = 1
    controller.write_in_progress = False

    assert _wait_until(lambda: view.improve_button.isEnabled())
    assert view.improve_button.text() == t("Improve text")
    assert view.result_view.markdown() == "The app works very well."
    assert view.result_view.isVisible()
    assert not view.placeholder.isVisible()
    assert view.copy_button.isEnabled()
    assert view.warning_label.isVisible()
    assert "1" in view.warning_label.text()
    assert not view._poll_timer.isActive()
    assert not view.cancel_button.isVisible()


def test_cancel_calls_controller_and_stops_polling(qapp, view, controller, monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(controller, "write_text", _busy_writer(controller, calls))

    view.editor.setPlainText("Some text")
    view.improve_button.click()
    assert view._poll_timer.isActive()

    cancelled: list[bool] = []

    def fake_cancel() -> None:
        cancelled.append(True)
        controller.write_in_progress = False

    monkeypatch.setattr(controller, "cancel_write", fake_cancel)
    view.cancel_button.click()

    assert cancelled == [True]
    assert not view._poll_timer.isActive()
    assert view.improve_button.isEnabled()
    assert view.improve_button.text() == t("Improve text")
    assert not view.cancel_button.isVisible()


def test_copy_uses_clipboard_and_shows_copied_state(qapp, view, controller):
    controller.write_output = "**Improved** text."
    view._sync_from_controller()
    qapp.processEvents()
    assert view.copy_button.isEnabled()

    original = QGuiApplication.clipboard().text()
    try:
        view.copy_button.click()
        assert QGuiApplication.clipboard().text() == "**Improved** text."
        assert view.copy_button.text() == t("Copied")
        assert view.copy_button.icon_name() == "check"
        assert not view.copy_button.isEnabled()

        view._end_copied()
        assert view.copy_button.text() == t("Copy")
        assert view.copy_button.icon_name() == "copy"
        assert view.copy_button.isEnabled()
    finally:
        QGuiApplication.clipboard().setText(original)


def test_error_and_warning_are_rendered(qapp, view, controller):
    controller.write_error = "The provider is unavailable."
    view._sync_from_controller()
    qapp.processEvents()
    assert view.error_row.isVisible()
    assert view.error_label.text() == "The provider is unavailable."

    controller.write_error = None
    controller.write_output = "Better text."
    controller.write_warning_count = 2
    view._sync_from_controller()
    qapp.processEvents()
    assert not view.error_row.isVisible()
    assert view.warning_label.isVisible()
    assert "2" in view.warning_label.text()


def test_retranslate_ui_changes_headings_and_keeps_state(qapp, view, controller):
    view.editor.setPlainText("Keep this source text")
    controller.write_output = "Keep this improved text."
    controller.write_warning_count = 0
    view._sync_from_controller()
    qapp.processEvents()

    controller.set_interface_language(AppLanguage.UK)
    qapp.processEvents()

    assert view.heading.text() == t("Improve text")
    assert view.heading.text() != "Improve text"
    assert view.control_label.text() == t("Improve in")
    assert view.subtitle.text() != "Improve clarity, grammar and style while keeping the meaning."
    assert view.editor.placeholderText() == t("Type or paste text to improve")
    assert view.source_card.title() == t("Source")
    assert view.result_card.title() == t("Result")
    assert view.editor.toPlainText() == "Keep this source text"
    assert view.result_view.markdown() == "Keep this improved text."


def test_copy_feedback_refreshes_panes(qapp, view, controller):
    controller.write_output = "Fresh text."
    controller.copyFeedback.emit(t("Translation copied"))
    qapp.processEvents()

    assert view.result_view.markdown() == "Fresh text."
    assert view.copy_button.isEnabled()
