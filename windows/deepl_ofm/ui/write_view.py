"""Write tab: improve a text and compare the result side by side.

Windows counterpart of ``Sources/HyMT/Views/WriteView.swift``.  The controller
does not publish write-specific signals, so this view mirrors its public
``write_*`` attributes with a short poll while a request is in flight; see
``_poll_timer`` below.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMimeData, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t, tf
from ..support import pasteboard
from . import icons
from .components import (
    Card,
    EmptyState,
    IconButton,
    LanguageCombo,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
    SegmentedControl,
)
from .markdown_view import MarkdownView
from .theme import Theme

if TYPE_CHECKING:
    from ..controller import AppController


class _RichTextEditor(QPlainTextEdit):
    """Write-tab editor that converts rich clipboard content to Markdown.

    Windows counterpart of the ``paste(_:)`` hook in
    ``Sources/HyMT/Views/SourceTextEditor.swift``.
    """

    def insertFromMimeData(self, source: QMimeData) -> None:
        markdown = pasteboard.mime_to_markdown(source)
        if markdown and markdown != source.text():
            self.insertPlainText(markdown)
            return
        super().insertFromMimeData(source)


def _role_colour(role: str) -> str:
    palette = Theme.palette()
    return getattr(palette, role, palette.text)


class _Label(QLabel):
    """A QLabel whose colour follows the active palette."""

    def __init__(
        self,
        text: str = "",
        role: str = "text",
        size: int = 12,
        weight: int = 400,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(str(text), parent)
        self._role = role
        self.setFont(Theme.font(size, weight))
        self._apply()
        Theme.changed.connect(self._apply)

    def _apply(self, *_args: Any) -> None:
        self.setStyleSheet(f"color: {_role_colour(self._role)};")


class _Icon(QLabel):
    """A palette-aware icon label."""

    def __init__(
        self,
        name: str,
        role: str = "muted",
        size: int = 16,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._role = role
        self._size = size
        self.setFixedSize(size, size)
        self._apply()
        Theme.changed.connect(self._apply)

    def _apply(self, *_args: Any) -> None:
        self.setPixmap(
            icons.pixmap(
                self._name,
                _role_colour(self._role),
                self._size,
                self.devicePixelRatioF(),
            )
        )


class WriteView(QWidget):
    """Two-pane rewrite tab: editable source on the left, Markdown on the right."""

    def __init__(
        self, controller: AppController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._busy = False
        self._last_output: str | None = None
        self._copied = False
        self._syncing_language = False
        self._language_was_chosen = False
        self._suppress_edit = False
        self._first_show = True
        self.setAutoFillBackground(True)

        self._build_ui()
        self._build_timer()
        self._connect()
        self.retranslate_ui()
        self._sync_languages()
        self._sync_from_controller()
        if self.controller.write_in_progress:
            self._poll_timer.start()

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.editor.setFocus(Qt.FocusReason.OtherFocusReason)

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addWidget(self._build_toolbar())

        panes = QHBoxLayout()
        panes.setContentsMargins(0, 0, 0, 0)
        panes.setSpacing(12)
        panes.addWidget(self._build_source_card(), 1)
        panes.addWidget(self._build_result_card(), 1)
        root.addLayout(panes, 1)

    def _build_header(self) -> QWidget:
        header = QWidget(self)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.heading = _Label(t("Improve text"), "text", 22, 600, header)
        self.subtitle = _Label(
            t("Improve clarity, grammar and style while keeping the meaning."),
            "muted",
            13,
            400,
            header,
        )
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.heading)
        layout.addWidget(self.subtitle)
        return header

    def _build_toolbar(self) -> Card:
        card = Card(parent=self, padding=16, spacing=0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.control_label = _Label(t("Improve in"), "muted", 13, 500, card)
        self.language_combo = LanguageCombo(False, card)
        self.language_combo.setMinimumWidth(210)

        self.improve_button = PrimaryButton(
            t("Improve text"), card, icon_name="sparkles"
        )
        self.cancel_button = SecondaryButton(t("Cancel"), card, icon_name="stop")
        self.cancel_button.hide()

        self.copy_button = SecondaryButton(t("Copy"), card, icon_name="copy")
        self.copy_button.setEnabled(False)

        row.addWidget(self.control_label)
        row.addWidget(self.language_combo)
        row.addWidget(self.improve_button)
        row.addWidget(self.cancel_button)
        row.addStretch(1)
        row.addWidget(self.copy_button)
        card.content_layout.addLayout(row)
        self.toolbar = card
        return card

    def _build_source_card(self) -> Card:
        card = Card(t("Source"), parent=self, padding=16, spacing=12)
        card.setMinimumHeight(250)

        self.clear_button = IconButton("x", t("Clear"), card)
        self.clear_button.hide()
        card.add_header_widget(self.clear_button)

        self.editor = _RichTextEditor(card)
        self.editor.setPlaceholderText(t("Type or paste text to improve"))
        self.editor.setFont(Theme.font(15))
        self.editor.setFrameShape(QFrame.Shape.NoFrame)
        self.editor.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; padding: 0px; }"
        )
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.editor.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.editor.setTabChangesFocus(True)
        # WriteView.swift: four points of vertical and six of horizontal
        # breathing room around the text, inside the card padding.
        holder = QWidget(card)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(6, 4, 6, 4)
        holder_layout.setSpacing(0)
        holder_layout.addWidget(self.editor, 1)
        card.content_layout.addWidget(holder, 1)

        self.source_card = card
        return card

    def _build_result_card(self) -> Card:
        card = Card(t("Result"), parent=self, padding=16, spacing=12)
        card.setMinimumHeight(250)

        self.view_switch = SegmentedControl(
            [t("Preview"), t("Text only"), t("Markdown")], 0, card
        )
        self.view_switch.setObjectName("writeViewSwitch")
        self.view_switch.setFixedWidth(250)
        self.view_switch.changed.connect(self._on_view_mode_changed)
        card.add_header_widget(self.view_switch)

        self.result_stack = QStackedWidget(card)
        self.placeholder = EmptyState(
            "sparkles", t("Improved text will appear here"), "", self.result_stack
        )
        self.placeholder_progress = ProgressBar(0, self.placeholder)
        self.placeholder_progress.setFixedWidth(160)
        self.placeholder_progress.hide()
        self.placeholder.set_action(self.placeholder_progress)
        self.result_view = MarkdownView("", self.result_stack)
        self.result_stack.addWidget(self.placeholder)
        self.result_stack.addWidget(self.result_view)
        card.content_layout.addWidget(self.result_stack, 1)

        self.error_row = QWidget(card)
        error_layout = QHBoxLayout(self.error_row)
        error_layout.setContentsMargins(0, 0, 0, 0)
        error_layout.setSpacing(8)
        self.error_icon = _Icon("warning", "danger", 14, self.error_row)
        self.error_label = _Label("", "text", 12, 400, self.error_row)
        self.error_label.setWordWrap(True)
        self.error_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        error_layout.addWidget(self.error_icon, 0, Qt.AlignmentFlag.AlignTop)
        error_layout.addWidget(self.error_label, 1)
        self.error_row.hide()
        card.content_layout.addWidget(self.error_row)

        self.warning_label = _Label("", "warning", 12, 400, card)
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        card.content_layout.addWidget(self.warning_label)

        self.duration_label = _Label("", "faint", 11, 400, card)
        self.duration_label.hide()
        card.content_layout.addWidget(self.duration_label)

        self.result_card = card
        return card

    def _build_timer(self) -> None:
        # AppController intentionally exposes no write-specific signals.  While
        # a request is in flight the view therefore polls write_in_progress,
        # write_output, write_error and write_warning_count on the GUI thread;
        # the 120 ms cadence keeps the panes responsive without busy-waiting.
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(120)
        self._poll_timer.timeout.connect(self._poll)

        self._copy_reset = QTimer(self)
        self._copy_reset.setSingleShot(True)
        self._copy_reset.setInterval(1400)
        self._copy_reset.timeout.connect(self._end_copied)

    def _connect(self) -> None:
        controller = self.controller
        controller.interfaceLanguageChanged.connect(self._on_language_changed)
        controller.languagesChanged.connect(self._on_languages_changed)
        controller.copyFeedback.connect(self._on_copy_feedback)

        self.editor.textChanged.connect(self._on_source_edited)
        self.improve_button.clicked.connect(self._improve)
        self.cancel_button.clicked.connect(self._cancel)
        self.copy_button.clicked.connect(self._copy)
        self.clear_button.clicked.connect(self.editor.clear)
        self.language_combo.code_changed.connect(self._on_language_selected)

    # -- controller sync ----------------------------------------------------
    def _on_language_changed(self, _code: str = "") -> None:
        self.retranslate_ui()

    def _on_languages_changed(self, _source: str = "", _target: str = "") -> None:
        self._sync_languages()

    def _sync_languages(self) -> None:
        code = getattr(self.controller.target_language, "code", "")
        if code and self.language_combo.code() != code:
            self._syncing_language = True
            try:
                self.language_combo.set_code(code)
            finally:
                self._syncing_language = False

    def _on_language_selected(self, code: str) -> None:
        if self._syncing_language or not code or code == "auto":
            return
        self._language_was_chosen = True
        self.controller.set_target_language(code)

    def _on_copy_feedback(self, _message: str) -> None:
        self._sync_from_controller()

    def _sync_from_controller(self) -> None:
        busy = bool(self.controller.write_in_progress)
        self._set_busy(busy)

        output = self.controller.write_output or ""
        if output != self._last_output:
            self._last_output = output
            self.result_view.set_markdown(output)

        if busy:
            self.result_stack.setCurrentWidget(self.placeholder)
        elif output:
            self.result_stack.setCurrentWidget(self.result_view)
        else:
            self.result_stack.setCurrentWidget(self.placeholder)

        self._sync_warning(
            int(self.controller.write_warning_count or 0) if output else 0
        )
        self._sync_error(None if busy else self.controller.write_error)
        duration = self.controller.write_duration_ms
        if output and duration:
            self.duration_label.setText(self._format_seconds(int(duration)))
            self.duration_label.show()
        else:
            self.duration_label.hide()
        self.copy_button.setEnabled(bool(output) and not busy and not self._copied)
        self._update_actions()

    def _set_busy(self, busy: bool) -> None:
        busy = bool(busy)
        if busy == self._busy:
            return
        self._busy = busy
        self.cancel_button.setVisible(busy)
        self.improve_button.setText(t("Improving…") if busy else t("Improve text"))
        self.placeholder.set_title(
            t("Improving…") if busy else t("Improved text will appear here")
        )
        if busy:
            self.placeholder_progress.show()
            self.placeholder_progress.indeterminate(True)
            self.result_stack.setCurrentWidget(self.placeholder)
        else:
            self.placeholder_progress.indeterminate(False)
            self.placeholder_progress.hide()
        self._update_actions()

    def _sync_warning(self, count: int) -> None:
        if count > 0:
            self.warning_label.setText(
                tf("Some paragraphs are still in the original language (%d).", count)
            )
            self.warning_label.show()
        else:
            self.warning_label.clear()
            self.warning_label.hide()

    def _sync_error(self, message: str | None) -> None:
        if message:
            self.error_label.setText(str(message))
            self.error_row.show()
        else:
            self.error_label.clear()
            self.error_row.hide()

    def _update_actions(self) -> None:
        text = self.editor.toPlainText()
        self.clear_button.setVisible(bool(text))
        self.improve_button.setEnabled(bool(text.strip()) and not self._busy)

    # -- commands -----------------------------------------------------------
    def set_source_text(self, text: str) -> None:
        """Prefill the editor (``--write-text`` and history restore)."""
        self.editor.setPlainText(text or "")
        self.editor.setFocus()

    def _on_source_edited(self) -> None:
        """Editing the draft cancels the request and drops the stale result."""
        if self._suppress_edit:
            return
        if (
            self.controller.write_output
            or self.controller.write_error
            or self.controller.write_in_progress
        ):
            self.controller.reset_write()
        self._sync_detected_language()
        self._update_actions()

    def _sync_detected_language(self) -> None:
        """Show the language the text is written in until the user chooses one."""
        if self._language_was_chosen:
            return
        from ..core.languages import detect_language

        detected = detect_language(
            self.editor.toPlainText(), self.controller.settings.interface_language
        )
        if detected is None or detected.code == self.language_combo.code():
            return
        self._syncing_language = True
        try:
            self.language_combo.set_code(detected.code)
        finally:
            self._syncing_language = False

    def _improve(self) -> None:
        text = self.editor.toPlainText()
        if not text.strip() or self._busy:
            return
        self._end_copied()
        self._sync_error(None)
        self._sync_warning(0)
        language_code = self.language_combo.code() if self._language_was_chosen else "auto"
        self.controller.write_text(text, language_code)
        self._sync_from_controller()
        if self.controller.write_in_progress:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    def _cancel(self) -> None:
        self.controller.cancel_write()
        self._poll_timer.stop()
        self._sync_from_controller()
        if self.controller.write_in_progress:
            self._poll_timer.start()

    def _poll(self) -> None:
        self._sync_from_controller()
        if not self.controller.write_in_progress:
            self._poll_timer.stop()

    @staticmethod
    def _format_seconds(duration_ms: int) -> str:
        """Format a duration with the localised ``%.1f s`` template."""
        value = f"{duration_ms / 1000.0:.1f}"
        template = t("%.1f s")
        if "%.1f" in template:
            return template.replace("%.1f", value)
        return f"{value} {t('s')}"

    def _on_view_mode_changed(self, index: int) -> None:
        mode = ("preview", "text", "markdown")[index] if 0 <= index <= 2 else "preview"
        self.result_view.set_mode(mode)

    def _copy(self) -> None:
        text = self.controller.write_output
        if not text:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - defensive
            return
        clipboard.setText(text)
        self._copied = True
        self.copy_button.setText(t("Copied"))
        self.copy_button.set_icon_name("check")
        self.copy_button.setEnabled(False)
        self._copy_reset.start()

    def _end_copied(self) -> None:
        if not self._copied:
            return
        self._copied = False
        self.copy_button.setText(t("Copy"))
        self.copy_button.set_icon_name("copy")
        self.copy_button.setEnabled(
            bool(self.controller.write_output) and not self._busy
        )

    # -- retranslation ------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.heading.setText(t("Improve text"))
        self.subtitle.setText(
            t("Improve clarity, grammar and style while keeping the meaning.")
        )
        self.control_label.setText(t("Improve in"))
        self.language_combo.retranslate_ui()
        self.improve_button.setText(t("Improving…") if self._busy else t("Improve text"))
        self.cancel_button.setText(t("Cancel"))
        self.copy_button.setText(t("Copied") if self._copied else t("Copy"))
        self.copy_button.set_icon_name("check" if self._copied else "copy")
        self.editor.setPlaceholderText(t("Type or paste text to improve"))
        self.clear_button.set_tooltip(t("Clear"))
        self.source_card.set_title(t("Source"))
        self.result_card.set_title(t("Result"))
        self.view_switch.set_labels([t("Preview"), t("Text only"), t("Markdown")])
        self.placeholder.set_title(
            t("Improving…") if self._busy else t("Improved text will appear here")
        )
        self._sync_from_controller()
