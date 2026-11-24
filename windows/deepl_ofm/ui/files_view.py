"""Files tab: translate a document and save the result in its original format.

Windows counterpart of ``Sources/HyMT/Views/FilesView.swift`` and the
``FileTranslationStore`` flow.  The view is a pure projection of
``AppController.file_job`` (published through ``fileJobChanged``): document text
is never shown in the pane, only the file name, progress and output file name.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QPointF, QProcess, QRectF, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t, tf
from . import icons
from .components import (
    Card,
    IconButton,
    LanguageCombo,
    LinkButton,
    Pill,
    PrimaryButton,
    ProgressBar,
    SecondaryButton,
)
from .theme import Theme

if TYPE_CHECKING:
    from ..controller import AppController

log = logging.getLogger(__name__)

#: Extensions accepted by the drop zone and the open dialog.
SUPPORTED_EXTENSIONS = frozenset(
    {".txt", ".text", ".md", ".markdown", ".mdown", ".pdf", ".docx"}
)
SUPPORTED_PATTERNS = "*.txt *.md *.markdown *.pdf *.docx"

_KIND_ICONS = {
    "txt": "file",
    "text": "file",
    "md": "write",
    "markdown": "write",
    "pdf": "file",
    "docx": "files",
}
_KIND_LABELS = {
    "txt": "TXT",
    "text": "TXT",
    "md": "Markdown",
    "markdown": "Markdown",
    "pdf": "PDF",
    "docx": "DOCX",
}
_RUNNING_STATES = frozenset({"reading", "translating", "writing"})


def _role_colour(role: str) -> str:
    palette = Theme.palette()
    return getattr(palette, role, palette.text)


def _format_size(size: int) -> str:
    """``12.4 MB``-style size for the file card."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _kind_label(kind: str) -> str:
    key = _KIND_LABELS.get(kind.lower())
    return t(key) if key else kind.upper()


# ---------------------------------------------------------------------------
# Small paint-time primitives


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

    def set_role(self, role: str) -> None:
        self._role = role
        self._apply()

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


class _FileBadge(QWidget):
    """Rounded square that carries the document-kind icon."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = "file"
        self.setFixedSize(42, 42)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_icon_name(self, name: str) -> None:
        self._name = name
        self.update()

    def paintEvent(self, event: Any) -> None:
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.card_hover))
            painter.drawRoundedRect(QRectF(self.rect()), 9.0, 9.0)
            rendered = icons.pixmap(
                self._name, palette.muted, 18, self.devicePixelRatioF()
            )
            x = (self.width() - 18.0) / 2.0
            y = (self.height() - 18.0) / 2.0
            painter.drawPixmap(QPointF(x, y), rendered)
        finally:
            painter.end()


class _DropZone(QWidget):
    """Large dashed drop target with icon, copy and the choose button."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active = False
        self.setMinimumHeight(300)
        self.setMaximumHeight(460)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(0)
        outer.addStretch(1)

        self.icon = _Icon("file", "accent", 34, self)
        outer.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addSpacing(14)

        self.title = _Label("", "text", 17, 600, self)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title.setWordWrap(True)
        outer.addWidget(self.title)
        outer.addSpacing(6)

        self.subtitle = _Label("", "muted", 12, 400, self)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.subtitle.setWordWrap(True)
        outer.addWidget(self.subtitle)
        outer.addSpacing(22)

        self.choose_button = PrimaryButton("", self, icon_name="folder")
        outer.addWidget(self.choose_button, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)

    def set_drag_active(self, active: bool) -> None:
        active = bool(active)
        if active != self._active:
            self._active = active
            self.update()

    def retranslate_ui(self) -> None:
        self.title.setText(t("Drop a file here or choose one"))
        self.subtitle.setText(t("Supported formats: TXT, Markdown, PDF and DOCX."))
        self.choose_button.setText(t("Choose a file…"))

    def paintEvent(self, event: Any) -> None:
        palette = Theme.palette()
        radius = float(Theme.radius + 4)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            fill = (
                Theme.mix(palette.card, palette.accent, 0.05)
                if self._active
                else palette.card
            )
            painter.setBrush(QColor(fill))
            border = (
                palette.accent
                if self._active
                else Theme.mix(palette.border, palette.faint, 0.55)
            )
            pen = QPen(QColor(border), 2.0 if self._active else 1.4)
            pen.setStyle(Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([7.0, 5.0])
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawRoundedRect(rect, radius, radius)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Files tab


class FilesView(QWidget):
    """Document translation tab driven by :attr:`AppController.file_job`."""

    def __init__(
        self, controller: AppController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.controller = controller
        self._job: dict[str, Any] = dict(controller.file_job or {})
        self._syncing_language = False
        self._target_code = getattr(controller.target_language, "code", "")
        self.setAcceptDrops(True)
        self.setAutoFillBackground(True)
        self._build_ui()
        self._connect()
        self.retranslate_ui()
        self._sync_languages()
        self._sync_state()

    # -- construction -------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        page = QWidget()
        page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll.setWidget(page)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(24, 24, 24, 24)
        page_layout.setSpacing(0)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addStretch(1)

        self.column = QWidget(page)
        self.column.setFixedWidth(740)
        self.column.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        column = QVBoxLayout(self.column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)

        column.addWidget(self._build_header())
        self.drop_zone = _DropZone(self.column)
        column.addWidget(self.drop_zone, 3)
        column.addWidget(self._build_file_card())
        column.addWidget(self._build_controls())
        column.addWidget(self._build_progress_card())
        column.addWidget(self._build_result_card())
        column.addWidget(self._build_error_card())
        column.addStretch(1)

        row.addWidget(self.column, 1)
        row.addStretch(1)
        page_layout.addLayout(row, 1)

    def _build_header(self) -> QWidget:
        header = QWidget(self.column)
        layout = QVBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        self.heading = _Label(t("Files"), "text", 22, 600, header)
        self.heading.setWordWrap(True)
        self.subtitle = _Label(
            t("Translate a document and save the result in its original format."),
            "muted",
            13,
            400,
            header,
        )
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.heading)
        layout.addWidget(self.subtitle)
        return header

    def _build_controls(self) -> QWidget:
        controls = QWidget(self.column)
        row = QHBoxLayout(controls)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(10)

        self.translate_label = _Label(t("Translate to"), "muted", 13, 500, controls)
        self.language_combo = LanguageCombo(False, controls)
        self.language_combo.setMinimumWidth(210)
        self.clear_button = LinkButton(t("Clear"), controls)
        self.clear_button.clicked.connect(self._clear)
        row.addWidget(self.clear_button, 0, Qt.AlignmentFlag.AlignVCenter)

        self.translate_button = PrimaryButton(
            t("Translate"), controls, icon_name="translate"
        )

        row.addWidget(self.translate_label)
        row.addWidget(self.language_combo)
        row.addStretch(1)
        row.addWidget(self.translate_button)
        return controls

    def _build_file_card(self) -> Card:
        card = Card(parent=self.column, padding=16, spacing=12)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        self.file_badge = _FileBadge(card)
        row.addWidget(self.file_badge, 0, Qt.AlignmentFlag.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)
        self.file_name_label = _Label("", "text", 14, 600, card)
        self.file_name_label.setWordWrap(True)
        self.file_name_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.file_kind_label = _Label("", "muted", 12, 400, card)
        text_column.addWidget(self.file_name_label)
        text_column.addWidget(self.file_kind_label)
        row.addLayout(text_column, 1)

        self.remove_button = IconButton("x", t("Remove file"), card)
        row.addWidget(self.remove_button, 0, Qt.AlignmentFlag.AlignVCenter)

        card.content_layout.addLayout(row)
        self.file_card = card
        return card

    def _build_progress_card(self) -> Card:
        card = Card(parent=self.column, padding=16, spacing=12)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.progress_status = _Label(t("Translating…"), "muted", 13, 500, card)
        self.percent_label = _Label("0%", "text", 14, 600, card)
        self.percent_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top.addWidget(self.progress_status, 1)
        top.addWidget(self.percent_label, 0)
        card.content_layout.addLayout(top)

        self.progress_bar = ProgressBar(0, card)
        card.content_layout.addWidget(self.progress_bar)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(10)
        self.count_label = _Label("", "muted", 11, 400, card)
        self.cancel_button = SecondaryButton(t("Cancel"), card, icon_name="stop")
        bottom.addWidget(self.count_label, 1)
        bottom.addWidget(self.cancel_button, 0)
        card.content_layout.addLayout(bottom)
        self.progress_card = card
        return card

    def _build_result_card(self) -> Card:
        card = Card(parent=self.column, padding=16, spacing=12)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        self.result_icon = _Icon("check", "success", 20, card)
        top.addWidget(self.result_icon, 0, Qt.AlignmentFlag.AlignTop)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)
        self.complete_label = _Label(t("Translation complete"), "text", 14, 600, card)
        self.output_name_label = _Label("", "muted", 12, 400, card)
        self.output_name_label.setWordWrap(True)
        text_column.addWidget(self.complete_label)
        text_column.addWidget(self.output_name_label)
        top.addLayout(text_column, 1)
        card.content_layout.addLayout(top)

        self.save_error_label = _Label("", "danger", 11, 400, card)
        self.save_error_label.setWordWrap(True)
        self.save_error_label.hide()
        card.content_layout.addWidget(self.save_error_label)

        self.fallback_label = Pill("", "warning", card)
        self.fallback_label.hide()
        card.content_layout.addWidget(
            self.fallback_label, 0, Qt.AlignmentFlag.AlignLeft
        )

        self.warning_label = _Label("", "warning", 12, 400, card)
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        card.content_layout.addWidget(self.warning_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(12)
        self.save_button = PrimaryButton(
            t("Save file…"), card, icon_name="download"
        )
        self.show_folder_button = SecondaryButton(
            t("Show in folder"), card, icon_name="folder-open"
        )
        self.translate_another_button = LinkButton(
            t("Translate another file"), card
        )
        actions.addWidget(self.save_button)
        actions.addWidget(self.show_folder_button)
        actions.addStretch(1)
        actions.addWidget(
            self.translate_another_button, 0, Qt.AlignmentFlag.AlignVCenter
        )
        card.content_layout.addLayout(actions)

        self.result_card = card
        return card

    def _build_error_card(self) -> Card:
        card = Card(parent=self.column, padding=16, spacing=12)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        self.error_icon = _Icon("warning", "danger", 16, card)
        row.addWidget(self.error_icon, 0, Qt.AlignmentFlag.AlignTop)

        self.message_label = _Label("", "text", 12, 400, card)
        self.message_label.setWordWrap(True)
        self.message_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self.message_label, 1)

        self.retry_button = LinkButton(t("Try again"), card)
        row.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignVCenter)
        card.content_layout.addLayout(row)

        self.error_card = card
        return card

    def _connect(self) -> None:
        controller = self.controller
        controller.fileJobChanged.connect(self._on_job_changed)
        controller.languagesChanged.connect(self._on_languages_changed)
        controller.interfaceLanguageChanged.connect(self._on_language_changed)

        self.drop_zone.choose_button.clicked.connect(self.pick_file)
        self.translate_button.clicked.connect(self._translate_again)
        self.cancel_button.clicked.connect(controller.cancel_file_translation)
        self.remove_button.clicked.connect(controller.clear_file_job)
        self.translate_another_button.clicked.connect(controller.clear_file_job)
        self.retry_button.clicked.connect(self._retry)
        self.save_button.clicked.connect(self._save_output)
        self.show_folder_button.clicked.connect(self._reveal_output)
        self.language_combo.code_changed.connect(self._on_language_selected)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        width = max(240, min(740, self.width() - 48))
        if width != self.column.width():
            self.column.setFixedWidth(width)

    # -- controller sync ----------------------------------------------------
    def _on_job_changed(self, job: dict[str, Any]) -> None:
        self._job = dict(job or {})
        self._sync_state()

    def _on_language_changed(self, _code: str = "") -> None:
        self.retranslate_ui()

    def _on_languages_changed(self, _source: str = "", _target: str = "") -> None:
        self._sync_languages()

    def _sync_languages(self) -> None:
        """Seed the picker from the app-wide target once; later choices stay local."""
        code = self._target_code or getattr(self.controller.target_language, "code", "")
        if code and self.language_combo.code() != code:
            self._syncing_language = True
            try:
                self.language_combo.set_code(code)
                self._target_code = code
            finally:
                self._syncing_language = False

    def _on_language_selected(self, code: str) -> None:
        if self._syncing_language or not code or code == "auto":
            return
        self._target_code = code

    def _sync_state(self) -> None:
        job = self._job
        state = str(job.get("state") or "")
        has_job = bool(job)
        running = state in _RUNNING_STATES
        done = state == "done"
        cancelled = state == "cancelled"
        failed = state == "failed"

        self.drop_zone.setVisible(not has_job)
        self.file_card.setVisible(has_job)
        self.progress_card.setVisible(running)
        self.result_card.setVisible(done)
        self.error_card.setVisible(failed)

        self.language_combo.setEnabled(not running)
        self.translate_button.setEnabled(not running)
        self.remove_button.setEnabled(not running)

        if has_job:
            self._sync_file(job)
        if running:
            self._sync_progress(job, state)
        if done:
            self._sync_done(job)
        if failed:
            self.message_label.setText(
                str(job.get("message") or t("The file could not be translated."))
            )
            self.retry_button.setVisible(bool(job.get("path")))
        if cancelled:
            # macOS returns to the idle controls after Stop, keeping the file.
            self.translate_button.setEnabled(True)
            self.language_combo.setEnabled(True)

    def _sync_file(self, job: dict[str, Any]) -> None:
        path = str(job.get("path") or "")
        name = str(job.get("name") or (Path(path).name if path else ""))
        kind = str(job.get("kind") or "").lower()
        self.file_name_label.setText(name)
        details = _kind_label(kind) if kind else ""
        size = int(job.get("size") or 0)
        if size > 0:
            details = f"{details} · {_format_size(size)}" if details else _format_size(size)
        self.file_kind_label.setText(details)
        self.file_kind_label.setVisible(bool(details))
        self.file_badge.set_icon_name(_KIND_ICONS.get(kind, "file"))

    def _sync_progress(self, job: dict[str, Any], state: str) -> None:
        completed = max(0, int(job.get("completed") or 0))
        total = max(0, int(job.get("total") or 0))
        percent = max(0, min(100, int(job.get("percent") or 0)))
        if total and not percent:
            percent = max(0, min(100, round(completed * 100 / total)))

        self.percent_label.setText(f"{percent}%")
        self.progress_status.setText(
            t("Preparing file…")
            if state in ("reading", "writing")
            else t("Translating…")
        )
        if total > 0:
            self.progress_bar.indeterminate(False)
            self.progress_bar.set_value(percent)
            self.count_label.setText(tf("Translating… %d of %d", completed, total))
            self.count_label.setVisible(True)
        else:
            self.progress_bar.set_value(0)
            self.progress_bar.indeterminate(True)
            self.count_label.setText("")
            self.count_label.setVisible(False)

    def _sync_done(self, job: dict[str, Any]) -> None:
        output = job.get("output")
        output_name = str(job.get("result_name") or "")
        if not output_name and output:
            output_name = Path(str(output)).name
        self.output_name_label.setText(output_name)
        self.output_name_label.setVisible(bool(output_name))

        warnings = max(0, int(job.get("warnings") or 0))
        if warnings:
            self.warning_label.setText(
                tf(
                    "Some paragraphs are still in the original language (%d).",
                    warnings,
                )
            )
            self.warning_label.setVisible(True)
        else:
            self.warning_label.clear()
            self.warning_label.setVisible(False)

        if job.get("fallback"):
            label = str(job.get("fallback_label") or "")
            self.fallback_label.setText(
                f"{t('Fallback')}: {label}" if label else t("Fallback")
            )
            self.fallback_label.setVisible(True)
        else:
            self.fallback_label.clear()
            self.fallback_label.setVisible(False)

        save_error = str(job.get("save_error") or "")
        self.save_error_label.setText(save_error)
        self.save_error_label.setVisible(bool(save_error))

        # The copy is only meaningful when the controller produced a file.
        self.save_button.setEnabled(bool(output))
        self.show_folder_button.setEnabled(bool(output or job.get("path")))

    # -- commands -----------------------------------------------------------
    def pick_file(self) -> None:
        """Ask for a document and start its translation (File > Open, Ctrl+O)."""
        if self._is_running():
            return
        path, _selected = QFileDialog.getOpenFileName(
            self,
            t("Translate file…"),
            str(Path.home()),
            f"{t('Files')} ({SUPPORTED_PATTERNS})",
        )
        if path:
            self._begin_translation(Path(path))

    def _clear(self) -> None:
        if self._is_running():
            self.controller.cancel_file_translation()
        self.controller.clear_file_job()

    def _translate_again(self) -> None:
        path = str(self._job.get("path") or "")
        if path and not self._is_running():
            self._begin_translation(Path(path))
            return
        if not self._job:
            self.pick_file()

    def _retry(self) -> None:
        path = str(self._job.get("path") or "")
        if path:
            self._begin_translation(Path(path))

    def _begin_translation(self, path: Path) -> None:
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            self.controller.report_error(t("This file type is not supported."))
            return
        if self._is_running():
            # macOS replaces the document and cancels the previous task.
            self.controller.cancel_file_translation()
        self.controller.start_file_translation(
            Path(path), self._target_code or None
        )

    def _is_running(self) -> bool:
        return str(self._job.get("state") or "") in _RUNNING_STATES

    def save_output(self) -> None:
        """Save the finished translation (File → Save translation…)."""
        self._save_output()

    def _save_output(self) -> None:
        job = self._job
        output = job.get("output")
        if not output:
            return
        output_path = Path(str(output))
        kind = str(job.get("kind") or "").lower()
        suffix = output_path.suffix or (f".{kind}" if kind else ".txt")
        result_name = str(job.get("result_name") or output_path.name)
        source = str(job.get("path") or "")
        directory = Path(source).parent if source else output_path.parent
        default_path = directory / result_name

        destination, _selected = QFileDialog.getSaveFileName(
            self,
            t("Save translation…"),
            str(default_path),
            f"{_kind_label(kind)} (*{suffix})" if kind else f"{t('Files')} (*{suffix})",
        )
        if not destination:
            return
        target = Path(destination)
        if target.suffix.lower() != suffix.lower():
            target = target.with_suffix(suffix)
        self.controller.save_translated_file(target)

    def _reveal_output(self) -> None:
        job = self._job
        output = str(job.get("output") or "")
        source = str(job.get("path") or "")
        if not output and not source:
            return
        target = Path(output or source)
        folder = target.parent if target.suffix else target
        selected = target if output and target.exists() else None

        if os.name == "nt":
            argument = f"/select,{os.path.normpath(str(selected or folder))}"
            started = QProcess.startDetached("explorer", [argument])
            if started is False:
                log.warning("could not open Explorer for %s", folder)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # -- drag and drop ------------------------------------------------------
    @staticmethod
    def _drop_path(url: QUrl) -> Path | None:
        if not url.isLocalFile():
            return None
        path = Path(url.toLocalFile())
        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return path
        return None

    def _drop_candidate(self, event: Any) -> Path | None:
        if not event.mimeData().hasUrls():
            return None
        for url in event.mimeData().urls():
            path = self._drop_path(url)
            if path is not None:
                return path
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        path = self._drop_candidate(event)
        if path is None:
            event.ignore()
            return
        self.drop_zone.set_drag_active(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._drop_candidate(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self.drop_zone.set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.drop_zone.set_drag_active(False)
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        for url in event.mimeData().urls():
            path = self._drop_path(url)
            if path is not None:
                event.acceptProposedAction()
                self._begin_translation(path)
                return
        event.acceptProposedAction()
        self.controller.report_error(t("This file type is not supported."))

    # -- retranslation ------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.heading.setText(t("Files"))
        self.subtitle.setText(
            t("Translate a document and save the result in its original format.")
        )
        self.drop_zone.retranslate_ui()
        self.translate_label.setText(t("Translate to"))
        self.translate_button.setText(t("Translate"))
        self.language_combo.retranslate_ui()
        self.remove_button.set_tooltip(t("Remove file"))
        self.cancel_button.setText(t("Cancel"))
        self.complete_label.setText(t("Translation complete"))
        self.save_button.setText(t("Save file…"))
        self.show_folder_button.setText(t("Show in folder"))
        self.translate_another_button.setText(t("Translate another file"))
        self.retry_button.setText(t("Try again"))
        self._sync_state()
