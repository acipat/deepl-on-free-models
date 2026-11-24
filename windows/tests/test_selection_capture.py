"""Selected-text capture: one shot per gesture, never copying from ourselves."""

from __future__ import annotations

import ctypes
import os
import types
from ctypes import wintypes
from pathlib import Path

from deepl_ofm.controller import AppController
from deepl_ofm.core.settings import AppSettings
from deepl_ofm.services.history import HistoryStore
from deepl_ofm.support import selection


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


def _win32() -> tuple[types.SimpleNamespace, types.SimpleNamespace]:
    user32 = types.SimpleNamespace(
        GetClipboardSequenceNumber=_FakeFunction(0),
        GetAsyncKeyState=_FakeFunction(0),
        GetForegroundWindow=_FakeFunction(0),
        GetWindowThreadProcessId=_FakeFunction(0),
        keybd_event=_FakeFunction(None),
    )
    kernel32 = types.SimpleNamespace()
    return user32, kernel32


def _use_win32(monkeypatch, user32, kernel32) -> None:
    monkeypatch.setattr(selection, "_WINDOWS", True)
    monkeypatch.setattr(selection, "_USER32", user32)
    monkeypatch.setattr(selection, "_KERNEL32", kernel32)


def _controller(tmp_path: Path) -> AppController:
    settings = AppSettings(path=tmp_path / "settings.json")
    settings.auto_translate = False
    settings.last_source_code = "en"
    settings.last_target_code = "uk"
    return AppController(
        settings=settings,
        history=HistoryStore(path=tmp_path / "history.json"),
    )


def _patched_capture(monkeypatch, texts: list[str]) -> list[str]:
    pending = iter(texts)
    calls: list[str] = []

    def fake_capture(**_kwargs: object) -> str:
        calls.append("capture")
        return next(pending)

    monkeypatch.setattr("deepl_ofm.support.selection.is_supported", lambda: True)
    monkeypatch.setattr("deepl_ofm.support.selection.capture_selection", fake_capture)
    return calls


# ---------------------------------------------------------------------------
# Controller: a queued duplicate must not run a second capture
# ---------------------------------------------------------------------------


def test_queued_selection_call_is_dropped(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    calls = _patched_capture(monkeypatch, ["Selected sentence", ""])
    monkeypatch.setattr(controller, "translate", lambda force=False: None)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)

    controller.translate_selection()
    controller.translate_selection()

    assert calls == ["capture"]
    assert controller.source_text == "Selected sentence"
    assert controller.error_message is None
    assert errors == []


def test_a_later_successful_capture_clears_the_banner(qapp, tmp_path, monkeypatch):
    controller = _controller(tmp_path)
    _patched_capture(monkeypatch, ["", "Selected sentence"])
    monkeypatch.setattr(controller, "translate", lambda force=False: None)
    errors: list[str] = []
    controller.errorRaised.connect(errors.append)
    clock = [100.0]
    monkeypatch.setattr("deepl_ofm.controller.time.monotonic", lambda: clock[0])

    controller.translate_selection()
    assert controller.error_message is not None
    assert "administrator" in errors[-1]

    clock[0] = 101.5  # the user waits a moment, then tries again
    controller.translate_selection()

    assert controller.error_message is None
    assert errors[-1] == ""
    assert controller.source_text == "Selected sentence"


# ---------------------------------------------------------------------------
# Selection module: never copy from our own window, wait for late clipboard text
# ---------------------------------------------------------------------------


def test_capture_ignores_a_foreground_window_owned_by_us(monkeypatch):
    user32, kernel32 = _win32()
    user32.GetForegroundWindow.result = 0x1234

    def own_process(window, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))[0] = os.getpid()
        return 1

    user32.GetWindowThreadProcessId = own_process
    _use_win32(monkeypatch, user32, kernel32)

    assert selection.capture_selection() == ""
    assert user32.keybd_event.calls == []
    assert user32.GetClipboardSequenceNumber.calls == []


def test_capture_sends_ctrl_c_to_a_foreign_foreground_window(monkeypatch):
    user32, kernel32 = _win32()
    user32.GetForegroundWindow.result = 0x1234

    def foreign_process(window, pointer):
        ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))[0] = os.getpid() + 1
        return 1

    user32.GetWindowThreadProcessId = foreign_process
    sequence = iter([10, 11])
    user32.GetClipboardSequenceNumber = lambda: next(sequence, 11)
    monkeypatch.setattr(selection, "_clipboard_text", lambda: "selected text")
    _use_win32(monkeypatch, user32, kernel32)

    assert selection.capture_selection(timeout_ms=100) == "selected text"
    assert len(user32.keybd_event.calls) == 4


def test_clipboard_retries_until_the_text_is_published(monkeypatch):
    user32, kernel32 = _win32()
    sequence = iter([10, 11])
    user32.GetClipboardSequenceNumber = lambda: next(sequence, 11)
    reads = iter(["", "", "published text"])
    monkeypatch.setattr(selection, "_clipboard_text", lambda: next(reads, "published text"))
    _use_win32(monkeypatch, user32, kernel32)

    assert selection.capture_selection(timeout_ms=500) == "published text"
