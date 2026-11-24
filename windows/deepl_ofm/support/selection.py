"""Capture the text selected in the foreground Windows application.

Counterpart of the ``⌘C`` dance in ``Sources/HyMT/AppState.swift``
(``translateSelection``): the app presses Copy in the other program and reads
what landed on the clipboard.  Unlike macOS this needs no Accessibility grant,
but there are three Windows-specific traps that this module handles:

1. the global hotkey fires while Ctrl and Alt are still physically held down, so
   a naive synthetic Ctrl+C reaches the target as Ctrl+Alt+C and does nothing —
   we wait (briefly) for the keys to be released and force-release them if not;
2. the clipboard may not be updated yet — we wait for the clipboard sequence
   number to change instead of sleeping for a fixed time;
3. an elevated target (UIPI) silently ignores synthetic input — the caller gets
   an empty string, not a stale clipboard.

The module is Windows-only and import-safe everywhere; Qt is not imported so it
can run from any thread.
"""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import time
from ctypes import wintypes

logger = logging.getLogger(__name__)

_WINDOWS = sys.platform == "win32"

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_C = 0x43
KEYEVENTF_KEYUP = 0x0002
CF_UNICODETEXT = 13
_MODIFIERS = (VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN)


def _declare(library: object, name: str, restype: object, argtypes: tuple[object, ...]) -> None:
    """Give one imported Win32 function an exact prototype.

    ``ctypes`` assumes a C ``int`` return value for functions without a
    ``restype``.  On Windows x64 that truncates the 64-bit clipboard handle and
    the pointer returned by ``GlobalLock`` to 32 bits, so reading the selection
    either faults or returns garbage instead of the copied text.
    """
    function = getattr(library, name)
    function.restype = restype  # type: ignore[attr-defined]
    function.argtypes = list(argtypes)  # type: ignore[attr-defined]


def _install_prototypes(user32: object, kernel32: object) -> None:
    """Declare every Win32 signature this module calls (64-bit safe)."""
    _declare(user32, "OpenClipboard", wintypes.BOOL, (wintypes.HWND,))
    _declare(user32, "GetClipboardData", wintypes.HANDLE, (wintypes.UINT,))
    _declare(user32, "CloseClipboard", wintypes.BOOL, ())
    _declare(user32, "GetClipboardSequenceNumber", wintypes.DWORD, ())
    _declare(user32, "GetAsyncKeyState", wintypes.SHORT, (ctypes.c_int,))
    _declare(user32, "GetForegroundWindow", wintypes.HWND, ())
    _declare(
        user32,
        "GetWindowThreadProcessId",
        wintypes.DWORD,
        (wintypes.HWND, ctypes.POINTER(wintypes.DWORD)),
    )
    _declare(
        user32,
        "keybd_event",
        None,
        (wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t),
    )
    _declare(kernel32, "GlobalLock", wintypes.LPVOID, (wintypes.HGLOBAL,))
    _declare(kernel32, "GlobalUnlock", wintypes.BOOL, (wintypes.HGLOBAL,))


if _WINDOWS:  # pragma: no cover - exercised on Windows only
    _USER32: object | None = ctypes.WinDLL("user32", use_last_error=True)
    _KERNEL32: object | None = ctypes.WinDLL("kernel32", use_last_error=True)
    _install_prototypes(_USER32, _KERNEL32)
else:
    _USER32 = None
    _KERNEL32 = None


def is_supported() -> bool:
    """Selected-text translation is implemented for Windows only."""
    return _WINDOWS


def capture_selection(*, timeout_ms: int = 700, modifier_wait_ms: int = 300) -> str:
    """Return the text selected in the foreground window, or ``""``.

    Blocks for at most ``modifier_wait_ms + timeout_ms``; call it from the GUI
    thread before the window is shown, so nothing visibly freezes.
    """
    if not _WINDOWS or _USER32 is None:
        return ""
    if _foreground_is_ours():
        # Copying from our own window can never be what the user meant, and the
        # synthetic Ctrl+C would otherwise land in the source box.
        logger.info("the foreground window belongs to this process; not copying")
        return ""
    try:
        user32 = _USER32
        before = int(user32.GetClipboardSequenceNumber())
    except Exception:
        before = -1

    _wait_for_modifier_release(modifier_wait_ms)
    _send_ctrl_c()

    deadline = time.monotonic() + timeout_ms / 1000.0
    changed = False
    while time.monotonic() < deadline:
        try:
            if int(user32.GetClipboardSequenceNumber()) != before:
                changed = True
                break
        except Exception:  # pragma: no cover - defensive
            break
        time.sleep(0.01)
    if not changed:
        logger.info("no clipboard update after Ctrl+C; the selection was not captured")
        return ""

    # Chrome, Word and Electron empty the clipboard before publishing the copied
    # text, so the first read after the sequence change can still be empty.
    while time.monotonic() < deadline:
        text = _clipboard_text()
        if text:
            return text
        time.sleep(0.02)
    logger.info("the clipboard changed but no text became available")
    return ""


# --------------------------------------------------------------------------
# Windows helpers
# --------------------------------------------------------------------------
def _modifier_is_down(user32: object, key: int) -> bool:
    try:
        return bool(user32.GetAsyncKeyState(key) & 0x8000)
    except Exception:  # pragma: no cover - defensive
        return False


def _foreground_is_ours() -> bool:
    """Whether this process owns the current foreground window."""
    if _USER32 is None:
        return False
    try:
        window = _USER32.GetForegroundWindow()
        if not window:
            return False
        process_id = wintypes.DWORD()
        _USER32.GetWindowThreadProcessId(window, ctypes.byref(process_id))
        return int(process_id.value) == os.getpid()
    except Exception:  # pragma: no cover - defensive
        return False


def _wait_for_modifier_release(timeout_ms: int) -> bool:
    """Wait until the user lets go of the hotkey modifiers."""
    if not _WINDOWS or _USER32 is None:
        return True
    user32 = _USER32
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if not any(_modifier_is_down(user32, key) for key in _MODIFIERS):
            return True
        time.sleep(0.01)
    # The user is still holding the combination: release it synthetically so the
    # target sees a plain Ctrl+C. Windows resyncs on the next physical key event.
    for key in _MODIFIERS:
        try:
            user32.keybd_event(key, 0, KEYEVENTF_KEYUP, 0)
        except Exception:  # pragma: no cover - defensive
            pass
    time.sleep(0.03)
    return False


def _send_ctrl_c() -> None:
    if _USER32 is None:
        return
    user32 = _USER32
    try:
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_C, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_C, 0, KEYEVENTF_KEYUP, 0)
        time.sleep(0.01)
        user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not send Ctrl+C", exc_info=True)


def _clipboard_text() -> str:
    """Read CF_UNICODETEXT without Qt, so this works off the GUI thread too."""
    if not _WINDOWS or _USER32 is None or _KERNEL32 is None:
        return ""
    user32 = _USER32
    kernel32 = _KERNEL32
    handle = None
    try:
        if not user32.OpenClipboard(None):
            return ""
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            return ""
        try:
            return ctypes.wstring_at(pointer)
        finally:
            kernel32.GlobalUnlock(handle)
    except Exception:  # pragma: no cover - defensive
        logger.debug("could not read the clipboard", exc_info=True)
        return ""
    finally:
        try:
            user32.CloseClipboard()
        except Exception:  # pragma: no cover - defensive
            pass
