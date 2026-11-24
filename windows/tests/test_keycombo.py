"""Tests for :mod:`deepl_ofm.core.keycombo` (port of ``KeyComboTests.swift``)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from deepl_ofm.core.keycombo import KeyCombo

_QT_SHIFT = 0x02000000
_QT_CONTROL = 0x04000000
_QT_ALT = 0x08000000
_QT_META = 0x10000000

# AppKit modifier masks, the values the Swift Codable stores.
_NS_COMMAND = 0x100000
_NS_OPTION = 0x80000


class FakeEvent:
    """Duck-typed stand-in for ``QKeyEvent``."""

    def __init__(self, key: int, modifiers: int) -> None:
        self._key = key
        self._modifiers = modifiers

    def key(self) -> int:
        return self._key

    def modifiers(self) -> int:
        return self._modifiers


def test_standard_shortcut() -> None:
    combo = KeyCombo.standard()
    assert combo == KeyCombo(key="t", command=True, option=True)
    assert combo.display == "Ctrl+Alt+T"
    assert combo.qt_sequence == "Ctrl+Alt+T"
    assert combo.is_valid


def test_selection_shortcut() -> None:
    combo = KeyCombo.selection()
    assert combo == KeyCombo(key="c", command=True, option=True)
    assert combo.display == "Ctrl+Alt+C"
    assert combo.qt_sequence == "Ctrl+Alt+C"
    assert combo.is_valid


def test_display_order() -> None:
    combo = KeyCombo("t", command=True, option=True, shift=True)
    assert combo.display == "Ctrl+Alt+Shift+T"
    assert combo.qt_sequence == "Ctrl+Alt+Shift+T"


def test_display_ignores_control_duplicate() -> None:
    # `control` is the macOS ⌃ flag; on Windows it maps to the same Ctrl key.
    combo = KeyCombo("t", command=True, control=True)
    assert combo.display == "Ctrl+T"
    assert combo.qt_sequence == "Ctrl+T"


def test_swift_punctuation_test() -> None:
    # KeyComboTests.testPunctuationKeyIsReadable: ⌥' on the Ukrainian layout.
    combo = KeyCombo("'", option=True)
    assert combo.display == "Alt+'"
    assert combo.qt_sequence == "Alt+Apostrophe"


def test_recorded_label_wins() -> None:
    # The label is stored as the key itself, so "є" is what gets displayed.
    combo = KeyCombo.from_dict({"label": "є", "modifiers": _NS_OPTION})
    assert combo.key == "є"
    assert combo.display == "Alt+Є"
    assert combo.option


def test_named_keys_display_and_qt() -> None:
    assert KeyCombo("space", command=True).display == "Ctrl+Space"
    assert KeyCombo("space", command=True).qt_sequence == "Ctrl+Space"
    assert KeyCombo("f5", command=True).display == "Ctrl+F5"
    assert KeyCombo("F5", command=True).qt_sequence == "Ctrl+F5"
    assert KeyCombo("pageup", command=True).display == "Ctrl+Page Up"
    assert KeyCombo("pageup", command=True).qt_sequence == "Ctrl+PgUp"
    assert KeyCombo("enter", command=True).qt_sequence == "Ctrl+Return"
    assert KeyCombo("delete", option=True).qt_sequence == "Alt+Del"
    assert KeyCombo("left", command=True).display == "Ctrl+Left"


def test_key_normalisation() -> None:
    assert KeyCombo("T").key == "t"
    assert KeyCombo(" F5 ").key == "f5"
    assert KeyCombo("Page Up").key == "pageup"
    assert KeyCombo("page_up").key == "pageup"
    assert KeyCombo("").key == ""
    assert KeyCombo("   ").key == ""


def test_validation_requires_ctrl_or_alt() -> None:
    assert KeyCombo("t").is_valid is False
    assert KeyCombo("t", shift=True).is_valid is False
    assert KeyCombo("t", command=True).is_valid is True
    assert KeyCombo("t", option=True).is_valid is True
    assert KeyCombo("t", control=True).is_valid is True
    assert KeyCombo("", command=True, option=True).is_valid is False


def test_rejected_keys() -> None:
    assert KeyCombo("\x01", command=True).is_valid is False
    assert KeyCombo("\uf700", command=True).is_valid is False
    assert KeyCombo("combining\u0301", command=True).is_valid is False
    assert KeyCombo("x" * 40, command=True).is_valid is False


def test_normalized_label_rules() -> None:
    assert KeyCombo.normalized_label("є") == "Є"
    assert KeyCombo.normalized_label("t") == "T"
    assert KeyCombo.normalized_label("Tab") == "Tab"
    assert KeyCombo.normalized_label("abcd") is None
    assert KeyCombo.normalized_label("  ") is None
    assert KeyCombo.normalized_label(None) is None
    assert KeyCombo.normalized_label("\x01") is None
    assert KeyCombo.normalized_label("\uf700") is None


def test_round_trip() -> None:
    combo = KeyCombo("t", command=True, option=True, control=False, shift=True)
    data = combo.to_dict()
    assert data == {
        "key": "t",
        "command": True,
        "option": True,
        "control": False,
        "shift": True,
    }
    assert KeyCombo.from_dict(data) == combo
    assert set(data) == {"key", "command", "option", "control", "shift"}


def test_from_dict_accepts_aliases() -> None:
    combo = KeyCombo.from_dict({"key": "T", "ctrl": True, "alt": True})
    assert combo == KeyCombo("t", command=True, option=True)
    combo = KeyCombo.from_dict({"key": "x", "command": 1, "shift": 0})
    assert combo.command is True
    assert combo.shift is False


def test_from_dict_reads_the_swift_codable_shape() -> None:
    combo = KeyCombo.from_dict(
        {"keyCode": 17, "modifiers": 0x100000 | 0x80000, "label": "t"}
    )
    assert combo.key == "t"
    assert combo.command is True
    assert combo.option is True
    assert combo.display == "Ctrl+Alt+T"


def test_from_dict_reads_a_json_string() -> None:
    combo = KeyCombo.from_dict('{"key": "k", "command": true, "shift": true}')
    assert combo == KeyCombo("k", command=True, shift=True)


@pytest.mark.parametrize("payload", [None, "", "not json", [], {}, 42, {"foo": "bar"}])
def test_from_dict_rejects_garbage_without_raising(payload: object) -> None:
    combo = KeyCombo.from_dict(payload)
    assert isinstance(combo, KeyCombo)
    assert combo.is_valid is False


def test_matches_event() -> None:
    combo = KeyCombo.standard()
    assert combo.matches(FakeEvent(ord("T"), _QT_CONTROL | _QT_ALT)) is True
    assert combo.matches(FakeEvent(ord("T"), _QT_CONTROL)) is False
    assert combo.matches(FakeEvent(ord("T"), _QT_CONTROL | _QT_ALT | _QT_SHIFT)) is False
    assert combo.matches(FakeEvent(ord("T"), _QT_CONTROL | _QT_ALT | _QT_META)) is False
    assert combo.matches(FakeEvent(ord("C"), _QT_CONTROL | _QT_ALT)) is False
    assert KeyCombo("f5", command=True).matches(
        FakeEvent(0x01000034, _QT_CONTROL)
    ) is True
    assert KeyCombo("f5", command=True).matches(FakeEvent(0x01000034, 0)) is False


def test_matches_tolerates_unknown_objects() -> None:
    assert KeyCombo.standard().matches(object()) is False
    assert KeyCombo.standard().matches(FakeEvent("T", None)) is False  # type: ignore[arg-type]


def test_str_repr_and_frozen() -> None:
    combo = KeyCombo.standard()
    assert str(combo) == "Ctrl+Alt+T"
    with pytest.raises(FrozenInstanceError):
        combo.key = "x"  # type: ignore[misc]
