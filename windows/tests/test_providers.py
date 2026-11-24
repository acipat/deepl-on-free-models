"""Tests for :mod:`deepl_ofm.core.providers` (port of ``Provider.swift``)."""
from __future__ import annotations

import pytest

from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.core.providers import BackendConfig, BackendKind, Provider


def test_provider_values_match_swift_raw_values() -> None:
    assert {provider.value for provider in Provider} == {
        "ollama",
        "ollamaCloud",
        "lmStudio",
        "omlx",
        "llamaCpp",
        "openRouter",
        "groq",
        "cerebras",
        "custom",
    }


def test_provider_titles() -> None:
    assert Provider.OLLAMA.title == "Ollama"
    assert Provider.OLLAMA_CLOUD.title == "Ollama Cloud"
    assert Provider.LM_STUDIO.title == "LM Studio"
    assert Provider.OMLX.title == "oMLX"
    assert Provider.LLAMA_CPP.title == "llama.cpp"
    assert Provider.OPEN_ROUTER.title == "OpenRouter"
    assert Provider.GROQ.title == "Groq"
    assert Provider.CEREBRAS.title == "Cerebras"
    assert Provider.CUSTOM.title == "Custom"


def test_provider_base_urls() -> None:
    assert Provider.OLLAMA.base_url == "http://127.0.0.1:11434"
    assert Provider.OLLAMA_CLOUD.base_url == "https://ollama.com/v1"
    assert Provider.LM_STUDIO.base_url == "http://127.0.0.1:1234/v1"
    assert Provider.OMLX.base_url == "http://127.0.0.1:50220/v1"
    assert Provider.LLAMA_CPP.base_url == "http://127.0.0.1:8080/v1"
    assert Provider.OPEN_ROUTER.base_url == "https://openrouter.ai/api/v1"
    assert Provider.GROQ.base_url == "https://api.groq.com/openai/v1"
    assert Provider.CEREBRAS.base_url == "https://api.cerebras.ai/v1"
    assert Provider.CUSTOM.base_url == "http://127.0.0.1:1234/v1"


def test_backend_kinds() -> None:
    assert Provider.OLLAMA.kind is BackendKind.OLLAMA
    for provider in Provider:
        if provider is not Provider.OLLAMA:
            assert provider.kind is BackendKind.OPENAI


def test_locality_and_key_requirements() -> None:
    assert {p for p in Provider if p.is_local} == {
        Provider.OLLAMA,
        Provider.LM_STUDIO,
        Provider.OMLX,
        Provider.LLAMA_CPP,
    }
    assert {p for p in Provider if p.requires_key} == {
        Provider.OLLAMA_CLOUD,
        Provider.OPEN_ROUTER,
        Provider.GROQ,
        Provider.CEREBRAS,
    }
    assert not Provider.CUSTOM.requires_key
    assert not Provider.CUSTOM.is_local


def test_key_url_and_account() -> None:
    assert Provider.OPEN_ROUTER.key_url == "https://openrouter.ai/keys"
    assert Provider.GROQ.key_url == "https://console.groq.com/keys"
    assert Provider.CEREBRAS.key_url == "https://cloud.cerebras.ai"
    assert Provider.OLLAMA_CLOUD.key_url == "https://ollama.com/settings/keys"
    assert Provider.OLLAMA.key_url is None
    assert Provider.GROQ.key_account == "provider:groq"
    assert Provider.OLLAMA_CLOUD.key_account == "provider:ollamaCloud"


def test_detail_returns_english_translation_key() -> None:
    assert Provider.OLLAMA.detail(AppLanguage.EN) == (
        "Local Ollama server. The model must be pulled with ollama pull."
    )
    assert Provider.OPEN_ROUTER.detail("en") == (
        "Hundreds of models with one key. Free models are marked :free."
    )
    assert Provider.CUSTOM.detail_key == (
        "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on."
    )
    assert isinstance(Provider.GROQ.detail(), str)


def test_all_providers_have_a_detail_key() -> None:
    keys = [provider.detail_key for provider in Provider]
    assert all(keys)
    assert len(set(keys)) == len(keys)


@pytest.mark.parametrize(
    ("backend", "base_url", "expected"),
    [
        (BackendKind.OLLAMA, "http://127.0.0.1:11434", Provider.OLLAMA),
        (BackendKind.OLLAMA, "https://example.com", Provider.OLLAMA),
        (BackendKind.OPENAI, "https://ollama.com/v1", Provider.OLLAMA_CLOUD),
        (BackendKind.OPENAI, "https://openrouter.ai/api/v1", Provider.OPEN_ROUTER),
        (BackendKind.OPENAI, "https://api.groq.com/openai/v1", Provider.GROQ),
        (BackendKind.OPENAI, "https://api.cerebras.ai/v1", Provider.CEREBRAS),
        (BackendKind.OPENAI, "http://127.0.0.1:1234/v1", Provider.LM_STUDIO),
        (BackendKind.OPENAI, "http://127.0.0.1:50220/v1", Provider.OMLX),
        (BackendKind.OPENAI, "http://127.0.0.1:8080/v1", Provider.LLAMA_CPP),
        (BackendKind.OPENAI, "http://localhost:9999/v1", Provider.CUSTOM),
        (BackendKind.OPENAI, "", Provider.CUSTOM),
    ],
)
def test_infer_provider_from_url(
    backend: BackendKind, base_url: str, expected: Provider
) -> None:
    assert Provider.infer(backend, base_url) is expected


def test_infer_accepts_lowercase_urls() -> None:
    assert Provider.infer(BackendKind.OPENAI, "HTTPS://OPENROUTER.AI/API/V1") is (
        Provider.OPEN_ROUTER
    )


def test_from_stored_is_tolerant() -> None:
    assert Provider.from_stored("groq") is Provider.GROQ
    assert Provider.from_stored("ollamaCloud") is Provider.OLLAMA_CLOUD
    assert Provider.from_stored("ollamacloud") is Provider.OLLAMA_CLOUD
    assert Provider.from_stored("OLLAMA_CLOUD") is Provider.OLLAMA_CLOUD
    assert Provider.from_stored("Ollama Cloud") is Provider.OLLAMA_CLOUD
    assert Provider.from_stored("LM Studio") is Provider.LM_STUDIO
    assert Provider.from_stored("lm_studio") is Provider.LM_STUDIO
    assert Provider.from_stored("llama.cpp") is Provider.LLAMA_CPP
    assert Provider.from_stored(Provider.CEREBRAS) is Provider.CEREBRAS
    assert Provider.from_stored("klingon") is None
    assert Provider.from_stored("") is None
    assert Provider.from_stored(None) is None


def test_backend_kind_values_and_defaults() -> None:
    assert BackendKind.OLLAMA.value == "ollama"
    assert BackendKind.OPENAI.value == "openAI"
    assert BackendKind.OLLAMA.default_base_url == "http://127.0.0.1:11434"
    assert BackendKind.OPENAI.default_base_url == "http://127.0.0.1:1234/v1"
    assert BackendKind.from_stored("openAI") is BackendKind.OPENAI
    assert BackendKind.from_stored("openai") is BackendKind.OPENAI
    assert BackendKind.from_stored("ollama") is BackendKind.OLLAMA
    assert BackendKind.from_stored("nonsense") is None
    assert BackendKind.from_stored(7) is None


def test_backend_config_defaults() -> None:
    config = BackendConfig(kind=BackendKind.OLLAMA, base_url="http://x", model="m")
    assert config.api_key == ""
    assert config.temperature == 0.7
    assert config.top_p == 0.6
    assert config.top_k == 20
    assert config.repetition_penalty == 1.05
    assert config.context_window == 8192
    assert config.requires_api_key is False


def test_backend_config_compatible_base() -> None:
    config = BackendConfig(
        kind=BackendKind.OPENAI, base_url="  http://127.0.0.1:1234/v1///  ", model="m"
    )
    assert config.compatible_base() == "http://127.0.0.1:1234/v1"
    empty = BackendConfig(kind=BackendKind.OLLAMA, base_url="", model="m")
    assert empty.compatible_base() == "http://127.0.0.1:11434"
    blank = BackendConfig(kind=BackendKind.OPENAI, base_url="   ", model="m")
    assert blank.compatible_base() == "http://127.0.0.1:1234/v1"


def test_backend_config_same_endpoint() -> None:
    a = BackendConfig(kind=BackendKind.OLLAMA, base_url="http://x", model="m", api_key="")
    b = BackendConfig(kind=BackendKind.OLLAMA, base_url="http://x", model="m", api_key="")
    c = BackendConfig(
        kind=BackendKind.OLLAMA, base_url="http://x", model="m", api_key="key"
    )
    assert a.uses_same_endpoint(b)
    assert not a.uses_same_endpoint(c)
