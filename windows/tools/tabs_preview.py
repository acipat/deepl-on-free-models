"""Render the Files and Write tabs offscreen for the documentation.

Run from ``windows/``:

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/tabs_preview.py

The script uses the real ``AppController`` with throw-away settings/history and
the real views at 1180x760, then writes ``docs/files-light.png``,
``docs/files-dark.png`` and ``docs/write-light.png``.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QWidget

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.files_view import FilesView
from deepl_ofm.ui.theme import Theme
from deepl_ofm.ui.write_view import WriteView

WIDTH = 1180
HEIGHT = 760

WRITE_SOURCE = (
    "The app is very good. It help me translate text fast and the formatting "
    "stays. I think it is a useful tool for every day work."
)

WRITE_RESULT = (
    "The app works very well. It helps me translate text quickly while "
    "preserving the original formatting, and I think it is a useful tool "
    "for everyday work.\n\n"
    "- **Fast** translations with the original formatting intact\n"
    "- A calm workspace that stays out of the way\n"
    "- One shortcut for the clipboard, one for the whole document\n"
)


def _controller(directory: Path) -> AppController:
    settings = AppSettings(path=directory / "settings.json")
    settings.interface_language = AppLanguage.EN
    settings.auto_translate = False
    return AppController(
        settings=settings,
        history=HistoryStore(path=directory / "history.json"),
    )


def _render(app: QApplication, widget: QWidget, destination: Path) -> None:
    widget.resize(WIDTH, HEIGHT)
    widget.show()
    if isinstance(widget, WriteView):
        widget.editor.setFocus()
    app.processEvents()
    app.processEvents()
    destination.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(destination), "PNG")
    widget.hide()
    widget.deleteLater()
    app.processEvents()


def _files_idle(controller: AppController) -> FilesView:
    controller.set_target_language("uk")
    return FilesView(controller)


def _files_done(controller: AppController) -> FilesView:
    controller.set_target_language("uk")
    source = Path.home() / "Documents" / "quarterly-report.pdf"
    output = source.with_name("quarterly-report_uk.pdf")
    controller.file_job = {
        "path": str(source),
        "name": source.name,
        "kind": "pdf",
        "state": "done",
        "completed": 42,
        "total": 42,
        "percent": 100,
        "output": str(output),
        "message": None,
        "result_name": output.name,
        "warnings": 2,
    }
    return FilesView(controller)


def _write_view(controller: AppController) -> WriteView:
    controller.set_target_language("en")
    controller.write_in_progress = False
    controller.write_output = WRITE_RESULT
    controller.write_error = None
    controller.write_warning_count = 0
    view = WriteView(controller)
    view.editor.setPlainText(WRITE_SOURCE)
    view._sync_from_controller()
    view.editor.moveCursor(QTextCursor.MoveOperation.End)
    return view


def main() -> int:
    app = QApplication.instance() or QApplication([])
    docs = ROOT / "docs"

    with tempfile.TemporaryDirectory(prefix="deepl-ofm-preview-") as temporary:
        root = Path(temporary)
        light_dir = root / "light"
        dark_dir = root / "dark"
        light_dir.mkdir()
        dark_dir.mkdir()

        Theme.apply(app, dark=False)
        light_controller = _controller(light_dir)
        _render(app, _files_idle(light_controller), docs / "files-light.png")
        _render(app, _write_view(light_controller), docs / "write-light.png")

        Theme.apply(app, dark=True)
        dark_controller = _controller(dark_dir)
        _render(app, _files_done(dark_controller), docs / "files-dark.png")

    for name in ("files-light.png", "files-dark.png", "write-light.png"):
        print(f"wrote {docs / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
