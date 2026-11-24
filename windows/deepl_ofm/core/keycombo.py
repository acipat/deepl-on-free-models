"""Keyboard shortcut value object with Windows semantics.

Replaces ``Sources/HyMT/Models/KeyCombo.swift``: the Carbon key code plus a
modifier bit mask become a normalised key name plus four booleans, with ⌘ mapped
to Ctrl and ⌥ to Alt. ``to_dict``/``from_dict`` also understand the legacy
``label``/``modifiers`` shape of the Swift ``Codable`` representation.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, fields
from typing import Any, Mapping

_QT_SHIFT = 0x02000000
_QT_CONTROL = 0x04000000
_QT_ALT = 0x08000000
_QT_META = 0x10000000
_QT_MODIFIER_MASK = _QT_SHIFT | _QT_CONTROL | _QT_ALT | _QT_META
_QT_KEY_MASK = 0x01FFFFFF

# AppKit modifier flags, used only to read short cuts stored by the macOS app.
_NS_COMMAND = 0x100000
_NS_OPTION = 0x80000
_NS_CONTROL = 0x40000
_NS_SHIFT = 0x20000

_FUNCTION_KEY_RE = re.compile(r"f(?:[1-9]|1[0-9]|2[0-4])")

# key -> (display name, Qt sequence name, Qt key code)
_NAMED_KEYS: dict[str, tuple[str, str, int]] = {
    "space": ("Space", "Space", 0x20),
    "enter": ("Enter", "Return", 0x01000004),
    "return": ("Enter", "Return", 0x01000004),
    "esc": ("Esc", "Esc", 0x01000000),
    "escape": ("Esc", "Esc", 0x01000000),
    "tab": ("Tab", "Tab", 0x01000001),
    "backspace": ("Backspace", "Backspace", 0x01000003),
    "delete": ("Delete", "Del", 0x01000007),
    "del": ("Delete", "Del", 0x01000007),
    "insert": ("Insert", "Ins", 0x01000006),
    "ins": ("Insert", "Ins", 0x01000006),
    "home": ("Home", "Home", 0x01000010),
    "end": ("End", "End", 0x01000011),
    "left": ("Left", "Left", 0x01000012),
    "right": ("Right", "Right", 0x01000014),
    "up": ("Up", "Up", 0x01000013),
    "down": ("Down", "Down", 0x01000015),
    "pageup": ("Page Up", "PgUp", 0x01000016),
    "pgup": ("Page Up", "PgUp", 0x01000016),
    "pagedown": ("Page Down", "PgDn", 0x01000017),
    "pgdn": ("Page Down", "PgDn", 0x01000017),
    "print": ("Print Screen", "Print", 0x01000009),
    "printscreen": ("Print Screen", "Print", 0x01000009),
    "pause": ("Pause", "Pause", 0x01000008),
    "menu": ("Menu", "Menu", 0x01000055),
    "capslock": ("Caps Lock", "CapsLock", 0x01000024),
    "numlock": ("Num Lock", "NumLock", 0x01000025),
    "scrolllock": ("Scroll Lock", "ScrollLock", 0x01000026),
}

# Punctuation keys: display character, Qt name, Qt key code.
_PUNCTUATION_KEYS: dict[str, tuple[str, str, int]] = {
    "=": ("=", "Equal", 0x3D),
    "-": ("-", "Minus", 0x2D),
    "]": ("]", "BracketRight", 0x5D),
    "[": ("[", "BracketLeft", 0x5B),
    "'": ("'", "Apostrophe", 0x27),
    ";": (";", "Semicolon", 0x3B),
    "\\": ("\\", "Backslash", 0x5C),
    ",": (",", "Comma", 0x2C),
    "/": ("/", "Slash", 0x2F),
    ".": (".", "Period", 0x2E),
    "`": ("`", "QuoteLeft", 0x60),
    "+": ("+", "Plus", 0x2B),
    "*": ("*", "Asterisk", 0x2A),
}


def _normalize_key(value: Any) -> str:
    """Return the canonical lower-case key name, or ``""`` for unusable input."""
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if len(text) > 1:
        text = re.sub(r"[\s_\-]+", "", text)
    lowered = text.lower()
    if len(lowered) > 24:
        return ""
    for character in lowered:
        code = ord(character)
        if code < 0x20 or 0x7F <= code <= 0x9F:
            return ""
        if 0xF700 <= code <= 0xF8FF:  # Apple private use area (arrows, function keys)
            return ""
        if unicodedata.combining(character):
            return ""
    return lowered


def _int_value(value: Any) -> int | None:
    """Read an int out of a plain number or a Qt enum member/flag."""
    try:
        return int(getattr(value, "value", value))
    except (TypeError, ValueError):
        return None


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return False


def _flag(data: Mapping[str, Any], *names: str) -> bool:
    for name in names:
        if name in data:
            return _bool_value(data[name])
    return False


@dataclass(frozen=True)
class KeyCombo:
    """A shortcut: one key plus modifier flags (Ctrl is kept as ``command``)."""

    key: str
    command: bool = False  # Ctrl on Windows (kept as `command` for parity)
    option: bool = False  # Alt
    control: bool = False  # ⌃ from the macOS build; treated as Ctrl when displaying
    shift: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _normalize_key(self.key))

    @property
    def display(self) -> str:
        """Human readable shortcut, e.g. ``Ctrl+Alt+T``."""
        parts: list[str] = []
        if self.command or self.control:
            parts.append("Ctrl")
        if self.option:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        key = self._key_display()
        if key:
            parts.append(key)
        return "+".join(parts)

    @property
    def qt_sequence(self) -> str:
        """Shortcut string accepted by ``QKeySequence``, e.g. ``Ctrl+Alt+T``."""
        parts: list[str] = []
        if self.command or self.control:
            parts.append("Ctrl")
        if self.option:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        key = self._key_qt()
        if key:
            parts.append(key)
        return "+".join(parts)

    @property
    def is_valid(self) -> bool:
        """True when a usable key with at least one of Ctrl/Alt/⌃ is present."""
        if not self.key:
            return False
        return bool(self.command or self.option or self.control)

    def matches(self, event: Any) -> bool:
        """Return True when a ``QKeyEvent`` (or a duck-typed lookalike) matches."""
        try:
            modifiers = _int_value(event.modifiers())
            key_code = _int_value(event.key())
        except (AttributeError, TypeError):
            return False
        if modifiers is None or key_code is None:
            return False
        expected = 0
        if self.command or self.control:
            expected |= _QT_CONTROL
        if self.option:
            expected |= _QT_ALT
        if self.shift:
            expected |= _QT_SHIFT
        if modifiers & _QT_MODIFIER_MASK != expected:
            return False
        expected_key = self._qt_key_code()
        if expected_key is None:
            return False
        return key_code & _QT_KEY_MASK == expected_key

    @staticmethod
    def standard() -> "KeyCombo":
        """Default translate shortcut: Ctrl+Alt+T."""
        return KeyCombo(key="t", command=True, option=True)

    @staticmethod
    def selection() -> "KeyCombo":
        """Default selection translate shortcut: Ctrl+Alt+C."""
        return KeyCombo(key="c", command=True, option=True)

    @staticmethod
    def normalized_label(value: str | None) -> str | None:
        """Port of ``KeyCombo.normalizedLabel`` (label accepted for display)."""
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        if not trimmed or len(trimmed) > 3:
            return None
        for character in trimmed:
            code = ord(character)
            if code < 0x20 or 0x7F <= code <= 0x9F:
                return None
            if 0xF700 <= code <= 0xF8FF:
                return None
            if unicodedata.combining(character):
                return None
        return trimmed.upper() if len(trimmed) == 1 else trimmed

    def to_dict(self) -> dict[str, Any]:
        """Serialise the combo; field names match the dataclass attributes."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def from_dict(cls, data: Any) -> "KeyCombo":
        """Tolerant parser for :meth:`to_dict` output and the Swift Codable shape."""
        if isinstance(data, cls):
            return data
        if isinstance(data, (bytes, bytearray)):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                return cls(key="")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (TypeError, ValueError):
                return cls(key="")
        if not isinstance(data, Mapping):
            return cls(key="")

        raw_key = data.get("key")
        if raw_key is None:
            raw_key = data.get("label")
        key = _normalize_key(raw_key)

        if any(name in data for name in ("command", "cmd", "ctrl", "option", "alt",
                                         "control", "shift")):
            command = _flag(data, "command", "cmd", "ctrl")
            option = _flag(data, "option", "alt")
            control = _flag(data, "control")
            shift = _flag(data, "shift")
        else:
            modifiers = _int_value(data.get("modifiers"))
            if modifiers is None:
                command = option = control = shift = False
            else:
                command = bool(modifiers & _NS_COMMAND)
                option = bool(modifiers & _NS_OPTION)
                control = bool(modifiers & _NS_CONTROL)
                shift = bool(modifiers & _NS_SHIFT)
        return cls(key=key, command=command, option=option, control=control, shift=shift)

    def __str__(self) -> str:
        return self.display

    def _key_display(self) -> str:
        if not self.key:
            return ""
        named = _NAMED_KEYS.get(self.key)
        if named is not None:
            return named[0]
        if _FUNCTION_KEY_RE.fullmatch(self.key):
            return self.key.upper()
        if len(self.key) == 1:
            return self.key.upper()
        return self.key.replace("_", " ").title()

    def _key_qt(self) -> str:
        if not self.key:
            return ""
        named = _NAMED_KEYS.get(self.key)
        if named is not None:
            return named[1]
        if _FUNCTION_KEY_RE.fullmatch(self.key):
            return self.key.upper()
        if len(self.key) == 1:
            punctuation = _PUNCTUATION_KEYS.get(self.key)
            if punctuation is not None:
                return punctuation[1]
            return self.key.upper()
        return self._key_display()

    def _qt_key_code(self) -> int | None:
        if not self.key:
            return None
        named = _NAMED_KEYS.get(self.key)
        if named is not None:
            return named[2]
        if _FUNCTION_KEY_RE.fullmatch(self.key):
            number = int(self.key[1:])
            return 0x01000030 + number - 1
        if len(self.key) != 1:
            return None
        punctuation = _PUNCTUATION_KEYS.get(self.key)
        if punctuation is not None:
            return punctuation[2]
        if self.key.isascii() and self.key.isalnum():
            return ord(self.key.upper())
        return ord(self.key.upper()) if len(self.key.upper()) == 1 else None
