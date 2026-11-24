"""History tab: filtering, actions, empty state and clear confirmation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QLabel, QMessageBox

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language
from deepl_ofm.services.history import HistoryEntry, HistoryStore
from deepl_ofm.ui.history_view import HistoryView, format_duration, format_relative_date
from deepl_ofm.ui.theme import Theme


class MemorySecrets:
    """In-memory stand-in for :class:`~deepl_ofm.services.secrets.SecretStore`."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def read(self, account: str) -> str:
        return self.values.get(account, "")

    def write(self, account: str, value: str) -> None:
        if value:
            self.values[account] = value
        else:
            self.values.pop(account, None)

    def delete(self, account: str) -> None:
        self.values.pop(account, None)

    def backend_name(self) -> str:
        return "plain"


@pytest.fixture(autouse=True)
def reset_language():
    set_language(AppLanguage.EN)
    yield
    set_language(AppLanguage.EN)


@pytest.fixture(scope="module", autouse=True)
def themed(qapp):
    Theme.apply(qapp, dark=False)
    yield
    Theme.set_dark(None)


@pytest.fixture
def controller(qapp, tmp_path: Path):
    settings = AppSettings(tmp_path / "settings.json", secrets=MemorySecrets())
    history = HistoryStore(tmp_path / "history.json")
    controller = AppController(settings=settings, history=history)
    yield controller
    controller.deleteLater()


def _seed(controller: AppController) -> list[HistoryEntry]:
    entries = [
        HistoryEntry(
            source_text="Hello world, this is a test",
            translated_text="Привіт, світе, це тест",
            source_code="en",
            target_code="uk",
            engine="Ollama · hy-mt2:7b",
            duration_ms=1240,
        ),
        HistoryEntry(
            source_text="Goodbye for now",
            translated_text="До побачення",
            source_code="en",
            target_code="uk",
            engine="Groq · gpt-oss-120b",
            duration_ms=480,
        ),
        HistoryEntry(
            source_text="The quick brown fox",
            translated_text="Швидка руда лисиця",
            source_code="en",
            target_code="uk",
            engine="Ollama · hy-mt2:7b",
            duration_ms=0,
        ),
    ]
    for entry in entries:
        controller.history.add(entry)
    controller.historyChanged.emit()
    return controller.history.entries


def test_filter_hides_rows_without_rebuilding(qapp, controller: AppController) -> None:
    _seed(controller)
    entries = {entry.source_text.split()[0]: entry for entry in controller.history.entries}
    view = HistoryView(controller)
    view.resize(900, 640)
    view.show()
    qapp.processEvents()

    assert len(view.rows) == 3
    assert len(view.visible_rows()) == 3
    original_rows = list(view.rows)
    original_ids = [row.entry.id for row in original_rows]

    view.search.setText("ПРИВІТ")
    qapp.processEvents()
    assert [row.entry.id for row in view.rows] == original_ids  # no rebuild
    assert len(view.visible_rows()) == 1
    assert view.visible_rows()[0].entry.id == entries["Hello"].id

    view.search.setText("goodbye")
    qapp.processEvents()
    assert [row.entry.id for row in view.visible_rows()] == [entries["Goodbye"].id]

    view.search.setText("nothing-matches-this")
    qapp.processEvents()
    assert view.visible_rows() == []
    assert view.stack.currentWidget() is view.empty_state
    assert any(
        "Nothing found" in label.text() for label in view.empty_state.findChildren(QLabel)
    )

    view.search.clear()
    qapp.processEvents()
    assert len(view.visible_rows()) == 3
    assert view.stack.currentWidget() is view.scroll


def test_empty_store_shows_the_automatic_save_message(
    qapp, controller: AppController
) -> None:
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    assert view.rows == []
    assert view.stack.currentWidget() is view.empty_state
    texts = " ".join(label.text() for label in view.findChildren(QLabel))
    assert "History is empty" in texts
    assert "Translations will be saved here automatically." in texts
    assert not view.clear_button.isEnabled()


def test_clear_asks_for_confirmation_and_empties_the_store(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(controller)
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    calls: list[tuple[object, ...]] = []

    def confirm(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        calls.append(args)
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr(QMessageBox, "question", confirm)
    view.clear_button.click()
    qapp.processEvents()

    assert calls, "the destructive action must ask first"
    assert controller.history.entries == []
    assert view.rows == []
    assert view.stack.currentWidget() is view.empty_state
    assert not view.clear_button.isEnabled()


def test_clear_can_be_cancelled(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(controller)
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )
    view.clear_button.click()
    qapp.processEvents()

    assert len(controller.history.entries) == 3
    assert len(view.rows) == 3


def test_row_actions_copy_restore_and_delete(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(controller)
    entries = controller.history.entries
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    restored: list[str] = []
    monkeypatch.setattr(controller, "load_history_entry", restored.append)

    row = view.rows[0]
    row.copy_button.click()
    qapp.processEvents()
    assert qapp.clipboard().text() == entries[0].translated_text

    row.restore_button.click()
    qapp.processEvents()
    assert restored == [entries[0].id]

    row.delete_button.click()
    qapp.processEvents()
    assert len(controller.history.entries) == 2
    assert entries[0].id not in [item.id for item in controller.history.entries]


def test_refreshes_on_history_changed(qapp, controller: AppController) -> None:
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()
    assert view.rows == []

    controller.history.add(
        HistoryEntry(
            source_text="New translation",
            translated_text="Новий переклад",
            source_code="en",
            target_code="uk",
        )
    )
    controller.historyChanged.emit()
    qapp.processEvents()
    assert len(view.rows) == 1


def test_date_and_duration_formatting() -> None:
    now = datetime.now().astimezone()
    assert format_relative_date(now.isoformat(timespec="seconds")).startswith("today ")
    yesterday = (now - timedelta(days=1)).isoformat(timespec="seconds")
    assert format_relative_date(yesterday) == "yesterday"
    assert format_duration(840) == "840 ms"
    assert format_duration(1240) == "1.2 s"
    assert format_duration(0) == ""


def test_count_badge_shows_visible_over_total_while_searching(
    qapp, controller: AppController
) -> None:
    _seed(controller)
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    assert view.count_label.text() == "3"

    view.search.setText("goodbye")
    qapp.processEvents()
    assert view.count_label.text() == "1/3"

    view.search.setText("en")
    qapp.processEvents()
    assert view.count_label.text() == "3/3"

    view.search.clear()
    qapp.processEvents()
    assert view.count_label.text() == "3"


def test_restore_keeps_the_entry_duration_on_the_controller(
    qapp, controller: AppController
) -> None:
    _seed(controller)
    entry = next(item for item in controller.history.entries if item.duration_ms == 1240)
    view = HistoryView(controller)
    view.show()
    qapp.processEvents()

    row = next(item for item in view.rows if item.entry.id == entry.id)
    row.restore_button.click()
    qapp.processEvents()

    assert controller.source_text == entry.source_text
    assert controller.last_duration_ms == 1240

    view.refresh()
    qapp.processEvents()
    assert controller.last_duration_ms == 1240
