"""Offscreen artwork generator for docs/ui-preview.png.

Run from ``windows/``:

    QT_QPA_PLATFORM=offscreen .venv/bin/python tools/ui_preview.py

This file is deliberately throwaway: it composes the real shared widgets into a
realistic Translate screen, adds a palette strip and grabs the window.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from deepl_ofm.ui import icons  # noqa: E402
from deepl_ofm.ui.components import (  # noqa: E402
    Card,
    Divider,
    IconButton,
    LanguageCombo,
    Pill,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    StyleChips,
    ToneChips,
)
from deepl_ofm.ui.markdown_view import MarkdownView  # noqa: E402
from deepl_ofm.ui.theme import Palette, Theme  # noqa: E402

WIDTH = 1280
HEIGHT = 860

SOURCE_TEXT = (
    "DeepL-oFM — це нативний перекладач для Windows на локальних і хмарних "
    "моделях. Він зберігає абзаци, списки й Markdown і показує готовий текст "
    "лише після перевірки всіх рядків.\n\n"
    "• Не потрібен обліковий запис для локальних моделей\n"
    "• Працює офлайн із Hy-MT2\n"
    "• Зберігає форматування без змін\n\n"
    "Результат надходить у міру перевірки кожного сегмента, тому "
    "напівперекладене речення ніколи не з'являється на екрані.\n"
)

RESULT_MARKDOWN = (
    "DeepL-oFM is a native translator for Windows that runs on local and cloud "
    "models. It preserves **paragraphs, lists and Markdown**, and shows the final "
    "text only after every line has been checked.\n\n"
    "- No account is required for local models\n"
    "- Works offline with Hy-MT2\n"
    "- Keeps your formatting intact\n\n"
    "The result streams in as each segment is verified, so a half-translated "
    "sentence never appears on screen.\n"
)


@dataclass(frozen=True)
class PreviewLanguage:
    code: str
    english_name: str
    local_name: str

    def display_name(self, language: object = None) -> str:
        return self.english_name


LANGUAGES = [
    PreviewLanguage("en", "English", "English"),
    PreviewLanguage("uk", "Ukrainian", "Українська"),
    PreviewLanguage("de", "German", "Deutsch"),
    PreviewLanguage("fr", "French", "Français"),
    PreviewLanguage("es", "Spanish", "Español"),
]


def _label(
    text: str,
    size: int = 12,
    weight: int = 400,
    colour: str | None = None,
) -> QLabel:
    label = QLabel(text)
    label.setFont(Theme.font(size, weight))
    label.setStyleSheet(f"color: {colour or Theme.palette().text};")
    return label


def _caption(text: str) -> QLabel:
    return _label(text, 11, 400, Theme.palette().muted)


class Logo(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(28, 28)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.accent))
            painter.drawRoundedRect(QRectF(self.rect()), 8.0, 8.0)
            rendered = icons.pixmap(
                "translate", Theme.on_accent(), 17, self.devicePixelRatioF()
            )
            painter.drawPixmap(QPointF(5.5, 5.5), rendered)
        finally:
            painter.end()


class NavTab(QPushButton):
    def __init__(
        self,
        icon_name: str,
        text: str,
        active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._active = active
        self.setText(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFont(Theme.font(13, 600 if active else 500))
        metrics = QFontMetrics(self.font())
        self.setFixedHeight(30)
        self.setFixedWidth(metrics.horizontalAdvance(text) + 48)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            if self._active:
                painter.setPen(QPen(QColor(palette.border), 1.0))
                painter.setBrush(QColor(palette.card_hover))
                painter.drawRoundedRect(rect, 7.0, 7.0)
            painter.setFont(self.font())
            painter.setPen(QColor(palette.text if self._active else palette.muted))
            rendered = icons.pixmap(
                self._icon_name,
                palette.text if self._active else palette.muted,
                14,
                self.devicePixelRatioF(),
            )
            painter.drawPixmap(QPointF(11.0, self.height() / 2 - 7.0), rendered)
            painter.drawText(
                QRectF(31.0, 0.0, self.width() - 35.0, self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.text(),
            )
        finally:
            painter.end()


class StatusPill(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(28)
        self.setFont(Theme.font(12, 500))
        width = QFontMetrics(self.font()).horizontalAdvance(text) + 40
        self.setFixedWidth(width)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.setBrush(QColor(palette.card))
            painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.success))
            painter.drawEllipse(QPointF(14.0, self.height() / 2), 3.5, 3.5)
            painter.setFont(self.font())
            painter.setPen(QColor(palette.muted))
            painter.drawText(
                QRectF(24.0, 0.0, self.width() - 30.0, self.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._text,
            )
        finally:
            painter.end()


class RoundIconButton(QPushButton):
    def __init__(
        self,
        icon_name: str,
        colour: str,
        background: str,
        border: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_name = icon_name
        self._colour = colour
        self._background = background
        self._border = border
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setPen(QPen(QColor(self._border), 1.0))
            painter.setBrush(QColor(self._background))
            painter.drawEllipse(rect)
            rendered = icons.pixmap(
                self._icon_name, self._colour, 14, self.devicePixelRatioF()
            )
            painter.drawPixmap(QPointF(9.0, 9.0), rendered)
        finally:
            painter.end()


class Header(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(60)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 0, 18, 0)
        layout.setSpacing(14)

        layout.addWidget(Logo(self))
        app_name = _label("DeepL-oFM", 14, 600)
        layout.addWidget(app_name)
        layout.addSpacing(8)

        tabs = [
            ("translate", "Translate", True),
            ("files", "Files", False),
            ("write", "Write", False),
            ("history", "History", False),
        ]
        for icon_name, title, active in tabs:
            layout.addWidget(NavTab(icon_name, title, active, self))
        layout.addStretch(1)
        layout.addWidget(StatusPill("openai/gpt-oss-120b", self))
        layout.addWidget(IconButton("more-horizontal", "More actions", self, size=28))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(palette.panel))
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        finally:
            painter.end()


class LanguageBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(60)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(12)

        local = QHBoxLayout()
        local.setSpacing(8)
        local.addWidget(Pill("Local", "success", self))
        local.addWidget(_caption("On-device · 38 languages"))
        layout.addLayout(local, 1)
        layout.addStretch(0)

        source = LanguageCombo(True, self)
        source.set_languages(LANGUAGES)
        source.set_code("auto")
        source.set_detected(PreviewLanguage("uk", "Ukrainian", "Українська"))
        source.setFixedWidth(204)
        layout.addWidget(source)

        palette = Theme.palette()
        swap = RoundIconButton(
            "swap", palette.muted, palette.card, palette.border, self
        )
        layout.addWidget(swap)

        target = LanguageCombo(False, self)
        target.set_languages(LANGUAGES)
        target.set_code("en")
        target.setFixedWidth(146)
        layout.addWidget(target)

        layout.addStretch(0)
        style_label = _caption("Style")
        layout.addWidget(style_label)
        style = StyleChips("natural", self)
        layout.addWidget(style)
        tone_label = _caption("Tone")
        layout.addWidget(tone_label)
        tone = ToneChips("standard", self)
        layout.addWidget(tone)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(Theme.palette().bg))
            painter.setPen(QPen(QColor(Theme.palette().border), 1.0))
            painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        finally:
            painter.end()


def _make_source_editor(text: str) -> QPlainTextEdit:
    editor = QPlainTextEdit(text)
    editor.setReadOnly(True)
    editor.setFrameShape(QFrame.Shape.NoFrame)
    editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    editor.setFont(Theme.font(14))
    editor.setStyleSheet(
        "QPlainTextEdit { background: transparent; border: none; padding: 0px; }"
    )
    editor.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    editor.document().setDocumentMargin(0)
    block = QTextBlockFormat()
    block.setLineHeight(158.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = editor.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(block)
    cursor.clearSelection()
    editor.setTextCursor(cursor)
    return editor


def _footer(
    parent: QWidget,
    left_widgets: list[QWidget],
    caption: str,
    right_widgets: list[QWidget],
) -> QWidget:
    widget = QWidget(parent)
    widget.setFixedHeight(30)
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)
    for item in left_widgets:
        layout.addWidget(item)
    layout.addStretch(1)
    layout.addWidget(_caption(caption))
    layout.addSpacing(4)
    for item in right_widgets:
        layout.addWidget(item)
    return widget


def _source_card() -> Card:
    card = Card(
        "Source",
        "Ukrainian · detected automatically",
        icon_name="globe",
        padding=18,
        spacing=14,
    )
    for icon_name, tip in (
        ("speaker", "Listen to the original"),
        ("clipboard", "Paste from clipboard"),
        ("eye", "Show rendered Markdown"),
    ):
        card.add_header_widget(IconButton(icon_name, tip, size=28, icon_size=15))
    card.add_header_widget(IconButton("x", "Clear", size=28, icon_size=15))

    editor = _make_source_editor(SOURCE_TEXT)
    card.body.addWidget(editor, 1)
    footer = _footer(
        card,
        [Pill("Markdown", "muted", card)],
        f"{len(SOURCE_TEXT)} characters",
        [IconButton("copy", "Copy the original", size=28, icon_size=15)],
    )
    card.body.addWidget(footer)
    return card


def _result_card() -> Card:
    card = Card(
        "Translation",
        "English · streaming now",
        icon_name="sparkles",
        padding=18,
        spacing=14,
    )
    for icon_name, tip in (
        ("speaker", "Listen to the translation"),
        ("refresh", "Translate again"),
        ("more-horizontal", "More result actions"),
    ):
        card.add_header_widget(IconButton(icon_name, tip, size=28, icon_size=15))

    preview = MarkdownView(RESULT_MARKDOWN, card)
    preview._browser.setVerticalScrollBarPolicy(
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    preview._browser.setStyleSheet(
        "QTextBrowser { background: transparent; border: none; padding: 0px; }"
    )
    card.body.addWidget(preview, 1)

    progress_row = QHBoxLayout()
    progress_row.setContentsMargins(0, 0, 0, 0)
    progress_row.setSpacing(8)
    progress_row.addWidget(_caption("Translating… 12 of 19 segments"))
    progress_row.addStretch(1)
    percent = _label("62 %", 12, 600)
    percent.setStyleSheet(f"color: {Theme.palette().text};")
    progress_row.addWidget(percent)
    card.body.addLayout(progress_row)

    bar = ProgressBar(62, card)
    card.body.addWidget(bar)

    footer = _footer(
        card,
        [Pill("Streaming", "accent", card), Pill("Markdown", "muted", card)],
        f"{len(RESULT_MARKDOWN)} characters",
        [IconButton("copy", "Copy", size=28, icon_size=15)],
    )
    card.body.addWidget(footer)
    return card


class Actions(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(56)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(8)
        layout.addWidget(Pill("Live", "accent", self))
        layout.addWidget(_caption("12 of 19 segments verified · 0.5 s"))
        layout.addStretch(1)
        layout.addWidget(SecondaryButton("Stop", self, icon_name="stop"))
        layout.addWidget(SecondaryButton("Paste", self, icon_name="clipboard"))
        layout.addWidget(PrimaryButton("Translate now", self, icon_name="arrow-right"))


class Swatch(QWidget):
    def __init__(
        self,
        name: str,
        value: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._value = value
        self.setFixedSize(116, 32)

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            box = QRectF(0.0, 4.0, 23.0, 23.0)
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.setBrush(QColor(self._value))
            painter.drawRoundedRect(box, 6.0, 6.0)
            painter.setPen(QColor(palette.text))
            painter.setFont(Theme.font(10, 600))
            painter.drawText(
                QRectF(31.0, 3.0, 80.0, 14.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._name,
            )
            painter.setPen(QColor(palette.muted))
            painter.setFont(Theme.font(9))
            painter.drawText(
                QRectF(31.0, 17.0, 82.0, 12.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._value,
            )
        finally:
            painter.end()


class PaletteStrip(QWidget):
    NAMES = (
        ("canvas", "bg"),
        ("card", "card"),
        ("border", "border"),
        ("text", "text"),
        ("muted", "muted"),
        ("accent", "accent"),
        ("accent soft", "accent_soft"),
        ("success", "success"),
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(108)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(18)

        heading = QVBoxLayout()
        heading.setContentsMargins(0, 2, 0, 0)
        heading.setSpacing(2)
        heading.addWidget(_label("DESIGN TOKENS", 10, 700, Theme.palette().muted))
        heading.addWidget(_caption("Light and dark palettes"))
        heading.addWidget(_caption("10 px cards · 8 px actions"))
        layout.addLayout(heading)
        layout.addSpacing(4)

        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(4)
        rows.addLayout(self._row("LIGHT", Theme.palette(False)))
        rows.addLayout(self._row("DARK", Theme.palette(True)))
        layout.addLayout(rows, 1)

    def _row(self, label: str, palette: Palette) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row_label = _label(label, 9, 700, Theme.palette().muted)
        row_label.setFixedWidth(40)
        row.addWidget(row_label)
        for display, attribute in self.NAMES:
            row.addWidget(Swatch(display, getattr(palette, attribute), self))
        row.addStretch(1)
        return row

    def paintEvent(self, event: object) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(palette.panel))
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawLine(0, 0, self.width(), 0)
        finally:
            painter.end()


class PreviewWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DeepL-oFM — UI preview")
        self.resize(WIDTH, HEIGHT)
        self.setMinimumSize(WIDTH, HEIGHT)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(Header(self))
        root.addWidget(LanguageBar(self))

        content = QWidget(self)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(24, 16, 24, 12)
        content_layout.setSpacing(16)
        content_layout.addWidget(_source_card(), 1)
        content_layout.addWidget(_result_card(), 1)
        root.addWidget(content, 1)

        divider = Divider("horizontal", self)
        root.addWidget(divider)
        root.addWidget(Actions(self))
        root.addWidget(PaletteStrip(self))

    def paintEvent(self, event: object) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(Theme.palette().bg))
        finally:
            painter.end()


def main() -> int:
    dark = "--light" not in sys.argv
    destination = ROOT / "docs" / "ui-preview.png"
    if "--out" in sys.argv:
        index = sys.argv.index("--out")
        if index + 1 < len(sys.argv):
            destination = Path(sys.argv[index + 1])

    app = QApplication.instance() or QApplication([])
    Theme.apply(app, dark=dark)
    window = PreviewWindow()
    window.show()
    app.processEvents()
    app.processEvents()

    destination.parent.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(destination), "PNG")
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
