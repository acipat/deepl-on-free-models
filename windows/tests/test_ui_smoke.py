"""UI integration guard: every tab and dialog constructs and re-translates.

The test runs headless (``QT_QPA_PLATFORM=offscreen``, provided by
``tests/conftest.py``) and walks all nine interface languages, because a missing
translation key or a stale widget reference only shows up when the UI is rebuilt.
"""

from __future__ import annotations

import pytest

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore


def _controller(tmp_path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.auto_translate = False
    return AppController(settings=settings, history=HistoryStore(path=tmp_path / "history.json"))


def test_every_view_survives_a_language_sweep(qapp, tmp_path):
    controller = _controller(tmp_path)
    controller.set_source_text("Hello, world! This is an interface smoke test.")

    from deepl_ofm.ui.translate_view import TranslateView

    views = [TranslateView(controller)]
    for module, name in (
        ("deepl_ofm.ui.files_view", "FilesView"),
        ("deepl_ofm.ui.write_view", "WriteView"),
        ("deepl_ofm.ui.history_view", "HistoryView"),
    ):
        mod = pytest.importorskip(module)
        views.append(getattr(mod, name)(controller))

    for language in AppLanguage:
        controller.set_interface_language(language)
        for view in views:
            view.retranslate_ui()
        qapp.processEvents()

    for view in views:
        view.close()


def test_dialogs_construct(qapp, tmp_path):
    controller = _controller(tmp_path)

    settings_module = pytest.importorskip("deepl_ofm.ui.settings_view")
    catalog_module = pytest.importorskip("deepl_ofm.ui.catalog_view")

    dialog = settings_module.SettingsView(controller)
    dialog.show()
    qapp.processEvents()
    dialog.retranslate_ui()
    dialog.close()

    catalog = catalog_module.CatalogView(controller)
    catalog.show()
    qapp.processEvents()
    catalog.retranslate_ui()
    catalog.close()


def test_main_window_switches_tabs(qapp, tmp_path):
    from deepl_ofm.ui.main_window import MainWindow

    controller = _controller(tmp_path)
    window = MainWindow(controller)
    window.resize(1100, 760)
    window.show()

    for tab in ("translate", "files", "write", "history"):
        window.select_tab(tab)
        qapp.processEvents()

    window.retranslate_ui()
    window.close()
