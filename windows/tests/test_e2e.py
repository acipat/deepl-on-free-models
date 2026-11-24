"""End-to-end test: real HTTP server, real streaming, real controller wiring.

No mocks of the network layer: :mod:`fake_http` speaks the Ollama NDJSON and
OpenAI SSE protocols so the whole path (chunker → prompt → stream → budget →
sanitizer → compose → controller state → history) runs over sockets.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication

from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import get_language
from deepl_ofm.core.prompts import TranslationStyle, TranslationTone
from deepl_ofm.core.providers import BackendConfig, BackendKind
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.services.translation import Translator

from fake_http import FakeProvider


@pytest.fixture()
def provider():
    with FakeProvider() as server:
        yield server


def _ollama_config(base: str) -> BackendConfig:
    return BackendConfig(
        kind=BackendKind.OLLAMA,
        base_url=base,
        model="hy-mt2:7b",
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
        context_window=8192,
    )


def _openai_config(base: str) -> BackendConfig:
    return BackendConfig(
        kind=BackendKind.OPENAI,
        base_url=base + "/v1",
        model="hy-mt2:7b",
        api_key="test-key",
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
        context_window=8192,
        requires_api_key=True,
    )


def test_ollama_stream_end_to_end(provider):
    translator = Translator()
    progress: list[tuple[int, int]] = []
    result = translator.translate(
        "Erste Zeile.\n\nZweite Zeile.",
        source=get_language("de"),
        target=get_language("en"),
        style=TranslationStyle.AUTO,
        tone=TranslationTone.STANDARD,
        config=_ollama_config(provider.base_url),
        on_progress=lambda done, total: progress.append((done, total)),
    )
    lines = result.text.split("\n")
    assert lines[0].startswith("Antwort")
    assert lines[1] == "", "blank line between paragraphs must be preserved"
    assert lines[2].startswith("Antwort")
    assert progress and progress[-1] == (2, 2)
    assert result.duration_ms is not None and result.duration_ms >= 0
    assert result.tokens_per_second == pytest.approx(400)

    body = provider.requests[0]["body"]
    assert body["stream"] is True
    assert body["options"]["num_ctx"] == 8192
    assert body["options"]["repeat_penalty"] == 1.05
    assert "Translate" in body["messages"][0]["content"]


def test_openai_stream_end_to_end(provider):
    translator = Translator()
    result = translator.translate(
        "Erste Zeile.",
        source=get_language("de"),
        target=get_language("en"),
        style=TranslationStyle.NATURAL,
        tone=TranslationTone.FORMAL,
        config=_openai_config(provider.base_url),
    )
    assert result.text.startswith("Antwort")
    request = provider.requests[0]
    assert request["path"].endswith("/v1/chat/completions")
    assert request["body"]["model"] == "hy-mt2:7b"


def test_list_models_both_protocols(provider):
    translator = Translator()
    assert translator.list_models(_ollama_config(provider.base_url)) == ["hy-mt2:7b", "qwen3:8b"]
    assert translator.list_models(_openai_config(provider.base_url)) == ["hy-mt2:7b", "gpt-oss-120b"]


def test_controller_translates_against_local_server(qapp, provider, tmp_path):
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.base_url = provider.base_url
    settings.model = "hy-mt2:7b"
    settings.auto_translate = False
    settings.last_source_code = "de"
    settings.last_target_code = "en"
    controller = AppController(settings=settings, history=HistoryStore(path=tmp_path / "history.json"))

    controller.set_source_text("Erste Zeile.\nZweite Zeile.")
    controller.translate(force=True)

    deadline = time.monotonic() + 8
    # Streamed partials now fill translated_text while the job is still
    # running, so completion (not non-empty text) is the end signal.
    while time.monotonic() < deadline and controller.is_translating:
        QApplication.processEvents()
        time.sleep(0.01)

    assert controller.translated_text.strip(), "controller produced no translation"
    assert "Antwort" in controller.translated_text
    assert controller.is_translating is False
    assert controller.tokens_per_second == pytest.approx(400)
    assert len(controller.history.entries) == 1
    assert controller.history.entries[0].target_code == "en"


def test_file_translation_end_to_end(qapp, provider, tmp_path):
    source = tmp_path / "brief.txt"
    source.write_text("Erste Zeile.\n\nZweite Zeile.\n", encoding="utf-8", newline="")

    settings = AppSettings(path=tmp_path / "settings.json")
    settings.base_url = provider.base_url
    settings.model = "hy-mt2:7b"
    settings.auto_translate = False
    settings.last_source_code = "de"
    settings.last_target_code = "en"
    controller = AppController(settings=settings, history=HistoryStore(path=tmp_path / "history.json"))

    controller.start_file_translation(source, "en")
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = (controller.file_job or {}).get("state")
        if state in {"done", "failed", "cancelled"}:
            break
        QApplication.processEvents()
        time.sleep(0.02)

    job = controller.file_job or {}
    assert job.get("state") == "done", job
    output = Path(job["output"])
    assert output.exists()
    assert output.name == "brief_en.txt"
    translated = output.read_text(encoding="utf-8")
    assert "Antwort" in translated
    assert "\n\n" in translated
