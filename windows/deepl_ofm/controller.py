"""Application state and background orchestration for DeepL-oFM for Windows.

Ported from ``Sources/HyMT/AppState.swift`` (state, debounce, history, hotkeys,
progress) without any SwiftUI/AppKit dependency: the controller is a plain
``QObject`` that owns the settings, the history store and the worker jobs, and
exposes everything the views need through signals.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import (
    QMimeData,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication

from .core.languages import (
    AppLanguage,
    Language,
    LanguageTable,
    detect_language,
    get_language,
)
from .core.prompts import TranslationStyle, TranslationTone
from .core.settings import AppSettings
from .i18n import set_language, t, tf
from .services.documents import DocumentError, DocumentTranslator, DocumentKind, OpenedDocument
from .services.history import HistoryEntry, HistoryStore
from .services.translation import (
    TranslationCancelled,
    TranslationError,
    TranslationOutput,
    Translator,
)

log = logging.getLogger(__name__)

TABS = ("translate", "files", "write", "history")
RESULT_VIEWS = ("preview", "text", "markdown")
#: Minimum distance between two streamed pane updates (seconds).
_PARTIAL_MIN_INTERVAL = 0.05


class _JobSignals(QObject):
    """Signals for one background job (created in the GUI thread, emitted from a worker).

    Delivery is forced through ``Qt.QueuedConnection``: PySide only marshals a
    signal into the receiver's thread when the receiver is a QObject, and plain
    Python callbacks would otherwise run inside the worker thread — mutating
    controller state and emitting view signals from there.  Every signal is
    therefore connected to a slot on this GUI-thread object, which then calls
    the per-job callback.
    """

    progress = Signal(int, int)
    partial = Signal(str)
    state = Signal(str)
    finished = Signal(object)
    failed = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.on_progress: Callable[[int, int], None] | None = None
        self.on_partial: Callable[[str], None] | None = None
        self.on_state: Callable[[str], None] | None = None
        self.on_finished: Callable[[Any], None] | None = None
        self.on_failed: Callable[[BaseException], None] | None = None
        queued = Qt.ConnectionType.QueuedConnection
        self.progress.connect(self._deliver_progress, queued)
        self.partial.connect(self._deliver_partial, queued)
        self.state.connect(self._deliver_state, queued)
        self.finished.connect(self._deliver_finished, queued)
        self.failed.connect(self._deliver_failed, queued)

    # -- GUI-thread delivery ------------------------------------------------
    def _call(self, callback, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:  # noqa: BLE001 - a broken callback must not kill the app
            log.exception("job callback failed")

    @Slot(int, int)
    def _deliver_progress(self, completed: int, total: int) -> None:
        self._call(self.on_progress, completed, total)

    @Slot(str)
    def _deliver_partial(self, text: str) -> None:
        self._call(self.on_partial, text)

    @Slot(str)
    def _deliver_state(self, state: str) -> None:
        self._call(self.on_state, state)

    @Slot(object)
    def _deliver_finished(self, result: object) -> None:
        self._call(self.on_finished, result)

    @Slot(object)
    def _deliver_failed(self, error: object) -> None:
        self._call(self.on_failed, error)


class _Job(QRunnable):
    """Runs ``fn(signals)`` in the global thread pool."""

    def __init__(self, fn: Callable[[_JobSignals], Any], signals: _JobSignals | None = None) -> None:
        super().__init__()
        self.signals = signals or _JobSignals()
        self._fn = fn
        self.setAutoDelete(True)

    def run(self) -> None:  # noqa: D401 - QRunnable API
        try:
            result = self._fn(self.signals)
        except BaseException as exc:  # noqa: BLE001 - transported to the GUI thread
            self.signals.failed.emit(exc)
        else:
            self.signals.finished.emit(result)


class AppController(QObject):
    """Owns application state; views read attributes and call the command methods."""

    # --- state notifications -------------------------------------------------
    sourceTextChanged = Signal(str)
    translatedTextChanged = Signal(str)
    partialTranslationChanged = Signal(str)
    progressChanged = Signal(int, int)
    translatingChanged = Signal(bool)
    warningCountChanged = Signal(int)
    errorRaised = Signal(str)
    translationFailed = Signal(str)
    detectedLanguageChanged = Signal(str)
    languagesChanged = Signal(str, str)
    styleChanged = Signal(str)
    toneChanged = Signal(str)
    resultViewChanged = Signal(str)
    backendStatusChanged = Signal(str)
    probeMessageChanged = Signal(str)
    modelsChanged = Signal(list)
    fallbackModelsChanged = Signal(list)
    modelsLoadingChanged = Signal(bool)
    fallbackModelsLoadingChanged = Signal(bool)
    modelsErrorChanged = Signal(str)
    fallbackModelsErrorChanged = Signal(str)
    settingsChanged = Signal()
    interfaceLanguageChanged = Signal(str)
    tabChanged = Signal(str)
    historyChanged = Signal()
    fileJobChanged = Signal(dict)
    speakingChanged = Signal(str)
    copyFeedback = Signal(str)
    writeFinished = Signal(str)
    writeStateChanged = Signal(bool)
    windowRequested = Signal()
    hotkeyStatusChanged = Signal(str, str)  # action, message
    metricsChanged = Signal()

    def __init__(
        self,
        settings: AppSettings | None = None,
        history: HistoryStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or AppSettings()
        self.history = history or HistoryStore()
        self.translator = Translator()
        self.pool = QThreadPool.globalInstance()

        # --- tab / panes -----------------------------------------------------
        self.tab: str = "translate"
        self.source_text: str = ""
        self.translated_text: str = ""

        # --- translation state ----------------------------------------------
        self.is_translating: bool = False
        self.completed: int = 0
        self.total: int = 0
        self.warning_count: int = 0
        self.error_message: str | None = None
        self.tokens_per_second: float | None = None
        self.last_duration_ms: int | None = None
        self.using_fallback: bool = False

        # --- languages -------------------------------------------------------
        self.source_language: Language = get_language(self.settings.last_source_code) or LanguageTable.AUTO
        self.target_language: Language = get_language(self.settings.last_target_code) or get_language("en")
        self.detected_language: Language | None = None

        # --- style -----------------------------------------------------------
        self.style: TranslationStyle = self.settings.last_style
        self.tone: TranslationTone = self.settings.last_tone
        self.result_view: str = self.settings.result_view if self.settings.result_view in RESULT_VIEWS else "preview"

        # --- backend ---------------------------------------------------------
        self.backend_status: str = "unknown"
        self.probe_message: str = ""
        self.provider_models: list[str] = []
        self.models_loading: bool = False
        self.models_error: str | None = None
        self.fallback_models: list[str] = []
        self.fallback_models_loading: bool = False
        self.fallback_models_error: str | None = None

        # --- hotkeys / speech ------------------------------------------------
        self.hotkey_message: str = ""
        self.selection_hotkey_message: str = ""
        self.speaking: str = ""

        # --- files -----------------------------------------------------------
        self.file_job: dict[str, Any] | None = None
        self._file_document: OpenedDocument | None = None
        self._file_output: Path | None = None

        # --- write -----------------------------------------------------------
        self.write_in_progress: bool = False
        self.write_output: str = ""
        self.write_error: str | None = None
        self.write_warning_count: int = 0
        self.write_duration_ms: int | None = None
        self.write_detected_code: str = ""

        # --- internals -------------------------------------------------------
        self._jobs: set[_JobSignals] = set()
        self._file_generation = 0
        self._write_generation = 0
        self._generation = 0
        self._cancel = threading.Event()
        self._file_cancel = threading.Event()
        self._write_cancel = threading.Event()
        self._booted = False
        self._last_completed_key: tuple[str, str, str, str, str, str, bool] | None = None
        self._suppress_auto = False
        self._capturing_selection = False
        self._last_partial_at = 0.0

        self._detect_timer = QTimer(self)
        self._detect_timer.setSingleShot(True)
        self._detect_timer.setInterval(300)
        self._detect_timer.timeout.connect(self._run_detection)

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(lambda: self.translate(force=False))

        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(600)
        self._probe_timer.timeout.connect(self.check_connection)

        set_language(self.settings.interface_language)

    # ------------------------------------------------------------------ utils
    def report_error(self, message: str) -> None:
        """Show a local error in the window status bar (used by the views)."""
        self._emit_error(message)

    def _emit_error(self, message: str) -> None:
        self.error_message = message
        self.errorRaised.emit(message)

    def _set_backend_status(self, status: str, message: str = "") -> None:
        self.backend_status = status
        self.backendStatusChanged.emit(status)
        if message or self.probe_message:
            self.probe_message = message
            self.probeMessageChanged.emit(message)

    def _language_name(self, language: Language | None) -> str:
        if language is None:
            return ""
        return language.display_name(self.settings.interface_language)

    def _engine_label(self) -> str:
        config = self.settings.snapshot()
        model = config.model or "?"
        return f"{self.settings.provider.title} · {model}"

    # -------------------------------------------------------------- lifecycle
    def bootstrap(self) -> None:
        """First run: probe the backend and optionally warm up the model."""
        if self._booted:
            return
        self._booted = True
        self._set_backend_status("checking", t("Connecting…"))
        self.check_connection()
        if self.settings.warm_up_on_launch:
            self._warm_up()

    def _warm_up(self) -> None:
        config = self.settings.snapshot()
        # A cloud request at launch would be billed just for starting the app.
        if not config.model or not self.settings.provider.is_local:
            return

        def job(signals: _JobSignals) -> bool:
            return self.translator.warm_up(config)

        self._run_job(job, on_done=self._warm_up_done, on_error=lambda exc: self._set_backend_status("failed", str(exc)))

    def _warm_up_done(self, ok: bool) -> None:
        if ok:
            self._set_backend_status("connected", t("Connected"))

    # --------------------------------------------------------------- language
    def set_source_language(self, code: str) -> None:
        language = get_language(code)
        if language is None or language.code == self.source_language.code:
            return
        self.source_language = language
        self.settings.last_source_code = language.code
        self.settings.save()
        self.languagesChanged.emit(self.source_language.code, self.target_language.code)
        self._retranslate_if_possible()

    def set_target_language(self, code: str) -> None:
        language = get_language(code)
        if language is None or language.code == self.target_language.code:
            return
        self.target_language = language
        self.settings.last_target_code = language.code
        self.settings.save()
        self.languagesChanged.emit(self.source_language.code, self.target_language.code)
        self._retranslate_if_possible()

    def swap_languages(self) -> None:
        source = self.source_language
        target = self.target_language
        if source.is_auto:
            detected = self.detected_language or detect_language(self.source_text)
            if detected is None:
                return
            source = detected
        if source.code == target.code:
            return
        self.source_language = target
        self.target_language = source
        self.settings.last_source_code = self.source_language.code
        self.settings.last_target_code = self.target_language.code
        self.settings.save()
        self.detected_language = None
        self.detectedLanguageChanged.emit("")

        source_text, translated_text = self.source_text, self.translated_text
        self._suppress_auto = True
        try:
            if translated_text.strip():
                self.set_source_text(translated_text)
                self.translated_text = source_text
                self.translatedTextChanged.emit(self.translated_text)
        finally:
            self._suppress_auto = False
        self.languagesChanged.emit(self.source_language.code, self.target_language.code)
        self.translate(force=True)

    def _retranslate_if_possible(self) -> None:
        """A direction, style or tone choice supersedes any pending or active job.

        These are deliberate setting changes, not typing: they must not wait for
        the keystroke debounce (the timer would fire while the old job is still
        running and the new request would be dropped), and they must cancel the
        old job so its result can never overwrite the new one.
        """
        if not self.source_text.strip():
            return
        self.translate(force=True)

    def _schedule_detection(self) -> None:
        self._detect_timer.start()

    def _run_detection(self) -> None:
        if not self.source_language.is_auto:
            return
        detected = detect_language(self.source_text, self.settings.interface_language)
        self.detected_language = detected
        self.detectedLanguageChanged.emit(detected.code if detected else "")

    def _resolved_source(self) -> Language:
        if not self.source_language.is_auto:
            return self.source_language
        # Never reuse ``detected_language``: the debounce may not have run for
        # the current text yet, and the previous text's guess would be wrong.
        detected = detect_language(self.source_text, self.settings.interface_language)
        return detected or get_language("en")

    # ------------------------------------------------------------- text state
    def set_source_text(self, text: str, *, from_user: bool = True) -> None:
        if text == self.source_text:
            return
        self.source_text = text
        if not text.strip():
            self.translated_text = ""
            self.translatedTextChanged.emit("")
            self.warning_count = 0
            self.warningCountChanged.emit(0)
            self.completed = self.total = 0
            self.progressChanged.emit(0, 0)
        self.sourceTextChanged.emit(text)
        if from_user and self.is_translating:
            # A result for the previous text must never land in the pane.
            self.cancel()
        if self.source_language.is_auto:
            self._schedule_detection()
        if from_user:
            self._schedule_translation()

    def _schedule_translation(self) -> None:
        if self._suppress_auto or not self.settings.auto_translate:
            return
        if not self.source_text.strip():
            return
        self._auto_timer.setInterval(max(80, int(self.settings.debounce * 1000)))
        self._auto_timer.start()

    def clear_source(self) -> None:
        if self.is_translating:
            self.cancel()
        self._auto_timer.stop()
        self.set_source_text("")
        self.sourceTextChanged.emit("")
        self.translated_text = ""
        self.translatedTextChanged.emit("")
        if self.error_message is not None:
            self.error_message = None
            self.errorRaised.emit("")
        self.warning_count = 0
        self.warningCountChanged.emit(0)
        self.completed = self.total = 0
        self.progressChanged.emit(0, 0)
        self.detected_language = None
        self.detectedLanguageChanged.emit("")
        self.tokens_per_second = None
        self.last_duration_ms = None
        self.using_fallback = False
        self.metricsChanged.emit()
        self._last_completed_key = None

    def set_result_view(self, mode: str) -> None:
        if mode not in RESULT_VIEWS or mode == self.result_view:
            return
        self.result_view = mode
        self.settings.result_view = mode
        self.settings.save()
        self.resultViewChanged.emit(mode)

    def set_style(self, style: TranslationStyle | str) -> None:
        value = TranslationStyle(style)
        if value == self.style:
            return
        self.style = value
        self.settings.last_style = value
        self.settings.save()
        self.styleChanged.emit(value.value)
        self._retranslate_if_possible()

    def set_tone(self, tone: TranslationTone | str) -> None:
        value = TranslationTone(tone)
        if value == self.tone:
            return
        self.tone = value
        self.settings.last_tone = value
        self.settings.save()
        self.toneChanged.emit(value.value)
        self._retranslate_if_possible()

    def set_tab(self, tab: str) -> None:
        if tab not in TABS or tab == self.tab:
            return
        self.tab = tab
        self.tabChanged.emit(tab)

    # ------------------------------------------------------------- translation
    def translate(self, force: bool = False) -> None:
        text = self.source_text
        if not text.strip():
            return
        if self.is_translating and not force:
            return
        # A forced run also supersedes the pending keystroke timer.
        if force:
            self._auto_timer.stop()

        if self.source_language.is_auto:
            detected = detect_language(text, self.settings.interface_language)
            self._detect_timer.stop()
            self.detected_language = detected
            self.detectedLanguageChanged.emit(detected.code if detected else "")
            source = detected or LanguageTable.AUTO
        else:
            source = self.source_language
        # The target is exactly what the user picked.  Auto-detection must never
        # silently redirect the translation to a different language.
        target = self.target_language
        config = self.settings.snapshot()

        one_request = self.settings.translate_in_one_request
        key = (
            text, source.code, target.code, self.style.value, self.tone.value,
            config.model, one_request,
        )
        if not force and key == self._last_completed_key and self.translated_text:
            return

        self._cancel.set()
        self._generation += 1
        generation = self._generation
        self._last_completed_key = None
        self.translated_text = ""
        self.translatedTextChanged.emit("")
        if self.error_message is not None:
            self.error_message = None
            self.errorRaised.emit("")
        self.warning_count = 0
        self.warningCountChanged.emit(0)
        self.completed = self.total = 0
        self.progressChanged.emit(0, 0)
        self.using_fallback = False
        self._last_partial_at = 0.0

        if not config.model:
            self._fail_translation(TranslationError("model"))
            return

        self._cancel = threading.Event()
        cancel = self._cancel
        self.is_translating = True
        self.translatingChanged.emit(True)
        style, tone = self.style, self.tone
        fallback = self.settings.fallback_config()
        if fallback is not None and fallback.uses_same_endpoint(config):
            fallback = None  # retrying the same endpoint would just fail twice
        translator = self.translator
        source_explicit = not self.source_language.is_auto

        def job(signals: _JobSignals) -> TranslationOutput:
            return translator.translate(
                text,
                source=source,
                target=target,
                style=style,
                tone=tone,
                config=config,
                fallback=fallback,
                source_explicit=source_explicit,
                one_request=one_request,
                on_progress=lambda done, total: signals.progress.emit(done, total),
                on_partial=lambda partial: signals.partial.emit(partial),
                cancel=cancel,
            )

        def done(result: TranslationOutput) -> None:
            if generation != self._generation:
                return
            self._last_completed_key = key
            self._finish_translation(result, text, source, target)

        def failed(exc: BaseException) -> None:
            if generation != self._generation:
                return
            self._fail_translation(exc)

        self._run_job(
            job,
            on_done=done,
            on_error=failed,
            on_progress=lambda completed, total: self._on_progress(completed, total, generation),
            on_partial=lambda partial: self._on_partial(partial, generation),
        )

    def _on_progress(self, completed: int, total: int, generation: int | None = None) -> None:
        if generation is not None and generation != self._generation:
            return
        self.completed, self.total = completed, total
        self.progressChanged.emit(completed, total)

    def _on_partial(self, text: str, generation: int) -> None:
        """Preview streamed text in the pane without finalising the job.

        Only the current generation may paint the pane (a cancelled job can
        still deliver queued signals) and updates are throttled so a fast
        stream does not repaint the Markdown view for every token.  The pane
        text is updated, but history, warnings and metrics are written by
        ``_finish_translation`` from the final output alone.
        """
        if generation != self._generation:
            return
        if not text:
            self._clear_translation_preview()
            return
        now = time.monotonic()
        if now - self._last_partial_at < _PARTIAL_MIN_INTERVAL:
            return
        self._last_partial_at = now
        self.translated_text = text
        self.partialTranslationChanged.emit(text)

    def _clear_translation_preview(self) -> None:
        self._last_partial_at = 0.0
        if self.translated_text:
            self.translated_text = ""
            self.translatedTextChanged.emit("")

    def _finish_translation(
        self, result: TranslationOutput, text: str, source: Language, target: Language
    ) -> None:
        self.is_translating = False
        self.translatingChanged.emit(False)
        self.translated_text = result.text
        self.translatedTextChanged.emit(result.text)
        self.warning_count = result.warnings
        self.warningCountChanged.emit(result.warnings)
        self.tokens_per_second = result.tokens_per_second
        self.last_duration_ms = result.duration_ms
        self.using_fallback = result.used_fallback
        self.metricsChanged.emit()
        if self.total:
            self.completed = self.total
            self.progressChanged.emit(self.completed, self.total)
        if result.warnings:
            self._emit_error(
                t("Some paragraphs are still in the original language (%d).") % result.warnings
            )
        if self.settings.keep_history and result.text.strip():
            self.history.add(
                HistoryEntry(
                    source_text=text,
                    translated_text=result.text,
                    source_code=source.code,
                    target_code=target.code,
                    style=self.style.value,
                    tone=self.tone.value,
                    engine=self._engine_label(),
                    duration_ms=result.duration_ms or 0,
                )
            )
            self.historyChanged.emit()

    def _fail_translation(self, exc: BaseException) -> None:
        self._clear_translation_preview()
        self.is_translating = False
        self.translatingChanged.emit(False)
        if isinstance(exc, TranslationCancelled):
            self.completed = self.total = 0
            self.progressChanged.emit(0, 0)
            return
        if isinstance(exc, TranslationError):
            message = exc.message(self.settings.interface_language)
            self._emit_error(message)
            self.translationFailed.emit(message)
            if exc.kind in ("connection", "server", "rate_limit", "unauthorized", "invalid_url"):
                self._set_backend_status("failed", exc.message(self.settings.interface_language))
        else:  # pragma: no cover - unexpected
            log.exception("translation failed", exc_info=exc)
            self._emit_error(str(exc))
            self.translationFailed.emit(str(exc))

    def cancel(self) -> None:
        if not self.is_translating:
            return
        self._cancel.set()
        self._generation += 1
        self._clear_translation_preview()
        self.is_translating = False
        self.translatingChanged.emit(False)
        self.completed = self.total = 0
        self.progressChanged.emit(0, 0)

    # --------------------------------------------------------------- clipboard
    def copy_translation(self) -> None:
        self._copy_text(self.translated_text, t("Translation copied"), self.result_view)

    def copy_source(self) -> None:
        self._copy_text(self.source_text, t("Source text copied"))

    def _copy_text(self, markdown: str, feedback: str, mode: str = "") -> None:
        """Copy in the flavour of the active result view (macOS AppState 654-665)."""
        if not markdown.strip():
            return
        mode = mode or self.result_view
        clipboard = QGuiApplication.clipboard()
        mime = QMimeData()
        if mode == "text":
            from .ui.markdown_view import markdown_to_plain

            mime.setText(markdown_to_plain(markdown))
        elif mode == "markdown":
            mime.setText(markdown)
        else:  # preview: rich text plus a plain fallback
            from .ui.markdown_view import markdown_to_html, markdown_to_plain, markdown_to_rtf

            mime.setText(markdown_to_plain(markdown))
            try:
                mime.setHtml(markdown_to_html(markdown))
                mime.setData("text/rtf", markdown_to_rtf(markdown).encode("latin-1", "replace"))
            except Exception:  # noqa: BLE001 - rich formats are a bonus
                log.debug("rich clipboard formats unavailable", exc_info=True)
        clipboard.setMimeData(mime)
        self.copyFeedback.emit(feedback)

    def translate_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        text = clipboard.text()
        try:  # rich text from a browser or a document becomes Markdown first
            from .support.pasteboard import mime_to_markdown

            mime = clipboard.mimeData()
            if mime is not None and (mime.hasHtml() or mime.hasFormat("text/rtf")):
                converted = mime_to_markdown(mime)
                if converted.strip():
                    text = converted
        except Exception:  # noqa: BLE001 - plain text is always a valid fallback
            log.debug("rich clipboard conversion failed", exc_info=True)
        if not text.strip():
            self._emit_error(t("The clipboard is empty."))
            return
        self.set_tab("translate")
        self.windowRequested.emit()
        self._suppress_auto = True
        self.set_source_text(text)
        self._suppress_auto = False
        self.translate(force=True)

    def translate_selection(self) -> None:
        """Copy the selection of the foreground app, then translate it.

        The capture must happen *before* the window is shown: raising our own
        window would take focus away from the app that holds the selection.
        """
        if self._capturing_selection:
            return
        from .support.selection import capture_selection, is_supported

        if not is_supported():
            self._emit_error(t("Selected text is only captured on Windows."))
            self.windowRequested.emit()
            return

        self._capturing_selection = True
        try:
            text = capture_selection()
        finally:
            self._capturing_selection = False

        self.set_tab("translate")
        self.windowRequested.emit()
        if not text.strip():
            self._emit_error(
                t(
                    "Could not copy the selected text. If the other app runs as "
                    "administrator, this shortcut cannot reach it."
                )
            )
            return

        self._suppress_auto = True
        self.set_source_text(text)
        self._suppress_auto = False
        self.translate(force=True)

    # ------------------------------------------------------------------ speech
    def speak(self, target: str) -> None:
        try:
            from .services.speech import Speaker
        except Exception:  # noqa: BLE001
            return
        speaker = getattr(self, "_speaker", None)
        if speaker is None:
            speaker = Speaker(self)
            speaker.started.connect(self._on_speaking_started)
            speaker.finished.connect(self._on_speaking_finished)
            self._speaker = speaker
        text = self.source_text if target == "source" else self.translated_text
        if not text.strip():
            return
        language = self._resolved_source() if target == "source" else self.target_language
        speaker.speak(
            text,
            self.settings.speech_voice_id,
            target,
            language_code=language.code if language is not None else "",
        )

    def stop_speaking(self) -> None:
        speaker = getattr(self, "_speaker", None)
        if speaker is not None:
            speaker.stop()
        if self.speaking:
            self.speaking = ""
            self.speakingChanged.emit("")

    def _on_speaking_started(self, target: str) -> None:
        self.speaking = target
        self.speakingChanged.emit(target)

    def _on_speaking_finished(self, target: str) -> None:
        if self.speaking == target:
            self.speaking = ""
            self.speakingChanged.emit("")

    # ---------------------------------------------------------------- backend
    def check_connection(self) -> None:
        config = self.settings.snapshot()

        def job(_signals: _JobSignals) -> list[str]:
            return self.translator.list_models(config)

        self._set_backend_status("checking", t("Connecting…"))
        self._run_job(job, on_done=self._connection_ok, on_error=self._connection_failed)

    def _connection_ok(self, models: list[str]) -> None:
        self._set_backend_status("connected", t("Connected"))
        if models and not self.provider_models:
            self.provider_models = models
            self.modelsChanged.emit(models)

    def _connection_failed(self, exc: BaseException) -> None:
        message = exc.message(self.settings.interface_language) if isinstance(exc, TranslationError) else str(exc)
        self._set_backend_status("failed", message)

    def connect_and_load_models(self) -> None:
        config = self.settings.snapshot()
        self.models_loading = True
        self.models_error = None
        self.modelsLoadingChanged.emit(True)
        self.modelsErrorChanged.emit("")

        def job(_signals: _JobSignals) -> list[str]:
            return self.translator.list_models(config)

        def done(models: list[str]) -> None:
            from .services.probe import model_listed

            self.models_loading = False
            self.modelsLoadingChanged.emit(False)
            self.provider_models = models
            self.modelsChanged.emit(models)

            if not models:
                message = t("The server returned no models.")
                self.models_error = message
                self.modelsErrorChanged.emit(message)
                self._set_backend_status("failed", message)
                return
            if config.model and not model_listed(config.model, models):
                message = tf(
                    "Server responds, but model “%@” is missing. Available: %@.",
                    config.model,
                    ", ".join(models[:6]),
                )
                self.models_error = message
                self.modelsErrorChanged.emit(message)
                self._set_backend_status("failed", tf("Model “%@” not found", config.model))
                self._emit_error(message)
                return
            self.models_error = None
            self.modelsErrorChanged.emit("")
            self._set_backend_status("connected", t("Connected"))

        def failed(exc: BaseException) -> None:
            self.models_loading = False
            self.modelsLoadingChanged.emit(False)
            message = exc.message(self.settings.interface_language) if isinstance(exc, TranslationError) else str(exc)
            self.models_error = message
            self.modelsErrorChanged.emit(message)
            self._set_backend_status("failed", message)

        self._run_job(job, on_done=done, on_error=failed)

    def load_fallback_models(self) -> None:
        config = self.settings.fallback_probe_config()
        self.fallback_models_loading = True
        self.fallbackModelsLoadingChanged.emit(True)
        self.fallbackModelsErrorChanged.emit("")

        def job(_signals: _JobSignals) -> list[str]:
            return self.translator.list_models(config)

        def done(models: list[str]) -> None:
            self.fallback_models_loading = False
            self.fallbackModelsLoadingChanged.emit(False)
            self.fallback_models_error = None
            self.fallback_models = models
            self.fallbackModelsChanged.emit(models)

        def failed(exc: BaseException) -> None:
            self.fallback_models_loading = False
            self.fallbackModelsLoadingChanged.emit(False)
            message = exc.message(self.settings.interface_language) if isinstance(exc, TranslationError) else str(exc)
            self.fallback_models_error = message
            self.fallbackModelsErrorChanged.emit(message)

        self._run_job(job, on_done=done, on_error=failed)

    def apply_catalog_entry(self, entry: Any) -> None:
        self.settings.apply_catalog_entry(entry)
        self.settings.save()
        self.settingsChanged.emit()
        self.connect_and_load_models()

    # --------------------------------------------------------------- settings
    def save_settings(self) -> None:
        self.settings.save()
        self.settingsChanged.emit()
        self._probe_timer.start()  # refresh the connection badge for the new values
        if self.settings.auto_translate:
            self._schedule_translation()

    def set_interface_language(self, language: AppLanguage | str) -> None:
        if isinstance(language, AppLanguage):
            value = language
        else:
            try:
                value = AppLanguage(str(language))
            except ValueError:
                log.warning("unknown interface language %r", language)
                return
        if value == self.settings.interface_language:
            return
        self.settings.interface_language = value
        self.settings.save()
        set_language(value)
        self.interfaceLanguageChanged.emit(value.value)

    # ---------------------------------------------------------------- history
    def load_history_entry(self, entry_id: str) -> None:
        entry = next((item for item in self.history.entries if item.id == entry_id), None)
        if entry is None:
            return
        self._suppress_auto = True
        self.set_source_text(entry.source_text)
        self._suppress_auto = False
        self.translated_text = entry.translated_text
        self.translatedTextChanged.emit(entry.translated_text)
        source = get_language(entry.source_code)
        target = get_language(entry.target_code)
        if source is not None:
            self.source_language = source
        if target is not None:
            self.target_language = target
        self.languagesChanged.emit(self.source_language.code, self.target_language.code)
        self.detected_language = (
            detect_language(entry.source_text, self.settings.interface_language)
            if self.source_language.is_auto
            else None
        )
        self.detectedLanguageChanged.emit(
            self.detected_language.code if self.detected_language else ""
        )
        self.last_duration_ms = entry.duration_ms or None
        self.tokens_per_second = None
        self.metricsChanged.emit()
        if entry.style in TranslationStyle._value2member_map_:
            self.style = TranslationStyle(entry.style)
            self.settings.last_style = self.style
        if entry.tone in TranslationTone._value2member_map_:
            self.tone = TranslationTone(entry.tone)
            self.settings.last_tone = self.tone
        self.settings.last_source_code = self.source_language.code
        self.settings.last_target_code = self.target_language.code
        self.settings.save()
        self.styleChanged.emit(self.style.value)
        self.toneChanged.emit(self.tone.value)
        self._last_completed_key = None
        self.set_tab("translate")
        self.windowRequested.emit()

    # ------------------------------------------------------------------ files
    def start_file_translation(self, path: Path, target_code: str | None = None) -> None:
        path = Path(path)
        target = get_language(target_code) if target_code else self.target_language
        if target is None:
            target = self.target_language
        config = self.settings.snapshot()
        if not config.model:
            self._emit_error(t("Choose a model in Settings."))
            return
        kind = DocumentKind.from_path(path)
        if kind is None:
            self._emit_error(t("This file type is not supported."))
            return

        # A new document replaces the current one: cancel the previous job first,
        # otherwise its worker keeps writing into a folder we are about to drop.
        self._file_cancel.set()
        self._discard_file_output()
        self._file_generation += 1
        generation = self._file_generation
        self._file_cancel = threading.Event()
        cancel = self._file_cancel

        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        self.file_job = {
            "path": str(path),
            "name": path.name,
            "kind": kind.value,
            "size": size,
            "state": "reading",
            "completed": 0,
            "total": 0,
            "percent": 0,
            "output": None,
            "message": None,
            "result_name": None,
            "warnings": 0,
            "fallback": False,
            "fallback_label": "",
            "save_error": None,
        }
        self._file_document = None
        self._file_output = None
        self._file_tempdir = None
        self._publish_file_job()

        translator = self.translator
        style, tone = self.style, self.tone
        fallback = self.settings.fallback_config()
        if fallback is not None and fallback.uses_same_endpoint(config):
            fallback = None
        source = self.source_language
        settings = self.settings
        counters = {"warnings": 0, "fallback": False}

        def translate_paragraph(text: str) -> str:
            result = translator.translate(
                text,
                source=source,
                target=target,
                style=style,
                tone=tone,
                config=config,
                fallback=fallback,
                source_explicit=not source.is_auto,
                cancel=cancel,
            )
            counters["warnings"] += int(result.warnings or 0)
            if result.used_fallback:
                counters["fallback"] = True
            return result.text

        def job(signals: _JobSignals) -> tuple[object, Path, Path, int, bool]:
            # Nothing in here may touch ``self``: this runs in a pool thread.
            document = DocumentTranslator.read(path)
            signals.state.emit("translating")
            suggested = DocumentTranslator.suggested_path(path, target)
            staging = Path(tempfile.mkdtemp(prefix="deepl-ofm-"))
            out_path = staging / suggested.name
            try:
                DocumentTranslator.write(
                    document,
                    out_path,
                    translate_paragraph,
                    on_progress=lambda done, total: signals.progress.emit(done, total),
                    cancel=cancel,
                )
            except BaseException:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            return document, staging, out_path, counters["warnings"], counters["fallback"]

        def done(result: tuple[object, Path, Path, int, bool]) -> None:
            if generation != self._file_generation:
                shutil.rmtree(result[1], ignore_errors=True)  # superseded job
                return
            document, staging, out_path, warnings, used_fallback = result
            self._file_document = document  # type: ignore[assignment]
            self._file_tempdir = staging
            self._file_output = out_path
            label = ""
            if used_fallback:
                fallback_config = settings.fallback_config()
                if fallback_config is not None:
                    label = f"{settings.fallback_provider.title} · {fallback_config.model}"
            self._update_file_job(
                state="done",
                percent=100,
                output=str(out_path),
                result_name=out_path.name,
                warnings=int(warnings),
                fallback=bool(used_fallback),
                fallback_label=label,
            )

        def failed(exc: BaseException) -> None:
            if generation != self._file_generation:
                return
            if isinstance(exc, TranslationCancelled):
                self._update_file_job(state="cancelled", message=t("Cancelled"))
                return
            if isinstance(exc, (DocumentError, TranslationError)):
                message = exc.message(settings.interface_language)
            else:
                log.exception("file translation failed", exc_info=exc)
                message = str(exc)
            self._update_file_job(state="failed", message=message)

        self._run_job(
            job,
            on_done=done,
            on_error=failed,
            on_progress=self._on_file_progress,
            on_state=self._on_file_state,
        )

    def _on_file_state(self, state: str) -> None:
        if self.file_job is not None:
            self._update_file_job(state=state)

    def _discard_file_tempdir(self) -> None:
        directory = getattr(self, "_file_tempdir", None)
        if directory is not None:
            shutil.rmtree(directory, ignore_errors=True)
            self._file_tempdir = None

    def _discard_file_output(self) -> None:
        self._discard_file_tempdir()
        self._file_output = None

    def _on_file_progress(self, completed: int, total: int) -> None:
        percent = int(round(completed * 100 / total)) if total else 0
        self._update_file_job(completed=completed, total=total, percent=percent)
        if total and completed >= total:
            # Translation is finished; the format is being rebuilt now.
            self._update_file_job(state="writing")

    def _update_file_job(self, **changes: Any) -> None:
        if self.file_job is None:
            return
        self.file_job.update(changes)
        if "completed" in changes and changes.get("total"):
            self.file_job["percent"] = int(round(changes["completed"] * 100 / changes["total"]))
        self._publish_file_job()

    def _publish_file_job(self) -> None:
        self.fileJobChanged.emit(dict(self.file_job) if self.file_job else {})

    def cancel_file_translation(self) -> None:
        self._file_cancel.set()

    def save_translated_file(self, destination: Path) -> None:
        if self._file_output is None:
            self._emit_error(t("The file could not be translated."))
            return
        try:
            destination = Path(destination)
            # Copy next to the target and rename, so a failure never truncates
            # an existing file the user chose.  The temporary name must be
            # unique (mkstemp), otherwise a neighbouring "<name>.part" would be
            # overwritten and two concurrent saves would collide.
            handle, temp_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
            )
            os.close(handle)
            staging = Path(temp_name)
            try:
                shutil.copyfile(self._file_output, staging)
                os.replace(staging, destination)
            finally:
                try:
                    staging.unlink()
                except OSError:
                    pass  # os.replace consumes it; a failed copy is best-effort
        except OSError as exc:
            log.exception("could not save translated file")
            self._update_file_job(save_error=str(exc))
            self._emit_error(str(exc))
            return
        self._update_file_job(
            output=str(destination),
            result_name=destination.name,
            save_error=None,
        )
        self.copyFeedback.emit(t("Saved"))

    def clear_file_job(self) -> None:
        self._file_cancel.set()
        self._file_generation += 1  # late callbacks are ignored
        self.file_job = None
        self._file_document = None
        self._discard_file_output()
        self._publish_file_job()

    # ------------------------------------------------------------------ write
    def write_text(self, text: str, target_code: str) -> None:
        if not text.strip() or self.write_in_progress:
            return
        config = self.settings.snapshot()
        if not config.model:
            self._emit_error(t("Choose a model in Settings."))
            return
        # The Write tab has no explicit language until the user picks one: in
        # that case the text is improved in its own language, like macOS.
        if not target_code or target_code == "auto":
            target = detect_language(text, self.settings.interface_language) or self.target_language
            self.write_detected_code = target.code
        else:
            target = get_language(target_code) or self.target_language
            self.write_detected_code = ""
        self._write_cancel.set()
        self._write_generation += 1
        generation = self._write_generation
        self._write_cancel = threading.Event()
        cancel = self._write_cancel
        self.write_in_progress = True
        self.write_output = ""
        self.write_error = None
        self.write_warning_count = 0
        self.write_duration_ms = None
        self.writeStateChanged.emit(True)
        translator = self.translator
        fallback = self.settings.fallback_config()

        def job(_signals: _JobSignals) -> TranslationOutput:
            return translator.rewrite(text, target=target, config=config, fallback=fallback, cancel=cancel)

        def done(result: TranslationOutput) -> None:
            if generation != self._write_generation:
                return
            self.write_output = result.text
            self.write_warning_count = result.warnings
            self.write_duration_ms = result.duration_ms
            self.write_in_progress = False
            self.writeStateChanged.emit(False)
            # Deliberately not translatedTextChanged: the Write tab has its own
            # pane, and reusing the translate signal would overwrite it.
            self.writeFinished.emit(result.text)

        def failed(exc: BaseException) -> None:
            if generation != self._write_generation:
                return
            self.write_in_progress = False
            if isinstance(exc, TranslationCancelled):
                self.write_error = None
                self.writeStateChanged.emit(False)
                return
            self.write_error = exc.message(self.settings.interface_language) if isinstance(exc, TranslationError) else str(exc)
            self.writeStateChanged.emit(False)
            self._emit_error(self.write_error)

        self._run_job(job, on_done=done, on_error=failed)

    def reset_write(self) -> None:
        """Drop the previous result when its source text changed."""
        if self.write_in_progress:
            self.cancel_write()
        self.write_output = ""
        self.write_error = None
        self.write_warning_count = 0
        self.write_duration_ms = None
        self.writeStateChanged.emit(False)

    def cancel_write(self) -> None:
        self._write_cancel.set()
        if self.write_in_progress:
            self.write_in_progress = False
            self.writeStateChanged.emit(False)

    # -------------------------------------------------------------- shutdown
    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Cancel running work and wait briefly for the workers to unwind."""
        for event in (self._cancel, self._file_cancel, self._write_cancel):
            event.set()
        self._auto_timer.stop()
        self._detect_timer.stop()
        self._probe_timer.stop()
        self._discard_file_tempdir()
        try:
            self.pool.waitForDone(timeout_ms)
        except Exception:  # noqa: BLE001 - shutdown must never raise
            log.debug("thread pool did not drain cleanly", exc_info=True)
        speaker = getattr(self, "_speaker", None)
        if speaker is not None:
            try:
                speaker.stop()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ jobs
    def _run_job(
        self,
        fn: Callable[[_JobSignals], Any],
        *,
        on_done: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
        on_progress: Callable[[int, int], None] | None = None,
        on_state: Callable[[str], None] | None = None,
        on_partial: Callable[[str], None] | None = None,
    ) -> _JobSignals:
        # A strong reference keeps the QObject alive for the whole job: a
        # Python-only reference would be collected while the worker still emits,
        # and the queued events would be dropped.
        signals = _JobSignals()
        signals.on_finished = on_done
        signals.on_failed = on_error
        signals.on_progress = on_progress
        signals.on_state = on_state
        signals.on_partial = on_partial
        self._jobs.add(signals)

        signals.finished.connect(lambda _value: self._jobs.discard(signals))
        signals.failed.connect(lambda _value: self._jobs.discard(signals))
        self.pool.start(_Job(fn, signals))
        return signals
