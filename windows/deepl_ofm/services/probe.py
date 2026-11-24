"""Model discovery ported from ``Sources/HyMT/Services/Probe.swift``.

``probe_models`` asks Ollama for ``/api/tags`` and every OpenAI-compatible
backend for ``/v1/models`` (the ``/v1`` segment follows the same rule as the
chat endpoint).  ``model_listed`` mirrors ``Probe.model(_:isListedIn:)`` and
accepts exact ids, ``name:tag`` and ``vendor/name`` forms.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit

import requests

from deepl_ofm.core.providers import BackendConfig, BackendKind
from deepl_ofm.services.translation import TranslationError, _http_error

logger = logging.getLogger(__name__)

_CONNECT_TIMEOUT = 10.0


def _endpoint(config: BackendConfig) -> str:
    base = config.compatible_base()
    if config.kind == BackendKind.OLLAMA:
        return base.rstrip("/") + "/api/tags"
    value = base.rstrip("/")
    if value.endswith("/v1"):
        return value + "/models"
    return value + "/v1/models"


def _check_url(url: str, base: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise TranslationError("invalid_url", detail=base)


def probe_models(
    config: BackendConfig,
    *,
    timeout: float = 8.0,
    session: requests.Session | None = None,
) -> list[str]:
    """Return the model ids advertised by ``config``'s backend.

    Raises :class:`TranslationError` with ``connection``, ``invalid_url``,
    ``unauthorized``, ``rate_limit``, ``server``, ``http`` or ``unexpected``.
    """
    base = config.compatible_base()
    url = _endpoint(config)
    _check_url(url, base)

    headers: dict[str, str] = {}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    client = session if session is not None else requests.Session()
    owns_client = session is None
    try:
        try:
            response = client.get(
                url,
                headers=headers,
                timeout=(min(_CONNECT_TIMEOUT, float(timeout)), float(timeout)),
            )
        except requests.exceptions.RequestException as exc:
            raise TranslationError("connection", detail=base) from exc

        try:
            status = int(getattr(response, "status_code", 0))
            if not 200 <= status < 300:
                raise _http_error(status)
            try:
                payload = response.json()
            except (ValueError, TypeError) as exc:
                raise TranslationError("unexpected", detail="invalid JSON") from exc
        finally:
            try:
                response.close()
            except Exception:  # pragma: no cover - defensive
                pass
    finally:
        if owns_client:
            try:
                client.close()
            except Exception:  # pragma: no cover - defensive
                pass

    if not isinstance(payload, dict):
        raise TranslationError("unexpected", detail="unexpected model list payload")

    if config.kind == BackendKind.OLLAMA:
        entries = payload.get("models")
        if not isinstance(entries, list):
            return []
        result: list[str] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name") or entry.get("model")
            if isinstance(name, str) and name:
                result.append(name)
        return result

    entries = payload.get("data")
    if not isinstance(entries, list):
        return []
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("id")
        if isinstance(name, str) and name:
            result.append(name)
    return result


def model_listed(name: str, models: list[str]) -> bool:
    """Whether ``name`` is present as an exact id, ``name:tag`` or ``vendor/name``."""
    target = name.lower()
    if not models:
        return False
    for listed in models:
        value = listed.lower()
        if value == target or value.startswith(target + ":") or value.endswith("/" + target):
            return True
    return False
