"""Generate the documentation screenshots from the real application window.

Run:  QT_QPA_PLATFORM=offscreen .venv/python tools/make_screenshots.py
Writes 2x PNGs into ``docs/``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTabWidget  # noqa: E402

from deepl_ofm.controller import AppController  # noqa: E402
from deepl_ofm.core.settings import AppSettings  # noqa: E402
from deepl_ofm.services.history import HistoryEntry, HistoryStore  # noqa: E402
from deepl_ofm.ui.main_window import MainWindow  # noqa: E402
from deepl_ofm.ui.settings_view import SettingsView  # noqa: E402
from deepl_ofm.ui.theme import Theme  # noqa: E402

DOCS = ROOT / "docs"
SCALE = 2

SOURCE = (
    "DeepL-oFM is a native translator for Windows that runs on local and cloud "
    "models. It keeps paragraphs, lists and Markdown intact."
)
TRANSLATION = (
    "DeepL-oFM — це нативний перекладач для Windows, який працює на локальних і "
    "хмарних моделях. Він зберігає абзаци, списки й Markdown без змін."
)


def _grab(widget, name: str) -> Path:
    widget.repaint()
    QApplication.processEvents()
    pixmap = QPixmap(widget.size() * SCALE)
    pixmap.setDevicePixelRatio(float(SCALE))
    pixmap.fill(QColor(Qt.transparent))
    widget.render(pixmap)
    target = DOCS / name
    pixmap.save(str(target))
    print(f"wrote {target.relative_to(ROOT)}")
    return target


def _controller(tmp: Path) -> AppController:
    settings = AppSettings(path=tmp / "settings.json")
    settings.auto_translate = False
    settings.last_source_code = "en"
    settings.last_target_code = "uk"
    controller = AppController(settings=settings, history=HistoryStore(path=tmp / "history.json"))
    controller.history.add(
        HistoryEntry(
            source_text="The quarterly report is ready for review.",
            translated_text="Квартальний звіт готовий до перегляду.",
            source_code="en",
            target_code="uk",
            style="auto",
            tone="standard",
            engine="Ollama · hy-mt2:7b",
            duration_ms=2400,
        )
    )
    controller.history.add(
        HistoryEntry(
            source_text="Customers asked for offline models and a smaller download.",
            translated_text="Клієнти просили офлайн-моделі та менший обсяг завантаження.",
            source_code="en",
            target_code="uk",
            style="natural",
            tone="standard",
            engine="Ollama · hy-mt2:7b",
            duration_ms=1870,
        )
    )
    controller.set_source_text(SOURCE)
    controller.translated_text = TRANSLATION
    controller.tokens_per_second = 41.2
    controller.last_duration_ms = 1840
    controller.backend_status = "connected"
    controller.provider_models = ["hy-mt2:7b", "hy-mt2:1.8b", "translategemma:4b", "qwen3:8b"]
    controller.models_loading = False
    return controller


def _window(controller: AppController, dark: bool) -> MainWindow:
    Theme.apply(QApplication.instance(), dark=dark)
    window = MainWindow(controller)
    window.resize(1180, 800)
    window.show()
    QApplication.processEvents()
    window.tray = None
    return window


def main() -> int:
    DOCS.mkdir(parents=True, exist_ok=True)
    app = QApplication(sys.argv[:1])
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        controller = _controller(tmp)

        window = _window(controller, dark=False)
        window.select_tab("translate")
        window.pages["translate"].focus_source()
        editor = window.pages["translate"].findChild(QPlainTextEdit)
        if editor is not None:
            editor.setFocus()
        app.processEvents()
        _grab(window, "screenshot-translate.png")
        window.select_tab("history")
        app.processEvents()
        _grab(window, "screenshot-history.png")
        window.close()

        (tmp / "dark").mkdir(parents=True, exist_ok=True)
        dark_controller = _controller(tmp / "dark")
        dark_window = _window(dark_controller, dark=True)
        dark_window.select_tab("translate")
        app.processEvents()
        _grab(dark_window, "screenshot-translate-dark.png")
        dark_window.close()

        Theme.apply(app, dark=False)
        controller.provider_models = ["hy-mt2:7b", "hy-mt2:1.8b", "translategemma:4b", "qwen3:8b"]
        controller.modelsLoadingChanged.emit(False)
        controller.modelsChanged.emit(controller.provider_models)
        settings = SettingsView(controller)
        settings.resize(780, 660)
        settings.show()
        app.processEvents()
        _grab(settings, "screenshot-settings.png")
        tabs = settings.findChild(QTabWidget)
        if tabs is not None:
            tabs.setCurrentIndex(1)
            app.processEvents()
            _grab(settings, "screenshot-settings-generation.png")
        settings.close()

        from deepl_ofm.ui.catalog_view import CatalogView

        catalog = CatalogView(controller)
        catalog.resize(820, 700)
        catalog.show()
        app.processEvents()
        _grab(catalog, "screenshot-catalog.png")
        catalog.close()

        Theme.apply(app, dark=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
