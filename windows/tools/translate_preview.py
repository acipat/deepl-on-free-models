"""Render the Translate tab offscreen for visual review.

Run from ``windows/``::

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/translate_preview.py \
        --state result --out docs/translate-light.png

The script composes the real :class:`~deepl_ofm.ui.translate_view.TranslateView`
with a real :class:`~deepl_ofm.controller.AppController` backed by temporary
settings and history, so the artwork and the application share one code path.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import get_language
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.ui.theme import Theme
from deepl_ofm.ui.translate_view import TranslateView

WIDTH = 1180
HEIGHT = 760

SOURCE_TEXT = """DeepL-oFM — це нативний перекладач для Windows на локальних і хмарних моделях. Він зберігає абзаци, списки й Markdown і показує готовий текст лише після перевірки всіх рядків.

• Працює офлайн із Hy-MT2
• Не потребує облікового запису
• Зберігає форматування без змін

Результат надходить у міру перевірки кожного сегмента, тому напівперекладене речення ніколи не з'являється на екрані.
"""

RESULT_MARKDOWN = """DeepL-oFM is a native translator for Windows that runs on local and cloud models. It preserves **paragraphs, lists and Markdown**, and shows the final text only after every line has been checked.

- Works offline with Hy-MT2
- No account required
- Keeps your formatting intact

The result streams in as each segment is verified, so a half-translated sentence never appears on screen.
"""


class PreviewWindow(QWidget):
    """A bare 1180x760 canvas holding the real view."""

    def __init__(self, view: TranslateView) -> None:
        super().__init__()
        self.setWindowTitle("DeepL-oFM — Translate")
        self.setFixedSize(WIDTH, HEIGHT)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(view)


def build_controller(directory: Path, state: str) -> AppController:
    settings = AppSettings(path=directory / "settings.json")
    settings.auto_translate = False
    settings.model = "hy-mt2:7b"
    settings.last_source_code = "auto"
    settings.last_target_code = "en"
    controller = AppController(
        settings=settings,
        history=HistoryStore(path=directory / "history.json"),
    )
    controller.set_source_text(SOURCE_TEXT)
    controller.detected_language = get_language("uk")
    controller.set_style("natural")
    controller.set_tone("standard")

    if state == "result":
        controller.translated_text = RESULT_MARKDOWN
        controller.tokens_per_second = 42.1
        controller.last_duration_ms = 1840
        controller.warning_count = 0
    else:
        controller.is_translating = True
        controller.completed = 13
        controller.total = 21
    return controller


def render(state: str, dark: bool, destination: Path) -> None:
    app = QApplication.instance() or QApplication([])
    Theme.apply(app, dark=dark)

    with tempfile.TemporaryDirectory(prefix="deepl-ofm-preview-") as temporary:
        controller = build_controller(Path(temporary), state)
        view = TranslateView(controller)
        window = PreviewWindow(view)
        window.show()
        app.processEvents()
        app.processEvents()

        destination.parent.mkdir(parents=True, exist_ok=True)
        saved = window.grab().save(str(destination), "PNG")
        if not saved:
            raise SystemExit(f"could not write {destination}")
        window.close()
        view.deleteLater()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=("result", "progress"), default="result")
    parser.add_argument("--dark", action="store_true")
    parser.add_argument("--out", metavar="PATH", default=None)
    parser.add_argument(
        "--all",
        action="store_true",
        help="render the four canonical previews (light/dark x result/progress)",
    )
    args = parser.parse_args(argv)

    if args.all:
        docs = ROOT / "docs"
        jobs = (
            ("result", False, docs / "translate-light.png"),
            ("progress", True, docs / "translate-dark.png"),
            ("result", True, docs / "translate-result-dark.png"),
            ("progress", False, docs / "translate-progress-light.png"),
        )
        for state, dark, destination in jobs:
            render(state, dark, destination)
            print(f"wrote {destination}")
        return 0

    if args.out:
        destination = Path(args.out)
        if not destination.is_absolute():
            destination = ROOT / destination
    else:
        suffix = "" if args.state == "result" else "-progress"
        theme = "dark" if args.dark else "light"
        destination = ROOT / "docs" / f"translate{suffix}-{theme}.png"

    render(args.state, args.dark, destination)
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
