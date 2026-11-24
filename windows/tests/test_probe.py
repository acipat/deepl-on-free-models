"""Tests for :mod:`deepl_ofm.services.probe` — no sockets.

Covers Ollama ``/api/tags`` / OpenAI ``/v1/models`` parsing, the ``/v1`` base
rule, error mapping through :class:`TranslationError` and the
``model_listed`` forms (exact, ``name:tag``, ``vendor/name``).
"""

from __future__ import annotations

import pytest
import requests

from deepl_ofm.core.providers import BackendConfig, BackendKind
from deepl_ofm.services import probe
from deepl_ofm.services.translation import TranslationError


class FakeResponse:
    def __init__(self, json_body=None, *, status_code: int = 200) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.closed = False

    def json(self):
        if self._json_body is None:
            raise ValueError("no JSON body")
        return self._json_body

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.requests: list[dict] = []
        self.closed = False

    def get(self, url: str, **kwargs):
        self.requests.append({"url": url, **kwargs})
        if self.error is not None:
            raise self.error
        return self.response

    def close(self) -> None:
        self.closed = True


def config(
    kind: BackendKind = BackendKind.OLLAMA,
    base_url: str = "http://127.0.0.1:11434",
    model: str = "hy-mt2:7b",
    **kwargs,
) -> BackendConfig:
    return BackendConfig(kind=kind, base_url=base_url, model=model, **kwargs)


def test_probe_models_parses_ollama_tags():
    session = FakeSession(
        FakeResponse(
            {
                "models": [
                    {"name": "hy-mt2:7b"},
                    {"name": "llama3:latest"},
                    {"model": "legacy-entry"},
                    {"size": 123},
                ]
            }
        )
    )
    models = probe.probe_models(config(), session=session)
    assert models == ["hy-mt2:7b", "llama3:latest", "legacy-entry"]
    assert session.requests[0]["url"] == "http://127.0.0.1:11434/api/tags"


def test_probe_models_parses_openai_models():
    session = FakeSession(
        FakeResponse({"data": [{"id": "gpt-4o-mini"}, {"id": "local-7b"}]})
    )
    models = probe.probe_models(
        config(BackendKind.OPENAI, "https://api.example.test", "gpt-4o-mini"),
        session=session,
    )
    assert models == ["gpt-4o-mini", "local-7b"]
    assert session.requests[0]["url"] == "https://api.example.test/v1/models"


def test_probe_models_does_not_double_v1():
    session = FakeSession(FakeResponse({"data": []}))
    probe.probe_models(
        config(BackendKind.OPENAI, "https://api.example.test/v1/", "x"),
        session=session,
    )
    assert session.requests[0]["url"] == "https://api.example.test/v1/models"


def test_probe_models_sends_bearer_token():
    session = FakeSession(FakeResponse({"data": [{"id": "x"}]}))
    probe.probe_models(
        config(BackendKind.OPENAI, "https://api.example.test", "x", api_key="secret"),
        session=session,
    )
    assert session.requests[0]["headers"]["Authorization"] == "Bearer secret"


def test_probe_models_raises_mapped_errors():
    with pytest.raises(TranslationError) as info:
        probe.probe_models(config(), session=FakeSession(FakeResponse({}, status_code=401)))
    assert info.value.kind == "unauthorized"
    assert info.value.status == 401

    with pytest.raises(TranslationError) as info:
        probe.probe_models(config(), session=FakeSession(FakeResponse({}, status_code=429)))
    assert info.value.kind == "rate_limit"

    with pytest.raises(TranslationError) as info:
        probe.probe_models(config(), session=FakeSession(FakeResponse({}, status_code=502)))
    assert info.value.kind == "server"

    with pytest.raises(TranslationError) as info:
        probe.probe_models(config(), session=FakeSession(FakeResponse(None)))
    assert info.value.kind == "unexpected"

    with pytest.raises(TranslationError) as info:
        probe.probe_models(
            config(),
            session=FakeSession(error=requests.exceptions.ConnectionError("down")),
        )
    assert info.value.kind == "connection"

    with pytest.raises(TranslationError) as info:
        probe.probe_models(config(base_url="not a url"), session=FakeSession(FakeResponse({})))
    assert info.value.kind == "invalid_url"


def test_model_listed_matches_exact_tag_and_vendor_forms():
    assert probe.model_listed("hy-mt2:7b", ["hy-mt2:7b"]) is True
    assert probe.model_listed("hy-mt2:7b", ["HY-MT2:7B"]) is True
    assert probe.model_listed("hy-mt2", ["hy-mt2:7b"]) is True
    assert probe.model_listed("hy-mt2-7b", ["tencent/hy-mt2-7b"]) is True


def test_model_listed_accepts_vendor_slash_form():
    assert probe.model_listed("hy-mt2-7b", ["tencent/hy-mt2-7b"]) is True
    assert probe.model_listed("gpt-oss", ["gpt-oss:120b-cloud"]) is True
    assert probe.model_listed("hy-mt2", ["hy-mt2:7b"]) is True
    assert probe.model_listed("hy-mt2:7b", []) is False
    assert probe.model_listed("hy-mt2:7b", ["llama-3.3-70b"]) is False
