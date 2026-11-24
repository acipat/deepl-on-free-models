"""Providers, wire protocols and request configuration.

Ported from ``Sources/HyMT/Models/Provider.swift`` and
``Sources/HyMT/Models/BackendConfig.swift``; the English ``detail`` sentences are
translation keys resolved through :func:`deepl_ofm.core.languages.translate`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from deepl_ofm.core.languages import AppLanguage, translate


class BackendKind(str, Enum):
    """Wire protocol used to talk to a provider."""

    OLLAMA = "ollama"
    OPENAI = "openAI"

    @property
    def default_base_url(self) -> str:
        """Base URL used when a provider has none configured."""
        if self is BackendKind.OLLAMA:
            return "http://127.0.0.1:11434"
        return "http://127.0.0.1:1234/v1"

    @classmethod
    def from_stored(cls, value: object) -> "BackendKind | None":
        """Tolerant lookup used by the legacy ``backend`` settings key."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        for member in cls:
            if member.value == text or member.value.lower() == text.lower():
                return member
        return None


class Provider(str, Enum):
    """A place a model can run."""

    OLLAMA = "ollama"
    OLLAMA_CLOUD = "ollamaCloud"
    LM_STUDIO = "lmStudio"
    OMLX = "omlx"
    LLAMA_CPP = "llamaCpp"
    OPEN_ROUTER = "openRouter"
    GROQ = "groq"
    CEREBRAS = "cerebras"
    CUSTOM = "custom"

    @property
    def title(self) -> str:
        """English display name; localised at the call site with ``t(title)``."""
        return _TITLES[self]

    @property
    def base_url(self) -> str:
        """Default server address for the provider."""
        return _BASE_URLS[self]

    @property
    def kind(self) -> BackendKind:
        """Wire protocol spoken by the provider."""
        return BackendKind.OLLAMA if self is Provider.OLLAMA else BackendKind.OPENAI

    @property
    def is_local(self) -> bool:
        """True when the model normally runs on this machine."""
        return self in _LOCAL_PROVIDERS

    @property
    def requires_key(self) -> bool:
        """True when an API key is mandatory."""
        return self in _KEY_PROVIDERS

    @property
    def key_url(self) -> str | None:
        """Where the user can create an API key, when the provider needs one."""
        return _KEY_URLS.get(self)

    @property
    def key_account(self) -> str:
        """Account name used by :class:`~deepl_ofm.services.secrets.SecretStore`."""
        return "provider:" + self.value

    @property
    def detail_key(self) -> str:
        """English sentence describing the provider (an i18n key)."""
        return _DETAIL_KEYS[self]

    def detail(self, app_language: AppLanguage | str | None = None) -> str:
        """Localised description shown under the provider button."""
        return translate(self.detail_key, app_language)

    @staticmethod
    def infer(backend: BackendKind | str, base_url: str) -> "Provider":
        """Guess the provider from the backend kind and the configured URL."""
        value = (base_url or "").lower()
        if "ollama.com" in value:
            return Provider.OLLAMA_CLOUD
        kind = backend if isinstance(backend, BackendKind) else BackendKind.from_stored(backend)
        if kind is BackendKind.OLLAMA:
            return Provider.OLLAMA
        if "openrouter.ai" in value:
            return Provider.OPEN_ROUTER
        if "api.groq.com" in value:
            return Provider.GROQ
        if "cerebras.ai" in value:
            return Provider.CEREBRAS
        if ":1234" in value:
            return Provider.LM_STUDIO
        if ":50220" in value:
            return Provider.OMLX
        if ":8080" in value:
            return Provider.LLAMA_CPP
        return Provider.CUSTOM

    @classmethod
    def from_stored(cls, value: object) -> "Provider | None":
        """Tolerant lookup accepting raw values, enum names and display titles."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            return None
        key = _alias_key(value)
        if not key:
            return None
        for member in cls:
            if key in (
                _alias_key(member.value),
                _alias_key(member.name),
                _alias_key(_TITLES[member]),
            ):
                return member
        return None


def _alias_key(value: str) -> str:
    """Normalise a stored provider spelling for comparison."""
    return re.sub(r"[\s_\-]+", "", value).lower()


_TITLES: dict[Provider, str] = {
    Provider.OLLAMA: "Ollama",
    Provider.OLLAMA_CLOUD: "Ollama Cloud",
    Provider.LM_STUDIO: "LM Studio",
    Provider.OMLX: "oMLX",
    Provider.LLAMA_CPP: "llama.cpp",
    Provider.OPEN_ROUTER: "OpenRouter",
    Provider.GROQ: "Groq",
    Provider.CEREBRAS: "Cerebras",
    Provider.CUSTOM: "Custom",
}

_BASE_URLS: dict[Provider, str] = {
    Provider.OLLAMA: "http://127.0.0.1:11434",
    Provider.OLLAMA_CLOUD: "https://ollama.com/v1",
    Provider.LM_STUDIO: "http://127.0.0.1:1234/v1",
    Provider.OMLX: "http://127.0.0.1:50220/v1",
    Provider.LLAMA_CPP: "http://127.0.0.1:8080/v1",
    Provider.OPEN_ROUTER: "https://openrouter.ai/api/v1",
    Provider.GROQ: "https://api.groq.com/openai/v1",
    Provider.CEREBRAS: "https://api.cerebras.ai/v1",
    Provider.CUSTOM: "http://127.0.0.1:1234/v1",
}

_LOCAL_PROVIDERS = frozenset({
    Provider.OLLAMA,
    Provider.LM_STUDIO,
    Provider.OMLX,
    Provider.LLAMA_CPP,
})

_KEY_PROVIDERS = frozenset({
    Provider.OLLAMA_CLOUD,
    Provider.OPEN_ROUTER,
    Provider.GROQ,
    Provider.CEREBRAS,
})

_KEY_URLS: dict[Provider, str] = {
    Provider.OPEN_ROUTER: "https://openrouter.ai/keys",
    Provider.GROQ: "https://console.groq.com/keys",
    Provider.CEREBRAS: "https://cloud.cerebras.ai",
    Provider.OLLAMA_CLOUD: "https://ollama.com/settings/keys",
}

_DETAIL_KEYS: dict[Provider, str] = {
    Provider.OLLAMA: (
        "Local Ollama server. The model must be pulled with ollama pull."
    ),
    Provider.OLLAMA_CLOUD: (
        "Ollama Cloud through a direct API key. No local server is needed."
    ),
    Provider.LM_STUDIO: (
        "LM Studio with its local server enabled. The model ID is shown in LM Studio."
    ),
    Provider.OMLX: (
        "oMLX — an MLX server for Apple Silicon. Enable the OpenAI-compatible API."
    ),
    Provider.LLAMA_CPP: (
        "llama-server with --api. The default address is port 8080."
    ),
    Provider.OPEN_ROUTER: (
        "Hundreds of models with one key. Free models are marked :free."
    ),
    Provider.GROQ: (
        "Very fast cloud. Has a free tier with request limits."
    ),
    Provider.CEREBRAS: (
        "Fastest inference for open models. Has a free tier with limits."
    ),
    Provider.CUSTOM: (
        "Any OpenAI-compatible server: your proxy, vLLM, LocalAI, Together, and so on."
    ),
}


@dataclass
class BackendConfig:
    """Everything a request needs: endpoint, model, credentials and sampling."""

    kind: BackendKind
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.7
    top_p: float = 0.6
    top_k: int = 20
    repetition_penalty: float = 1.05
    context_window: int = 8192
    requires_api_key: bool = False

    def compatible_base(self) -> str:
        """Base URL without trailing slashes, falling back to the kind default."""
        value = (self.base_url or "").strip()
        while value.endswith("/"):
            value = value[:-1]
        if value:
            return value
        kind = self.kind
        if not isinstance(kind, BackendKind):
            kind = BackendKind.from_stored(kind) or BackendKind.OPENAI
        return kind.default_base_url

    def uses_same_endpoint(self, other: "BackendConfig") -> bool:
        """True when two configs address the same endpoint (Swift parity helper)."""
        return (
            self.kind == other.kind
            and self.base_url == other.base_url
            and self.model == other.model
            and self.api_key == other.api_key
        )
