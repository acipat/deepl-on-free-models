"""Translate tab tests: layout states, controller wiring and retranslation."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, Qt
from PySide6.QtTest import QTest

from deepl_ofm.controller import AppController
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language, t
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.translate_view import TranslateView


def _controller(tmp_path: Path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.model = "hy-mt2:7b"
    settings.auto_translate = False
    controller = AppController(
        settings=settings,
        history=HistoryStore(path=tmp_path / "history.json"),
    )
    return controller


@pytest.fixture
def controller(qapp, tmp_path):
    value = _controller(tmp_path)
    yield value
    set_language("en")


@pytest.fixture
def view(qapp, controller):
    widget = TranslateView(controller)
    widget.resize(1180, 760)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Editing


def test_typing_updates_controller(qapp, view, controller):
    view._editor.setFocus()
    qapp.processEvents()
    QTest.keyClicks(view._editor, "Hello")
    qapp.processEvents()

    assert controller.source_text == "Hello"
    assert view._editor.toPlainText() == "Hello"
    assert "5" in view._source_counter.text()


def test_ctrl_enter_starts_translation(qapp, view, controller, monkeypatch):
    view.set_source_text("Hello")
    calls: list[bool] = []
    monkeypatch.setattr(controller, "translate", lambda force=False: calls.append(force))

    view._editor.setFocus()
    qapp.processEvents()
    QTest.keyClick(view._editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)

    assert calls == [True]


def test_escape_clears_editor_focus(qapp, view):
    view._editor.setFocus()
    qapp.processEvents()
    assert view._editor.hasFocus()

    QTest.keyClick(view._editor, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert not view._editor.hasFocus()


def test_set_source_text_and_paste_text(qapp, view, controller):
    view.set_source_text("Prefill")
    assert controller.source_text == "Prefill"
    assert view._editor.toPlainText() == "Prefill"

    view.paste_text("Pasted text")
    assert controller.source_text == "Pasted text"
    assert view._editor.toPlainText() == "Pasted text"


# ---------------------------------------------------------------------------
# Result pane states


def test_translating_shows_progress_and_stop(qapp, view, controller):
    controller.is_translating = True
    controller.translatingChanged.emit(True)
    controller.progressChanged.emit(13, 21)
    qapp.processEvents()

    assert view._stack.currentWidget() is view._progress_page
    assert view._progress_bar.value() == 62
    assert view._progress_percent.text() == "62%"
    assert "13" in view._progress_status.text()
    assert "21" in view._progress_status.text()
    assert view._progress_stop.isVisible()

    controller.is_translating = False
    controller.translatingChanged.emit(False)
    qapp.processEvents()

    assert view._stack.currentWidget() is view._empty_page


def test_progress_without_total_is_indeterminate(qapp, view, controller):
    controller.is_translating = True
    controller.translatingChanged.emit(True)
    controller.progressChanged.emit(0, 0)
    qapp.processEvents()

    assert view._progress_bar.is_indeterminate()
    assert not view._progress_counts.isVisibleTo(view)
    assert view._progress_percent.text() == ""


def test_result_shows_markdown_and_enables_copy(qapp, view, controller):
    translation = "# Title\n\nПривіт, **світ**!"
    controller.translated_text = translation
    controller.translatedTextChanged.emit(translation)
    qapp.processEvents()

    assert view._stack.currentWidget() is view._result_view
    assert view._result_view.markdown() == translation
    assert view._result_view.mode() == "preview"
    assert view._copy_button.isEnabled()
    assert "Привіт" in view._result_view.plain_text()


def test_result_view_mode_changes(qapp, view, controller):
    controller.translated_text = "Hello"
    controller.translatedTextChanged.emit("Hello")

    controller.set_result_view("markdown")
    qapp.processEvents()

    assert controller.result_view == "markdown"
    assert view._segmented.index() == 2
    assert view._result_view.mode() == "markdown"
    assert view._copy_button.toolTip() == t("Copy translation (Markdown)")


def test_error_shows_message_and_retry(qapp, view, controller):
    view.set_source_text("Hello")
    message = "Server unavailable. Check the model and try again."
    controller.error_message = message
    controller.translationFailed.emit(message)
    qapp.processEvents()

    assert view._stack.currentWidget() is view._error_page
    assert view._error_label.text() == message
    assert view._error_retry.isVisible()
    assert view._error_retry.isEnabled()


def test_error_keeps_existing_result_visible(qapp, view, controller):
    controller.translated_text = "Hello"
    controller.translatedTextChanged.emit("Hello")
    controller.error_message = "Some paragraphs are still in the original language (2)."
    controller.translationFailed.emit(controller.error_message)
    qapp.processEvents()

    assert view._stack.currentWidget() is view._result_view
    assert view._error_banner.isVisible()
    assert "original language" in view._banner_label.text()


def test_warning_pill_appears(qapp, view, controller):
    controller.warning_count = 2
    controller.warningCountChanged.emit(2)
    qapp.processEvents()

    assert view._warning_pill.isVisible()
    assert "2" in view._warning_pill.text()


# ---------------------------------------------------------------------------
# Controller wiring


def test_language_combo_selection_reaches_controller(qapp, view, controller):
    view._source_combo._select("uk", True)
    qapp.processEvents()
    assert controller.source_language.code == "uk"

    view._target_combo._select("de", True)
    qapp.processEvents()
    assert controller.target_language.code == "de"


def test_style_and_tone_reach_controller(qapp, view, controller):
    view._style_chips.changed.emit("literal")
    view._tone_chips.changed.emit("formal")
    qapp.processEvents()

    assert controller.style.value == "literal"
    assert controller.tone.value == "formal"
    assert view._style_chips.value() == "literal"
    assert view._tone_chips.value() == "formal"


def test_copy_button_calls_controller(qapp, view, controller, monkeypatch):
    controller.translated_text = "Hello"
    controller.translatedTextChanged.emit("Hello")
    calls: list[bool] = []
    monkeypatch.setattr(controller, "copy_translation", lambda: calls.append(True))

    view._copy_button.click()
    qapp.processEvents()

    assert calls == [True]
    assert view._copy_button.icon_name() == "check"


def test_stop_button_calls_cancel(qapp, view, controller, monkeypatch):
    controller.is_translating = True
    controller.translatingChanged.emit(True)
    calls: list[bool] = []
    monkeypatch.setattr(controller, "cancel", lambda: calls.append(True))

    view._progress_stop.click()
    qapp.processEvents()

    assert calls == [True]


def test_empty_state_action_starts_translation(qapp, view, controller, monkeypatch):
    view.set_source_text("Hello")
    calls: list[bool] = []
    monkeypatch.setattr(controller, "translate", lambda force=False: calls.append(force))

    view._translate_now.click()
    qapp.processEvents()

    assert calls == [True]


def test_speaking_updates_result_button(qapp, view, controller):
    controller.speaking = "translation"
    controller.speakingChanged.emit("translation")
    qapp.processEvents()

    assert view._speak_result_button.icon_name() == "stop"
    assert view._speak_result_button.toolTip() == t("Stop")

    controller.speaking = ""
    controller.speakingChanged.emit("")
    qapp.processEvents()

    assert view._speak_result_button.icon_name() == "speaker"


# ---------------------------------------------------------------------------
# Retranslation and responsiveness


def test_retranslate_ui_switches_titles_and_keeps_state(qapp, view, controller):
    view.set_source_text("Hello")

    controller.set_interface_language("uk")
    qapp.processEvents()
    view.retranslate_ui()

    assert view._source_card.title() == "Оригінал"
    assert view._result_card.title() == "Переклад"
    assert view._editor.placeholderText() == "Введіть або вставте текст…"
    assert view._editor.toPlainText() == "Hello"
    assert view._style_chips.options()[0][1] == "Авто"
    assert view._segmented.labels()[0] == "Перегляд"


def test_narrow_window_collapses_chips_into_menus(qapp, view, controller):
    controller.translated_text = "Hello"
    controller.translatedTextChanged.emit("Hello")
    qapp.processEvents()

    view.resize(960, 700)
    qapp.processEvents()
    assert view._menu_group.isVisibleTo(view)
    assert not view._chips_group.isVisibleTo(view)
    assert not view._result_counter.isVisibleTo(view)

    view.resize(1440, 760)
    qapp.processEvents()
    assert view._chips_group.isVisibleTo(view)
    assert not view._menu_group.isVisibleTo(view)
    assert view._result_counter.isVisibleTo(view)


def test_long_interface_language_needs_a_wider_bar(qapp, view, controller):
    # The breakpoint is a constant-width model of the translated labels, so
    # a long interface language moves it without consulting font metrics.
    controller.set_interface_language("uk")
    qapp.processEvents()

    view.resize(1440, 760)
    qapp.processEvents()
    assert view._menu_group.isVisibleTo(view)
    assert not view._chips_group.isVisibleTo(view)

    controller.set_interface_language("en")
    qapp.processEvents()
    view.resize(1440, 760)
    qapp.processEvents()
    assert view._chips_group.isVisibleTo(view)

    view.resize(1100, 760)
    qapp.processEvents()
    assert view._menu_group.isVisibleTo(view)
    assert not view._chips_group.isVisibleTo(view)


# ---------------------------------------------------------------------------
# Centred language controls (2.0.3)


def test_language_cluster_is_centred_at_1180(qapp, view, controller):
    view.resize(1180, 760)
    qapp.processEvents()

    group = view._language_group
    centre = group.mapTo(view, QPoint(group.width() // 2, 0)).x()
    assert abs(centre - view.width() / 2) <= 2


def test_long_language_name_does_not_widen_the_cluster(qapp, view, controller):
    controller.set_interface_language("en")
    qapp.processEvents()
    width = view._language_group.width()
    assert view._source_combo.width() == 164
    assert view._target_combo.width() == 164

    view._source_combo._select("zh-Hant", True)
    qapp.processEvents()

    assert view._source_combo.display_text() == "Traditional Chinese"
    assert view._source_combo.toolTip() == "Traditional Chinese"
    assert view._language_group.width() == width


def test_compact_style_tone_appears_below_the_threshold(qapp, view, controller):
    view.resize(1180, 760)
    qapp.processEvents()
    assert view._menu_group.isVisibleTo(view)
    assert not view._chips_group.isVisibleTo(view)

    view.resize(1440, 760)
    qapp.processEvents()
    assert view._chips_group.isVisibleTo(view)
    assert not view._menu_group.isVisibleTo(view)


def test_long_unbroken_text_keeps_the_panes_equal(qapp, view, controller):
    text = "https://example.com/" + "a" * 1200
    view.set_source_text(text)
    controller.translated_text = text
    controller.translatedTextChanged.emit(text)
    qapp.processEvents()

    assert view._source_card.width() == view._result_card.width()
    assert view._source_card.width() >= 380


# ---------------------------------------------------------------------------
# Source Markdown preview


def test_source_preview_toggle_and_focus_source(qapp, view, controller):
    source = "# Heading\n\nSome **bold** text."
    view.set_source_text(source)
    qapp.processEvents()

    assert view._source_stack.currentWidget() is view._editor
    assert view._preview_button.icon_name() == "eye"
    assert view._preview_button.toolTip() == t("Show rendered Markdown")

    view._preview_button.click()
    qapp.processEvents()

    assert view._source_previewing
    assert view._source_stack.currentWidget() is view._source_preview
    assert view._source_preview.mode() == "preview"
    assert view._source_preview.markdown() == source
    assert view._editor.isReadOnly()
    assert view._preview_button.icon_name() == "code"
    assert view._preview_button.toolTip() == t("Show Markdown source")
    assert "Heading" in view._source_preview.plain_text()
    assert str(len(source)) in view._source_counter.text()

    controller.set_source_text("# Replaced")
    qapp.processEvents()
    assert view._source_preview.markdown() == "# Replaced"

    view.focus_source()
    qapp.processEvents()
    assert view._source_stack.currentWidget() is view._editor
    assert not view._editor.isReadOnly()
    assert view._editor.hasFocus()
    assert view._preview_button.toolTip() == t("Show rendered Markdown")


def test_source_actions_keep_working_in_preview(
    qapp, view, controller, monkeypatch
):
    view.set_source_text("Hello")
    view._preview_button.click()
    qapp.processEvents()
    assert view._source_stack.currentWidget() is view._source_preview

    calls: list[bool] = []
    monkeypatch.setattr(controller, "copy_source", lambda: calls.append(True))
    view._copy_source_button.click()
    qapp.processEvents()
    assert calls == [True]

    view._clear_button.click()
    qapp.processEvents()
    assert controller.source_text == ""
    assert not view._source_previewing
    assert view._source_stack.currentWidget() is view._editor
    assert view._editor.toPlainText() == ""


def test_rich_paste_switches_to_preview(qapp, view):
    mime = QMimeData()
    mime.setHtml("<h2>Title</h2><p>Hello <b>world</b></p>")
    mime.setText("Title\nHello world")

    view._editor.insertFromMimeData(mime)
    qapp.processEvents()

    assert view._source_previewing
    assert view._source_stack.currentWidget() is view._source_preview
    assert "Title" in view._source_preview.markdown()
    assert "**world**" in view._source_preview.markdown()
