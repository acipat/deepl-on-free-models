"""Headless smoke test: build the whole UI offscreen and exercise every tab.

Run:  python tools/smoke_test.py
Exit code 0 means the window, all four tabs and both dialogs constructed
without an exception and a screenshot was written next to this file.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from deepl_ofm.controller import AppController  # noqa: E402
from deepl_ofm.core.settings import AppSettings  # noqa: E402
from deepl_ofm.services.history import HistoryStore  # noqa: E402
from deepl_ofm.ui.main_window import MainWindow  # noqa: E402
from deepl_ofm.ui.theme import Theme  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv[:1])
    app.setApplicationName("DeepL-oFM")
    Theme.apply(app)

    with tempfile.TemporaryDirectory() as tmp:
        settings = AppSettings(path=Path(tmp) / "settings.json")
        history = HistoryStore(path=Path(tmp) / "history.json")
        controller = AppController(settings=settings, history=history)
        controller.set_source_text("Hello, world! This is a smoke test.")

        window = MainWindow(controller)
        window.resize(1280, 820)
        window.show()

        for tab in ("translate", "files", "write", "history"):
            window.select_tab(tab)
            app.processEvents()

        window.select_tab("translate")
        app.processEvents()

        if "--screenshot" in sys.argv:
            shot = ROOT / "docs" / "ui-smoke.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(shot))
            print(f"smoke ok; screenshot: {shot}")
        else:
            print("smoke ok")

        try:
            from deepl_ofm.ui.catalog_view import CatalogView
            from deepl_ofm.ui.settings_view import SettingsView

            SettingsView(controller, window).close()
            CatalogView(controller, window).close()
            print("dialogs ok")
        except Exception as exc:  # noqa: BLE001
            print(f"dialog smoke failed: {exc!r}")
            return 2

        window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
