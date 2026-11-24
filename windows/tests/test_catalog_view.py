"""Model catalogue: one card per entry, filtering, copy and apply."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from deepl_ofm.controller import AppController
from deepl_ofm.core.catalog import ModelCatalog
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.providers import Provider
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.i18n import set_language
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.catalog_view import CatalogView
from deepl_ofm.ui.theme import Theme


class MemorySecrets:
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
    controller = AppController(
        settings=settings, history=HistoryStore(tmp_path / "history.json")
    )
    yield controller
    controller.deleteLater()


def _show(controller: AppController) -> CatalogView:
    view = CatalogView(controller)
    view.show()
    QApplication.processEvents()
    return view


def test_one_card_per_catalog_entry(qapp, controller: AppController) -> None:
    view = _show(controller)
    assert len(view.cards) == len(ModelCatalog.ENTRIES)
    assert [card.entry.model_id for card in view.cards] == [
        entry.model_id for entry in ModelCatalog.ENTRIES
    ]
    assert all(card.use_button.text() for card in view.cards)
    view.close()


def test_provider_and_text_filters_hide_cards(qapp, controller: AppController) -> None:
    view = _show(controller)
    index = view.provider_filter.findData(Provider.OPEN_ROUTER.value)
    assert index >= 0
    view.provider_filter.setCurrentIndex(index)
    qapp.processEvents()

    visible = view.visible_cards()
    assert visible
    assert all(card.entry.provider is Provider.OPEN_ROUTER for card in visible)
    assert len(visible) < len(view.cards)

    view.search.setText("gemma")
    qapp.processEvents()
    narrowed = view.visible_cards()
    assert narrowed
    assert all(
        "gemma" in (card.entry.name + card.entry.model_id).casefold() for card in narrowed
    )

    view.search.setText("nothing at all")
    qapp.processEvents()
    assert view.visible_cards() == []
    assert view.stack.currentWidget() is view.empty_state
    view.close()


def test_copy_install_command_uses_the_clipboard(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    card = next(card for card in view.cards if card.entry.install_command)
    assert card.command_box is not None

    card.command_box.copy_button.click()
    qapp.processEvents()

    assert qapp.clipboard().text() == card.entry.install_command
    view.close()


def test_use_model_applies_the_entry_and_closes(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    applied: list[object] = []
    controller.apply_catalog_entry = applied.append  # type: ignore[method-assign]

    card = next(
        card for card in view.cards if card.entry.provider is Provider.OPEN_ROUTER
    )
    card.use_button.click()
    qapp.processEvents()

    assert applied == [card.entry]
    assert view.result() == QDialog.DialogCode.Accepted
    assert not view.isVisible()


def test_free_only_toggle_filters_cards(qapp, controller: AppController) -> None:
    view = _show(controller)
    view.free_toggle.check_box().click()
    qapp.processEvents()

    visible = view.visible_cards()
    assert visible
    assert all(card.entry.is_free for card in visible)
    assert len(visible) == sum(entry.is_free for entry in ModelCatalog.ENTRIES)
    assert len(visible) < len(view.cards)

    view.free_toggle.check_box().click()
    qapp.processEvents()
    assert len(view.visible_cards()) == len(view.cards)
    view.close()


def test_badges_render_in_swift_order_after_the_provider_pill(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    card = view.cards[0]
    entry = card.entry

    assert [pill.text() for pill in card.badge_pills] == list(entry.badges)
    assert all(pill.variant() == "muted" for pill in card.badge_pills)
    flow_items = [
        card._title_flow.itemAt(index).widget()
        for index in range(card._title_flow.count())
    ]
    assert flow_items[0] is card.name_label
    assert flow_items[1] is card.provider_label
    assert flow_items[2:] == card.badge_pills
    # The old ad-hoc size/languages/free pills were replaced by badges.
    assert not hasattr(card, "size_label")
    assert not hasattr(card, "languages_label")
    view.close()


def test_sections_group_recommended_and_hide_when_empty(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    assert view.recommended_section.header.text() == "RECOMMENDED"
    assert view.models_section.header.text() == "MODELS"
    assert view.recommended_section.isVisible()
    assert view.models_section.isVisible()

    index = view.provider_filter.findData(Provider.OLLAMA.value)
    view.provider_filter.setCurrentIndex(index)
    view.search.setText("hy-mt2:7b")
    qapp.processEvents()
    assert [card.entry.model_id for card in view.visible_cards()] == ["hy-mt2:7b"]
    assert view.recommended_section.isVisible()
    assert not view.models_section.isVisible()

    view.search.setText("translategemma")
    qapp.processEvents()
    assert view.visible_cards()
    assert not view.recommended_section.isVisible()
    assert view.models_section.isVisible()

    view.search.setText("nothing at all")
    qapp.processEvents()
    assert not view.recommended_section.isVisible()
    assert not view.models_section.isVisible()
    assert view.stack.currentWidget() is view.empty_state
    view.close()


def test_fetch_from_server_shows_busy_state_and_rows(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    calls: list[str] = []

    def fake_fetch() -> None:
        calls.append("fetch")
        controller.models_loading = True
        controller.modelsLoadingChanged.emit(True)

    controller.connect_and_load_models = fake_fetch  # type: ignore[method-assign]
    view.fetch_button.click()
    qapp.processEvents()

    assert calls == ["fetch"]
    assert not view.fetch_button.isEnabled()
    assert view.busy_label.isVisible()
    assert view.busy_label.text() == "Connecting…"
    assert view.server_rows == []

    controller.models_loading = False
    controller.provider_models = ["hy-mt2:7b", "new-model:1b"]
    controller.modelsLoadingChanged.emit(False)
    controller.modelsChanged.emit(controller.provider_models)
    qapp.processEvents()

    assert view.fetch_button.isEnabled()
    assert not view.busy_label.isVisible()
    assert [row.model for row in view.server_rows] == ["new-model:1b"]
    assert view.server_section.isVisible()
    assert view.server_section.header.text() == "FOUND ON THE SERVER"
    assert view.server_rows[0].choose_button.text() == "Choose"
    view.close()


def test_empty_server_response_reports_an_error(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    controller.models_loading = False
    controller.provider_models = []
    controller.modelsChanged.emit([])
    controller.modelsErrorChanged.emit("The server returned no models.")
    qapp.processEvents()

    assert view.server_rows == []
    assert not view.server_section.isVisible()
    assert view.error_label.isVisible()
    assert view.error_label.text() == "The server returned no models."
    assert view.fetch_button.isEnabled()
    view.close()


def test_choose_server_model_keeps_provider_and_saves(
    qapp, controller: AppController
) -> None:
    view = _show(controller)
    provider_before = controller.settings.provider
    saved: list[str] = []

    def fake_save() -> None:
        saved.append(controller.settings.model)

    controller.save_settings = fake_save  # type: ignore[method-assign]

    controller.provider_models = ["hy-mt2:7b", "brand-new:9b"]
    controller.modelsChanged.emit(controller.provider_models)
    qapp.processEvents()

    assert [row.model for row in view.server_rows] == ["brand-new:9b"]
    view.server_rows[0].choose_button.click()
    qapp.processEvents()

    assert controller.settings.model == "brand-new:9b"
    assert controller.settings.provider is provider_before
    assert saved == ["brand-new:9b"]
    assert view.result() == QDialog.DialogCode.Accepted
    assert not view.isVisible()


def test_retranslate_refreshes_labels(qapp, controller: AppController) -> None:
    view = _show(controller)
    view.retranslate_ui()
    qapp.processEvents()
    assert view.title_label.text() == "Model catalog"
    assert view.search.placeholderText()
    assert view.free_toggle.label() == "Free only"
    assert view.fetch_button.text() == "Fetch from server"
    assert view.recommended_section.header.text() == "RECOMMENDED"
    assert view.models_section.header.text() == "MODELS"
    assert len(view.cards) == len(ModelCatalog.ENTRIES)

    set_language(AppLanguage.UK)
    view.retranslate_ui()
    qapp.processEvents()
    assert view.free_toggle.label() == "Лише безкоштовні"
    assert view.fetch_button.text() == "Отримати з сервера"
    assert view.recommended_section.header.text() == "РЕКОМЕНДОВАНІ"
    assert view.models_section.header.text() == "МОДЕЛІ"
    assert [pill.text() for pill in view.cards[0].badge_pills] == [
        "33 мови",
        "≈4,6 ГБ",
        "рекомендовано",
    ]
    view.close()
