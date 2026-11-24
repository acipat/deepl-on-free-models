"""The Translate tab: language bar, source editor, result pane and footer.

Ported from ``Sources/HyMT/Views/TranslateView.swift`` (the language bar, the
source and target panes and their footers) and ``SourceTextEditor.swift`` (the
plain-text editor that submits with Ctrl+Enter).  The visual grammar is the
Windows design system: two calm cards on the page background, one accent, and
only the controls that matter for reading and moving text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QKeyEvent,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
    QTextOption,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.languages import get_language
from ..core.prompts import TranslationStyle, TranslationTone
from ..i18n import t, tf
from ..support import pasteboard
from . import icons
from .components import (
    Card,
    EmptyState,
    IconButton,
    LanguageCombo,
    LinkButton,
    Pill,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SegmentedControl,
    StyleChips,
    ToneChips,
)
from .markdown_view import MarkdownView
from .theme import Theme

if TYPE_CHECKING:  # pragma: no cover - avoids the ui <-> controller cycle
    from ..controller import AppController

RESULT_MODES = ("preview", "text", "markdown")
RESULT_LABELS = ("Preview", "Text only", "Markdown")
COLLAPSE_WIDTH = 1040
RESULT_COUNTER_WIDTH = 1120
MIN_PANE_WIDTH = 380

# The language bar is measured from the outside in, never from font metrics:
# the two pickers have a fixed width, so the cluster is a constant and a long
# language name cannot move it.  The style/tone controls get exactly half of
# what is left, and these constants model their width (base + characters) so
# the breakpoint stays identical on every font database and in the web UI.
LANGUAGE_PICKER_WIDTH = 164
BAR_PADDING = 16
BAR_SPACING = 8
FULL_CHIPS_BASE_WIDTH = 1100
FULL_CHIPS_PER_CHARACTER = 5
MINIMAL_MENUS_CONTENT_WIDTH = 1000
COMPACT_TRAILING_MIN_WIDTH = 240
COMPACT_ICON_TRAILING_MIN_WIDTH = 96
COMPACT_ICON_BUTTON_WIDTH = 44
CHIP_LABELS = (
    "Style",
    "Auto",
    "Literal",
    "Natural",
    "Tone",
    "Default",
    "Formal",
    "Casual",
)


# ---------------------------------------------------------------------------
# Small local widgets
# ---------------------------------------------------------------------------


class _TrailingHost(QWidget):
    """Right-aligned host that claims the other half of the free bar space.

    Its size hint is deliberately empty: ``QHBoxLayout`` then splits the width
    left over by the language cluster evenly between the leading spacer and
    this host, which keeps the cluster centred.  The style/tone controls sit at
    the trailing edge of the host.  A hidden size hint also keeps the breakpoint
    independent of font metrics; if a very wide font makes the full controls
    wider than their half, Qt clips the overflow at the host instead of letting
    it run into the language cluster.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(0)
        self._row.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._row.addStretch(1)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def add_control(self, widget: QWidget) -> None:
        self._row.addWidget(widget, 0, Qt.AlignmentFlag.AlignRight)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 34)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, 34)


class _SourceEditor(QPlainTextEdit):
    """Plain-text source editor with the macOS submit/escape keys."""

    submitted = Signal()
    richPaste = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFont(Theme.font(14))
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.document().setDocumentMargin(0)
        # Long unbroken text must not push the pane wider than its sibling.
        self.setMinimumWidth(0)
        self.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; padding: 0px; }"
        )
        self.setTabChangesFocus(False)
        self.apply_line_height()

    def apply_line_height(self, percent: int = 158) -> None:
        """Give the document a comfortable reading rhythm."""
        block = QTextBlockFormat()
        block.setLineHeight(
            percent, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
        )
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.mergeBlockFormat(block)
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Paste rich clipboard content as Markdown (``SourceTextView.paste``).

        HTML and RTF are converted first so headings, lists, links and
        emphasis survive translation; plain text still takes the normal path.
        """
        markdown = pasteboard.mime_to_markdown(source)
        if markdown and markdown != source.text():
            self.insertPlainText(markdown)
            self.richPaste.emit()
            return
        super().insertFromMimeData(source)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # Qt API
        modifiers = event.modifiers()
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and modifiers & Qt.KeyboardModifier.ControlModifier
        ):
            self.submitted.emit()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)


@dataclass(frozen=True)
class _ComboEntry:
    """Duck-typed stand-in for the language picker's private entry type."""

    code: str
    label: str
    search: str
    language: Any | None = None


class _LocalizedLanguageCombo(LanguageCombo):
    """A :class:`LanguageCombo` whose names follow the interface language.

    The shared widget asks :meth:`Language.display_name` without an interface
    language, which makes every picker English.  This subclass only overrides
    the entry list and the closed-state text, so the popup and the button agree
    with the rest of the localised chrome.
    """

    def __init__(
        self,
        app_language: Any,
        include_auto: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        self._app_language = app_language
        super().__init__(include_auto, parent)

    def set_app_language(self, app_language: Any) -> None:
        if app_language == self._app_language:
            return
        self._app_language = app_language
        self.updateGeometry()
        self.update()

    def _label(self, language: Any | None) -> str:
        if language is None:
            return t("Auto-detect")
        try:
            return str(language.display_name(self._app_language))
        except Exception:  # noqa: BLE001 - a placeholder language object
            return str(getattr(language, "english_name", "") or "")

    def _entries(self) -> list[_ComboEntry]:
        self._ensure_languages()
        entries: list[_ComboEntry] = []
        if self._include_auto:
            label = t("Auto-detect")
            entries.append(
                _ComboEntry(
                    "auto",
                    label,
                    f"auto detect auto-detect {label}".lower(),
                )
            )
        for language in self._languages or []:
            code = str(getattr(language, "code", ""))
            if not code or getattr(language, "is_auto", False):
                continue
            label = self._label(language)
            keywords = " ".join(
                str(value)
                for value in (
                    code,
                    getattr(language, "local_name", ""),
                    getattr(language, "english_name", ""),
                    getattr(language, "bcp47", "") or "",
                    label,
                )
                if value
            )
            entries.append(_ComboEntry(code, label, keywords.lower(), language))
        return entries

    def _display_text(self) -> str:
        code = self.code()
        if code == "auto":
            label = t("Auto-detect")
            if self._detected is not None:
                return f"{label} · {self._label(self._detected)}"
            return label
        for entry in self._entries():
            if entry.code == code:
                return entry.label
        return code.upper() if code else t("Language")


class _SwapButton(QPushButton):
    """The round swap control between the two language pickers."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def enterEvent(self, event: object) -> None:  # Qt API
        self.update()
        super().enterEvent(event)  # type: ignore[arg-type]

    def leaveEvent(self, event: object) -> None:  # Qt API
        self.update()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: object) -> None:  # Qt API
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            hovered = self.underMouse() and self.isEnabled()
            pressed = self.isDown() and self.isEnabled()
            painter.setBrush(
                QColor(
                    palette.selection
                    if pressed
                    else (palette.card_hover if hovered else palette.card)
                )
            )
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawEllipse(rect)
            if self.hasFocus():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(palette.accent), 1.3))
                painter.drawEllipse(rect.adjusted(1.6, 1.6, -1.6, -1.6))
            colour = palette.text if hovered else palette.muted
            if not self.isEnabled():
                colour = palette.faint
            rendered = icons.pixmap(
                "swap", colour, 14, self.devicePixelRatioF()
            )
            painter.drawPixmap(
                (self.width() - 14) / 2.0,
                (self.height() - 14) / 2.0,
                rendered,
            )
        finally:
            painter.end()


def _normalise(text: str) -> str:
    """Qt normalises CRLF on paste; compare like with like."""
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


class _CopyButton(SecondaryButton):
    """Neutral button with the accent outline that marks the primary output action."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent, icon_name="copy")
        self.setFixedHeight(30)
        self.setMinimumWidth(92)

    def paintEvent(self, event: object) -> None:  # Qt API
        super().paintEvent(event)  # type: ignore[arg-type]
        if not self.isEnabled():
            return
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(palette.accent), 1.3))
            painter.drawRoundedRect(
                rect,
                float(Theme.radius_small),
                float(Theme.radius_small),
            )
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Translate tab
# ---------------------------------------------------------------------------


class TranslateView(QWidget):
    """The main translation workspace."""

    def __init__(self, controller: AppController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self._syncing = False
        self._source_previewing = False
        self._minimal_menus = False
        self._error_text = controller.error_message or ""
        # Streamed text shown while a job is running; never the committed result.
        self._partial_text = ""
        self._role_labels: dict[str, list[QLabel]] = {
            "muted": [],
            "faint": [],
            "text": [],
            "danger": [],
            "success": [],
        }

        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.setInterval(1300)
        self._copy_timer.timeout.connect(self._reset_copy_icon)

        self._feedback_timer = QTimer(self)
        self._feedback_timer.setSingleShot(True)
        self._feedback_timer.setInterval(1800)
        self._feedback_timer.timeout.connect(self._clear_feedback)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(2 * MIN_PANE_WIDTH + 12 + 48, 520)
        self.setAccessibleName(t("Translate"))

        self._build_ui()
        self._connect()
        self._apply_theme()
        self._sync_all()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 12)
        outer.setSpacing(14)

        self._top_bar = self._build_top_bar()
        outer.addWidget(self._top_bar)

        panes = QHBoxLayout()
        panes.setContentsMargins(0, 0, 0, 0)
        panes.setSpacing(12)
        self._source_card = self._build_source_card()
        self._result_card = self._build_result_card()
        panes.addWidget(self._source_card, 1)
        panes.addWidget(self._result_card, 1)
        outer.addLayout(panes, 1)

        outer.addWidget(self._build_footer())
        self._update_responsive()

    # -- top bar ------------------------------------------------------------
    def _build_top_bar(self) -> QWidget:
        bar = QWidget(self)
        row = QHBoxLayout(bar)
        row.setContentsMargins(BAR_PADDING, 0, BAR_PADDING, 0)
        # Spacing is added explicitly around the cluster below: QHBoxLayout
        # folds a plain spacing into a leading stretch asymmetrically, which
        # shifts the "centred" cluster a few pixels off centre.
        row.setSpacing(0)

        languages = QWidget(bar)
        self._language_group = languages
        language_row = QHBoxLayout(languages)
        language_row.setContentsMargins(0, 0, 0, 0)
        language_row.setSpacing(8)

        self._source_combo = _LocalizedLanguageCombo(
            self.controller.settings.interface_language, True, languages
        )
        self._source_combo.setFixedWidth(LANGUAGE_PICKER_WIDTH)
        self._source_combo.set_code(self.controller.source_language.code)
        language_row.addWidget(self._source_combo)

        self._swap_button = _SwapButton(languages)
        language_row.addWidget(self._swap_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self._target_combo = _LocalizedLanguageCombo(
            self.controller.settings.interface_language, False, languages
        )
        self._target_combo.setFixedWidth(LANGUAGE_PICKER_WIDTH)
        self._target_combo.set_code(self.controller.target_language.code)
        language_row.addWidget(self._target_combo)

        # Equal flexible space on both sides of the fixed-width language
        # cluster keeps it (and the swap button) centred over the pane divider.
        row.addStretch(1)
        row.addSpacing(BAR_SPACING)
        row.addWidget(languages, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addSpacing(BAR_SPACING)
        self._trailing_host = _TrailingHost(bar)
        row.addWidget(self._trailing_host, 1)

        # Full chips, shown on wide windows.
        self._chips_group = QWidget(self._trailing_host)
        chips = QHBoxLayout(self._chips_group)
        chips.setContentsMargins(0, 0, 0, 0)
        chips.setSpacing(7)

        self._style_caption = self._make_label("", 11, 600, "muted")
        self._style_chips = StyleChips(self.controller.style.value, self._chips_group)
        self._tone_caption = self._make_label("", 11, 600, "muted")
        self._tone_chips = ToneChips(self.controller.tone.value, self._chips_group)
        chips.addWidget(self._style_caption)
        chips.addWidget(self._style_chips)
        chips.addSpacing(12)
        chips.addWidget(self._tone_caption)
        chips.addWidget(self._tone_chips)
        self._trailing_host.add_control(self._chips_group)

        # Compact menus, shown when the window gets narrow.
        self._menu_group = QWidget(self._trailing_host)
        menus = QHBoxLayout(self._menu_group)
        menus.setContentsMargins(0, 0, 0, 0)
        menus.setSpacing(8)
        self._style_button = SecondaryButton("", self._menu_group)
        self._style_button.setFixedHeight(32)
        self._tone_button = SecondaryButton("", self._menu_group)
        self._tone_button.setFixedHeight(32)
        menus.addWidget(self._style_button)
        menus.addWidget(self._tone_button)
        self._trailing_host.add_control(self._menu_group)

        self._style_menu = self._build_choice_menu(
            "style", [value.value for value in TranslationStyle]
        )
        self._tone_menu = self._build_choice_menu(
            "tone", [value.value for value in TranslationTone]
        )
        self._style_button.clicked.connect(self._show_style_menu)
        self._tone_button.clicked.connect(self._show_tone_menu)

        return bar

    def _build_choice_menu(self, kind: str, values: list[str]) -> QMenu:
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        actions: dict[str, QAction] = {}
        for value in values:
            action = QAction(menu)
            action.setCheckable(True)
            action.setData(value)
            if kind == "style":
                action.triggered.connect(
                    lambda _checked=False, code=value: self.controller.set_style(code)
                )
            else:
                action.triggered.connect(
                    lambda _checked=False, code=value: self.controller.set_tone(code)
                )
            group.addAction(action)
            menu.addAction(action)
            actions[value] = action
        if kind == "style":
            self._style_actions = actions
        else:
            self._tone_actions = actions
        return menu

    # -- panes --------------------------------------------------------------
    def _build_source_card(self) -> Card:
        card = Card(t("Source"), icon_name="globe", padding=18, spacing=12)
        card.setMinimumWidth(MIN_PANE_WIDTH)

        self._source_counter = self._make_label("", 11, 400, "muted")
        self._source_counter.setContentsMargins(0, 0, 6, 0)
        card.add_header_widget(self._source_counter)
        card.header_actions.addSpacing(6)

        self._speak_source_button = IconButton(
            "speaker", t("Listen to the original"), card, size=28, icon_size=15
        )
        self._preview_button = IconButton(
            "eye", t("Show rendered Markdown"), card, size=28, icon_size=15
        )
        self._copy_source_button = IconButton(
            "copy", t("Copy the original"), card, size=28, icon_size=15
        )
        self._paste_button = IconButton(
            "clipboard", t("Paste from clipboard"), card, size=28, icon_size=15
        )
        self._clear_button = IconButton("x", t("Clear"), card, size=28, icon_size=15)
        card.add_header_widget(self._speak_source_button)
        card.add_header_widget(self._preview_button)
        card.add_header_widget(self._copy_source_button)
        card.add_header_widget(self._paste_button)
        card.add_header_widget(self._clear_button)

        self._editor = _SourceEditor(card)
        self._editor.setPlaceholderText(t("Enter or paste text…"))
        self._editor.setAccessibleName(t("Source"))
        self._source_preview: MarkdownView | None = None
        self._source_stack = QStackedWidget(card)
        self._source_stack.setMinimumWidth(0)
        self._source_stack.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._source_stack.addWidget(self._editor)
        self._source_stack.setCurrentWidget(self._editor)
        # SourceTextEditor.textInset: 20 x 16 around the text.  A plain
        # container gives a stable inset for both the editor and the rendered
        # preview, whose stacked page ignores margins set on the stack itself.
        self._source_body = QWidget(card)
        source_inset = QVBoxLayout(self._source_body)
        source_inset.setContentsMargins(20, 16, 20, 16)
        source_inset.setSpacing(0)
        source_inset.addWidget(self._source_stack, 1)
        card.body.addWidget(self._source_body, 1)
        return card

    def _build_result_card(self) -> Card:
        card = Card(t("Translation"), icon_name="sparkles", padding=18, spacing=12)
        card.setMinimumWidth(MIN_PANE_WIDTH)

        self._warning_pill = Pill("", "warning", card)
        self._warning_pill.hide()
        self._speak_result_button = IconButton(
            "speaker", t("Listen to the translation"), card, size=28, icon_size=15
        )
        self._again_button = IconButton(
            "refresh", t("Translate again"), card, size=28, icon_size=15
        )
        self._copy_button = _CopyButton(t("Copy"), card)
        card.add_header_widget(self._warning_pill)
        card.add_header_widget(self._again_button)
        card.add_header_widget(self._speak_result_button)
        card.add_header_widget(self._copy_button)

        controls = QWidget(card)
        control_row = QHBoxLayout(controls)
        control_row.setContentsMargins(0, 0, 0, 0)
        control_row.setSpacing(10)
        self._segmented = SegmentedControl(
            [t(label) for label in RESULT_LABELS],
            RESULT_MODES.index(self.controller.result_view),
            controls,
        )
        self._segmented.setFixedHeight(30)
        self._result_counter = self._make_label("", 11, 400, "muted")
        control_row.addWidget(self._segmented)
        control_row.addStretch(1)
        control_row.addWidget(self._result_counter)
        card.body.addWidget(controls)

        self._stack = QStackedWidget(card)
        self._stack.setMinimumWidth(0)
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._progress_page = self._build_progress_page(card)
        self._error_page = self._build_error_page(card)
        self._empty_page = self._build_empty_page(card)
        self._result_view = MarkdownView("", card)
        self._result_view.setObjectName("resultView")
        self._result_view.set_mode(self.controller.result_view)
        self._result_view.setAccessibleName(t("Translation"))
        # MarkdownPreview.textInset: 10 x 12 around the rendered text.
        self._result_view.setContentsMargins(10, 12, 10, 12)
        self._result_view.setMinimumWidth(0)
        self._result_view.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
        )
        self._stack.addWidget(self._progress_page)
        self._stack.addWidget(self._error_page)
        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._result_view)
        card.body.addWidget(self._stack, 1)

        self._error_banner = self._build_error_banner(card)
        self._error_banner.hide()
        card.body.addWidget(self._error_banner)
        return card

    def _build_progress_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addStretch(1)

        inner = QWidget(page)
        inner.setFixedWidth(320)
        body = QVBoxLayout(inner)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(11)

        self._progress_title = self._make_label("", 14, 600, "text")
        self._progress_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_bar = ProgressBar(0, inner)
        self._progress_counts = QWidget(inner)
        counts = QHBoxLayout(self._progress_counts)
        counts.setContentsMargins(0, 0, 0, 0)
        counts.setSpacing(8)
        self._progress_status = self._make_label("", 12, 400, "muted")
        self._progress_percent = self._make_label("", 12, 600, "text", mono=True)
        self._progress_percent.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        counts.addWidget(self._progress_status, 1)
        counts.addWidget(self._progress_percent)
        self._progress_stop = SecondaryButton(t("Stop"), inner, icon_name="stop")
        self._progress_stop.setFixedHeight(32)

        body.addWidget(self._progress_title)
        body.addWidget(self._progress_bar)
        body.addWidget(self._progress_counts)
        body.addSpacing(3)
        body.addWidget(self._progress_stop, 0, Qt.AlignmentFlag.AlignHCenter)

        column.addWidget(inner, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        return page

    def _build_error_page(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        column = QVBoxLayout(page)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(9)
        column.addStretch(1)

        self._error_icon = QLabel(page)
        self._error_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_icon.setFixedHeight(34)
        column.addWidget(self._error_icon, 0, Qt.AlignmentFlag.AlignHCenter)

        self._error_title = self._make_label("", 14, 600, "text")
        self._error_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        column.addWidget(self._error_title)

        self._error_label = self._make_label("", 12, 400, "muted")
        self._error_label.setWordWrap(True)
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setMaximumWidth(380)
        column.addWidget(self._error_label)

        self._error_retry = PrimaryButton(t("Retry"), page, icon_name="refresh")
        self._error_retry.setFixedHeight(34)
        column.addSpacing(5)
        column.addWidget(self._error_retry, 0, Qt.AlignmentFlag.AlignHCenter)
        column.addStretch(1)
        return page

    def _build_empty_page(self, parent: QWidget) -> QWidget:
        page = EmptyState("translate", t("Translation will appear here"), "", parent)
        self._translate_now = PrimaryButton(
            t("Translate now"), page, icon_name="arrow-right"
        )
        self._translate_now.setFixedHeight(34)
        page.set_action(self._translate_now)
        return page

    def _build_error_banner(self, parent: QWidget) -> QFrame:
        banner = QFrame(parent)
        banner.setObjectName("errorBanner")
        row = QHBoxLayout(banner)
        row.setContentsMargins(11, 9, 11, 9)
        row.setSpacing(9)
        self._banner_icon = QLabel(banner)
        self._banner_icon.setFixedWidth(16)
        self._banner_label = self._make_label("", 12, 400, "text")
        self._banner_label.setWordWrap(True)
        self._banner_retry = LinkButton(t("Retry"), banner)
        row.addWidget(self._banner_icon, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self._banner_label, 1)
        row.addWidget(self._banner_retry, 0, Qt.AlignmentFlag.AlignTop)
        return banner

    # -- footer -------------------------------------------------------------
    def _build_footer(self) -> QWidget:
        footer = QWidget(self)
        row = QHBoxLayout(footer)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(8)

        self._detected_icon = QLabel(footer)
        self._detected_icon.setFixedWidth(14)
        self._detected_label = self._make_label("", 11, 400, "muted")
        self._feedback_label = self._make_label("", 11, 500, "success")
        self._feedback_label.hide()
        row.addWidget(self._detected_icon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self._detected_label)
        row.addWidget(self._feedback_label)
        row.addStretch(1)

        self._fallback_pill = Pill(t("fallback"), "warning", footer)
        self._fallback_pill.hide()
        self._model_label = self._make_label("", 11, 400, "muted")
        self._metric_dot = self._make_label("·", 11, 400, "faint")
        self._metrics_label = self._make_label("", 11, 400, "faint", mono=True)
        row.addWidget(self._fallback_pill)
        row.addWidget(self._model_label)
        row.addWidget(self._metric_dot)
        row.addWidget(self._metrics_label)
        return footer

    # ------------------------------------------------------------- helpers
    def _make_label(
        self,
        text: str,
        size: int = 12,
        weight: int = 400,
        role: str = "text",
        *,
        mono: bool = False,
    ) -> QLabel:
        label = QLabel(text, self)
        label.setFont(Theme.font(size, weight, mono=mono))
        if role not in self._role_labels:
            role = "text"
        self._role_labels[role].append(label)
        return label

    def _characters(self, count: int) -> str:
        key = "%d character" if count == 1 else "%d characters"
        return tf(key, count)

    @staticmethod
    def _seconds(duration_ms: int) -> str:
        """Format a duration with the localised ``%.1f s`` template."""
        value = f"{duration_ms / 1000.0:.1f}"
        template = t("%.1f s")
        if "%.1f" in template:
            return template.replace("%.1f", value)
        return f"{value} {t('s')}"

    def _menu_text(self, caption: str, value: str) -> str:
        return f"{t(caption)}: {t(value)} ▾"

    # ------------------------------------------------------------- signals
    def _connect(self) -> None:
        c = self.controller
        c.sourceTextChanged.connect(self._on_source_text)
        c.translatedTextChanged.connect(self._on_translated_text)
        c.partialTranslationChanged.connect(self._on_partial_text)
        c.progressChanged.connect(self._on_progress)
        c.translatingChanged.connect(self._on_translating)
        c.languagesChanged.connect(self._on_languages)
        c.styleChanged.connect(self._on_style)
        c.toneChanged.connect(self._on_tone)
        c.resultViewChanged.connect(self._on_result_view)
        c.detectedLanguageChanged.connect(self._on_detected)
        c.translationFailed.connect(self._on_error)
        c.warningCountChanged.connect(self._on_warnings)
        c.metricsChanged.connect(self._on_metrics)
        c.speakingChanged.connect(self._on_speaking)
        c.copyFeedback.connect(self._on_copy_feedback)
        c.interfaceLanguageChanged.connect(self._on_interface_language)
        c.settingsChanged.connect(self._on_settings_changed)
        Theme.changed.connect(self._on_theme_changed)

        self._editor.textChanged.connect(self._on_editor_changed)
        self._editor.submitted.connect(self._submit)
        self._editor.richPaste.connect(self._on_rich_paste)
        self._source_combo.code_changed.connect(self.controller.set_source_language)
        self._target_combo.code_changed.connect(self.controller.set_target_language)
        self._swap_button.clicked.connect(self.controller.swap_languages)
        self._style_chips.changed.connect(self.controller.set_style)
        self._tone_chips.changed.connect(self.controller.set_tone)
        self._segmented.changed.connect(self._on_segment_changed)
        self._copy_source_button.clicked.connect(self.controller.copy_source)
        self._again_button.clicked.connect(lambda: self.controller.translate(force=True))
        self._speak_source_button.clicked.connect(self._toggle_source_speech)
        self._speak_result_button.clicked.connect(self._toggle_result_speech)
        self._preview_button.clicked.connect(self._toggle_source_preview)
        self._paste_button.clicked.connect(self.controller.translate_clipboard)
        self._clear_button.clicked.connect(self._clear_source)
        self._copy_button.clicked.connect(self._copy_translation)
        self._progress_stop.clicked.connect(self.controller.cancel)
        self._error_retry.clicked.connect(self._retry)
        self._banner_retry.clicked.connect(self._retry)
        self._translate_now.clicked.connect(self._retry)

    # --------------------------------------------------------------- sync
    def _sync_all(self) -> None:
        c = self.controller
        self._partial_text = ""
        self._set_editor_text(c.source_text)
        self._result_view.set_markdown(c.translated_text)
        self._result_view.set_mode(c.result_view)
        self._segmented.set_index(RESULT_MODES.index(c.result_view))
        self._source_combo.set_code(c.source_language.code)
        self._target_combo.set_code(c.target_language.code)
        self._source_combo.set_detected(
            c.detected_language if c.source_language.is_auto else None
        )
        self._refresh_language_tooltips()
        self._style_chips.set_value(c.style.value)
        self._tone_chips.set_value(c.tone.value)
        self._sync_choice_menus()
        self._on_progress(c.completed, c.total)
        self._on_warnings(c.warning_count)
        self._refresh_footer()
        self._refresh_header()
        self._refresh_result_state()
        self.retranslate_ui()

    def _set_editor_text(self, text: str) -> None:
        if self._editor.toPlainText() == text:
            return
        self._syncing = True
        try:
            cursor = self._editor.textCursor()
            position = cursor.position()
            scroll = self._editor.verticalScrollBar().value()
            self._editor.setPlainText(text)
            self._editor.apply_line_height()
            cursor = self._editor.textCursor()
            cursor.setPosition(min(position, len(text)))
            self._editor.setTextCursor(cursor)
            self._editor.verticalScrollBar().setValue(scroll)
        finally:
            self._syncing = False

    def _on_editor_changed(self) -> None:
        if self._syncing:
            return
        text = self._editor.toPlainText()
        if _normalise(text) != _normalise(self.controller.source_text):
            self.controller.set_source_text(text)

    def _on_source_text(self, text: str) -> None:
        if _normalise(self._editor.toPlainText()) != _normalise(text):
            self._set_editor_text(text)
        if self._source_previewing and self._source_preview is not None:
            self._source_preview.set_markdown(text)
        if not text.strip():
            self._error_text = ""
        self._refresh_header()
        self._refresh_result_state()

    def _on_translated_text(self, text: str) -> None:
        self._partial_text = ""
        self._result_view.set_markdown(text)
        self._refresh_header()
        self._refresh_result_state()

    def _on_partial_text(self, text: str) -> None:
        """Paint streamed text; the controller commits the final result later."""
        if not self.controller.is_translating:
            return
        if not text.strip():
            return
        self._partial_text = text
        self._result_view.set_markdown(text)
        self._refresh_header()
        self._refresh_result_state()

    def _on_progress(self, completed: int, total: int) -> None:
        percent = round(completed * 100 / total) if total > 0 else 0
        self._progress_bar.indeterminate(total <= 0)
        self._progress_bar.set_value(percent)
        self._progress_title.setText(t("Translating…"))
        if total > 0:
            self._progress_status.setText(tf("%d of %d", completed, total))
            self._progress_percent.setText(f"{percent}%")
        else:
            self._progress_status.setText("")
            self._progress_percent.setText("")
        self._progress_counts.setVisible(total > 0)

    def _on_translating(self, translating: bool) -> None:
        if translating:
            self._error_text = ""
        self._partial_text = ""
        self._refresh_result_state()

    def _on_languages(self, source: str, target: str) -> None:
        self._source_combo.set_code(source)
        self._target_combo.set_code(target)
        self._source_combo.set_detected(
            self.controller.detected_language if source == "auto" else None
        )
        self._refresh_language_tooltips()
        self._refresh_footer()

    def _on_style(self, value: str) -> None:
        self._style_chips.set_value(value)
        self._sync_choice_menus()

    def _on_tone(self, value: str) -> None:
        self._tone_chips.set_value(value)
        self._sync_choice_menus()

    def _on_result_view(self, mode: str) -> None:
        if mode in RESULT_MODES:
            self._segmented.set_index(RESULT_MODES.index(mode))
            self._result_view.set_mode(mode)
            self._refresh_copy_tooltip()

    def _on_segment_changed(self, index: int) -> None:
        if 0 <= index < len(RESULT_MODES):
            self.controller.set_result_view(RESULT_MODES[index])

    def _on_detected(self, code: str) -> None:
        language = get_language(code) if code else None
        self._source_combo.set_detected(
            language if self.controller.source_language.is_auto else None
        )
        self._refresh_language_tooltips()
        self._refresh_footer()

    def _on_error(self, message: str) -> None:
        self._error_text = str(message or "")
        self._refresh_result_state()

    def _on_warnings(self, count: int) -> None:
        if count > 0:
            key = "%d warning" if count == 1 else "%d warnings"
            self._warning_pill.setText(tf(key, count))
            self._warning_pill.show()
        else:
            self._warning_pill.hide()
        self._refresh_result_state()

    def _on_metrics(self) -> None:
        self._refresh_footer()

    def _on_settings_changed(self) -> None:
        self._refresh_footer()

    def _on_speaking(self, target: str) -> None:
        source = target == "source"
        translation = target == "translation"
        self._speak_source_button.set_icon_name("stop" if source else "speaker")
        self._speak_result_button.set_icon_name("stop" if translation else "speaker")
        self._speak_source_button.set_tooltip(
            t("Stop") if source else t("Listen to the original")
        )
        self._speak_result_button.set_tooltip(
            t("Stop") if translation else t("Listen to the translation")
        )
        self._refresh_header()

    def _on_copy_feedback(self, message: str) -> None:
        if not message:
            return
        self._feedback_label.setText(message)
        self._feedback_label.show()
        self._feedback_timer.start()
        if message == t("Translation copied"):
            self._flash_copy_icon()

    def _on_interface_language(self, _language: str) -> None:
        self.retranslate_ui()

    def _on_theme_changed(self, _dark: bool) -> None:
        self._apply_theme()
        self.update()

    def _refresh_language_tooltips(self) -> None:
        """Show the full picker label as its tooltip (it ellipses in 164 px)."""
        self._source_combo.setToolTip(self._source_combo.display_text())
        self._target_combo.setToolTip(self._target_combo.display_text())

    # -------------------------------------------------------------- states
    def _refresh_header(self) -> None:
        source = self.controller.source_text
        translated = self.controller.translated_text
        self._source_counter.setText(self._characters(len(source)))
        self._result_counter.setText(
            self._characters(len(translated)) if translated.strip() else ""
        )
        self._result_counter.setVisible(
            bool(translated.strip()) and self.width() >= RESULT_COUNTER_WIDTH
        )
        has_source = bool(source.strip())
        has_result = bool(translated.strip())
        self._preview_button.setEnabled(has_source)
        if not has_source and self._source_previewing:
            self._set_source_preview(False)
        self._speak_source_button.setEnabled(has_source)
        self._copy_source_button.setEnabled(has_source)
        self._again_button.setEnabled(has_source)
        self._clear_button.setEnabled(has_source)
        self._speak_result_button.setEnabled(
            has_result or self.controller.speaking == "translation"
        )
        self._copy_button.setEnabled(has_result)
        self._translate_now.setEnabled(has_source and not self.controller.is_translating)

    def _refresh_result_state(self) -> None:
        c = self.controller
        error = self._error_text or c.error_message or ""
        has_result = bool(c.translated_text.strip())
        has_partial = bool(self._partial_text.strip())

        if c.is_translating and not has_partial:
            self._stack.setCurrentWidget(self._progress_page)
        elif error and not has_result and not has_partial:
            self._error_label.setText(error)
            self._stack.setCurrentWidget(self._error_page)
        elif not has_result and not has_partial:
            self._stack.setCurrentWidget(self._empty_page)
        else:
            self._stack.setCurrentWidget(self._result_view)

        banner = bool(error) and has_result and not c.is_translating
        self._banner_label.setText(error)
        self._error_banner.setVisible(banner)
        self._error_title.setText(t("Translation failed"))
        self._error_retry.setEnabled(not c.is_translating and bool(c.source_text.strip()))
        self._banner_retry.setEnabled(
            not c.is_translating and bool(c.source_text.strip())
        )
        self._refresh_header()

    def _refresh_footer(self) -> None:
        c = self.controller
        language = c.settings.interface_language
        auto = c.source_language.is_auto
        detected = c.detected_language if auto else None
        show_detected = detected is not None
        self._detected_icon.setVisible(show_detected)
        self._detected_label.setVisible(show_detected)
        if show_detected:
            self._detected_label.setText(
                tf("Detected: %@", detected.display_name(language))
            )

        model = c.settings.model.strip()
        self._model_label.setText(model)
        self._model_label.setVisible(bool(model))

        parts: list[str] = []
        if c.tokens_per_second is not None and c.tokens_per_second > 0:
            parts.append(f"{c.tokens_per_second:.1f} {t('t/s')}")
        if c.last_duration_ms is not None:
            parts.append(self._seconds(c.last_duration_ms))
        metrics = "  ·  ".join(parts)
        self._metrics_label.setText(metrics)
        self._metrics_label.setVisible(bool(metrics))
        self._metric_dot.setVisible(bool(model) and bool(metrics))
        self._fallback_pill.setVisible(c.using_fallback)

    def _bar_width(self) -> int:
        """Content width of the language bar, outside both sets of margins.

        The fixed chips threshold is expressed on this width, exactly like the
        web UI's ResizeObserver content width.
        """
        layout = self.layout()
        if layout is None:
            return self.width()
        margins = layout.contentsMargins()
        width = self.width() - margins.left() - margins.right()
        bar_layout = self._top_bar.layout()
        if bar_layout is not None:
            bar_margins = bar_layout.contentsMargins()
            width -= bar_margins.left() + bar_margins.right()
        return max(0, width)

    def _full_chips_threshold(self) -> int:
        """Smallest bar that can show the full style/tone chips.

        The breakpoint comes from the translated label lengths, not from
        ``sizeHint()``: font metrics differ between machines and would make
        the responsive state (and its tests) depend on the installed fonts.
        A long selected language name does not enter this calculation because
        the picker is fixed at 164 px.
        """
        characters = sum(len(t(label)) for label in CHIP_LABELS)
        return FULL_CHIPS_BASE_WIDTH + characters * FULL_CHIPS_PER_CHARACTER

    def _update_responsive(self) -> None:
        if not hasattr(self, "_trailing_host"):
            return
        bar_width = self._bar_width()
        collapsed = self.width() < COLLAPSE_WIDTH
        if not collapsed:
            collapsed = bar_width < self._full_chips_threshold()
        self._chips_group.setVisible(not collapsed)
        self._menu_group.setVisible(collapsed)
        # At the smallest widths even "Style: value" is too wide for a long
        # interface language; the menus then fall back to icon-only buttons.
        minimal = collapsed and bar_width < MINIMAL_MENUS_CONTENT_WIDTH
        if minimal != self._minimal_menus:
            self._minimal_menus = minimal
            self._sync_choice_menus()
        # Keep the compact pair from being clipped at the smallest sizes while
        # leaving the cluster centred whenever the two halves are wide enough.
        if not collapsed:
            trailing_min = 0
        elif minimal:
            trailing_min = COMPACT_ICON_TRAILING_MIN_WIDTH
        else:
            trailing_min = COMPACT_TRAILING_MIN_WIDTH
        self._trailing_host.setMinimumWidth(trailing_min)
        if hasattr(self, "_result_counter"):
            self._refresh_header()

    def _sync_choice_menus(self) -> None:
        style = self.controller.style
        tone = self.controller.tone
        for value, action in self._style_actions.items():
            member = TranslationStyle(value)
            action.setText(f"{t(member.title)} — {t(member.detail)}")
            action.setChecked(value == style.value)
        for value, action in self._tone_actions.items():
            member = TranslationTone(value)
            action.setText(f"{t(member.title)} — {t(member.detail)}")
            action.setChecked(value == tone.value)
        if self._minimal_menus:
            self._set_compact_button(self._style_button, "style", "Style", style.title)
            self._set_compact_button(self._tone_button, "tone", "Tone", tone.title)
        else:
            style_text = self._menu_text("Style", style.title)
            tone_text = self._menu_text("Tone", tone.title)
            for button, text in (
                (self._style_button, style_text),
                (self._tone_button, tone_text),
            ):
                button.setMinimumWidth(0)
                button.setMaximumWidth(16777215)
                button.set_icon_name(None)
                button.setText(text)
                button.setToolTip(text)

    def _set_compact_button(
        self, button: SecondaryButton, icon: str, caption: str, value: str
    ) -> None:
        """Icon-only menu button for the narrowest bar (Swift's compact form)."""
        button.setText("")
        button.setFixedWidth(COMPACT_ICON_BUTTON_WIDTH)
        button.set_icon_name(icon)
        label = f"{t(caption)} · {t(value)}"
        button.setToolTip(label)
        button.setAccessibleName(label)

    # ------------------------------------------------------------- actions
    def _submit(self) -> None:
        if self.controller.source_text.strip():
            self.controller.translate(force=True)

    def _retry(self) -> None:
        if self.controller.source_text.strip():
            self.controller.translate(force=True)
        self._editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _clear_source(self) -> None:
        self.controller.clear_source()
        self._error_text = ""
        self._refresh_result_state()
        self.focus_source()

    def _toggle_source_preview(self) -> None:
        """Swap the source body between the editor and the rendered Markdown."""
        if not self.controller.source_text.strip():
            return
        self._set_source_preview(not self._source_previewing)
        if self._source_previewing:
            self._source_preview.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._editor.setFocus(Qt.FocusReason.OtherFocusReason)

    def _ensure_source_preview(self) -> MarkdownView:
        """Create the rendered source pane on first use.

        Keeping it lazy leaves the translation pane as the only
        :class:`MarkdownView` until the user actually asks for a preview, so
        ``findChild(MarkdownView)`` keeps finding the result.
        """
        preview = self._source_preview
        if preview is None:
            preview = MarkdownView("", self._source_stack)
            preview.set_mode(MarkdownView.PREVIEW)
            preview.setAccessibleName(t("Source"))
            preview.setMinimumWidth(0)
            preview.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
            )
            self._source_stack.addWidget(preview)
            self._source_preview = preview
        return preview

    def _set_source_preview(self, enabled: bool) -> None:
        enabled = bool(enabled)
        page: QWidget | None = None
        if enabled:
            preview = self._ensure_source_preview()
            preview.set_markdown(self.controller.source_text)
            page = preview
        self._source_previewing = enabled
        self._source_stack.setCurrentWidget(page or self._editor)
        self._editor.setReadOnly(enabled)
        self._preview_button.set_icon_name("code" if enabled else "eye")
        self._preview_button.set_tooltip(
            t("Show Markdown source") if enabled else t("Show rendered Markdown")
        )

    def _on_rich_paste(self) -> None:
        """A rich paste arrives as Markdown: show the rendered result."""
        if self.controller.source_text.strip():
            self._set_source_preview(True)

    def _toggle_source_speech(self) -> None:
        if self.controller.speaking == "source":
            self.controller.stop_speaking()
        else:
            self.controller.speak("source")

    def _toggle_result_speech(self) -> None:
        if self.controller.speaking == "translation":
            self.controller.stop_speaking()
        else:
            self.controller.speak("translation")

    def _copy_translation(self) -> None:
        self.controller.copy_translation()
        self._flash_copy_icon()

    def _flash_copy_icon(self) -> None:
        self._copy_button.set_icon_name("check")
        self._copy_timer.start()

    def _reset_copy_icon(self) -> None:
        self._copy_button.set_icon_name("copy")

    def _clear_feedback(self) -> None:
        self._feedback_label.clear()
        self._feedback_label.hide()

    def _show_style_menu(self) -> None:
        self._sync_choice_menus()
        position = self._style_button.mapToGlobal(
            QPoint(0, self._style_button.height() + 4)
        )
        self._style_menu.exec(position)

    def _show_tone_menu(self) -> None:
        self._sync_choice_menus()
        position = self._tone_button.mapToGlobal(
            QPoint(0, self._tone_button.height() + 4)
        )
        self._tone_menu.exec(position)

    # ------------------------------------------------------------- public
    def retranslate_ui(self) -> None:
        """Refresh every visible string without touching the current state."""
        self.setAccessibleName(t("Translate"))
        self._source_card.set_title(t("Source"))
        self._result_card.set_title(t("Translation"))
        self._editor.setPlaceholderText(t("Enter or paste text…"))
        self._editor.setAccessibleName(t("Source"))
        self._result_view.setAccessibleName(t("Translation"))
        language = self.controller.settings.interface_language
        self._source_combo.set_app_language(language)
        self._target_combo.set_app_language(language)
        self._source_combo.retranslate_ui()
        self._target_combo.retranslate_ui()
        self._source_combo.setAccessibleName(t("Source language"))
        self._target_combo.setAccessibleName(t("Target language"))
        self._refresh_language_tooltips()
        self._swap_button.setToolTip(t("Swap languages") + " (Ctrl+Shift+S)")
        self._swap_button.setAccessibleName(t("Swap languages") + " (Ctrl+Shift+S)")

        self._style_caption.setText(t("Style"))
        self._tone_caption.setText(t("Tone"))
        self._style_chips.retranslate_ui()
        self._tone_chips.retranslate_ui()
        self._sync_choice_menus()

        self._speak_source_button.set_tooltip(
            t("Stop")
            if self.controller.speaking == "source"
            else t("Listen to the original")
        )
        self._preview_button.set_tooltip(
            t("Show Markdown source")
            if self._source_previewing
            else t("Show rendered Markdown")
        )
        if self._source_preview is not None:
            self._source_preview.setAccessibleName(t("Source"))
            self._source_preview.retranslate_ui()
        self._speak_result_button.set_tooltip(
            t("Stop")
            if self.controller.speaking == "translation"
            else t("Listen to the translation")
        )
        self._paste_button.set_tooltip(t("Paste from clipboard"))
        self._clear_button.set_tooltip(t("Clear"))
        self._copy_button.setText(t("Copy"))
        self._refresh_copy_tooltip()

        self._segmented.set_labels([t(label) for label in RESULT_LABELS])
        self._segmented.set_index(RESULT_MODES.index(self.controller.result_view))
        self._segmented.setAccessibleName(t("View"))
        self._progress_title.setText(t("Translating…"))
        self._on_progress(self.controller.completed, self.controller.total)
        self._progress_stop.setText(t("Stop"))
        self._error_title.setText(t("Translation failed"))
        self._error_retry.setText(t("Retry"))
        self._banner_retry.setText(t("Retry"))
        self._translate_now.setText(t("Translate now"))
        self._empty_page.set_title(t("Translation will appear here"))
        self._fallback_pill.setText(t("fallback"))
        self._warning_pill.setText(
            tf(
                "%d warning" if self.controller.warning_count == 1 else "%d warnings",
                self.controller.warning_count,
            )
        )
        self._result_view.retranslate_ui()
        self._clear_feedback()

        self._refresh_header()
        self._refresh_result_state()
        self._refresh_footer()
        self._update_responsive()
        self.update()

    def focus_source(self) -> None:
        """Put the caret in the editor, at the end of the existing text."""
        self._set_source_preview(False)
        self._editor.setFocus(Qt.FocusReason.ShortcutFocusReason)
        cursor = self._editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._editor.setTextCursor(cursor)
        self._editor.ensureCursorVisible()

    def set_source_text(self, text: str) -> None:
        """Prefill the editor from a command-line flag or another view."""
        value = str(text)
        self.controller.set_source_text(value)
        self._set_editor_text(value)
        self._refresh_header()
        self._refresh_result_state()

    def paste_text(self, text: str) -> None:
        """Handle the Paste menu item: replace the source and focus the editor."""
        value = str(text)
        if not value.strip():
            return
        self.set_source_text(value)
        self.focus_source()

    # -------------------------------------------------------------- layout
    def minimumSizeHint(self) -> QSize:
        """Keep the panes at their minimum width without the top bar's hint.

        The chip row is much wider in some interface languages; letting it
        drive the page minimum would stop the window from ever reaching the
        960 px layout where the chips collapse into menus.
        """
        return QSize(2 * MIN_PANE_WIDTH + 12 + 48, 520)

    def resizeEvent(self, event: object) -> None:  # Qt API
        self._update_responsive()
        super().resizeEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: object) -> None:  # Qt API
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(Theme.palette().bg))
        finally:
            painter.end()

    # --------------------------------------------------------------- theme
    def _apply_theme(self) -> None:
        palette = Theme.palette()
        colours = {
            "muted": palette.muted,
            "faint": palette.faint,
            "text": palette.text,
            "danger": palette.danger,
            "success": palette.success,
        }
        for role, labels in self._role_labels.items():
            colour = colours.get(role, palette.text)
            for label in labels:
                label.setStyleSheet(f"color: {colour};")

        soft = Theme.mix(palette.card, palette.danger, 0.08)
        border = Theme.mix(palette.card, palette.danger, 0.36)
        self._error_banner.setStyleSheet(
            "QFrame#errorBanner {"
            f" background: {soft};"
            f" border: 1px solid {border};"
            f" border-radius: {Theme.radius_small}px;"
            " }"
        )
        self._error_icon.setPixmap(icons.pixmap("warning", palette.danger, 30))
        self._banner_icon.setPixmap(icons.pixmap("warning", palette.danger, 15))
        self._detected_icon.setPixmap(icons.pixmap("globe", palette.faint, 13))
        self._detected_icon.setFixedSize(14, 14)
        self._copy_button.update()
        self._swap_button.update()

    # -------------------------------------------------------------- tooltip
    def _refresh_copy_tooltip(self) -> None:
        key = {
            "preview": "Copy translation (formatted text)",
            "text": "Copy translation (plain text)",
            "markdown": "Copy translation (Markdown)",
        }.get(self.controller.result_view, "Copy translation")
        self._copy_button.setToolTip(t(key))
        self._copy_button.setAccessibleName(t(key))
