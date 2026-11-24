"""JSON backed application settings.

Ported from ``Sources/HyMT/Models/AppSettings.swift``: the Swift ``UserDefaults``
keys become one atomic JSON document, API keys stay out of that document and are
read/written through :class:`deepl_ofm.services.secrets.SecretStore` when it is
available. Per-provider ``base_url``/``model`` memory and the "never lose the last
entry point" rule are preserved.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepl_ofm.core.catalog import CatalogEntry, ModelCatalog
from deepl_ofm.core.keycombo import KeyCombo
from deepl_ofm.core.languages import AppLanguage, coerce_app_language
from deepl_ofm.core.providers import BackendConfig, BackendKind, Provider

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps secrets optional at runtime
    from deepl_ofm.services.secrets import SecretStore

try:  # the prompts module is written by a sibling task; keep settings importable
    from deepl_ofm.core.prompts import TranslationStyle, TranslationTone
except ImportError:  # pragma: no cover - only while core.prompts is missing

    class TranslationStyle(str, Enum):  # type: ignore[no-redef]
        """Minimal stand-in matching ``core.prompts.TranslationStyle``."""

        AUTO = "auto"
        LITERAL = "literal"
        NATURAL = "natural"

    class TranslationTone(str, Enum):  # type: ignore[no-redef]
        """Minimal stand-in matching ``core.prompts.TranslationTone``."""

        STANDARD = "standard"
        FORMAL = "formal"
        CASUAL = "casual"


logger = logging.getLogger(__name__)

_RESULT_VIEWS: tuple[str, ...] = ("preview", "text", "markdown")

_PERSISTED_FIELDS: tuple[str, ...] = (
    "provider",
    "base_url",
    "model",
    "fallback_enabled",
    "fallback_provider",
    "fallback_base_url",
    "fallback_model",
    "temperature",
    "top_p",
    "top_k",
    "repetition_penalty",
    "context_window",
    "auto_translate",
    "translate_in_one_request",
    "debounce",
    "hot_key",
    "selection_hot_key",
    "show_in_menu_bar",
    "show_in_dock",
    "speech_voice_id",
    "keep_history",
    "warm_up_on_launch",
    "interface_language",
    "result_view",
    "last_style",
    "last_tone",
    "last_target_code",
    "last_source_code",
)

_MEMORY_PREFIXES: tuple[str, ...] = (
    "base_url",
    "model",
    "fallback_base_url",
    "fallback_model",
)

_MEMORY_ALIASES: dict[str, str] = {
    "baseURL": "base_url",
    "model": "model",
    "fallbackBaseURL": "fallback_base_url",
    "fallbackModel": "fallback_model",
}

_ALIASES: dict[str, str] = {
    "baseURL": "base_url",
    "fallbackEnabled": "fallback_enabled",
    "fallbackProvider": "fallback_provider",
    "fallbackBaseURL": "fallback_base_url",
    "fallbackModel": "fallback_model",
    "topP": "top_p",
    "topK": "top_k",
    "repetitionPenalty": "repetition_penalty",
    "contextWindow": "context_window",
    "autoTranslate": "auto_translate",
    "translateInOneRequest": "translate_in_one_request",
    "hotKey": "hot_key",
    "selectionHotKey": "selection_hot_key",
    "showInMenuBar": "show_in_menu_bar",
    "showInDock": "show_in_dock",
    "speechVoiceID": "speech_voice_id",
    "keepHistory": "keep_history",
    "warmUpOnLaunch": "warm_up_on_launch",
    "interfaceLanguage": "interface_language",
    "resultView": "result_view",
    "lastStyle": "last_style",
    "lastTone": "last_tone",
    "lastTargetCode": "last_target_code",
    "lastSourceCode": "last_source_code",
    "lastTarget": "last_target_code",
    "lastSource": "last_source_code",
}


def _default_values() -> dict[str, Any]:
    """Defaults copied from ``AppSettings.init`` in the Swift source."""
    return {
        "provider": Provider.OLLAMA,
        "base_url": Provider.OLLAMA.base_url,
        "model": "hy-mt2:7b",
        "api_key": "",
        "fallback_enabled": False,
        "fallback_provider": Provider.OLLAMA,
        "fallback_api_key": "",
        "fallback_base_url": Provider.OLLAMA.base_url,
        "fallback_model": "",
        "temperature": 0.7,
        "top_p": 0.6,
        "top_k": 20,
        "repetition_penalty": 1.05,
        "context_window": 8192,
        "auto_translate": True,
        "translate_in_one_request": True,
        "debounce": 0.45,
        "hot_key": KeyCombo.standard(),
        "selection_hot_key": KeyCombo.selection(),
        "show_in_menu_bar": True,
        "show_in_dock": True,
        "speech_voice_id": "",
        "keep_history": True,
        "warm_up_on_launch": False,
        "interface_language": AppLanguage.SYSTEM,
        "result_view": "preview",
        "last_style": TranslationStyle.AUTO,
        "last_tone": TranslationTone.STANDARD,
        "last_target_code": "en",
        "last_source_code": "auto",
    }


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) else default


def _as_code(value: Any, default: str) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return default


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return default


def _as_float(value: Any, default: float) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return default


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return default


def _as_provider(value: Any, default: Provider | None) -> Provider | None:
    if isinstance(value, Provider):
        return value
    if isinstance(value, str):
        found = Provider.from_stored(value)
        if found is not None:
            return found
    return default


def _as_choice(value: Any, choices: tuple[str, ...], default: str) -> str:
    if isinstance(value, str) and value.strip().lower() in choices:
        return value.strip().lower()
    return default


def _as_enum(enum_type: Any, value: Any, default: Any) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value.strip())
        except ValueError:
            return default
    return default


def _as_keycombo(value: Any, default: KeyCombo) -> KeyCombo:
    if isinstance(value, KeyCombo):
        combo = value
    elif isinstance(value, Mapping):
        combo = KeyCombo.from_dict(value)
    else:
        return default
    return combo if combo.is_valid else default


class AppSettings:
    """JSON backed settings, independent of Qt and safe to use in tests."""

    def __init__(
        self,
        path: Path | None = None,
        secrets: "SecretStore | None" = None,
    ) -> None:
        self._lock = threading.RLock()
        self.path = Path(path) if path is not None else AppSettings.default_path()
        self._secrets = secrets
        self._secrets_resolved = secrets is not None
        self._values: dict[str, Any] = _default_values()
        self._remembered: dict[str, str] = {}
        self._load()
        self._apply_entry_point_rule()
        self._values["api_key"] = self._read_secret(self._values["provider"].key_account)
        self._values["fallback_api_key"] = self._read_secret(
            self._values["fallback_provider"].key_account
        )

    # MARK: persistence ---------------------------------------------------

    @staticmethod
    def default_path() -> Path:
        """``%APPDATA%\\DeepL-oFM\\settings.json`` (or the POSIX equivalent)."""
        appdata = os.environ.get("APPDATA")
        root = Path(appdata) if appdata else Path.home() / ".config"
        return root / "DeepL-oFM" / "settings.json"

    def save(self) -> None:
        """Write the whole document atomically; failures are logged, never raised."""
        payload: dict[str, Any] = dict(self._remembered)
        with self._lock:
            for name in _PERSISTED_FIELDS:
                payload[name] = self._serialize(self._values[name])
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            except (OSError, TypeError, ValueError) as error:
                logger.warning("cannot prepare settings file %s: %s", self.path, error)
                return
        self._write_atomic(text + "\n")

    def _write_atomic(self, text: str) -> None:
        temporary = ""
        try:
            handle_fd, temporary = tempfile.mkstemp(
                prefix=".settings-", suffix=".tmp", dir=str(self.path.parent)
            )
            with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            logger.warning("cannot save settings to %s: %s", self.path, error)
            if temporary:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _serialize(self, value: Any) -> Any:
        if isinstance(value, KeyCombo):
            return value.to_dict()
        if isinstance(value, Enum):
            return value.value
        return value

    def _load(self) -> None:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as error:
            logger.warning("cannot read settings %s: %s", self.path, error)
            return
        try:
            document = json.loads(raw)
        except (TypeError, ValueError) as error:
            logger.warning("settings file %s is not valid JSON: %s", self.path, error)
            return
        if not isinstance(document, Mapping):
            logger.warning("settings file %s does not contain an object", self.path)
            return
        self._apply_document(document)

    def _apply_document(self, document: Mapping[str, Any]) -> None:
        values = self._values
        defaults = _default_values()
        flat: dict[str, Any] = {}
        for raw_key, raw_value in document.items():
            if not isinstance(raw_key, str):
                continue
            key = raw_key.strip()
            if not key:
                continue
            if "." in key:
                prefix, suffix = key.split(".", 1)
                prefix = _MEMORY_ALIASES.get(prefix, prefix)
                suffix = suffix.strip()
                if prefix in _MEMORY_PREFIXES and suffix and isinstance(raw_value, str):
                    self._remembered[f"{prefix}.{suffix}"] = raw_value
                continue
            flat[_ALIASES.get(key, key)] = raw_value

        legacy_kind = BackendKind.from_stored(flat.get("backend")) or BackendKind.OLLAMA
        stored_base = _as_str(flat.get("base_url"), "").strip()
        provider = _as_provider(flat.get("provider"), None)
        if provider is not None:
            if not stored_base:
                stored_base = provider.base_url
        else:
            if not stored_base:
                stored_base = legacy_kind.default_base_url
            provider = Provider.infer(legacy_kind, stored_base)
        values["provider"] = provider
        values["base_url"] = stored_base
        values["model"] = _as_str(flat.get("model"), defaults["model"])

        fallback_provider = _as_provider(
            flat.get("fallback_provider"), defaults["fallback_provider"]
        )
        values["fallback_provider"] = fallback_provider
        values["fallback_enabled"] = _as_bool(
            flat.get("fallback_enabled"), defaults["fallback_enabled"]
        )
        values["fallback_base_url"] = _as_str(
            flat.get("fallback_base_url"), fallback_provider.base_url
        )
        values["fallback_model"] = _as_str(
            flat.get("fallback_model"), defaults["fallback_model"]
        )

        values["temperature"] = _as_float(flat.get("temperature"), defaults["temperature"])
        values["top_p"] = _as_float(flat.get("top_p"), defaults["top_p"])
        values["top_k"] = _as_int(flat.get("top_k"), defaults["top_k"])
        values["repetition_penalty"] = _as_float(
            flat.get("repetition_penalty"), defaults["repetition_penalty"]
        )
        values["context_window"] = _as_int(
            flat.get("context_window"), defaults["context_window"]
        )
        values["auto_translate"] = _as_bool(
            flat.get("auto_translate"), defaults["auto_translate"]
        )
        values["translate_in_one_request"] = _as_bool(
            flat.get("translate_in_one_request"), defaults["translate_in_one_request"]
        )
        values["debounce"] = _as_float(flat.get("debounce"), defaults["debounce"])
        values["hot_key"] = _as_keycombo(flat.get("hot_key"), defaults["hot_key"])
        values["selection_hot_key"] = _as_keycombo(
            flat.get("selection_hot_key"), defaults["selection_hot_key"]
        )
        values["show_in_menu_bar"] = _as_bool(
            flat.get("show_in_menu_bar"), defaults["show_in_menu_bar"]
        )
        values["show_in_dock"] = _as_bool(
            flat.get("show_in_dock"), defaults["show_in_dock"]
        )
        values["speech_voice_id"] = _as_str(
            flat.get("speech_voice_id"), defaults["speech_voice_id"]
        )
        values["keep_history"] = _as_bool(
            flat.get("keep_history"), defaults["keep_history"]
        )
        values["warm_up_on_launch"] = _as_bool(
            flat.get("warm_up_on_launch"), defaults["warm_up_on_launch"]
        )
        if "interface_language" in flat:
            values["interface_language"] = coerce_app_language(flat["interface_language"])
        values["result_view"] = _as_choice(
            flat.get("result_view"), _RESULT_VIEWS, defaults["result_view"]
        )
        values["last_style"] = _as_enum(
            TranslationStyle, flat.get("last_style"), defaults["last_style"]
        )
        values["last_tone"] = _as_enum(
            TranslationTone, flat.get("last_tone"), defaults["last_tone"]
        )
        values["last_target_code"] = _as_code(
            flat.get("last_target_code"), defaults["last_target_code"]
        )
        values["last_source_code"] = _as_code(
            flat.get("last_source_code"), defaults["last_source_code"]
        )

    def _apply_entry_point_rule(self) -> None:
        menu_bar = self._values["show_in_menu_bar"]
        dock = self._values["show_in_dock"]
        if not menu_bar and not dock:
            self._values["show_in_dock"] = True

    # MARK: secrets -------------------------------------------------------

    def _secret_store(self) -> "SecretStore | None":
        if self._secrets is not None:
            return self._secrets
        if self._secrets_resolved:
            return None
        self._secrets_resolved = True
        try:
            from deepl_ofm.services.secrets import SecretStore
        except ImportError:
            return None
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("secret store unavailable: %s", error)
            return None
        try:
            self._secrets = SecretStore()
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("cannot open the secret store: %s", error)
            self._secrets = None
        return self._secrets

    def _read_secret(self, account: str) -> str:
        store = self._secret_store()
        if store is None:
            return ""
        try:
            return str(store.read(account) or "")
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("cannot read secret %s: %s", account, error)
            return ""

    def _write_secret(self, account: str, value: str) -> None:
        store = self._secret_store()
        if store is None:
            return
        try:
            store.write(account, value)
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("cannot write secret %s: %s", account, error)

    def _delete_secret(self, account: str) -> None:
        store = self._secret_store()
        if store is None:
            return
        try:
            store.delete(account)
        except Exception as error:  # pragma: no cover - defensive
            logger.warning("cannot delete secret %s: %s", account, error)

    # MARK: helpers -------------------------------------------------------

    def _set(self, name: str, value: Any) -> None:
        with self._lock:
            if self._values.get(name) == value:
                return
            self._values[name] = value
        self.save()

    @property
    def kind(self) -> BackendKind:
        """Wire protocol of the selected provider."""
        return self._values["provider"].kind

    # MARK: connection ----------------------------------------------------

    @property
    def provider(self) -> Provider:
        """Selected provider."""
        return self._values["provider"]

    @provider.setter
    def provider(self, value: Provider | str) -> None:
        target = _as_provider(value, self._values["provider"])
        with self._lock:
            old = self._values["provider"]
            if old is target:
                return
            self._values["provider"] = target
            self._remembered[f"base_url.{old.value}"] = str(self._values["base_url"])
            self._remembered[f"model.{old.value}"] = str(self._values["model"])
            self._values["base_url"] = self._remembered.get(
                f"base_url.{target.value}", target.base_url
            )
            self._values["model"] = self._remembered.get(f"model.{target.value}", "")
            self._values["api_key"] = self._read_secret(target.key_account)
        self.save()

    @property
    def api_key(self) -> str:
        """API key of the selected provider (kept in the secret store)."""
        return self._values["api_key"]

    @api_key.setter
    def api_key(self, value: str) -> None:
        text = _as_str(value, "")
        with self._lock:
            if self._values["api_key"] == text:
                return
            self._values["api_key"] = text
            account = self._values["provider"].key_account
        self._write_secret(account, text)

    @property
    def base_url(self) -> str:
        """Server address of the selected provider."""
        return self._values["base_url"]

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._set("base_url", _as_str(value, self._values["base_url"]))

    @property
    def model(self) -> str:
        """Model identifier sent to the provider."""
        return self._values["model"]

    @model.setter
    def model(self, value: str) -> None:
        self._set("model", _as_str(value, self._values["model"]))

    # MARK: fallback provider ---------------------------------------------

    @property
    def fallback_enabled(self) -> bool:
        """Whether a second provider may be used when the first one fails."""
        return self._values["fallback_enabled"]

    @fallback_enabled.setter
    def fallback_enabled(self, value: bool) -> None:
        self._set("fallback_enabled", _as_bool(value, self._values["fallback_enabled"]))

    @property
    def fallback_provider(self) -> Provider:
        """Provider used as a fallback."""
        return self._values["fallback_provider"]

    @fallback_provider.setter
    def fallback_provider(self, value: Provider | str) -> None:
        target = _as_provider(value, self._values["fallback_provider"])
        with self._lock:
            old = self._values["fallback_provider"]
            if old is target:
                return
            self._values["fallback_provider"] = target
            self._remembered[f"fallback_base_url.{old.value}"] = str(
                self._values["fallback_base_url"]
            )
            self._remembered[f"fallback_model.{old.value}"] = str(
                self._values["fallback_model"]
            )
            self._values["fallback_base_url"] = self._remembered.get(
                f"fallback_base_url.{target.value}", target.base_url
            )
            self._values["fallback_model"] = self._remembered.get(
                f"fallback_model.{target.value}", ""
            )
            self._values["fallback_api_key"] = self._read_secret(target.key_account)
        self.save()

    @property
    def fallback_api_key(self) -> str:
        """API key of the fallback provider."""
        return self._values["fallback_api_key"]

    @fallback_api_key.setter
    def fallback_api_key(self, value: str) -> None:
        text = _as_str(value, "")
        with self._lock:
            if self._values["fallback_api_key"] == text:
                return
            self._values["fallback_api_key"] = text
            account = self._values["fallback_provider"].key_account
        self._write_secret(account, text)

    @property
    def fallback_base_url(self) -> str:
        """Server address of the fallback provider."""
        return self._values["fallback_base_url"]

    @fallback_base_url.setter
    def fallback_base_url(self, value: str) -> None:
        self._set(
            "fallback_base_url",
            _as_str(value, self._values["fallback_base_url"]),
        )

    @property
    def fallback_model(self) -> str:
        """Model identifier of the fallback provider."""
        return self._values["fallback_model"]

    @fallback_model.setter
    def fallback_model(self, value: str) -> None:
        self._set("fallback_model", _as_str(value, self._values["fallback_model"]))

    # MARK: generation ----------------------------------------------------

    @property
    def temperature(self) -> float:
        """Sampling temperature."""
        return self._values["temperature"]

    @temperature.setter
    def temperature(self, value: float) -> None:
        self._set("temperature", _as_float(value, self._values["temperature"]))

    @property
    def top_p(self) -> float:
        """Nucleus sampling probability."""
        return self._values["top_p"]

    @top_p.setter
    def top_p(self, value: float) -> None:
        self._set("top_p", _as_float(value, self._values["top_p"]))

    @property
    def top_k(self) -> int:
        """Top-K sampling cut-off."""
        return self._values["top_k"]

    @top_k.setter
    def top_k(self, value: int) -> None:
        self._set("top_k", _as_int(value, self._values["top_k"]))

    @property
    def repetition_penalty(self) -> float:
        """Repetition penalty passed to Ollama."""
        return self._values["repetition_penalty"]

    @repetition_penalty.setter
    def repetition_penalty(self, value: float) -> None:
        self._set(
            "repetition_penalty",
            _as_float(value, self._values["repetition_penalty"]),
        )

    @property
    def context_window(self) -> int:
        """Context window size in tokens."""
        return self._values["context_window"]

    @context_window.setter
    def context_window(self, value: int) -> None:
        self._set("context_window", _as_int(value, self._values["context_window"]))

    # MARK: behaviour -----------------------------------------------------

    @property
    def auto_translate(self) -> bool:
        """Translate while typing."""
        return self._values["auto_translate"]

    @auto_translate.setter
    def auto_translate(self, value: bool) -> None:
        self._set("auto_translate", _as_bool(value, self._values["auto_translate"]))

    @property
    def translate_in_one_request(self) -> bool:
        """Translate the text pane in one request before retrying by block."""
        return self._values["translate_in_one_request"]

    @translate_in_one_request.setter
    def translate_in_one_request(self, value: bool) -> None:
        self._set(
            "translate_in_one_request",
            _as_bool(value, self._values["translate_in_one_request"]),
        )

    @property
    def debounce(self) -> float:
        """Delay between the last keystroke and an automatic translation."""
        return self._values["debounce"]

    @debounce.setter
    def debounce(self, value: float) -> None:
        self._set("debounce", _as_float(value, self._values["debounce"]))

    @property
    def hot_key(self) -> KeyCombo:
        """Global shortcut that translates the clipboard."""
        return self._values["hot_key"]

    @hot_key.setter
    def hot_key(self, value: KeyCombo | Mapping[str, Any]) -> None:
        self._set("hot_key", _as_keycombo(value, self._values["hot_key"]))

    @property
    def selection_hot_key(self) -> KeyCombo:
        """Global shortcut that translates the selected text."""
        return self._values["selection_hot_key"]

    @selection_hot_key.setter
    def selection_hot_key(self, value: KeyCombo | Mapping[str, Any]) -> None:
        self._set(
            "selection_hot_key",
            _as_keycombo(value, self._values["selection_hot_key"]),
        )

    @property
    def show_in_menu_bar(self) -> bool:
        """Whether the tray icon is shown."""
        return self._values["show_in_menu_bar"]

    @show_in_menu_bar.setter
    def show_in_menu_bar(self, value: bool) -> None:
        enabled = _as_bool(value, self._values["show_in_menu_bar"])
        with self._lock:
            changed = self._values["show_in_menu_bar"] != enabled
            self._values["show_in_menu_bar"] = enabled
            # Never leave the app without a way to reach it.
            if not enabled and not self._values["show_in_dock"]:
                self._values["show_in_dock"] = True
                changed = True
        if changed:
            self.save()

    @property
    def show_in_dock(self) -> bool:
        """Whether the main window is shown in the taskbar."""
        return self._values["show_in_dock"]

    @show_in_dock.setter
    def show_in_dock(self, value: bool) -> None:
        enabled = _as_bool(value, self._values["show_in_dock"])
        with self._lock:
            changed = self._values["show_in_dock"] != enabled
            self._values["show_in_dock"] = enabled
            if not enabled and not self._values["show_in_menu_bar"]:
                self._values["show_in_menu_bar"] = True
                changed = True
        if changed:
            self.save()

    @property
    def speech_voice_id(self) -> str:
        """Identifier of the chosen text-to-speech voice."""
        return self._values["speech_voice_id"]

    @speech_voice_id.setter
    def speech_voice_id(self, value: str) -> None:
        self._set("speech_voice_id", _as_str(value, self._values["speech_voice_id"]))

    @property
    def keep_history(self) -> bool:
        """Whether translations are stored in the history."""
        return self._values["keep_history"]

    @keep_history.setter
    def keep_history(self, value: bool) -> None:
        self._set("keep_history", _as_bool(value, self._values["keep_history"]))

    @property
    def warm_up_on_launch(self) -> bool:
        """Whether a local model is loaded during start-up."""
        return self._values["warm_up_on_launch"]

    @warm_up_on_launch.setter
    def warm_up_on_launch(self, value: bool) -> None:
        self._set(
            "warm_up_on_launch",
            _as_bool(value, self._values["warm_up_on_launch"]),
        )

    @property
    def interface_language(self) -> AppLanguage:
        """Interface language (``system`` follows the OS)."""
        return self._values["interface_language"]

    @interface_language.setter
    def interface_language(self, value: AppLanguage | str) -> None:
        self._set("interface_language", coerce_app_language(value))

    @property
    def result_view(self) -> str:
        """Result presentation mode: ``preview``, ``text`` or ``markdown``."""
        return self._values["result_view"]

    @result_view.setter
    def result_view(self, value: str) -> None:
        self._set(
            "result_view",
            _as_choice(value, _RESULT_VIEWS, self._values["result_view"]),
        )

    # MARK: last selection ------------------------------------------------

    @property
    def last_style(self) -> TranslationStyle:
        """Last used translation style."""
        return self._values["last_style"]

    @last_style.setter
    def last_style(self, value: TranslationStyle | str) -> None:
        self._set(
            "last_style",
            _as_enum(TranslationStyle, value, self._values["last_style"]),
        )

    @property
    def last_tone(self) -> TranslationTone:
        """Last used tone."""
        return self._values["last_tone"]

    @last_tone.setter
    def last_tone(self, value: TranslationTone | str) -> None:
        self._set(
            "last_tone",
            _as_enum(TranslationTone, value, self._values["last_tone"]),
        )

    @property
    def last_target_code(self) -> str:
        """Last target language code."""
        return self._values["last_target_code"]

    @last_target_code.setter
    def last_target_code(self, value: str) -> None:
        self._set(
            "last_target_code",
            _as_code(value, self._values["last_target_code"]),
        )

    @property
    def last_source_code(self) -> str:
        """Last source language code (``auto`` by default)."""
        return self._values["last_source_code"]

    @last_source_code.setter
    def last_source_code(self, value: str) -> None:
        self._set(
            "last_source_code",
            _as_code(value, self._values["last_source_code"]),
        )

    # MARK: derived configuration ----------------------------------------

    @property
    def normalized_base_url(self) -> str:
        """Base URL without trailing slashes, never empty."""
        value = self._values["base_url"].strip()
        while value.endswith("/"):
            value = value[:-1]
        return value or self._values["provider"].base_url

    @property
    def normalized_fallback_base_url(self) -> str:
        """Fallback base URL without trailing slashes, never empty."""
        value = self._values["fallback_base_url"].strip()
        while value.endswith("/"):
            value = value[:-1]
        return value or self._values["fallback_provider"].base_url

    def snapshot(self) -> BackendConfig:
        """Current backend configuration for a translation request."""
        provider = self._values["provider"]
        return BackendConfig(
            kind=provider.kind,
            base_url=self.normalized_base_url,
            model=self._values["model"].strip(),
            api_key=self._values["api_key"].strip(),
            temperature=self._values["temperature"],
            top_p=self._values["top_p"],
            top_k=self._values["top_k"],
            repetition_penalty=self._values["repetition_penalty"],
            context_window=self._values["context_window"],
            requires_api_key=provider.requires_key,
        )

    def fallback_config(self) -> BackendConfig | None:
        """Fallback configuration, or ``None`` when it is disabled or incomplete."""
        if not self._values["fallback_enabled"]:
            return None
        model = self._values["fallback_model"].strip()
        if not model:
            return None
        provider = self._values["fallback_provider"]
        return BackendConfig(
            kind=provider.kind,
            base_url=self.normalized_fallback_base_url,
            model=model,
            api_key=self._values["fallback_api_key"].strip(),
            temperature=self._values["temperature"],
            top_p=self._values["top_p"],
            top_k=self._values["top_k"],
            repetition_penalty=self._values["repetition_penalty"],
            context_window=self._values["context_window"],
            requires_api_key=provider.requires_key,
        )

    def fallback_probe_config(self) -> BackendConfig:
        """Fallback endpoint used for the "load models" probe, even when disabled."""
        provider = self._values["fallback_provider"]
        return BackendConfig(
            kind=provider.kind,
            base_url=self.normalized_fallback_base_url,
            model=self._values["fallback_model"].strip(),
            api_key=self._values["fallback_api_key"].strip(),
            temperature=self._values["temperature"],
            top_p=self._values["top_p"],
            top_k=self._values["top_k"],
            repetition_penalty=self._values["repetition_penalty"],
            context_window=self._values["context_window"],
            requires_api_key=provider.requires_key,
        )

    # MARK: commands ------------------------------------------------------

    def apply_provider(self, provider: Provider, model: str | None = None) -> None:
        """Switch provider, restoring its remembered model/base URL."""
        target = _as_provider(provider, self._values["provider"])
        if target is self._values["provider"]:
            if model:
                self.model = model
            return
        self.provider = target
        if model:
            self.model = model

    def apply_catalog_entry(self, entry: CatalogEntry) -> None:
        """Apply a catalogue entry: provider plus its model id."""
        self.apply_provider(entry.provider, entry.model_id)

    def clear_key(self) -> None:
        """Forget the API key of the selected provider."""
        with self._lock:
            account = self._values["provider"].key_account
            self._values["api_key"] = ""
        self._delete_secret(account)
        self.save()

    def install_command(self) -> str | None:
        """Ollama command that installs the currently selected local model."""
        return ModelCatalog.install_command(self.model)

    def __repr__(self) -> str:
        return (
            f"AppSettings(path={str(self.path)!r}, provider={self.provider.value!r}, "
            f"model={self.model!r})"
        )
