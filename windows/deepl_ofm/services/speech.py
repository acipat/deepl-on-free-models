"""Text-to-speech for source and translation.

Ported from ``Sources/HyMT/Support/Speaker.swift``.  ``PySide6.QtTextToSpeech``
is used when it is importable and an engine is installed; otherwise this class
degrades to a silent no-op so headless builds (and CI) still start normally.
"""
from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Signal

logger = logging.getLogger(__name__)

try:
    from PySide6.QtTextToSpeech import QTextToSpeech, QVoice
    _QT_SPEECH_AVAILABLE = True
except Exception as exc:  # pragma: no cover - depends on the Qt build
    QTextToSpeech = None  # type: ignore[assignment]
    QVoice = None  # type: ignore[assignment]
    _QT_SPEECH_AVAILABLE = False
    logger.warning("PySide6.QtTextToSpeech is unavailable: %s", exc)


def _voice_id(voice: QVoice) -> str:
    """Stable id for a ``QVoice`` (Qt exposes no id of its own)."""
    try:
        locale_name = voice.locale().name()
    except Exception:
        locale_name = ""
    try:
        name = voice.name()
    except Exception:
        name = ""
    return f"{locale_name}::{name}"


class Speaker(QObject):
    """Explicit voice choice, real stop control and graceful degradation."""

    started = Signal(str)     # target: "source" | "translation"
    finished = Signal(str)

    MAX_CHARS = 4000

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._engine: Any = None
        self._engine_failed = False
        self._current_target: str | None = None
        self._finish_emitted = True

    # -- availability -------------------------------------------------------

    def is_available(self) -> bool:
        engine = self._ensure_engine()
        if engine is None:
            return False
        try:
            return engine.state() != QTextToSpeech.State.Error
        except Exception:
            return False

    def _ensure_engine(self) -> Any:
        if self._engine is not None:
            return self._engine
        if self._engine_failed or not _QT_SPEECH_AVAILABLE or QTextToSpeech is None:
            return None
        # QTextToSpeech needs an application object; do not cache this failure
        # because the caller may construct the Speaker before QApplication.
        if QCoreApplication.instance() is None:
            return None
        try:
            if not QTextToSpeech.availableEngines():
                logger.info("no text-to-speech engine is installed")
                self._engine_failed = True
                return None
            engine = QTextToSpeech()
            engine.stateChanged.connect(self._on_state_changed)
            error_signal = getattr(engine, "errorOccurred", None)
            if error_signal is not None:
                error_signal.connect(self._on_error)
            if engine.state() == QTextToSpeech.State.Error:
                logger.info("text-to-speech engine reported an error state")
            self._engine = engine
            return engine
        except Exception:
            logger.exception("could not create the text-to-speech engine")
            self._engine_failed = True
            return None

    # -- voices -------------------------------------------------------------

    def voices(self) -> list[tuple[str, str]]:
        """Available voices as ``(id, label)`` pairs, sorted by label."""
        engine = self._ensure_engine()
        if engine is None:
            return []
        try:
            available = list(engine.availableVoices())
        except Exception:
            logger.debug("could not list voices", exc_info=True)
            return []
        result: list[tuple[str, str]] = []
        for voice in available:
            try:
                name = voice.name()
            except Exception:
                continue
            result.append((_voice_id(voice), name))
        result.sort(key=lambda item: item[1].casefold())
        return result

    # -- playback -----------------------------------------------------------

    def speak(
        self,
        text: str,
        voice_id: str = "",
        target: str = "translation",
        language_code: str = "",
    ) -> None:
        """Speak ``text`` with the chosen voice, or one matching ``language_code``.

        ``language_code`` is an optional extension used by the controller; it
        mirrors the language argument of the Swift ``Speaker.speak``.
        """
        target = (target or "translation").strip() or "translation"
        trimmed = (text or "").strip()
        if not trimmed:
            return
        engine = self._ensure_engine()
        if engine is None or not self.is_available():
            logger.debug("speech is unavailable; ignoring %s text", target)
            return
        self.stop()
        try:
            self._apply_voice(engine, voice_id, language_code)
            self._current_target = target
            self._finish_emitted = False
            self.started.emit(target)
            engine.say(trimmed[: self.MAX_CHARS])
        except Exception:
            logger.exception("text-to-speech failed")
            self._finish_current()

    def stop(self) -> None:
        engine = self._engine
        if engine is not None:
            try:
                state = engine.state()
                if state in (
                    QTextToSpeech.State.Speaking,
                    QTextToSpeech.State.Synthesizing,
                    QTextToSpeech.State.Paused,
                ):
                    engine.stop()
            except Exception:
                logger.debug("could not stop speech", exc_info=True)
        self._finish_current()

    def is_speaking(self) -> bool:
        engine = self._engine
        if engine is None:
            return False
        try:
            return engine.state() in (
                QTextToSpeech.State.Speaking,
                QTextToSpeech.State.Synthesizing,
                QTextToSpeech.State.Paused,
            )
        except Exception:
            return False

    # -- internals ----------------------------------------------------------

    def _apply_voice(
        self, engine: Any, voice_id: str, language_code: str = ""
    ) -> None:
        wanted = (voice_id or "").strip()
        try:
            available = list(engine.availableVoices())
        except Exception:
            available = []

        if wanted:
            for voice in available:
                try:
                    if _voice_id(voice) == wanted or voice.name() == wanted:
                        engine.setVoice(voice)
                        return
                except Exception:
                    continue
            try:
                for locale in engine.availableLocales():
                    if locale.name().lower() == wanted.lower():
                        engine.setLocale(locale)
                        return
            except Exception:
                logger.debug("could not match voice %r", wanted, exc_info=True)

        code = (language_code or "").strip()
        if code and code.lower() != "auto":
            for voice in available:
                try:
                    if self._language_matches(voice.locale().name(), code):
                        engine.setVoice(voice)
                        return
                except Exception:
                    continue
            try:
                for locale in engine.availableLocales():
                    if self._language_matches(locale.name(), code):
                        engine.setLocale(locale)
                        return
            except Exception:
                logger.debug("could not match language %r", code, exc_info=True)

    @staticmethod
    def _language_matches(tag: str, code: str) -> bool:
        normalized_tag = (tag or "").lower().replace("-", "_")
        normalized_code = (code or "").lower().replace("-", "_")
        if not normalized_code:
            return False
        return normalized_tag == normalized_code or normalized_tag.startswith(
            normalized_code + "_"
        )

    def _on_state_changed(self, state: Any) -> None:
        try:
            terminal = state in (
                QTextToSpeech.State.Ready,
                QTextToSpeech.State.Error,
            )
        except Exception:
            terminal = False
        if terminal:
            self._finish_current()

    def _on_error(self, reason: Any = None, message: Any = None) -> None:
        logger.warning("text-to-speech error (%s): %s", reason, message)
        self._finish_current()

    def _finish_current(self) -> None:
        target = self._current_target
        if target is None or self._finish_emitted:
            self._current_target = None
            return
        self._finish_emitted = True
        self._current_target = None
        self.finished.emit(target)
