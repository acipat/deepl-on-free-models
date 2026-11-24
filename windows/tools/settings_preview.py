"""Render documentation screenshots for the settings, catalogue and history UI.

Run from ``windows/``:

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/settings_preview.py

The script builds the real dialogs/views with a temporary settings and history
store, then writes four PNGs into ``docs/``:

    settings-model.png  settings-generation.png  catalog.png  history-light.png
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from deepl_ofm.controller import AppController  # noqa: E402
from deepl_ofm.core.languages import AppLanguage  # noqa: E402
from deepl_ofm.core.providers import Provider  # noqa: E402
from deepl_ofm.core.settings import AppSettings  # noqa: E402
from deepl_ofm.i18n import t  # noqa: E402
from deepl_ofm.services.history import HistoryEntry, HistoryStore  # noqa: E402
from deepl_ofm.ui.catalog_view import CatalogView  # noqa: E402
from deepl_ofm.ui.main_window import MainWindow  # noqa: E402
from deepl_ofm.ui.settings_view import SettingsView  # noqa: E402
from deepl_ofm.ui.theme import Theme  # noqa: E402


class _MemorySecrets:
    """Keep the preview away from the real credential store."""

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


HISTORY_SAMPLES = (
    (
        "The release notes are ready. Please review the migration section before "
        "the announcement tomorrow.",
        "Нотатки до випуску готові. Будь ласка, перегляньте розділ про міграцію "
        "перед завтрашнім оголошенням.",
        "Ollama · hy-mt2:7b",
        1840,
    ),
    (
        "Local models keep your text on this computer and work without an account.",
        "Локальні моделі зберігають ваш текст на цьому комп'ютері та працюють без "
        "облікового запису.",
        "Ollama · hy-mt2:7b",
        960,
    ),
    (
        "Markdown formatting, lists and headings must survive the translation.",
        "Форматування Markdown, списки й заголовки мають пережити переклад.",
        "Groq · openai/gpt-oss-120b",
        620,
    ),
    (
        "A short sentence is enough to check the layout of a history row.",
        "Короткого речення достатньо, щоб перевірити вигляд рядка історії.",
        "Ollama · hy-mt2:7b",
        430,
    ),
)


def _make_controller(workdir: Path) -> AppController:
    secrets = _MemorySecrets()
    settings = AppSettings(workdir / "settings.json", secrets=secrets)
    settings.provider = Provider.GROQ
    settings.base_url = Provider.GROQ.base_url
    settings.model = "openai/gpt-oss-120b"
    settings.api_key = "sk-preview-demo-key-0123456789"
    settings.fallback_enabled = False
    settings.temperature = 0.7
    settings.top_p = 0.6
    settings.top_k = 20
    settings.repetition_penalty = 1.05
    settings.context_window = 8192
    settings.auto_translate = True
    settings.debounce = 0.45
    settings.keep_history = True
    settings.warm_up_on_launch = False
    settings.interface_language = AppLanguage.EN
    settings.save()

    history = HistoryStore(workdir / "history.json")
    now = datetime.now().astimezone()
    for index, (source, translated, engine, duration) in enumerate(
        reversed(HISTORY_SAMPLES)
    ):
        days = len(HISTORY_SAMPLES) - index - 1
        history.add(
            HistoryEntry(
                date=(now - timedelta(days=days)).isoformat(timespec="seconds"),
                source_text=source,
                translated_text=translated,
                source_code="en",
                target_code="uk",
                style="natural",
                tone="standard",
                engine=engine,
                duration_ms=duration,
            )
        )

    controller = AppController(settings=settings, history=history)
    controller.provider_models = [
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.3-70b-versatile",
        "qwen/qwen3.8-27b",
    ]
    controller.backend_status = "connected"
    controller.probe_message = t("Connection works.")
    return controller


def _grab(widget, destination: Path) -> Path:
    app = QApplication.instance()
    widget.show()
    for _ in range(4):
        app.processEvents()
    destination.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(destination), "PNG")
    return destination


def main() -> int:
    app = QApplication.instance() or QApplication([])
    Theme.apply(app, dark=True)

    with tempfile.TemporaryDirectory(prefix="deepl-ofm-preview-") as temporary:
        controller = _make_controller(Path(temporary))

        settings_view = SettingsView(controller)
        settings_view.tabs.setCurrentIndex(0)
        written = [
            _grab(settings_view, ROOT / "docs" / "settings-model.png"),
        ]
        settings_view.tabs.setCurrentIndex(1)
        written.append(_grab(settings_view, ROOT / "docs" / "settings-generation.png"))

        catalog = CatalogView(controller)
        written.append(_grab(catalog, ROOT / "docs" / "catalog.png"))
        catalog.provider_filter.clearFocus()
        catalog.setFocus()
        for _ in range(2):
            app.processEvents()
        catalog.grab().save(str(ROOT / "docs" / "catalog.png"), "PNG")
        catalog.close()

        settings_view.hide()

        Theme.apply(app, dark=False)
        window = MainWindow(controller)
        window.resize(1180, 800)
        window.select_tab("history")
        written.append(_grab(window, ROOT / "docs" / "history-light.png"))
        window.close()

    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
