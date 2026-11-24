"""Regression tests for the eight defects found by the external review."""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import threading
import time
import types
import uuid
from ctypes import wintypes
from pathlib import Path

import pytest
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QWidget

from deepl_ofm import app as app_module
from deepl_ofm.controller import AppController
from deepl_ofm.core.languages import get_language
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.services.translation import TranslationCancelled, TranslationOutput
from deepl_ofm.support import selection
from deepl_ofm.ui.translate_view import TranslateView


def wait_until(predicate, timeout: float = 3.0, step: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        QApplication.processEvents()
        time.sleep(step)
    return bool(predicate())


def _controller(tmp_path: Path, *, auto_translate: bool = False) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.model = "hy-mt2:7b"
    settings.auto_translate = auto_translate
    settings.last_source_code = "en"
    settings.last_target_code = "uk"
    return AppController(
        settings=settings,
        history=HistoryStore(path=tmp_path / "history.json"),
    )


# ---------------------------------------------------------------------------
# 1. ctypes prototypes keep 64-bit clipboard handles intact
# ---------------------------------------------------------------------------


class _FakeFunction:
    """Callable that records calls and accepts ``restype``/``argtypes``."""

    def __init__(self, result=None) -> None:
        self.result = result
        self.restype = None
        self.argtypes = None
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


def _fake_win32() -> tuple[types.SimpleNamespace, types.SimpleNamespace]:
    user32 = types.SimpleNamespace(
        OpenClipboard=_FakeFunction(1),
        GetClipboardData=_FakeFunction(0),
        CloseClipboard=_FakeFunction(1),
        GetClipboardSequenceNumber=_FakeFunction(0),
        GetAsyncKeyState=_FakeFunction(0),
        keybd_event=_FakeFunction(None),
    )
    kernel32 = types.SimpleNamespace(
        GlobalLock=_FakeFunction(0),
        GlobalUnlock=_FakeFunction(1),
    )
    return user32, kernel32


def test_win32_functions_declare_pointer_sized_prototypes():
    user32, kernel32 = _fake_win32()

    selection._install_prototypes(user32, kernel32)

    # The two functions that return memory addresses must not default to int:
    # that is exactly what truncates a HANDLE/LPVOID to 32 bits on Windows x64.
    assert user32.GetClipboardData.restype is ctypes.c_void_p
    assert user32.GetClipboardData.restype is not ctypes.c_int
    assert user32.GetClipboardData.argtypes == [wintypes.UINT]
    assert kernel32.GlobalLock.restype is ctypes.c_void_p
    assert kernel32.GlobalLock.restype is not ctypes.c_int
    assert kernel32.GlobalLock.argtypes == [wintypes.HGLOBAL]
    assert kernel32.GlobalUnlock.restype is wintypes.BOOL
    assert kernel32.GlobalUnlock.argtypes == [wintypes.HGLOBAL]

    assert user32.OpenClipboard.restype is wintypes.BOOL
    assert user32.OpenClipboard.argtypes == [wintypes.HWND]
    assert user32.CloseClipboard.argtypes == []
    assert user32.GetClipboardSequenceNumber.restype is wintypes.DWORD
    assert user32.GetClipboardSequenceNumber.argtypes == []
    assert user32.GetAsyncKeyState.restype is wintypes.SHORT
    assert user32.GetAsyncKeyState.argtypes == [ctypes.c_int]
    assert user32.keybd_event.restype is None
    assert len(user32.keybd_event.argtypes) == 4


def test_clipboard_text_reads_a_full_64_bit_handle(qapp, monkeypatch):
    user32, kernel32 = _fake_win32()
    selection._install_prototypes(user32, kernel32)
    buffer = ctypes.create_unicode_buffer("selected text")
    handle = 0x7FFE_1234_5678  # wider than 32 bits: the old ctypes int truncated it
    user32.GetClipboardData.result = handle
    kernel32.GlobalLock.result = ctypes.addressof(buffer)

    monkeypatch.setattr(selection, "_WINDOWS", True)
    monkeypatch.setattr(selection, "_USER32", user32)
    monkeypatch.setattr(selection, "_KERNEL32", kernel32)

    assert selection._clipboard_text() == "selected text"
    assert user32.GetClipboardData.calls == [(selection.CF_UNICODETEXT,)]
    assert kernel32.GlobalLock.calls == [(handle,)]
    assert kernel32.GlobalUnlock.calls == [(handle,)]
    assert user32.CloseClipboard.calls == [()]


# ---------------------------------------------------------------------------
# 2. "Save as" must not clobber a neighbouring .part file
# ---------------------------------------------------------------------------


def test_save_as_leaves_an_unrelated_part_file_alone(qapp, tmp_path):
    controller = _controller(tmp_path)
    source = tmp_path / "translated.txt"
    source.write_text("NEW", encoding="utf-8")
    destination = tmp_path / "report.pdf"
    destination.write_text("OLD", encoding="utf-8")
    neighbour = tmp_path / "report.pdf.part"
    neighbour.write_text("KEEP", encoding="utf-8")

    controller._file_output = source
    controller.file_job = {"output": str(source), "result_name": source.name}
    controller.save_translated_file(destination)

    assert destination.read_text(encoding="utf-8") == "NEW"
    assert neighbour.read_text(encoding="utf-8") == "KEEP"


def test_save_as_removes_its_temporary_file_on_failure(qapp, tmp_path):
    controller = _controller(tmp_path)
    destination = tmp_path / "report.pdf"
    destination.write_text("OLD", encoding="utf-8")
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    controller._file_output = tmp_path / "missing.txt"  # copyfile fails
    controller.file_job = {"output": "", "result_name": destination.name}
    controller.save_translated_file(destination)

    assert destination.read_text(encoding="utf-8") == "OLD"
    assert errors
    assert list(tmp_path.glob(".report.pdf.*.part")) == []


# ---------------------------------------------------------------------------
# 3. Language/style/tone changes supersede a running job immediately
# ---------------------------------------------------------------------------


def _blocking_translator(calls: list[tuple], started: threading.Event, release: threading.Event):
    def fake(text, **kwargs):
        calls.append(
            (
                kwargs["target"].code,
                kwargs["style"].value,
                kwargs["tone"].value,
                kwargs.get("source_explicit"),
            )
        )
        if len(calls) == 1:
            started.set()
            release.wait(3)
            raise TranslationCancelled()
        return TranslationOutput(text="Nouveau", duration_ms=5)

    return fake


def test_language_change_during_translation_starts_immediately(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path, auto_translate=True)
    controller.settings.debounce = 5.0  # a debounce would be plainly visible
    calls: list[tuple] = []
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        controller.translator, "translate", _blocking_translator(calls, started, release)
    )
    controller.set_source_text("Hello world")
    controller.translate(force=True)
    assert started.wait(2)
    assert controller.is_translating

    began = time.monotonic()
    controller.set_target_language("fr")
    assert wait_until(lambda: len(calls) == 2, timeout=1.0)
    assert time.monotonic() - began < 1.0  # not the 5 s debounce
    assert calls[1][0] == "fr"

    release.set()
    assert wait_until(lambda: controller.translated_text == "Nouveau")
    assert [
        (entry.source_code, entry.target_code) for entry in controller.history.entries
    ] == [("en", "fr")]
    assert controller.history.entries[0].translated_text == "Nouveau"


@pytest.mark.parametrize(
    ("setter", "value", "index"),
    [("set_style", "literal", 1), ("set_tone", "formal", 2)],
)
def test_style_or_tone_change_during_translation_starts_immediately(
    qapp, tmp_path, monkeypatch, setter, value, index
):
    controller = _controller(tmp_path, auto_translate=True)
    controller.settings.debounce = 5.0
    calls: list[tuple] = []
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        controller.translator, "translate", _blocking_translator(calls, started, release)
    )
    controller.set_source_text("Hello world")
    controller.translate(force=True)
    assert started.wait(2)

    getattr(controller, setter)(value)
    assert wait_until(lambda: len(calls) == 2, timeout=1.0)
    assert calls[1][index] == value

    release.set()
    assert wait_until(lambda: controller.translated_text == "Nouveau")


def test_typing_still_waits_for_the_debounce(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path, auto_translate=True)
    controller.settings.debounce = 0.2
    calls: list[str] = []

    def fake(text, **_kwargs):
        calls.append(text)
        return TranslationOutput(text="Hallo", duration_ms=5)

    monkeypatch.setattr(controller.translator, "translate", fake)
    controller.set_source_text("Hello")
    assert calls == []
    assert controller._auto_timer.isActive()
    assert wait_until(lambda: calls == ["Hello"], timeout=2.0)


def test_translate_again_stays_usable_while_translating(qapp, tmp_path):
    controller = _controller(tmp_path)
    view = TranslateView(controller)
    view.show()
    try:
        controller.set_source_text("Hello")
        controller.is_translating = True
        controller.translatingChanged.emit(True)
        qapp.processEvents()
        assert view._again_button.isEnabled()
    finally:
        view.close()
        view.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 4. Immediate translations use the current text's detection, not a stale one
# ---------------------------------------------------------------------------


def _start_immediate(controller: AppController, opener: str, text: str, monkeypatch) -> None:
    if opener == "clipboard":
        QGuiApplication.clipboard().setText(text)
        controller.translate_clipboard()
    else:
        monkeypatch.setattr("deepl_ofm.support.selection.is_supported", lambda: True)
        monkeypatch.setattr(
            "deepl_ofm.support.selection.capture_selection", lambda **_: text
        )
        controller.translate_selection()


@pytest.mark.parametrize("opener", ["clipboard", "selection"])
def test_immediate_translation_detects_current_text_and_keeps_target(
    qapp, tmp_path, monkeypatch, opener
):
    controller = _controller(tmp_path)
    controller.set_source_language("auto")
    controller.set_target_language("de")
    controller.detected_language = get_language("fr")  # guess for the previous text
    calls: list[tuple[str, str, bool]] = []

    def fake(text, **kwargs):
        calls.append(
            (kwargs["source"].code, kwargs["target"].code, kwargs["source_explicit"])
        )
        return TranslationOutput(text="Das ist ein Bericht.", duration_ms=3)

    monkeypatch.setattr(controller.translator, "translate", fake)
    _start_immediate(controller, opener, "Das ist ein Bericht.", monkeypatch)

    assert wait_until(lambda: bool(calls))
    source_code, target_code, source_explicit = calls[0]
    assert source_code == "de"  # detected from the text being translated
    assert target_code == "de"  # never silently redirected to another language
    assert source_explicit is False
    assert controller.detected_language is not None
    assert controller.detected_language.code == "de"


def test_explicit_source_language_is_forwarded(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    calls: list[tuple[str, bool]] = []

    def fake(text, **kwargs):
        calls.append((kwargs["source"].code, kwargs["source_explicit"]))
        return TranslationOutput(text="Hallo", duration_ms=3)

    monkeypatch.setattr(controller.translator, "translate", fake)
    controller.set_source_language("en")
    controller.set_source_text("Hello")
    controller.translate(force=True)

    assert wait_until(lambda: bool(calls))
    assert calls[0] == ("en", True)


def test_auto_detected_persian_remains_an_implicit_source(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    controller.set_source_language("auto")
    controller.set_target_language("en")
    calls: list[tuple[str, str, bool]] = []

    def fake(text, **kwargs):
        calls.append((kwargs["source"].code, kwargs["target"].code, kwargs["source_explicit"]))
        return TranslationOutput(text="This is a report.", duration_ms=3)

    monkeypatch.setattr(controller.translator, "translate", fake)
    controller.set_source_text("سلام، این یک گزارش است.")
    controller.translate(force=True)

    assert wait_until(lambda: bool(calls))
    assert calls[0] == ("fa", "en", False)


# ---------------------------------------------------------------------------
# 5. A second launch forwards its arguments to the running instance
# ---------------------------------------------------------------------------


class _FakeWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.presented = 0
        self.tabs: list[str] = []
        self.prefills: list[tuple[str, bool]] = []
        self.catalog_opened = 0
        self.pages: dict[str, object] = {}

    def present(self) -> None:
        self.presented += 1

    def select_tab(self, tab: str) -> None:
        self.tabs.append(tab)

    def set_source_text(self, text: str, translate: bool = False) -> None:
        self.prefills.append((text, translate))

    def open_catalog(self) -> None:
        self.catalog_opened += 1


class _FakeWriteView:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def set_source_text(self, text: str) -> None:
        self.texts.append(text)


class _FakeController:
    def __init__(self) -> None:
        self.clipboard = 0
        self.files: list[str] = []
        self.connected = 0
        self.fallback_loaded = 0

    def translate_clipboard(self) -> None:
        self.clipboard += 1

    def start_file_translation(self, path: Path) -> None:
        self.files.append(str(path))

    def connect_and_load_models(self) -> None:
        self.connected += 1

    def load_fallback_models(self) -> None:
        self.fallback_loaded += 1


def test_action_payload_round_trips_every_startup_action():
    args = app_module._parse_args(
        [
            "--prefill",
            "Bonjour",
            "--tab",
            "write",
            "--open-file",
            "a.docx",
            "--write-text",
            "draft",
            "--translate-clipboard",
            "--connect",
            "--catalog",
            "--load-fallback-models",
        ]
    )
    payload = json.loads(json.dumps(app_module._action_payload(args)))
    restored = app_module._actions_from_payload(payload)
    for name in app_module._ACTION_FIELDS:
        assert getattr(restored, name) == getattr(args, name)


def test_second_launch_applies_every_action(qapp, tmp_path):
    """Every action of a launch payload must reach the window and controller.

    This is the logic under test, without the socket: the transport below is
    Qt's, and failing here would point at the wrong layer.
    """
    window = _FakeWindow()
    write_view = _FakeWriteView()
    window.pages["write"] = write_view
    controller = _FakeController()
    target = tmp_path / "report.pdf"
    args = app_module._parse_args(
        [
            "--prefill",
            "Bonjour",
            "--open-file",
            str(target),
            "--write-text",
            "draft",
            "--translate-clipboard",
            "--connect",
            "--catalog",
            "--load-fallback-models",
        ]
    )
    payload = app_module._action_payload(args)
    app_module._handle_instance_message(
        window, controller, json.dumps(payload).encode("utf-8")
    )
    assert wait_until(lambda: bool(controller.files), timeout=5.0), "open file"
    assert wait_until(lambda: bool(controller.clipboard), timeout=5.0), "clipboard"
    assert wait_until(lambda: bool(controller.connected), timeout=5.0), "connect"
    assert wait_until(lambda: bool(controller.fallback_loaded), timeout=5.0), (
        "fallback models"
    )
    assert wait_until(lambda: bool(window.catalog_opened), timeout=5.0), "catalog"
    assert wait_until(lambda: bool(write_view.texts), timeout=5.0), "write text"
    assert window.prefills == [("Bonjour", True)]
    assert controller.files == [str(target)]
    assert controller.clipboard == 1
    assert controller.connected == 1
    assert controller.fallback_loaded == 1
    assert window.catalog_opened == 1
    assert write_view.texts == ["draft"]
    assert "write" in window.tabs
    assert "files" in window.tabs  # --open-file switches to the Files tab


def test_second_launch_applies_its_actions(qapp, tmp_path, monkeypatch):
    key = f"deepl-ofm-test-{uuid.uuid4()}"
    monkeypatch.setattr(app_module, "SINGLE_INSTANCE_KEY", key)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    window = _FakeWindow()
    write_view = _FakeWriteView()
    window.pages["write"] = write_view
    controller = _FakeController()
    # Record what actually crossed the socket: when an effect does not arrive,
    # the failure must say whether the message was wrong or its application was.
    received: list[bytes] = []
    original = app_module._handle_instance_message

    def record(window_, controller_, raw):
        received.append(raw)
        return original(window_, controller_, raw)

    monkeypatch.setattr(app_module, "_handle_instance_message", record)
    server = app_module._install_instance_server(window, controller)
    try:
        assert server.isListening(), server.errorString()
        target = tmp_path / "report.pdf"
        launcher = (
            "import runpy, sys\n"
            "from deepl_ofm import app\n"
            "app.SINGLE_INSTANCE_KEY = sys.argv.pop(1)\n"
            "def reject_duplicate():\n"
            "    raise RuntimeError('second launch tried to start another instance')\n"
            "app.AppController = reject_duplicate\n"
            "runpy.run_module('deepl_ofm', run_name='__main__')\n"
        )
        with subprocess.Popen(
            [
                sys.executable,
                "-c",
                launcher,
                key,
                "--prefill",
                "Bonjour",
                "--open-file",
                str(target),
                "--write-text",
                "draft",
                "--translate-clipboard",
                "--connect",
                "--catalog",
                "--load-fallback-models",
            ],
            cwd=Path(app_module.__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ) as sender:
            try:
                assert wait_until(lambda: sender.poll() is not None, timeout=10.0), "sender"
                output, _ = sender.communicate()
                assert sender.returncode == 0, output.decode("utf-8", errors="replace")
            finally:
                if sender.poll() is None:
                    sender.kill()
        # The connection itself must always be accepted.
        assert wait_until(lambda: window.presented >= 1, timeout=10.0), "accept"
        # Wait for each effect separately so a failure names the effect that did
        # not arrive instead of reporting an opaque `assert []`.  The window is
        # slow on CI runners, hence the generous timeout.
        arrived = wait_until(lambda: bool(window.prefills), timeout=10.0)
        assert arrived, (
            "prefill: received=" + repr(received)
            + " listening=" + repr(server.isListening())
            + " pending=" + repr(server.hasPendingConnections())
            + " presented=" + repr(window.presented)
        )
        assert wait_until(lambda: bool(controller.files), timeout=10.0), "open file"
        assert wait_until(lambda: bool(controller.clipboard), timeout=10.0), "clipboard"
        assert wait_until(lambda: bool(controller.connected), timeout=10.0), "connect"
        assert wait_until(lambda: bool(controller.fallback_loaded), timeout=10.0), (
            "fallback models"
        )
        assert wait_until(lambda: bool(window.catalog_opened), timeout=10.0), "catalog"
        assert wait_until(lambda: bool(write_view.texts), timeout=10.0), "write text"

        assert window.presented >= 1
        assert window.prefills == [("Bonjour", True)]
        assert controller.files == [str(target)]
        assert controller.clipboard == 1
        assert controller.connected == 1
        assert controller.fallback_loaded == 1
        assert window.catalog_opened == 1
        assert write_view.texts == ["draft"]
        assert "write" in window.tabs
        assert "files" in window.tabs  # --open-file switches to the Files tab
    finally:
        server.close()
        window.close()
        window.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------------
# 6. Streamed partial output reaches the pane; history/metrics stay final
# ---------------------------------------------------------------------------


def test_streamed_text_reaches_the_pane_without_being_committed(
    qapp, tmp_path, monkeypatch
):
    controller = _controller(tmp_path)
    view = TranslateView(controller)
    view.show()
    qapp.processEvents()
    partials: list[str] = []
    controller.partialTranslationChanged.connect(partials.append)
    started = threading.Event()
    release = threading.Event()

    def fake(text, **kwargs):
        kwargs["on_progress"](0, 2)
        kwargs["on_partial"]("Привіт")
        started.set()
        release.wait(3)
        kwargs["on_partial"]("Привіт, світе")
        kwargs["on_progress"](1, 1)
        return TranslationOutput(
            text="Привіт, світе!",
            warnings=0,
            duration_ms=31,
            tokens_per_second=7.5,
        )

    monkeypatch.setattr(controller.translator, "translate", fake)
    try:
        controller.set_source_text("Hello, world!")
        controller.translate(force=True)
        assert started.wait(2)
        assert wait_until(lambda: bool(partials))
        assert controller.is_translating
        # The pane state carries the preview; the committed records do not.
        assert controller.translated_text == "Привіт"
        assert controller.last_duration_ms is None
        assert controller.tokens_per_second is None
        assert controller.history.entries == []
        assert view._stack.currentWidget() is view._result_view
        assert "Привіт" in view._result_view.markdown()

        release.set()
        assert wait_until(lambda: controller.translated_text == "Привіт, світе!")
        assert wait_until(lambda: view._result_view.markdown() == "Привіт, світе!")
        assert len(controller.history.entries) == 1
        assert controller.history.entries[0].translated_text == "Привіт, світе!"
        assert controller.last_duration_ms == 31
        assert controller.tokens_per_second == 7.5
    finally:
        release.set()
        view.close()
        view.deleteLater()
        qapp.processEvents()


def test_partial_updates_are_throttled(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    emitted: list[str] = []
    controller.partialTranslationChanged.connect(emitted.append)
    clock = iter([100.0, 100.01, 100.02, 100.06])
    monkeypatch.setattr("deepl_ofm.controller.time.monotonic", lambda: next(clock))
    controller._generation = 1

    controller._on_partial("H", 1)
    controller._on_partial("He", 1)
    controller._on_partial("Hel", 1)
    controller._on_partial("Hell", 1)

    assert emitted == ["H", "Hell"]


def test_stale_partial_output_never_reaches_the_pane(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    partials: list[str] = []
    controller.partialTranslationChanged.connect(partials.append)
    calls: list[str] = []
    started = threading.Event()
    release = threading.Event()

    def fake(text, **kwargs):
        calls.append(text)
        if len(calls) == 1:
            started.set()
            release.wait(3)
            kwargs["on_partial"]("STALE")
            raise TranslationCancelled()
        return TranslationOutput(text="New result", duration_ms=2)

    monkeypatch.setattr(controller.translator, "translate", fake)
    controller.set_source_text("First text")
    controller.translate(force=True)
    assert started.wait(2)

    controller.set_source_text("Second text")
    controller.translate(force=True)
    assert wait_until(lambda: controller.translated_text == "New result")
    release.set()
    # Give the cancelled worker a chance to deliver its queued partial.
    assert wait_until(lambda: not controller.is_translating, timeout=1.0)
    qapp.processEvents()
    time.sleep(0.06)
    qapp.processEvents()

    assert "STALE" not in partials
    assert controller.translated_text == "New result"
