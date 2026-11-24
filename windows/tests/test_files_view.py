"""Files tab: drop zone, progress, result and error states, save and retry."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language, t
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.files_view import FilesView
from deepl_ofm.ui.theme import Theme


@pytest.fixture
def controller(qapp, tmp_path):
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
    widget = FilesView(controller)
    widget.resize(1180, 760)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.deleteLater()
    qapp.processEvents()


def _job(tmp_path: Path, **overrides) -> dict:
    source = tmp_path / "report.pdf"
    payload = {
        "path": str(source),
        "name": source.name,
        "kind": "pdf",
        "state": "translating",
        "completed": 0,
        "total": 0,
        "percent": 0,
        "output": None,
        "message": None,
        "result_name": None,
        "warnings": 0,
    }
    payload.update(overrides)
    return payload


def _done(tmp_path: Path, **overrides) -> dict:
    output = tmp_path / "report_uk.pdf"
    payload = _job(
        tmp_path,
        state="done",
        completed=14,
        total=14,
        percent=100,
        output=str(output),
        result_name=output.name,
    )
    payload.update(overrides)
    return payload


def test_idle_state_shows_drop_zone(qapp, view, controller):
    assert view.drop_zone.isVisible()
    assert not view.file_card.isVisible()
    assert not view.progress_card.isVisible()
    assert not view.result_card.isVisible()
    assert view.drop_zone.title.text() == t("Drop a file here or choose one")
    assert view.drop_zone.subtitle.text() == t(
        "Supported formats: TXT, Markdown, PDF and DOCX."
    )
    assert view.drop_zone.choose_button.text() == t("Choose a file…")
    assert view.translate_button.text() == t("Translate")
    assert view.language_combo.include_auto() is False
    assert view.language_combo.code() == controller.target_language.code


def test_reading_state_shows_indeterminate_progress(qapp, view, tmp_path):
    view._on_job_changed(_job(tmp_path, state="reading"))
    qapp.processEvents()

    assert view.progress_card.isVisible()
    assert view.file_card.isVisible()
    assert view.drop_zone.isHidden()
    assert not view.result_card.isVisible()
    assert view.percent_label.text() == "0%"
    assert view.progress_bar.is_indeterminate()
    assert view.cancel_button.isVisible()
    assert view.progress_status.text() == t("Preparing file…")


def test_translating_state_updates_percent_and_count(qapp, view, tmp_path):
    view._on_job_changed(
        _job(tmp_path, completed=6, total=14, percent=43)
    )
    qapp.processEvents()

    assert view.percent_label.text() == "43%"
    assert view.progress_bar.value() == 43
    assert "6 of 14" in view.count_label.text()
    assert view.progress_status.text() == t("Translating…")
    assert view.file_name_label.text() == "report.pdf"
    assert view.file_kind_label.text() == "PDF"
    assert view.cancel_button.isVisible()


def test_done_state_enables_save_only_with_output(qapp, view, tmp_path):
    view._on_job_changed(_done(tmp_path, output=None, result_name=None))
    qapp.processEvents()

    assert view.result_card.isVisible()
    assert not view.progress_card.isVisible()
    assert view.complete_label.text() == t("Translation complete")
    assert not view.save_button.isEnabled()

    output = tmp_path / "report_uk.pdf"
    view._on_job_changed(_done(tmp_path, output=str(output), result_name=output.name))
    qapp.processEvents()

    assert view.save_button.isEnabled()
    assert view.output_name_label.text() == "report_uk.pdf"
    assert view.show_folder_button.isVisible()
    assert view.translate_another_button.isVisible()
    assert not view.cancel_button.isVisible()


def test_failed_and_cancelled_show_message_and_retry(qapp, view, tmp_path):
    view._on_job_changed(
        _job(tmp_path, state="failed", message="The document is encrypted.")
    )
    qapp.processEvents()

    assert view.error_card.isVisible()
    assert not view.result_card.isVisible()
    assert view.message_label.text() == "The document is encrypted."
    assert view.retry_button.isVisible()
    assert view.retry_button.text() == t("Try again")

    view._on_job_changed(
        _job(tmp_path, state="cancelled", message="Cancelled")
    )
    qapp.processEvents()

    # Stop returns to the idle state instead of showing a failure card.
    assert not view.error_card.isVisible()
    assert view.translate_button.isEnabled()
    assert view.language_combo.isEnabled()


def test_pick_file_filters_and_starts_translation(qapp, view, controller, monkeypatch, tmp_path):
    source = tmp_path / "brief.docx"
    source.write_text("source", encoding="utf-8", newline="")
    calls: list[Path] = []
    filters: list[str] = []

    monkeypatch.setattr(
        controller,
        "start_file_translation",
        lambda path, code=None: calls.append((Path(path), code)),
    )

    def fake_open(parent, caption, directory, filter_text):
        filters.append(filter_text)
        return str(source), ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(fake_open))

    view.pick_file()

    assert calls and calls[0][0] == source
    assert len(filters) == 1
    for extension in (".txt", ".md", ".markdown", ".pdf", ".docx"):
        assert f"*{extension}" in filters[0]


def test_save_dialog_keeps_extension_and_default_name(
    qapp, view, controller, monkeypatch, tmp_path
):
    output = tmp_path / "report_uk.pdf"
    view._on_job_changed(_done(tmp_path, output=str(output)))
    qapp.processEvents()

    captured: dict[str, object] = {}

    def fake_save(parent, caption, directory, filter_text):
        captured["directory"] = directory
        captured["filter"] = filter_text
        return str(tmp_path / "exported"), ""

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake_save))
    saved: list[Path] = []
    monkeypatch.setattr(
        controller, "save_translated_file", lambda destination: saved.append(Path(destination))
    )

    view.save_button.click()

    assert saved == [tmp_path / "exported.pdf"]
    assert str(captured["directory"]).endswith("report_uk.pdf")
    assert "*.pdf" in str(captured["filter"])


def test_translate_another_returns_to_drop_zone(qapp, view, tmp_path):
    view._on_job_changed(_done(tmp_path))
    qapp.processEvents()
    assert view.result_card.isVisible()

    view.translate_another_button.click()
    qapp.processEvents()

    assert view.drop_zone.isVisible()
    assert not view.result_card.isVisible()
    assert not view.file_card.isVisible()


def test_retranslate_ui_changes_headings_and_keeps_state(qapp, view, controller, tmp_path):
    view._on_job_changed(_done(tmp_path))
    qapp.processEvents()
    assert view.save_button.isEnabled()

    set_language("uk")
    view.retranslate_ui()
    qapp.processEvents()

    assert view.heading.text() == t("Files")
    assert view.heading.text() != "Files"
    original = "Translate a document and save the result in its original format."
    assert view.subtitle.text() != original
    assert view.complete_label.text() == t("Translation complete")
    assert view.drop_zone.title.text() == t("Drop a file here or choose one")
    assert view.save_button.isEnabled()
    assert view.result_card.isVisible()


def test_drop_accepts_only_supported_extensions(qapp, view, tmp_path):
    supported = [".txt", ".md", ".markdown", ".pdf", ".docx"]
    for extension in supported:
        path = tmp_path / f"document{extension}"
        assert view._drop_path(QUrl.fromLocalFile(str(path))) == path

    rejected = view._drop_path(QUrl.fromLocalFile(str(tmp_path / "photo.png")))
    assert rejected is None
    assert view._drop_path(QUrl("https://example.com/report.pdf")) is None


def test_drop_event_starts_supported_file(qapp, view, controller, monkeypatch, tmp_path):
    source = tmp_path / "report.md"
    source.write_text("# Source", encoding="utf-8", newline="")
    calls: list[Path] = []
    monkeypatch.setattr(
        controller,
        "start_file_translation",
        lambda path, code=None: calls.append((Path(path), code)),
    )

    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    enter = QDragEnterEvent(
        QPointF(10.0, 10.0), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view, enter)
    assert enter.isAccepted()
    assert view.drop_zone._active

    drop = QDropEvent(
        QPointF(10.0, 10.0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view, drop)

    assert drop.isAccepted()
    assert calls and calls[0][0] == source
    assert not view.drop_zone._active


def test_unsupported_drop_reports_an_error(qapp, view, controller, monkeypatch, tmp_path):
    calls: list[Path] = []
    monkeypatch.setattr(
        controller,
        "start_file_translation",
        lambda path, code=None: calls.append((Path(path), code)),
    )
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "photo.png"))])
    enter = QDragEnterEvent(
        QPointF(10.0, 10.0), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view, enter)
    assert not enter.isAccepted()
    assert not view.drop_zone._active

    drop = QDropEvent(
        QPointF(10.0, 10.0), Qt.DropAction.CopyAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    view.dropEvent(drop)
    assert calls == []
    assert errors and "not supported" in errors[-1].lower()
