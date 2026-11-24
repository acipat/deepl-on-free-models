"""Main window shell: connection capsule, More-actions menu and tab wiring."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.providers import Provider
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language, t
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.main_window import MainWindow


@pytest.fixture(autouse=True)
def reset_language():
    set_language(AppLanguage.EN)
    yield
    set_language(AppLanguage.EN)


@pytest.fixture
def controller(qapp, tmp_path: Path):
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.auto_translate = False
    settings.model = "hy-mt2:7b"
    value = AppController(
        settings=settings,
        history=HistoryStore(path=tmp_path / "history.json"),
    )
    yield value
    value.deleteLater()


@pytest.fixture
def window(qapp, controller: AppController):
    widget = MainWindow(controller)
    widget.resize(1180, 800)
    widget.show()
    qapp.processEvents()
    yield widget
    widget.tray = None
    widget.close()
    widget.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# Connection capsule


def test_connection_capsule_reflects_provider_and_model(
    qapp, window: MainWindow, controller: AppController
) -> None:
    capsule = window.connection_capsule

    assert controller.settings.provider.title in capsule.text()
    assert "hy-mt2:7b" in capsule.text()
    assert capsule.toolTip() == t("Connection status")

    controller.settings.provider = Provider.GROQ
    controller.settings.model = "gpt-oss-120b"
    controller.settingsChanged.emit()
    qapp.processEvents()

    assert "Groq" in capsule.text()
    assert "gpt-oss-120b" in capsule.text()


def test_connection_capsule_tracks_backend_status(
    qapp, window: MainWindow, controller: AppController
) -> None:
    controller.backend_status = "connected"
    controller.backendStatusChanged.emit("connected")
    qapp.processEvents()
    assert window.connection_capsule._status == "connected"

    controller.backend_status = "failed"
    controller.backendStatusChanged.emit("failed")
    qapp.processEvents()
    assert window.connection_capsule._status == "failed"


def test_connection_capsule_opens_settings(
    qapp, window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(window, "open_settings", lambda: calls.append(True))

    QTest.mouseClick(window.connection_capsule, Qt.MouseButton.LeftButton)
    qapp.processEvents()

    assert calls == [True]


# ---------------------------------------------------------------------------
# More-actions menu


def test_more_actions_menu_contains_the_expected_items(
    qapp, window: MainWindow
) -> None:
    menu = window.more_menu
    assert window.more_button.menu() is menu
    assert window.more_button.toolTip() == t("More actions")

    actions = menu.actions()
    assert [action.isSeparator() for action in actions] == [
        False,
        False,
        True,
        False,
        True,
        False,
        False,
    ]
    labels = [action.text() for action in actions if not action.isSeparator()]
    assert labels[0].startswith(t("Translate clipboard"))
    assert labels[1].startswith(t("Translate selection"))
    assert labels[2] == t("Check connection")
    assert labels[3] == t("History")
    assert labels[4] == t("Settings")
    assert not any("Update" in label for label in labels)

    assert window.action_more_clipboard is actions[0]
    assert window.action_more_selection is actions[1]
    assert window.action_more_check is actions[3]
    assert window.action_more_history is actions[5]
    assert window.action_more_settings is actions[6]


def test_more_actions_call_the_controller(
    qapp,
    window: MainWindow,
    controller: AppController,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        controller, "translate_clipboard", lambda: calls.append("clipboard")
    )
    monkeypatch.setattr(
        controller, "translate_selection", lambda: calls.append("selection")
    )
    monkeypatch.setattr(
        controller, "check_connection", lambda: calls.append("check")
    )
    monkeypatch.setattr(window, "open_settings", lambda: calls.append("settings"))

    window.action_more_clipboard.trigger()
    window.action_more_selection.trigger()
    window.action_more_check.trigger()
    window.action_more_history.trigger()
    window.action_more_settings.trigger()
    qapp.processEvents()

    assert calls == ["clipboard", "selection", "check", "settings"]
    assert controller.tab == "history"


def test_more_actions_menu_follows_the_interface_language(
    qapp, window: MainWindow, controller: AppController
) -> None:
    controller.set_interface_language("uk")
    qapp.processEvents()

    assert window.action_more_clipboard.text().startswith("Перекласти буфер обміну")
    assert window.action_more_check.text() == "Перевірити з'єднання"
    assert window.action_more_history.text() == "Історія"
    assert window.action_more_settings.text() == "Налаштування"
    assert window.more_button.toolTip() == "Інші дії"
