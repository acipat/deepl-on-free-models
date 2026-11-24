"""System-wide hotkeys.

Ported from ``Sources/HyMT/Services/HotKeyManager.swift``.  Windows is the only
supported platform: a dedicated ``QThread`` owns ``RegisterHotKey`` and the
``GetMessageW`` loop (a hotkey message is posted to the thread that registered
it), then hands presses back to the GUI thread through a queued Qt signal.
Elsewhere ``register`` refuses politely instead of raising.
"""
from __future__ import annotations

import ctypes
import logging
import queue
import re
import sys
import threading
from typing import Any

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, Signal

logger = logging.getLogger(__name__)

_WINDOWS = sys.platform == "win32"

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_APP = 0x8000

_MSG_UNSUPPORTED = "Global shortcuts are only available on Windows."
_MSG_INVALID = "This shortcut needs Ctrl or Alt."
_MSG_COULD_NOT_REGISTER = "Could not register %@. The shortcut may be taken."

try:
    from deepl_ofm.i18n import t as _t
except Exception:  # pragma: no cover - the catalogue is always present in the app
    def _t(key: str, language: Any = None) -> str:
        return key


def _tr(key: str, language: Any = None) -> str:
    try:
        return _t(key, language)
    except Exception:
        return key


class HotkeyError(Exception):
    """A registration problem with a localisable, user-facing message."""

    def __init__(
        self,
        message: str = "",
        *,
        kind: str = "failed",
        combo_display: str = "",
        detail: str = "",
    ) -> None:
        if not message:
            message = {
                "unsupported": _MSG_UNSUPPORTED,
                "invalid": _MSG_INVALID,
            }.get(kind, _MSG_COULD_NOT_REGISTER)
        super().__init__(message)
        self.kind = kind
        self.combo_display = combo_display
        self.detail = detail
        self._source = message

    def message(self, language: Any = None) -> str:
        text = _tr(self._source, language)
        replacement = self.combo_display or "the shortcut"
        text = text.replace("%@", replacement)
        text = text.replace("{}", replacement)
        return text

    def __str__(self) -> str:
        return self.message()


_NAMED_VK: dict[str, int] = {
    "space": 0x20,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pgup": 0x21,
    "prior": 0x21,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "next": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "print": 0x2C,
    "menu": 0x5D,
    "pause": 0x13,
    "capslock": 0x14,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "plus": 0xBB,
    "minus": 0xBD,
    "comma": 0xBC,
    "period": 0xBE,
    "slash": 0xBF,
    "backslash": 0xDC,
    "semicolon": 0xBA,
    "quote": 0xDE,
    "grave": 0xC0,
    "bracketleft": 0xDB,
    "bracketright": 0xDD,
}

# US-layout virtual-key codes for unshifted punctuation.
_PUNCT_VK: dict[str, int] = {
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}

# Characters that need Shift on a US layout: character -> virtual-key code.
_SHIFTED_VK: dict[str, int] = {
    "!": 0x31,
    "@": 0x32,
    "#": 0x33,
    "$": 0x34,
    "%": 0x35,
    "^": 0x36,
    "&": 0x37,
    "*": 0x38,
    "(": 0x39,
    ")": 0x30,
    ":": 0xBA,
    "+": 0xBB,
    "<": 0xBC,
    "_": 0xBD,
    ">": 0xBE,
    "?": 0xBF,
    "~": 0xC0,
    "{": 0xDB,
    "|": 0xDC,
    "}": 0xDD,
    '"': 0xDE,
}

_FKEY_RE = re.compile(r"f([1-9]|1[0-9]|2[0-4])")


class _Win32:
    """Lazily loaded user32/kernel32 entry points (Windows only)."""

    def __init__(self) -> None:
        from ctypes import wintypes

        self.ctypes = ctypes
        self.wintypes = wintypes
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        user32 = self.user32
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.UnregisterHotKey.restype = wintypes.BOOL
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL
        user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostThreadMessageW.restype = wintypes.BOOL
        user32.VkKeyScanW.argtypes = [ctypes.c_wchar]
        user32.VkKeyScanW.restype = ctypes.c_short

        self.kernel32.GetCurrentThreadId.argtypes = []
        self.kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    def msg(self) -> Any:
        return self.wintypes.MSG()


_win32_instance: _Win32 | None = None
_win32_failed = False
_win32_lock = threading.Lock()


def _win32() -> _Win32 | None:
    global _win32_instance, _win32_failed
    if not _WINDOWS:
        return None
    with _win32_lock:
        if _win32_instance is None and not _win32_failed:
            try:
                _win32_instance = _Win32()
            except Exception:
                _win32_failed = True
                logger.exception("could not load the Windows hotkey API")
        return _win32_instance


def _vk_key_scan(character: str) -> int:
    """Map a single character to a virtual-key code through the keyboard layout."""
    api = _win32()
    if api is None:
        return 0
    try:
        result = int(api.user32.VkKeyScanW(character))
    except Exception:
        return 0
    if result == -1:
        return 0
    return result & 0xFF


def _virtual_key(key: str) -> tuple[int, bool]:
    """Return ``(virtual_key, needs_shift)`` for a ``KeyCombo.key`` value."""
    value = (key or "").strip()
    if not value:
        return 0, False

    if len(value) == 1:
        character = value
        upper = character.upper()
        if character.isascii() and "A" <= upper <= "Z":
            return ord(upper), False
        if "0" <= character <= "9":
            return ord(character), False
        if character in _PUNCT_VK:
            return _PUNCT_VK[character], False
        if character in _SHIFTED_VK:
            return _SHIFTED_VK[character], True
        return _vk_key_scan(character), False

    lowered = value.lower()
    if lowered in _NAMED_VK:
        return _NAMED_VK[lowered], False
    match = _FKEY_RE.fullmatch(lowered)
    if match:
        return 0x70 + int(match.group(1)) - 1, False
    return 0, False


def _modifiers_and_vk(combo: Any) -> tuple[int, int]:
    """Translate a ``KeyCombo`` into ``(MOD_* flags, virtual-key code)``.

    ``command`` is the macOS ⌘ flag, mapped to Ctrl on Windows, so both
    ``command`` and ``control`` produce ``MOD_CONTROL``.
    """
    modifiers = 0
    if getattr(combo, "command", False) or getattr(combo, "control", False):
        modifiers |= MOD_CONTROL
    if getattr(combo, "option", False) or getattr(combo, "alt", False):
        modifiers |= MOD_ALT
    if getattr(combo, "shift", False):
        modifiers |= MOD_SHIFT
    if getattr(combo, "win", False) or getattr(combo, "meta", False):
        modifiers |= MOD_WIN
    vk, needs_shift = _virtual_key(getattr(combo, "key", ""))
    if needs_shift:
        modifiers |= MOD_SHIFT
    return modifiers, vk


def _combo_is_valid(combo: Any) -> bool:
    try:
        declared = getattr(combo, "is_valid", None)
    except Exception:
        declared = None
    if isinstance(declared, bool):
        return declared
    command = bool(
        getattr(combo, "command", False) or getattr(combo, "control", False)
    )
    option = bool(getattr(combo, "option", False) or getattr(combo, "alt", False))
    return command or option


def _combo_display(combo: Any) -> str:
    try:
        declared = getattr(combo, "display", None)
        if isinstance(declared, str) and declared:
            return declared
    except Exception:
        pass
    parts: list[str] = []
    if getattr(combo, "command", False) or getattr(combo, "control", False):
        parts.append("Ctrl")
    if getattr(combo, "option", False) or getattr(combo, "alt", False):
        parts.append("Alt")
    if getattr(combo, "shift", False):
        parts.append("Shift")
    if getattr(combo, "win", False) or getattr(combo, "meta", False):
        parts.append("Win")
    key = str(getattr(combo, "key", "") or "").strip()
    if key:
        parts.append(key.upper() if len(key) == 1 else key.title())
    return "+".join(parts)


class _HotkeyThread(QThread):
    """Owns the Windows message queue: registration and ``WM_HOTKEY`` reception."""

    hotkey_pressed = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._commands: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._thread_id = 0
        self._stopping = False
        self._registered: dict[int, tuple[int, int]] = {}

    # -- control from the GUI thread ---------------------------------------

    def wait_ready(self, timeout: float) -> bool:
        return self._ready.wait(timeout)

    def request_register(
        self, hotkey_id: int, modifiers: int, vk: int
    ) -> tuple[bool, int]:
        reply = threading.Event()
        box: dict[str, Any] = {"ok": False, "error": 0}
        self._commands.put(("register", hotkey_id, modifiers, vk, reply, box))
        self._wake()
        if not reply.wait(2.0):
            return False, -1
        return bool(box["ok"]), int(box["error"])

    def request_unregister(self, hotkey_id: int) -> None:
        if not self.isRunning():
            return
        reply = threading.Event()
        self._commands.put(("unregister", hotkey_id, reply))
        self._wake()
        if not reply.wait(1.0):
            logger.warning("hotkey thread did not acknowledge unregister")

    def stop(self, timeout_ms: int = 3000) -> None:
        if not self.isRunning():
            return
        reply = threading.Event()
        self._commands.put(("shutdown", reply))
        self._wake()
        if not reply.wait(1.0):
            logger.warning("hotkey thread did not acknowledge shutdown")
        if not self.wait(timeout_ms):
            logger.warning("hotkey thread did not stop; terminating it")
            self.terminate()
            self.wait(1000)

    def _wake(self) -> None:
        api = _win32()
        thread_id = self._thread_id
        if api is None or not thread_id:
            return
        try:
            api.user32.PostThreadMessageW(thread_id, WM_APP + 1, 0, 0)
        except Exception:
            logger.debug("could not wake the hotkey thread", exc_info=True)

    # -- worker thread ------------------------------------------------------

    def run(self) -> None:  # noqa: D401 - QThread entry point
        api = _win32()
        if api is None:
            self._ready.set()
            return
        ctypes_module = api.ctypes
        user32 = api.user32
        self._thread_id = int(api.kernel32.GetCurrentThreadId())
        message = api.msg()
        # Create this thread's message queue before anyone posts to it.
        user32.PeekMessageW(
            ctypes_module.byref(message), None, WM_APP, WM_APP, 0
        )
        self._ready.set()
        try:
            while True:
                self._drain_commands()
                if self._stopping:
                    break
                result = user32.GetMessageW(
                    ctypes_module.byref(message), None, 0, 0
                )
                if result == 0 or result == -1:
                    break
                if message.message == WM_HOTKEY:
                    self.hotkey_pressed.emit(int(message.wParam))
        except Exception:
            logger.exception("hotkey message loop failed")
        finally:
            for hotkey_id in list(self._registered):
                try:
                    user32.UnregisterHotKey(None, hotkey_id)
                except Exception:
                    pass
            self._registered.clear()
            self._thread_id = 0
            self._ready.set()

    def _drain_commands(self) -> None:
        api = _win32()
        while True:
            try:
                command = self._commands.get_nowait()
            except queue.Empty:
                return
            kind = command[0]
            if kind == "register":
                _, hotkey_id, modifiers, vk, reply, box = command
                ok = False
                error = 0
                if api is not None:
                    try:
                        ok = bool(
                            api.user32.RegisterHotKey(
                                None,
                                hotkey_id,
                                modifiers | MOD_NOREPEAT,
                                vk,
                            )
                        )
                    except Exception:
                        ok = False
                    if not ok:
                        error = int(api.ctypes.get_last_error())
                box["ok"] = ok
                box["error"] = error
                if ok:
                    self._registered[hotkey_id] = (modifiers, vk)
                reply.set()
            elif kind == "unregister":
                _, hotkey_id, reply = command
                if api is not None and hotkey_id in self._registered:
                    try:
                        api.user32.UnregisterHotKey(None, hotkey_id)
                    except Exception:
                        pass
                    self._registered.pop(hotkey_id, None)
                reply.set()
            elif kind == "shutdown":
                _, reply = command
                if api is not None:
                    for hotkey_id in list(self._registered):
                        try:
                            api.user32.UnregisterHotKey(None, hotkey_id)
                        except Exception:
                            pass
                self._registered.clear()
                self._stopping = True
                reply.set()
                return


class HotkeyManager(QObject):
    """Registers system-wide shortcuts and re-emits presses as ``triggered``."""

    triggered = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._actions: dict[str, int] = {}
        self._next_id = 10
        self._thread: _HotkeyThread | None = None

    # -- public API ---------------------------------------------------------

    def is_supported(self) -> bool:
        return _WINDOWS and _win32() is not None

    def register(self, action: str, combo: Any) -> bool:
        name = (action or "").strip()
        if not name:
            self.error.emit(HotkeyError(kind="invalid").message())
            return False
        if not self.is_supported():
            self.error.emit(HotkeyError(kind="unsupported").message())
            return False
        if not _combo_is_valid(combo):
            self.error.emit(
                HotkeyError(
                    kind="invalid", combo_display=_combo_display(combo)
                ).message()
            )
            return False

        modifiers, vk = _modifiers_and_vk(combo)
        display = _combo_display(combo)
        if vk == 0:
            logger.warning("unsupported hotkey key: %r", getattr(combo, "key", ""))
            self.error.emit(
                HotkeyError(kind="invalid", combo_display=display).message()
            )
            return False

        with self._lock:
            if name in self._actions:
                self.unregister(name)
            thread = self._ensure_thread()
            if thread is None:
                self.error.emit(
                    HotkeyError(kind="failed", combo_display=display).message()
                )
                return False
            hotkey_id = self._next_id
            self._next_id += 1
            ok, error_code = thread.request_register(hotkey_id, modifiers, vk)
            if not ok:
                logger.warning(
                    "RegisterHotKey failed for %s (error %s)", display, error_code
                )
                self.error.emit(
                    HotkeyError(
                        kind="failed",
                        combo_display=display,
                        detail=str(error_code),
                    ).message()
                )
                return False
            self._actions[name] = hotkey_id
        return True

    def unregister(self, action: str) -> None:
        with self._lock:
            hotkey_id = self._actions.pop((action or "").strip(), None)
            thread = self._thread
            if hotkey_id is None or thread is None:
                return
            thread.request_unregister(hotkey_id)

    def unregister_all(self) -> None:
        with self._lock:
            self._actions.clear()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.stop()

    # -- internals ----------------------------------------------------------

    def _ensure_thread(self) -> _HotkeyThread | None:
        if self._thread is not None and self._thread.isRunning():
            return self._thread
        if _win32() is None:
            return None
        thread = _HotkeyThread()
        thread.hotkey_pressed.connect(
            self._on_hotkey_pressed, Qt.ConnectionType.QueuedConnection
        )
        thread.start()
        if not thread.wait_ready(2.0):
            logger.warning("hotkey thread did not start")
            thread.stop()
            return None
        self._thread = thread
        app = QCoreApplication.instance()
        if app is not None:
            try:
                app.aboutToQuit.connect(self.unregister_all)
            except Exception:
                logger.debug("could not hook aboutToQuit", exc_info=True)
        return thread

    def _on_hotkey_pressed(self, hotkey_id: int) -> None:
        with self._lock:
            action = next(
                (
                    name
                    for name, identifier in self._actions.items()
                    if identifier == hotkey_id
                ),
                "",
            )
        if action:
            logger.debug("hotkey pressed: %s", action)
            self.triggered.emit(action)

    def __del__(self) -> None:  # pragma: no cover - interpreter shutdown path
        try:
            self.unregister_all()
        except Exception:
            pass
