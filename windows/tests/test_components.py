"""Icons, shared widgets and Markdown rendering, exercised offscreen."""

from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
)

from deepl_ofm.ui import components as ui
from deepl_ofm.ui import icons
from deepl_ofm.ui.markdown_view import MarkdownView, safe_href
from deepl_ofm.ui.theme import Theme, _DARK, _LIGHT

REQUIRED_ICONS = (
    "translate",
    "files",
    "write",
    "history",
    "settings",
    "copy",
    "check",
    "x",
    "swap",
    "play",
    "stop",
    "speaker",
    "search",
    "download",
    "plus",
    "trash",
    "chevron-down",
    "chevron-up",
    "sparkles",
    "globe",
    "arrow-right",
    "folder",
    "file",
    "warning",
    "info",
    "refresh",
    "external",
    "folder-open",
)


@dataclass(frozen=True)
class FakeLanguage:
    code: str
    english_name: str
    local_name: str

    def display_name(self, language: object = None) -> str:
        return self.english_name


FAKE_LANGUAGES = (
    FakeLanguage("en", "English", "English"),
    FakeLanguage("uk", "Ukrainian", "Українська"),
    FakeLanguage("de", "German", "Deutsch"),
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def themed(qapp: QApplication):
    Theme.apply(qapp, dark=False)
    qapp.processEvents()
    yield
    Theme.set_dark(None)


# ---------------------------------------------------------------------------
# Icons


@pytest.mark.parametrize("name", REQUIRED_ICONS)
def test_every_required_icon_renders(qapp: QApplication, name: str) -> None:
    rendered = icons.pixmap(name, size=20, dpr=2)
    assert not rendered.isNull()
    assert rendered.width() == 40
    assert rendered.height() == 40
    assert rendered.devicePixelRatio() == 2.0
    assert not icons.icon(name).isNull()
    assert icons.has_icon(name)


def test_unknown_icon_has_a_safe_fallback(qapp: QApplication) -> None:
    assert not icons.pixmap("does-not-exist").isNull()
    assert not icons.icon("does-not-exist").isNull()


# ---------------------------------------------------------------------------
# Widgets


def _all_widgets() -> list[object]:
    return [
        ui.Card("Source", "Detected · Ukrainian", icon_name="translate"),
        ui.ProgressBar(62),
        ui.Pill("Streaming", "accent"),
        ui.SearchField("Search languages"),
        ui.SearchBar("Filter"),
        ui.LanguageCombo(True),
        ui.StyleChips(),
        ui.ToneChips(),
        ui.SegmentedControl(["Preview", "Text", "Markdown"]),
        ui.FormRow("Model", ui.SearchField("Model name"), "Shown in the status bar"),
        ui.ToggleRow("Keep history", True, hint="Store translations locally"),
        ui.LinkButton("Get key"),
        ui.PrimaryButton("Translate now", icon_name="arrow-right"),
        ui.SecondaryButton("Paste", icon_name="clipboard"),
        ui.IconButton("copy", "Copy"),
        ui.EmptyState("sparkles", "Nothing here yet", "Translate something to begin."),
        ui.Divider(),
    ]


def test_every_component_instantiates_and_paints(qapp: QApplication) -> None:
    for widget in _all_widgets():
        widget.resize(320, 160)
        widget.show()
        qapp.processEvents()
        widget.retranslate_ui()
        rendered = widget.grab()
        assert not rendered.isNull(), type(widget).__name__
        widget.hide()
        widget.deleteLater()
    qapp.processEvents()


def test_component_base_classes() -> None:
    assert issubclass(ui.Card, QFrame)
    assert issubclass(ui.Pill, QLabel)
    assert issubclass(ui.SearchField, QLineEdit)
    assert issubclass(ui.SearchBar, QLineEdit)
    assert issubclass(ui.LinkButton, QPushButton)
    assert issubclass(ui.PrimaryButton, QPushButton)
    assert issubclass(ui.SecondaryButton, QPushButton)
    assert issubclass(ui.IconButton, QPushButton)
    for cls in (
        ui.Card,
        ui.ProgressBar,
        ui.Pill,
        ui.SearchField,
        ui.LanguageCombo,
        ui.StyleChips,
        ui.ToneChips,
        ui.SegmentedControl,
        ui.FormRow,
        ui.ToggleRow,
        ui.LinkButton,
        ui.PrimaryButton,
        ui.SecondaryButton,
        ui.EmptyState,
        ui.SearchBar,
    ):
        assert hasattr(cls, "retranslate_ui")
    assert hasattr(ui.LanguageCombo, "code_changed")
    assert hasattr(ui.StyleChips, "changed")
    assert hasattr(ui.ToneChips, "changed")
    assert hasattr(ui.SegmentedControl, "changed")
    assert hasattr(ui.ToggleRow, "toggled")


def test_chip_and_segment_signals(qapp: QApplication) -> None:
    style = ui.StyleChips()
    style_seen: list[str] = []
    style.changed.connect(style_seen.append)
    QTest.keyClick(style, Qt.Key.Key_Right)
    assert style_seen == ["literal"]
    QTest.keyClick(style, Qt.Key.Key_End)
    assert style.value() == "natural"
    assert style_seen[-1] == "natural"
    style.set_value("auto")
    assert len(style_seen) == 2

    tone = ui.ToneChips()
    tone_seen: list[str] = []
    tone.changed.connect(tone_seen.append)
    QTest.keyClick(tone, Qt.Key.Key_Right)
    assert tone.value() == "formal"
    assert tone_seen == ["formal"]

    segmented = ui.SegmentedControl(["Preview", "Text", "Markdown"])
    segment_seen: list[int] = []
    segmented.changed.connect(segment_seen.append)
    QTest.keyClick(segmented, Qt.Key.Key_Right)
    assert segmented.index() == 1
    assert segment_seen == [1]
    segmented.set_index(2)
    assert segmented.index() == 2
    assert segment_seen == [1]


def test_toggle_row_signal(qapp: QApplication) -> None:
    row = ui.ToggleRow("Keep history", True)
    seen: list[bool] = []
    row.toggled.connect(seen.append)
    assert row.is_checked()
    row.check_box().setChecked(False)
    assert seen == [False]
    row.set_checked(True)
    assert row.is_checked()
    assert seen == [False]


def test_switch_toggles_from_a_click_on_the_pill(qapp: QApplication) -> None:
    row = ui.ToggleRow("Keep history", False)
    row.resize(320, 40)
    row.show()
    qapp.processEvents()
    switch = row.check_box()
    seen: list[bool] = []
    row.toggled.connect(seen.append)

    # The old hidden QCheckBox indicator only covered the far-left strip.
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(19, 11))
    qapp.processEvents()
    assert switch.isChecked()
    assert row.is_checked()
    assert seen == [True]

    # Click the knob on the right side of the painted pill, not the indicator.
    QTest.mouseClick(switch, Qt.MouseButton.LeftButton, pos=QPoint(27, 11))
    qapp.processEvents()
    assert not switch.isChecked()
    assert not row.is_checked()
    assert seen == [True, False]
    row.hide()
    row.deleteLater()


def test_progress_bar(qapp: QApplication) -> None:
    bar = ui.ProgressBar(62)
    assert bar.value() == 62
    seen: list[int] = []
    bar.value_changed.connect(seen.append)
    bar.set_value(80)
    assert bar.value() == 80
    assert seen == [80]
    bar.set_value(120)
    assert bar.value() == 100
    bar.indeterminate(True)
    assert bar.is_indeterminate()
    bar.indeterminate(False)


def test_language_combo_search_and_selection(qapp: QApplication) -> None:
    combo = ui.LanguageCombo(True)
    combo.set_languages(FAKE_LANGUAGES)
    entries = combo._entries()
    assert entries[0].code == "auto"
    assert [entry.code for entry in entries[1:]] == ["en", "uk", "de"]
    assert combo.code() == "auto"

    seen: list[str] = []
    combo.code_changed.connect(seen.append)
    combo.show()
    combo._open_popup()
    assert combo._popup.isVisible()
    combo._popup.search.setText("ukr")
    visible = combo._popup._visible_items()
    assert [item.text() for item in visible] == ["Ukrainian"]
    QTest.keyClick(combo._popup.search, Qt.Key.Key_Return)
    assert combo.code() == "uk"
    assert seen == ["uk"]
    assert not combo._popup.isVisible()

    combo._open_popup()
    QTest.keyClick(combo._popup.search, Qt.Key.Key_Escape)
    assert not combo._popup.isVisible()
    combo.set_code("de")
    assert combo.code() == "de"
    assert seen == ["uk"]


def test_card_surface_follows_theme(qapp: QApplication) -> None:
    Theme.apply(qapp, dark=False)
    card = ui.Card()
    card.resize(240, 140)
    card.show()
    qapp.processEvents()
    image = card.grab().toImage()
    light_pixel = image.pixelColor(120, 70).name().upper()
    assert light_pixel == _LIGHT.card.upper()

    Theme.set_dark(True)
    qapp.processEvents()
    image = card.grab().toImage()
    dark_pixel = image.pixelColor(120, 70).name().upper()
    assert dark_pixel == _DARK.card.upper()
    card.deleteLater()


# ---------------------------------------------------------------------------
# Markdown


def test_markdown_escaping_blocks_raw_html(qapp: QApplication) -> None:
    view = MarkdownView()
    view.set_markdown(
        "<script>alert('x')</script> <img src=x onerror=alert(2)> & text"
    )
    document = view.html()
    assert "<script" not in document.lower()
    assert "<img" not in document.lower()
    assert "&lt;script&gt;" in document
    assert "&amp;" in document
    assert view.plain_text() == (
        "<script>alert('x')</script> <img src=x onerror=alert(2)> & text"
    )


def test_markdown_link_schemes_are_filtered(qapp: QApplication) -> None:
    view = MarkdownView()
    view.set_markdown(
        "[web](https://example.com/a?b=1) "
        "[mail](mailto:hi@example.com) "
        "[relative](guide/start.html) "
        "[bad](javascript:alert(1)) "
        "[data](data:text/html;base64,PHNjcmlwdD4=) "
        "[sneaky](javascript&#58;alert(1))"
    )
    document = view.html()
    assert 'href="https://example.com/a?b=1"' in document
    assert 'href="mailto:hi@example.com"' in document
    assert 'href="guide/start.html"' in document
    assert "javascript:" not in document
    assert "javascript&amp;#58;" not in document
    assert "data:text" not in document
    assert "sneaky" in document
    assert safe_href("//evil.example/x") is None
    assert safe_href("javascript:alert(1)") is None
    assert safe_href("https://example.com") == "https://example.com"
    assert safe_href("mailto:a@b.c") == "mailto:a@b.c"
    assert safe_href("../up.html") == "../up.html"


def test_blockquote_has_a_left_rule_and_muted_text(qapp: QApplication) -> None:
    view = MarkdownView("> A quoted paragraph.")
    document = view.html()
    palette = Theme.palette()
    assert '<table width="100%"' in document
    assert f"background-color: {palette.accent}" in document
    assert f"color: {palette.muted}" in document


def test_plain_text_strips_markers(qapp: QApplication) -> None:
    source = (
        "# Heading\n\n"
        "Some **bold**, *italic* and `code` with a [label](https://example.com).\n\n"
        "- alpha\n- beta\n\n"
        "1. first\n2. second\n\n"
        "> quoted\n\n"
        "```\nraw code\n```\n"
    )
    view = MarkdownView(source)
    plain = view.plain_text()
    for marker in ("# ", "**", "`", "](", "[", "```"):
        assert marker not in plain
    assert "Heading" in plain
    assert "bold" in plain and "italic" in plain and "code" in plain
    assert "label" in plain
    assert "• alpha" in plain and "• beta" in plain
    assert "1. first" in plain and "2. second" in plain
    assert "quoted" in plain
    assert "raw code" in plain


def test_markdown_modes(qapp: QApplication) -> None:
    source = "# Title\n\nBody **bold**."
    view = MarkdownView(source)
    assert view.mode() == "preview"
    view.set_mode("text")
    assert view.mode() == "text"
    assert view._text_editor.toPlainText() == view.plain_text()
    view.set_mode("markdown")
    assert view._markdown_editor.toPlainText() == source
    view.set_mode("preview")
    assert view._stack.currentWidget() is view._browser
    with pytest.raises(ValueError):
        view.set_mode("xml")


def test_markdown_rtf_and_copy_hook(qapp: QApplication) -> None:
    view = MarkdownView("# Заголовок\n\nТекст **жирний** і `код`.")
    rtf = view.rtf()
    assert rtf.startswith("{\\rtf1")
    assert "\\u" in rtf
    assert isinstance(view.copy_button, QToolButton)
    assert not view.copy_button.isVisible()
    view.resize(320, 200)
    view.show()
    view.show_copy_button(True)
    qapp.processEvents()
    assert view.copy_button.isVisible()

    clipboard = QApplication.instance().clipboard()
    try:
        view.set_mode("preview")
        view.copy_to_clipboard()
        assert "Текст" in clipboard.text()
        assert clipboard.mimeData().hasHtml()
        view.set_mode("markdown")
        view.copy_to_clipboard()
        assert clipboard.text().startswith("# Заголовок")
    finally:
        clipboard.clear()
