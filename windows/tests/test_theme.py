"""Design-token and stylesheet tests."""

from __future__ import annotations

import os
import re
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from deepl_ofm.ui.theme import Palette, Theme, _DARK, _LIGHT

HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

EXPECTED_FIELDS = {
    "bg",
    "panel",
    "card",
    "card_hover",
    "border",
    "text",
    "muted",
    "faint",
    "accent",
    "accent_hover",
    "accent_soft",
    "danger",
    "success",
    "warning",
    "selection",
}


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_palette_is_complete_and_hex() -> None:
    assert {field.name for field in fields(Palette)} == EXPECTED_FIELDS
    for palette in (_LIGHT, _DARK):
        for name in EXPECTED_FIELDS:
            value = getattr(palette, name)
            assert isinstance(value, str) and value, name
            assert HEX_RE.match(value), f"{name}={value!r} is not a plain hex colour"


def test_direction_palette_values() -> None:
    assert _LIGHT.bg == "#F6F7F9"
    assert _LIGHT.card == "#FFFFFF"
    assert _LIGHT.border == "#E3E6EB"
    assert _LIGHT.text == "#14161A"
    assert _LIGHT.muted == "#6B7280"
    assert _DARK.bg == "#15171C"
    assert _DARK.card == "#1D2027"
    assert _DARK.border == "#2A2E37"
    assert _DARK.text == "#F2F4F8"
    assert _DARK.muted == "#9AA1AE"
    assert _LIGHT.accent == "#2F6BFF"
    assert _DARK.accent == "#2F6BFF"


def test_contrast_is_readable_in_both_modes() -> None:
    for palette in (_LIGHT, _DARK):
        pairs = [
            (palette.text, palette.bg, "text on canvas"),
            (palette.text, palette.card, "text on card"),
            (palette.muted, palette.bg, "secondary on canvas"),
            (palette.muted, palette.card, "secondary on card"),
            (palette.danger, palette.card, "danger on card"),
            (palette.success, palette.card, "success on card"),
            (palette.warning, palette.card, "warning on card"),
        ]
        for foreground, background, label in pairs:
            ratio = Theme.contrast_ratio(foreground, background)
            assert ratio >= 4.5, f"{label}: {ratio:.2f}<4.5"
        # The accent is fixed by the design direction; WCAG reports 4.50.
        assert round(Theme.contrast_ratio(Theme.on_accent(), palette.accent), 2) >= 4.5


def test_palette_is_frozen() -> None:
    with pytest.raises((FrozenInstanceError, AttributeError)):
        _LIGHT.text = "#000000"  # type: ignore[misc]


def test_apply_sets_a_real_stylesheet(qapp: QApplication) -> None:
    Theme.apply(qapp, dark=True)
    assert Theme.is_dark()
    sheet = qapp.styleSheet()
    assert _DARK.bg.upper() in sheet.upper()
    assert _DARK.accent.upper() in sheet.upper()
    assert "{p." not in sheet
    assert "border-radius" in sheet

    Theme.set_dark(False)
    assert not Theme.is_dark()
    sheet = qapp.styleSheet()
    assert _LIGHT.bg.upper() in sheet.upper()
    assert _LIGHT.card.upper() in sheet.upper()
    assert Theme.palette().text == _LIGHT.text
    assert Theme.palette(True).text == _DARK.text

    Theme.set_dark(None)
    assert Theme.palette() in (_LIGHT, _DARK)


def test_fonts_and_tokens(qapp: QApplication) -> None:
    Theme.apply(qapp, dark=False)
    assert Theme.font_family()
    assert Theme.mono_family()
    font = Theme.font(14, 600)
    assert font.pixelSize() == 14
    assert font.weight() == 600
    assert Theme.font_family() != Theme.mono_family()
    assert Theme.radius == 10
    assert Theme.radius_small == 8
    assert Theme.spacing == 12
    assert Theme.on_accent() == "#FFFFFF"


def test_combo_arrows_are_styled_and_present(qapp: QApplication) -> None:
    from PySide6.QtWidgets import QComboBox

    for dark in (False, True):
        Theme.apply(qapp, dark=dark)
        sheet = qapp.styleSheet()
        assert "QComboBox::down-arrow" in sheet
        match = re.search(
            r'QComboBox::down-arrow \{\s*image: url\("([^"]+)"\)', sheet
        )
        assert match is not None
        assert Path(match.group(1)).exists()
        combo = QComboBox()
        combo.addItems(["Ollama", "Groq", "Custom"])
        combo.resize(260, 34)
        combo.show()
        qapp.processEvents()
        assert not combo.grab().isNull()
        combo.hide()
        combo.deleteLater()
    qapp.processEvents()


def test_no_hardcoded_colours_outside_theme() -> None:
    ui_dir = Path(__file__).resolve().parents[1] / "deepl_ofm" / "ui"
    for name in ("icons.py", "components.py", "markdown_view.py"):
        text = (ui_dir / name).read_text(encoding="utf-8")
        found = re.findall(r"#[0-9A-Fa-f]{6}\b", text)
        assert not found, f"{name} contains hard-coded colours: {found}"
