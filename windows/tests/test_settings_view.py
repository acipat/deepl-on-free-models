"""Settings dialog: loading, provider defaults, Save/Cancel and language."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QDialog

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.providers import Provider
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language, t, tf
from deepl_ofm.services import startup
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.services.startup import StartupError, StartupStatus
from deepl_ofm.ui.settings_view import SettingsView
from deepl_ofm.ui.theme import Theme


class MemorySecrets:
    """In-memory stand-in for the credential vault."""

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
def secrets() -> MemorySecrets:
    return MemorySecrets()


@pytest.fixture
def settings(tmp_path: Path, secrets: MemorySecrets) -> AppSettings:
    values = AppSettings(tmp_path / "settings.json", secrets=secrets)
    values.temperature = 0.7
    values.top_p = 0.6
    values.top_k = 20
    values.repetition_penalty = 1.05
    values.context_window = 8192
    values.save()
    return values


@pytest.fixture
def controller(settings: AppSettings, tmp_path: Path) -> AppController:
    history = HistoryStore(tmp_path / "history.json")
    controller = AppController(settings=settings, history=history)
    yield controller
    controller.deleteLater()


def _show(controller: AppController) -> SettingsView:
    view = SettingsView(controller)
    view.show()
    QApplication.processEvents()
    return view


def test_dialog_opens_with_all_tabs(qapp, controller: AppController) -> None:
    view = _show(controller)
    assert view.isVisible()
    assert view.size().width() == 760
    assert view.size().height() == 640
    assert view.tabs.count() == 5
    assert view.provider_combo.count() == len(list(Provider))
    assert view.language_combo.count() == len(list(AppLanguage))
    assert view.models_list is not None
    assert view.catalog_button.text()
    view.close()


def test_exec_runs_modally(qapp, controller: AppController) -> None:
    view = SettingsView(controller)
    QTimer.singleShot(0, view.reject)
    assert view.exec() == QDialog.DialogCode.Rejected


def test_provider_change_fills_the_default_base_url(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    index = view.provider_combo.findData(Provider.GROQ.value)
    assert index >= 0
    view.provider_combo.setCurrentIndex(index)
    qapp.processEvents()
    assert view.base_url_edit.text() == Provider.GROQ.base_url
    assert view.provider_detail.text() == Provider.GROQ.detail()
    view.close()


def test_save_persists_temperature_to_disk(
    qapp, controller: AppController, tmp_path: Path, secrets: MemorySecrets
) -> None:
    view = _show(controller)
    view.temperature_slider.setValue(25)  # 0.05 * 25 = 1.25
    assert view.temperature_field.value() == pytest.approx(1.25)

    view.save_button.click()
    qapp.processEvents()

    assert view.result() == QDialog.DialogCode.Accepted
    assert controller.settings.temperature == pytest.approx(1.25)
    reloaded = AppSettings(tmp_path / "settings.json", secrets=secrets)
    assert reloaded.temperature == pytest.approx(1.25)


def test_cancel_restores_the_previous_values(
    qapp, controller: AppController, tmp_path: Path, secrets: MemorySecrets
) -> None:
    view = _show(controller)
    assert controller.settings.temperature == pytest.approx(0.7)
    view.temperature_slider.setValue(5)  # 0.25
    view.base_url_edit.setText("http://example.invalid:1234")

    view.cancel_button.click()
    qapp.processEvents()

    assert view.result() == QDialog.DialogCode.Rejected
    assert controller.settings.temperature == pytest.approx(0.7)
    assert controller.settings.base_url == Provider.OLLAMA.base_url
    reloaded = AppSettings(tmp_path / "settings.json", secrets=secrets)
    assert reloaded.temperature == pytest.approx(0.7)
    assert reloaded.base_url == Provider.OLLAMA.base_url


def test_interface_language_change_reaches_the_controller(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    index = view.language_combo.findData(AppLanguage.DE.value)
    assert index >= 0
    view.language_combo.setCurrentIndex(index)

    view.save_button.click()
    qapp.processEvents()

    assert controller.settings.interface_language is AppLanguage.DE
    assert view.result() == QDialog.DialogCode.Accepted


def test_model_list_follows_controller_signals(qapp, controller: AppController) -> None:
    view = _show(controller)
    controller.provider_models = ["hy-mt2:7b", "qwen3:8b"]
    controller.modelsChanged.emit(list(controller.provider_models))
    qapp.processEvents()
    assert view.models_list.count() == 2

    view.model_filter.setText("qwen")
    qapp.processEvents()
    assert view.models_list.count() == 1
    assert view.models_list.item(0).text() == "qwen3:8b"

    controller.modelsLoadingChanged.emit(True)
    qapp.processEvents()
    assert not view.connect_button.isEnabled()

    controller.modelsErrorChanged.emit("boom")
    qapp.processEvents()
    assert "boom" in view.models_error_label.text()
    view.close()


def test_invalid_hotkey_shows_a_muted_hint(qapp, controller: AppController) -> None:
    view = _show(controller)
    view.hotkey_edit.setKeySequence(QKeySequence("T"))
    qapp.processEvents()
    assert view.hotkey_row.hint()
    assert "Ctrl" in view.hotkey_row.hint() or "Alt" in view.hotkey_row.hint()

    view.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+T"))
    qapp.processEvents()
    assert view.hotkey_row.hint() == ""


def test_fallback_fields_follow_the_provider(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    view.fallback_toggle.check_box().setChecked(True)
    qapp.processEvents()
    assert view.fallback_body.isVisible()

    index = view.fallback_provider_combo.findData(Provider.OPEN_ROUTER.value)
    view.fallback_provider_combo.setCurrentIndex(index)
    qapp.processEvents()
    assert view.fallback_base_edit.text() == Provider.OPEN_ROUTER.base_url
    assert view.fallback_key_field.key_link.isVisible()
    view.close()


def test_connect_without_a_key_shows_the_required_hint(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _show(controller)
    index = view.provider_combo.findData(Provider.GROQ.value)
    view.provider_combo.setCurrentIndex(index)
    view.api_key_field.set_value("")

    calls: list[bool] = []
    monkeypatch.setattr(
        controller, "connect_and_load_models", lambda: calls.append(True)
    )

    view.connect_button.click()
    qapp.processEvents()

    assert calls == []
    assert view.connect_status.text() == tf(
        "Enter the API key for %@ in Settings first.", Provider.GROQ.title
    )
    assert view.connect_status._role == "danger"
    assert view.connect_button.isEnabled()
    view.close()


def test_connect_with_a_key_probes_the_provider(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _show(controller)
    index = view.provider_combo.findData(Provider.GROQ.value)
    view.provider_combo.setCurrentIndex(index)
    view.api_key_field.set_value("gsk-test")

    calls: list[bool] = []
    monkeypatch.setattr(
        controller, "connect_and_load_models", lambda: calls.append(True)
    )

    view.connect_button.click()
    qapp.processEvents()

    assert calls == [True]
    assert view.connect_status.text() != tf(
        "Enter the API key for %@ in Settings first.", Provider.GROQ.title
    )
    view.close()


def test_missing_model_shows_the_install_command(
    qapp, controller: AppController
) -> None:
    controller.settings.provider = Provider.OLLAMA
    controller.settings.model = "hy-mt2:7b"
    view = _show(controller)
    assert not view.install_row.isVisible()

    controller.provider_models = ["qwen3:8b"]
    controller.modelsChanged.emit(list(controller.provider_models))
    controller.modelsErrorChanged.emit(
        tf(
            "Server responds, but model “%@” is missing. Available: %@.",
            "hy-mt2:7b",
            "qwen3:8b",
        )
    )
    qapp.processEvents()

    assert view.install_row.isVisible()
    assert view.install_command_label.text().startswith("ollama pull")
    assert view.install_copy_button.text() == t("Copy install command")

    view.install_copy_button.click()
    qapp.processEvents()
    assert qapp.clipboard().text() == view.install_command_label.text()

    controller.modelsErrorChanged.emit("")
    qapp.processEvents()
    assert not view.install_row.isVisible()
    view.close()


def test_install_command_is_hidden_for_an_unknown_model(
    qapp, controller: AppController
) -> None:
    controller.settings.provider = Provider.OLLAMA
    controller.settings.model = "private-model:latest"
    view = _show(controller)

    controller.modelsErrorChanged.emit(
        tf(
            "Server responds, but model “%@” is missing. Available: %@.",
            "private-model:latest",
            "qwen3:8b",
        )
    )
    qapp.processEvents()

    assert not view.install_row.isVisible()
    view.close()


def test_models_section_is_tall_and_refreshable(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = _show(controller)
    assert view.models_list.minimumHeight() >= 210

    calls: list[bool] = []
    monkeypatch.setattr(
        controller, "connect_and_load_models", lambda: calls.append(True)
    )

    view.models_refresh.click()
    qapp.processEvents()
    assert calls == [True]

    controller.modelsLoadingChanged.emit(True)
    qapp.processEvents()
    assert not view.models_refresh.isEnabled()
    assert not view.connect_button.isEnabled()

    controller.modelsLoadingChanged.emit(False)
    qapp.processEvents()
    assert view.models_refresh.isEnabled()
    view.close()


def test_hotkey_caption_prompts_and_then_shows_the_combo(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    view.activateWindow()
    view.hotkey_edit.setFocus(Qt.FocusReason.OtherFocusReason)
    qapp.processEvents()

    assert view.hotkey_edit.hasFocus()
    assert view.hotkey_caption.text() == t("Press a combination…")

    view.hotkey_edit.setKeySequence(QKeySequence("T"))
    qapp.processEvents()
    assert view.hotkey_row.hint()
    assert view.hotkey_caption.text() == t("Press a combination…")

    view.hotkey_edit.clearFocus()
    qapp.processEvents()
    assert view.hotkey_caption.text() == "T"
    assert view.hotkey_row.hint()

    view.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+T"))
    qapp.processEvents()
    assert view.hotkey_row.hint() == ""
    assert view.hotkey_caption.text() == "Ctrl+Alt+T"

    view.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Shift+X"))
    qapp.processEvents()
    assert view.hotkey_caption.text() == "Ctrl+Shift+X"
    view.hotkey_reset.click()
    qapp.processEvents()
    assert view.hotkey_caption.text() == "Ctrl+Alt+T"
    view.close()


# ---------------------------------------------------------------------------
# Open at login (SMAppService parity)


def test_open_at_login_toggle_reflects_the_os_status(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        startup, "status", lambda: StartupStatus.ENABLED
    )
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    assert view.login_controls.isVisible()
    assert view.login_toggle.is_checked()
    assert view.login_approval.isHidden()
    assert view.login_error.isHidden()
    view.close()


def test_open_at_login_hint_appears_only_for_requires_approval(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"status": StartupStatus.REQUIRES_APPROVAL}
    monkeypatch.setattr(startup, "status", lambda: state["status"])
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    assert not view.login_toggle.is_checked()
    assert view.login_approval.isVisible()
    assert view.login_hint.text() == t(
        "Allow DeepL-oFM to open at login in System Settings."
    )
    assert view.login_settings_button.text() == t("Open System Settings")

    state["status"] = StartupStatus.DISABLED
    view._refresh_open_at_login()
    qapp.processEvents()
    assert view.login_controls.isVisible()
    assert view.login_approval.isHidden()
    view.close()


def test_open_at_login_unsupported_hides_the_whole_row(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(startup, "status", lambda: StartupStatus.UNSUPPORTED)
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    assert view.login_controls.isHidden()
    assert not view.login_controls.isVisible()
    view.close()


def test_open_at_login_toggle_applies_the_change(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"enabled": False}
    applied: list[bool] = []
    monkeypatch.setattr(
        startup,
        "status",
        lambda: StartupStatus.ENABLED if state["enabled"] else StartupStatus.DISABLED,
    )

    def fake_set_enabled(enabled: bool) -> None:
        applied.append(enabled)
        state["enabled"] = enabled

    monkeypatch.setattr(startup, "set_enabled", fake_set_enabled)
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    assert not view.login_toggle.is_checked()
    view.login_toggle.check_box().setChecked(True)
    qapp.processEvents()

    assert applied == [True]
    assert view.login_toggle.is_checked()
    assert view.login_error.isHidden()
    view.close()


def test_open_at_login_failure_shows_the_localised_error(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(startup, "status", lambda: StartupStatus.DISABLED)

    def fail(_enabled: bool) -> None:
        raise StartupError("Could not change Open at login. Access is denied.")

    monkeypatch.setattr(startup, "set_enabled", fail)
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    view.login_toggle.check_box().setChecked(True)
    qapp.processEvents()

    assert not view.login_toggle.is_checked()
    assert view.login_error.isVisible()
    assert view.login_error.text() == (
        "Could not change Open at login. Access is denied."
    )
    view.close()


def test_open_at_login_requires_approval_opens_system_settings(
    qapp, controller: AppController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(startup, "status", lambda: StartupStatus.REQUIRES_APPROVAL)
    opened: list[bool] = []
    applied: list[bool] = []
    monkeypatch.setattr(
        startup, "open_settings", lambda: opened.append(True) or True
    )
    monkeypatch.setattr(startup, "set_enabled", applied.append)
    view = _show(controller)
    view.tabs.setCurrentIndex(2)
    qapp.processEvents()

    view.login_toggle.check_box().setChecked(True)
    qapp.processEvents()
    assert opened == [True]
    assert applied == []
    assert not view.login_toggle.is_checked()

    view.login_settings_button.click()
    qapp.processEvents()
    assert opened == [True, True]
    view.close()
