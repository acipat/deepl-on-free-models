"""Tests for :mod:`deepl_ofm.core.settings` (port of ``AppSettings.swift``)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from deepl_ofm.core.catalog import ModelCatalog
from deepl_ofm.core.keycombo import KeyCombo
from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.providers import BackendKind, Provider
from deepl_ofm.core.settings import AppSettings, TranslationStyle, TranslationTone


class FakeSecrets:
    """In-memory stand-in for ``deepl_ofm.services.secrets.SecretStore``."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.deleted: list[str] = []

    def read(self, account: str) -> str:
        return self.data.get(account, "")

    def write(self, account: str, value: str) -> None:
        self.data[account] = value

    def delete(self, account: str) -> None:
        self.deleted.append(account)
        self.data.pop(account, None)

    def backend_name(self) -> str:
        return "fake"


@pytest.fixture()
def settings_path(tmp_path: Path) -> Path:
    return tmp_path / "DeepL-oFM" / "settings.json"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8", newline="")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_defaults_match_the_swift_initialiser(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())

    assert settings.provider is Provider.OLLAMA
    assert settings.base_url == "http://127.0.0.1:11434"
    assert settings.model == "hy-mt2:7b"
    assert settings.api_key == ""
    assert settings.kind is BackendKind.OLLAMA

    assert settings.fallback_enabled is False
    assert settings.fallback_provider is Provider.OLLAMA
    assert settings.fallback_base_url == "http://127.0.0.1:11434"
    assert settings.fallback_model == ""
    assert settings.fallback_api_key == ""

    assert settings.temperature == 0.7
    assert settings.top_p == 0.6
    assert settings.top_k == 20
    assert settings.repetition_penalty == 1.05
    assert settings.context_window == 8192

    assert settings.auto_translate is True
    assert settings.debounce == 0.45
    assert settings.hot_key == KeyCombo.standard()
    assert settings.selection_hot_key == KeyCombo.selection()

    assert settings.show_in_menu_bar is True
    assert settings.show_in_dock is True
    assert settings.speech_voice_id == ""
    assert settings.keep_history is True
    assert settings.warm_up_on_launch is False
    assert settings.interface_language is AppLanguage.SYSTEM
    assert settings.result_view == "preview"

    assert settings.last_style.value == "auto"
    assert settings.last_tone.value == "standard"
    assert settings.last_target_code == "en"
    assert settings.last_source_code == "auto"


def test_missing_file_loads_defaults(settings_path: Path) -> None:
    assert not settings_path.exists()
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.provider is Provider.OLLAMA
    assert settings.model == "hy-mt2:7b"
    assert AppSettings(settings_path, FakeSecrets()).model == "hy-mt2:7b"


def test_corrupt_file_is_tolerated(settings_path: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text("{ this is not json", encoding="utf-8", newline="")
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.model == "hy-mt2:7b"
    assert settings.temperature == 0.7

    # A save repairs the file.
    settings.temperature = 0.3
    assert _read(settings_path)["temperature"] == 0.3


def test_json_array_is_tolerated(settings_path: Path) -> None:
    _write(settings_path, [1, 2, 3])
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.provider is Provider.OLLAMA


def test_bad_values_fall_back_to_defaults(settings_path: Path) -> None:
    _write(
        settings_path,
        {
            "provider": "nonsense",
            "base_url": "http://127.0.0.1:11434",
            "model": 42,
            "temperature": "hot",
            "top_p": None,
            "top_k": "many",
            "repetition_penalty": [1.0],
            "context_window": 1.5,
            "debounce": None,
            "hot_key": "Ctrl+Alt+T",
            "selection_hot_key": {"key": ""},
            "result_view": "bogus",
            "last_style": "nope",
            "last_tone": 3,
            "interface_language": 7,
            "keep_history": "yes",
            "last_target_code": "",
        },
    )
    settings = AppSettings(settings_path, FakeSecrets())

    assert settings.provider is Provider.OLLAMA
    assert settings.model == "hy-mt2:7b"
    assert settings.temperature == 0.7
    assert settings.top_p == 0.6
    assert settings.top_k == 20
    assert settings.repetition_penalty == 1.05
    assert settings.context_window == 8192
    assert settings.debounce == 0.45
    assert settings.hot_key == KeyCombo.standard()
    assert settings.selection_hot_key == KeyCombo.selection()
    assert settings.result_view == "preview"
    assert settings.last_style.value == "auto"
    assert settings.last_tone.value == "standard"
    assert settings.interface_language is AppLanguage.SYSTEM
    assert settings.keep_history is True
    assert settings.last_target_code == "en"


def test_unknown_keys_are_ignored(settings_path: Path) -> None:
    _write(settings_path, {"model": "hy-mt2:1.8b", "future_key": {"a": 1}})
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.model == "hy-mt2:1.8b"
    settings.top_k = 10
    data = _read(settings_path)
    assert "future_key" not in data
    assert data["model"] == "hy-mt2:1.8b"


def test_camel_case_aliases_are_accepted(settings_path: Path) -> None:
    _write(
        settings_path,
        {
            "baseURL": "http://127.0.0.1:1234/v1",
            "topP": 0.5,
            "hotKey": {"key": "k", "command": True},
            "lastTarget": "de",
            "interfaceLanguage": "uk",
        },
    )
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.base_url == "http://127.0.0.1:1234/v1"
    assert settings.top_p == 0.5
    assert settings.hot_key == KeyCombo("k", command=True)
    assert settings.last_target_code == "de"
    assert settings.interface_language is AppLanguage.UK


def test_legacy_backend_key_is_understood(settings_path: Path) -> None:
    _write(
        settings_path,
        {"backend": "openAI", "base_url": "https://openrouter.ai/api/v1"},
    )
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.provider is Provider.OPEN_ROUTER
    assert settings.kind is BackendKind.OPENAI
    assert settings.base_url == "https://openrouter.ai/api/v1"


def test_stored_provider_without_base_url_uses_its_default(settings_path: Path) -> None:
    _write(settings_path, {"provider": "groq", "model": "openai/gpt-oss-120b"})
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.provider is Provider.GROQ
    assert settings.base_url == Provider.GROQ.base_url
    assert settings.snapshot().base_url == "https://api.groq.com/openai/v1"


def test_non_string_provider_memory_is_ignored(settings_path: Path) -> None:
    _write(
        settings_path,
        {"provider": "ollama", "base_url": "http://127.0.0.1:11434", "model.x": None},
    )
    settings = AppSettings(settings_path, FakeSecrets())
    settings.apply_provider(Provider.GROQ)
    assert settings.base_url == Provider.GROQ.base_url


def test_save_and_reload_round_trip(settings_path: Path) -> None:
    secrets = FakeSecrets()
    settings = AppSettings(settings_path, secrets)

    settings.apply_provider(Provider.GROQ)
    settings.model = "openai/gpt-oss-120b"
    settings.api_key = "gsk-test-key"
    settings.temperature = 0.2
    settings.top_p = 0.9
    settings.top_k = 5
    settings.repetition_penalty = 1.2
    settings.context_window = 4096
    settings.auto_translate = False
    settings.debounce = 0.8
    settings.hot_key = KeyCombo("k", command=True, shift=True)
    settings.selection_hot_key = KeyCombo("j", option=True)
    settings.interface_language = AppLanguage.DE
    settings.result_view = "markdown"
    settings.last_style = "literal"  # type: ignore[assignment]
    settings.last_tone = TranslationTone.FORMAL
    settings.last_target_code = "uk"
    settings.last_source_code = "de"
    settings.keep_history = False
    settings.warm_up_on_launch = True
    settings.speech_voice_id = "voice-1"
    settings.show_in_menu_bar = False
    settings.save()

    raw = settings_path.read_text(encoding="utf-8")
    assert "gsk-test-key" not in raw
    data = _read(settings_path)
    assert "api_key" not in data
    assert data["base_url.ollama"] == "http://127.0.0.1:11434"
    assert data["model.ollama"] == "hy-mt2:7b"
    assert secrets.data["provider:groq"] == "gsk-test-key"

    reloaded = AppSettings(settings_path, secrets)
    assert reloaded.provider is Provider.GROQ
    assert reloaded.model == "openai/gpt-oss-120b"
    assert reloaded.api_key == "gsk-test-key"
    assert reloaded.temperature == 0.2
    assert reloaded.top_p == 0.9
    assert reloaded.top_k == 5
    assert reloaded.repetition_penalty == 1.2
    assert reloaded.context_window == 4096
    assert reloaded.auto_translate is False
    assert reloaded.debounce == 0.8
    assert reloaded.hot_key == KeyCombo("k", command=True, shift=True)
    assert reloaded.selection_hot_key == KeyCombo("j", option=True)
    assert reloaded.interface_language is AppLanguage.DE
    assert reloaded.result_view == "markdown"
    assert reloaded.last_style is TranslationStyle.LITERAL
    assert reloaded.last_tone is TranslationTone.FORMAL
    assert reloaded.last_target_code == "uk"
    assert reloaded.last_source_code == "de"
    assert reloaded.keep_history is False
    assert reloaded.warm_up_on_launch is True
    assert reloaded.speech_voice_id == "voice-1"
    assert reloaded.show_in_menu_bar is False
    assert reloaded.show_in_dock is True


def test_per_provider_memory(settings_path: Path) -> None:
    secrets = FakeSecrets()
    settings = AppSettings(settings_path, secrets)
    settings.base_url = "http://127.0.0.1:9999"
    settings.model = "custom-model"
    settings.api_key = "ollama-key"

    settings.apply_provider(Provider.GROQ)
    assert settings.provider is Provider.GROQ
    assert settings.base_url == Provider.GROQ.base_url
    assert settings.model == ""
    assert settings.api_key == ""
    settings.api_key = "groq-key"

    settings.apply_provider(Provider.OLLAMA)
    assert settings.provider is Provider.OLLAMA
    assert settings.base_url == "http://127.0.0.1:9999"
    assert settings.model == "custom-model"
    assert settings.api_key == "ollama-key"

    data = _read(settings_path)
    assert data["base_url.groq"] == Provider.GROQ.base_url
    assert data["model.groq"] == ""
    assert data["base_url.ollama"] == "http://127.0.0.1:9999"

    # Memory survives a restart.
    restarted = AppSettings(settings_path, secrets)
    assert restarted.base_url == "http://127.0.0.1:9999"
    restarted.apply_provider(Provider.GROQ)
    restarted.apply_provider(Provider.OLLAMA)
    assert restarted.base_url == "http://127.0.0.1:9999"
    assert restarted.model == "custom-model"


def test_apply_provider_with_model(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.apply_provider(Provider.OPEN_ROUTER, "tencent/hy-mt2-7b")
    assert settings.provider is Provider.OPEN_ROUTER
    assert settings.base_url == Provider.OPEN_ROUTER.base_url
    assert settings.model == "tencent/hy-mt2-7b"
    assert settings.kind is BackendKind.OPENAI


def test_api_key_never_reaches_the_json_file(settings_path: Path) -> None:
    secrets = FakeSecrets()
    settings = AppSettings(settings_path, secrets)
    settings.api_key = "super-secret"
    settings.save()
    assert "super-secret" not in settings_path.read_text(encoding="utf-8")
    assert secrets.data == {"provider:ollama": "super-secret"}


def test_clear_key(settings_path: Path) -> None:
    secrets = FakeSecrets()
    settings = AppSettings(settings_path, secrets)
    settings.api_key = "secret"
    settings.clear_key()
    assert settings.api_key == ""
    assert "provider:ollama" in secrets.deleted
    assert secrets.data.get("provider:ollama", "") == ""


def test_works_without_a_secret_store(settings_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Even if the real SecretStore cannot be constructed, settings stay usable.
    import deepl_ofm.core.settings as settings_module

    monkeypatch.setattr(settings_module.AppSettings, "_secret_store", lambda self: None)
    settings = AppSettings(settings_path, FakeSecrets())
    settings.api_key = "memory-only"
    assert settings.api_key == "memory-only"
    settings.save()
    assert settings.model == "hy-mt2:7b"


def test_snapshot(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.base_url = "http://127.0.0.1:11434///"
    settings.model = "  hy-mt2:7b  "
    settings.temperature = 0.4
    settings.top_p = 0.5
    settings.top_k = 12
    settings.repetition_penalty = 1.1
    settings.context_window = 2048
    config = settings.snapshot()

    assert config.kind is BackendKind.OLLAMA
    assert config.base_url == "http://127.0.0.1:11434"
    assert config.model == "hy-mt2:7b"
    assert config.api_key == ""
    assert config.temperature == 0.4
    assert config.top_p == 0.5
    assert config.top_k == 12
    assert config.repetition_penalty == 1.1
    assert config.context_window == 2048
    assert config.requires_api_key is False

    settings.apply_provider(Provider.GROQ, "openai/gpt-oss-120b")
    groq = settings.snapshot()
    assert groq.kind is BackendKind.OPENAI
    assert groq.requires_api_key is True
    assert groq.base_url == "https://api.groq.com/openai/v1"


def test_fallback_config_requires_enabled_and_model(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.fallback_config() is None

    settings.fallback_model = "qwen3:8b"
    assert settings.fallback_config() is None

    settings.fallback_enabled = True
    config = settings.fallback_config()
    assert config is not None
    assert config.kind is BackendKind.OLLAMA
    assert config.base_url == "http://127.0.0.1:11434"
    assert config.model == "qwen3:8b"
    assert config.api_key == ""
    assert config.temperature == settings.temperature
    assert config.requires_api_key is False

    settings.fallback_provider = Provider.OPEN_ROUTER
    settings.fallback_model = " tencent/hy-mt2-7b "
    config = settings.fallback_config()
    assert config is not None
    assert config.kind is BackendKind.OPENAI
    assert config.base_url == "https://openrouter.ai/api/v1"
    assert config.model == "tencent/hy-mt2-7b"
    assert config.requires_api_key is True


def test_fallback_probe_config_ignores_the_enabled_flag(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    probe = settings.fallback_probe_config()
    assert probe.kind is BackendKind.OLLAMA
    assert probe.base_url == "http://127.0.0.1:11434"
    assert probe.model == ""

    settings.fallback_enabled = False
    settings.fallback_model = "aya-expanse:8b"
    assert settings.fallback_probe_config().model == "aya-expanse:8b"


def test_fallback_api_key_round_trip(settings_path: Path) -> None:
    secrets = FakeSecrets()
    settings = AppSettings(settings_path, secrets)
    settings.fallback_enabled = True
    settings.fallback_provider = Provider.GROQ
    settings.fallback_model = "openai/gpt-oss-20b"
    settings.fallback_api_key = "groq-fallback"
    assert secrets.data["provider:groq"] == "groq-fallback"

    reloaded = AppSettings(settings_path, secrets)
    config = reloaded.fallback_config()
    assert config is not None
    assert config.api_key == "groq-fallback"


def test_entry_point_rule(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.show_in_menu_bar = False
    assert settings.show_in_menu_bar is False
    assert settings.show_in_dock is True

    settings.show_in_dock = False
    assert settings.show_in_dock is False
    assert settings.show_in_menu_bar is True

    settings.show_in_menu_bar = False
    assert settings.show_in_menu_bar is False
    assert settings.show_in_dock is True


def test_entry_point_rule_applies_to_loaded_files(settings_path: Path) -> None:
    _write(
        settings_path,
        {"show_in_menu_bar": False, "show_in_dock": False},
    )
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.show_in_menu_bar is False
    assert settings.show_in_dock is True


def test_result_view_validation(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.result_view = "bogus"
    assert settings.result_view == "preview"
    settings.result_view = "markdown"
    assert settings.result_view == "markdown"
    settings.result_view = "text"
    assert settings.result_view == "text"


def test_interface_language_round_trip(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.interface_language = "uk_UA"  # type: ignore[assignment]
    assert settings.interface_language is AppLanguage.UK
    assert AppSettings(settings_path, FakeSecrets()).interface_language is AppLanguage.UK


def test_apply_catalog_entry(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    entry = next(
        item for item in ModelCatalog.ENTRIES if item.model_id == "tencent/hy-mt2-7b"
    )
    settings.apply_catalog_entry(entry)
    assert settings.provider is Provider.OPEN_ROUTER
    assert settings.model == "tencent/hy-mt2-7b"
    assert settings.base_url == "https://openrouter.ai/api/v1"


def test_install_command(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    assert settings.install_command() == (
        "ollama pull maternion/hy-mt2:7b && ollama cp maternion/hy-mt2:7b hy-mt2:7b"
    )
    settings.model = "some-unknown-model"
    assert settings.install_command() is None


def test_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert AppSettings.default_path() == (
        tmp_path / "roaming" / "DeepL-oFM" / "settings.json"
    )

    # `Path.home()` ignores $HOME on Windows, so patch the function itself:
    # the fallback then behaves the same on every platform.
    monkeypatch.delenv("APPDATA")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    assert AppSettings.default_path() == (
        tmp_path / "home" / ".config" / "DeepL-oFM" / "settings.json"
    )


def test_atomic_write_leaves_no_temporary_files(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    settings.model = "hy-mt2:1.8b"
    settings.top_k = 7
    assert settings_path.exists()
    assert sorted(path.name for path in settings_path.parent.iterdir()) == [
        "settings.json"
    ]


def test_settings_survive_repeated_saves(settings_path: Path) -> None:
    settings = AppSettings(settings_path, FakeSecrets())
    for index in range(20):
        settings.top_k = index
    assert AppSettings(settings_path, FakeSecrets()).top_k == 19


def test_repr(settings_path: Path) -> None:
    text = repr(AppSettings(settings_path, FakeSecrets()))
    assert "AppSettings" in text
    assert "settings.json" in text


def test_lazy_secret_store_is_created_on_demand(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys
    import types

    created: list[FakeSecrets] = []

    class FakeStore(FakeSecrets):
        def __init__(self) -> None:
            super().__init__()
            created.append(self)

    module = types.ModuleType("deepl_ofm.services.secrets")
    module.SecretStore = FakeStore  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "deepl_ofm.services.secrets", module)

    settings = AppSettings(settings_path)
    settings.api_key = "lazy-key"
    assert created, "the secret store should be constructed lazily"
    assert created[0].data == {"provider:ollama": "lazy-key"}


def test_catalog_entries_are_complete() -> None:
    entries = ModelCatalog.ENTRIES
    assert len(entries) == 28
    assert len({entry.model_id for entry in entries}) == 28
    assert {entry.provider for entry in entries} == {
        Provider.OLLAMA,
        Provider.OLLAMA_CLOUD,
        Provider.OPEN_ROUTER,
        Provider.GROQ,
        Provider.CEREBRAS,
    }
    assert ModelCatalog.install_command("hy-mt2:30b") == (
        "ollama pull maternion/hy-mt2:30b-a3b && "
        "ollama cp maternion/hy-mt2:30b-a3b hy-mt2:30b"
    )
    assert ModelCatalog.install_command("gemma4:31b") is None
    assert ModelCatalog.install_command("does-not-exist") is None
    for entry in ModelCatalog.for_provider(Provider.OLLAMA):
        assert entry.install_command.startswith("ollama pull ")
    assert ModelCatalog.for_provider(Provider.CUSTOM) == []
    assert all(entry.name and entry.note for entry in entries)
