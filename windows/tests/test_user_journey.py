"""User journey: type → translate → copy → history → language switch.

Runs against a real local HTTP server and the real ``MainWindow``, so it checks
that the views, the controller and the network layer agree with each other.
"""

from __future__ import annotations

import time

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QLabel

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.main_window import MainWindow
from deepl_ofm.ui.markdown_view import MarkdownView

from fake_http import FakeProvider


def _pump(predicate, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(0.01)
    return predicate()


def test_translation_journey(qapp, tmp_path):
    with FakeProvider() as provider:
        settings = AppSettings(path=tmp_path / "settings.json")
        settings.base_url = provider.base_url
        settings.model = "hy-mt2:7b"
        settings.auto_translate = False
        settings.last_source_code = "de"
        settings.last_target_code = "en"
        controller = AppController(
            settings=settings, history=HistoryStore(path=tmp_path / "history.json")
        )
        window = MainWindow(controller)
        window.resize(1180, 780)
        window.show()
        qapp.processEvents()

        translate_view = window.pages["translate"]
        translate_view.set_source_text("Erste Zeile.\nZweite Zeile.")
        controller.translate(force=True)

        assert _pump(lambda: bool(controller.translated_text)), "translation never arrived"
        assert "Antwort" in controller.translated_text

        views = translate_view.findChildren(MarkdownView)
        assert views, "the panes have no MarkdownView"
        assert _pump(lambda: any("Antwort" in view.markdown() for view in views))

        controller.copy_translation()
        assert "Antwort" in QGuiApplication.clipboard().text()

        # History tab reflects the finished translation.
        window.select_tab("history")
        qapp.processEvents()
        assert _pump(lambda: any(
            "Erste Zeile" in (label.text() or "")
            for label in window.pages["history"].findChildren(QLabel)
        ), timeout=3), "history row was not rendered"

        # Interface language switch reaches the chrome and every tab.
        controller.set_interface_language(AppLanguage.UK)
        qapp.processEvents()
        assert window.tab_buttons["translate"].text() == "Перекласти"
        assert window.tab_buttons["history"].text() == "Історія"
        assert window.file_menu.title() == "Файл"

        # Back to English and close without touching the tray.
        controller.set_interface_language(AppLanguage.EN)
        qapp.processEvents()
        window.tray = None
        window.close()
        controller.shutdown(timeout_ms=1000)
