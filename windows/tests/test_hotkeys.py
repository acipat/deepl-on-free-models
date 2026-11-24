"""Tests for ``deepl_ofm.services.hotkeys`` (port of HotKeyManager.swift)."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from deepl_ofm.services import hotkeys  # noqa: E402
from deepl_ofm.services.hotkeys import (  # noqa: E402
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    HotkeyError,
    HotkeyManager,
    _modifiers_and_vk,
)

_APP = None


def _ensure_app() -> QApplication:
    global _APP
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _APP = app
    return app


@pytest.fixture(scope="module", autouse=True)
def qapp() -> QApplication:
    return _ensure_app()


@dataclass(frozen=True)
class Combo:
    """Stand-in for core.keycombo.KeyCombo with the same attributes."""

    key: str
    command: bool = False
    option: bool = False
    control: bool = False
    shift: bool = False

    @property
    def display(self) -> str:
        parts = []
        if self.command or self.control:
            parts.append("Ctrl")
        if self.option:
            parts.append("Alt")
        if self.shift:
            parts.append("Shift")
        parts.append(self.key.upper() if len(self.key) == 1 else self.key.title())
        return "+".join(parts)

    @property
    def is_valid(self) -> bool:
        return self.command or self.control or self.option


def test_modifiers_and_vk_ctrl_alt_t() -> None:
    modifiers, vk = _modifiers_and_vk(Combo("t", command=True, option=True))
    assert modifiers == MOD_CONTROL | MOD_ALT
    assert vk == ord("T")


def test_modifiers_and_vk_ctrl_shift_f5() -> None:
    modifiers, vk = _modifiers_and_vk(Combo("f5", command=True, shift=True))
    assert modifiers == MOD_CONTROL | MOD_SHIFT
    assert vk == 0x74  # VK_F5


def test_modifiers_and_vk_alt_1() -> None:
    modifiers, vk = _modifiers_and_vk(Combo("1", option=True))
    assert modifiers == MOD_ALT
    assert vk == 0x31


def test_modifier_translation_details() -> None:
    # `control` is the explicit Ctrl flag; `command` is the macOS ⌘ parity flag.
    assert _modifiers_and_vk(Combo("t", control=True))[0] == MOD_CONTROL
    assert _modifiers_and_vk(Combo("t", command=True, control=True))[0] == MOD_CONTROL
    assert _modifiers_and_vk(Combo("t")) == (0, ord("T"))
    assert _modifiers_and_vk(Combo("t", shift=True)) == (MOD_SHIFT, ord("T"))


def test_named_keys_and_punctuation() -> None:
    assert _modifiers_and_vk(Combo("space", command=True))[1] == 0x20
    assert _modifiers_and_vk(Combo("F12", command=True))[1] == 0x7B
    assert _modifiers_and_vk(Combo("+", command=True))[0] == MOD_CONTROL | MOD_SHIFT
    assert _modifiers_and_vk(Combo("+", command=True))[1] == 0xBB


def test_unknown_key_has_no_virtual_key() -> None:
    assert _modifiers_and_vk(Combo("definitely-not-a-key", command=True)) == (
        MOD_CONTROL,
        0,
    )
    assert _modifiers_and_vk(Combo("", command=True)) == (MOD_CONTROL, 0)


def test_is_supported_matches_platform() -> None:
    manager = HotkeyManager()
    if sys.platform == "win32":
        assert manager.is_supported() is True
    else:
        assert manager.is_supported() is False


@pytest.mark.skipif(
    sys.platform == "win32", reason="non-Windows fallback behaviour"
)
def test_register_on_non_windows_returns_false_and_emits_error() -> None:
    manager = HotkeyManager()
    errors: list[str] = []
    triggered: list[str] = []
    manager.error.connect(errors.append)
    manager.triggered.connect(triggered.append)

    result = manager.register("translate", Combo("t", command=True, option=True))

    assert result is False
    assert triggered == []
    assert len(errors) == 1
    assert errors[0] == HotkeyError(kind="unsupported").message()
    assert "Windows" in errors[0]


@pytest.mark.skipif(
    sys.platform == "win32", reason="non-Windows fallback behaviour"
)
def test_unregister_without_registration_is_silent() -> None:
    manager = HotkeyManager()
    manager.unregister("translate")
    manager.unregister("")
    manager.unregister_all()


def test_hotkey_error_message_contains_display() -> None:
    error = HotkeyError(kind="failed", combo_display="Ctrl+Alt+T")
    message = error.message()
    assert "Ctrl+Alt+T" in message
    assert error.kind == "failed"
    assert str(error) == message


def test_hotkey_error_defaults_to_registration_problem() -> None:
    message = HotkeyError(combo_display="Ctrl+Alt+T").message()
    assert "Ctrl+Alt+T" in message
    assert HotkeyError(kind="invalid").message()


def test_mod_constants_match_win32() -> None:
    assert (MOD_ALT, MOD_CONTROL, MOD_SHIFT) == (0x0001, 0x0002, 0x0004)
    assert hotkeys.MOD_NOREPEAT == 0x4000
    assert hotkeys.WM_HOTKEY == 0x0312


def test_real_keycombo_if_the_module_exists() -> None:
    try:
        from deepl_ofm.core.keycombo import KeyCombo
    except Exception:
        pytest.skip("core.keycombo has not been written yet")
    modifiers, vk = _modifiers_and_vk(KeyCombo.standard())
    assert modifiers == MOD_CONTROL | MOD_ALT
    assert vk == ord("T")
