"""History tab: searchable list of finished translations.

Counterpart of ``Sources/HyMT/Views/HistoryView.swift``.  Rows are real widgets
created once per history change; typing in the search box only toggles their
visibility, so a full store of 400 entries stays responsive.  Every colour and
font comes from the shared design system (:mod:`deepl_ofm.ui.theme`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from PySide6.QtCore import QDate, QLocale, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from . import icons
from .components import (
    Card,
    Divider,
    EmptyState,
    IconButton,
    Pill,
    SearchField,
    SecondaryButton,
)
from .theme import Theme

if TYPE_CHECKING:  # pragma: no cover - typing only, keeps ui -> controller one-way
    from ..controller import AppController


# ---------------------------------------------------------------------------
# Small themed helpers


def _normalise(text: str) -> str:
    """Collapse line breaks and runs of whitespace for a compact snippet."""
    return " ".join((text or "").split())


class _RoleLabel(QLabel):
    """QLabel whose colour follows a palette role and the current theme."""

    def __init__(
        self,
        text: str = "",
        role: str = "text",
        size: int = 12,
        weight: int = 400,
        parent: QWidget | None = None,
        *,
        mono: bool = False,
    ) -> None:
        super().__init__(text, parent)
        self._role = role
        self.setFont(Theme.font(size, weight, mono=mono))
        Theme.changed.connect(self._sync_colour)
        self._sync_colour()

    def set_role(self, role: str) -> None:
        self._role = role
        self._sync_colour()

    def _sync_colour(self, *_args: object) -> None:
        colour = getattr(Theme.palette(), self._role, Theme.palette().text)
        self.setStyleSheet(f"color: {colour};")


class _Snippet(QLabel):
    """Word-wrapped text clamped to a fixed number of lines.

    The full string stays available through :meth:`text` (and as a tooltip), but
    painting stops after ``lines`` visual lines and elides the last one, which
    keeps rows tidy without the layout jumping around.
    """

    def __init__(
        self,
        text: str,
        role: str = "text",
        size: int = 12,
        lines: int = 2,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(_normalise(text), parent)
        self._role = role
        self._line_count = max(1, int(lines))
        self._full_text = _normalise(text)
        self.setFont(Theme.font(size, 400))
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setWordWrap(False)
        self.setToolTip(self._full_text)
        metrics = self.fontMetrics()
        self.setFixedHeight(metrics.lineSpacing() * self._line_count + 2)
        Theme.changed.connect(self._on_theme_changed)

    def set_full_text(self, text: str) -> None:
        self._full_text = _normalise(text)
        super().setText(self._full_text)
        self.setToolTip(self._full_text)
        self.update()

    def _on_theme_changed(self, *_args: object) -> None:
        self.update()

    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        if not self._full_text:
            return
        palette = Theme.palette()
        colour = getattr(palette, self._role, palette.text)
        width = max(1, self.width())
        layout = QTextLayout(self._full_text, self.font())
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(option)
        layout.beginLayout()
        lines = []
        while len(lines) < self._line_count:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(float(width))
            lines.append(line)
        layout.endLayout()
        if not lines:
            return

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.setPen(QColor(colour))
            painter.setFont(self.font())
            metrics = painter.fontMetrics()
            offset = 0.0
            for index, line in enumerate(lines):
                last = index == len(lines) - 1
                consumed = line.textStart() + line.textLength()
                overflow = last and consumed < len(self._full_text)
                baseline = offset + float(line.ascent())
                if overflow:
                    remaining = self._full_text[line.textStart():]
                    text = metrics.elidedText(
                        remaining, Qt.TextElideMode.ElideRight, width
                    )
                    painter.drawText(QPointF(0.0, baseline), text)
                else:
                    painter.drawText(
                        QPointF(0.0, baseline),
                        self._full_text[line.textStart():consumed],
                    )
                offset += float(line.height())
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Date and duration formatting


def _parse_date(value: str) -> datetime | None:
    """Tolerant ISO-8601 parser for a stored date string."""
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone()
    return parsed


def _locale_for(controller: "AppController") -> QLocale:
    try:
        language = controller.settings.interface_language.resolved
        locale = QLocale(language.locale_identifier)
        if locale.language() != QLocale.Language.C:
            return locale
    except Exception:  # noqa: BLE001 - a broken locale must not break the tab
        pass
    return QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)


def _style_text(value: object) -> str:
    """Localised chip text for a style or tone, tolerating enums and None."""
    raw = getattr(value, "value", value)
    text = str(raw or "").strip()
    if not text:
        return ""
    return t(text[:1].upper() + text[1:])


def format_relative_date(value: str, locale: QLocale | None = None) -> str:
    """Return ``today 14:02``, ``yesterday`` or a short local date."""
    parsed = _parse_date(value)
    if parsed is None:
        return (value or "")[:16]
    today = date.today()
    if parsed.date() == today:
        return f"{t('today')} {parsed:%H:%M}"
    if (today - parsed.date()).days == 1:
        return t("yesterday")
    locale = locale or QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    english = locale.language() == QLocale.Language.English
    pattern = "MMM d" if english else "d MMM"
    if parsed.year != today.year:
        pattern += ", yyyy" if english else " yyyy"
    return locale.toString(QDate(parsed.year, parsed.month, parsed.day), pattern)


def format_duration(milliseconds: int) -> str:
    """Short human duration: ``840 ms`` or ``1.2 s``."""
    if milliseconds is None or milliseconds <= 0:
        return ""
    if milliseconds < 1000:
        return f"{int(milliseconds)} ms"
    return f"{milliseconds / 1000.0:.1f} s"


# ---------------------------------------------------------------------------
# Row


class _HistoryRow(QFrame):
    """One history entry: languages, engine, snippets and inline actions."""

    copyRequested = Signal(str)
    restoreRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self, controller: "AppController", entry: object, parent: QWidget | None = None):
        super().__init__(parent)
        self.entry = entry
        self._controller = controller
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        language = controller.settings.interface_language
        source = self._language_name(entry.source_code, language)
        target = self._language_name(entry.target_code, language)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 12, 12, 12)
        outer.setSpacing(12)

        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(6)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(6)

        self.source_chip = Pill(source.upper(), "muted", self)
        self.source_chip.setToolTip(source)
        meta.addWidget(self.source_chip)

        self.arrow_label = QLabel(self)
        self._sync_arrow()
        Theme.changed.connect(self._on_theme_changed)
        self.arrow_label.setFixedSize(12, 16)
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meta.addWidget(self.arrow_label)

        self.target_chip = Pill(target.upper(), "muted", self)
        self.target_chip.setToolTip(target)
        meta.addWidget(self.target_chip)
        meta.addSpacing(4)

        self.style_pill = Pill(_style_text(entry.style), "muted", self)
        self.style_pill.setToolTip(t("Style"))
        meta.addWidget(self.style_pill)
        meta.addSpacing(4)
        if str(entry.tone or "standard") != "standard":
            self.tone_pill = Pill(_style_text(entry.tone), "muted", self)
            self.tone_pill.setToolTip(t("Tone"))
            meta.addWidget(self.tone_pill)
            meta.addSpacing(4)
        else:
            self.tone_pill = None

        self.engine_label = _RoleLabel(entry.engine or "", "faint", 11, parent=self)
        self.engine_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self.engine_label.setToolTip(entry.engine or "")
        meta.addWidget(self.engine_label, 1)

        self.date_label = _RoleLabel(
            format_relative_date(entry.date, _locale_for(controller)),
            "faint",
            11,
            parent=self,
        )
        self.date_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        meta.addWidget(self.date_label)

        duration = format_duration(entry.duration_ms)
        self.duration_label = _RoleLabel(
            f"· {duration}" if duration else "", "faint", 11, parent=self, mono=True
        )
        self.duration_label.setVisible(bool(entry.duration_ms))
        meta.addWidget(self.duration_label)

        column.addLayout(meta)

        self.source_label = _Snippet(
            entry.source_text, "text", 12, 2, self
        )
        column.addWidget(self.source_label)

        self.translated_label = _Snippet(
            entry.translated_text, "muted", 12, 2, self
        )
        column.addWidget(self.translated_label)

        outer.addLayout(column, 1)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(2)

        self.restore_button = IconButton(
            "translate", t("Translate again"), self, size=28, icon_size=14
        )
        self.restore_button.clicked.connect(
            lambda: self.restoreRequested.emit(entry.id)
        )
        actions.addWidget(self.restore_button)

        self.copy_button = IconButton(
            "copy", t("Copy translation"), self, size=28, icon_size=14
        )
        self.copy_button.clicked.connect(lambda: self.copyRequested.emit(entry.id))
        actions.addWidget(self.copy_button)

        self.delete_button = IconButton(
            "trash", t("Delete entry"), self, size=28, icon_size=14
        )
        self.delete_button.clicked.connect(
            lambda: self.deleteRequested.emit(entry.id)
        )
        actions.addWidget(self.delete_button)

        outer.addLayout(actions, 0)

    @staticmethod
    def _language_name(code: str, language: object) -> str:
        from ..core.languages import get_language

        language_obj = get_language(code)
        if language_obj is None:
            return (code or "?").upper()
        return language_obj.display_name(language)

    def matches(self, needle: str) -> bool:
        """Search text, engine, language names and the style/tone words."""
        entry = self.entry
        haystack = [
            entry.source_text,
            entry.translated_text,
            entry.engine,
            self._language_name(
                entry.source_code, self._controller.settings.interface_language
            ),
            self._language_name(
                entry.target_code, self._controller.settings.interface_language
            ),
            _style_text(entry.style),
            _style_text(entry.tone),
        ]
        return any(needle in str(value).casefold() for value in haystack if value)

    def _sync_arrow(self) -> None:
        self.arrow_label.setPixmap(
            icons.pixmap("arrow-right", Theme.palette().faint, 10)
        )

    def _on_theme_changed(self, *_args: object) -> None:
        self._sync_arrow()
        self.update()

    # -- feedback -----------------------------------------------------------
    def show_copied(self) -> None:
        """Flash a check mark after the translation was copied."""
        self.copy_button.set_icon_name("check")
        QTimer.singleShot(1200, self._reset_copy_icon)

    def _reset_copy_icon(self) -> None:
        try:
            self.copy_button.set_icon_name("copy")
        except RuntimeError:  # the row was deleted in the meantime
            pass

    def update_entry(self, entry: object) -> None:
        """Refresh the row in place when the store hands back a new object."""
        self.entry = entry
        self.source_label.set_full_text(entry.source_text)
        self.translated_label.set_full_text(entry.translated_text)
        self.engine_label.setText(entry.engine or "")
        self.engine_label.setToolTip(entry.engine or "")
        duration = format_duration(entry.duration_ms)
        self.duration_label.setText(f"· {duration}" if duration else "")
        self.duration_label.setVisible(bool(entry.duration_ms))
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        language = self._controller.settings.interface_language
        self.source_chip.setText(
            self._language_name(self.entry.source_code, language).upper()
        )
        self.target_chip.setText(
            self._language_name(self.entry.target_code, language).upper()
        )
        self.date_label.setText(
            format_relative_date(self.entry.date, _locale_for(self._controller))
        )
        self._sync_arrow()
        self.style_pill.setText(_style_text(self.entry.style))
        if self.tone_pill is not None:
            self.tone_pill.setText(_style_text(self.entry.tone))
        self.restore_button.set_tooltip(t("Translate again"))
        self.copy_button.set_tooltip(t("Copy translation"))
        self.delete_button.set_tooltip(t("Delete entry"))

    # -- events -------------------------------------------------------------
    def paintEvent(self, event: object) -> None:  # noqa: N802 - Qt API
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            if self.underMouse():
                rect = QRectF(self.rect()).adjusted(5.0, 2.0, -5.0, -2.0)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.card_hover))
                painter.drawRoundedRect(rect, 8.0, 8.0)
            painter.setPen(QColor(palette.border))
            painter.drawLine(18, self.height() - 1, self.width() - 18, self.height() - 1)
        finally:
            painter.end()

    def enterEvent(self, event: object) -> None:  # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:  # noqa: N802
        self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event: object) -> None:  # noqa: N802
        if getattr(event, "button", lambda: None)() == Qt.MouseButton.LeftButton:
            self.restoreRequested.emit(self.entry.id)
            return
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# View


class HistoryView(QWidget):
    """The History tab: header, search, rows and empty states."""

    def __init__(self, controller: "AppController", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.rows: list[_HistoryRow] = []
        self._query = ""
        self.setObjectName("historyView")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(Divider("horizontal", self))

        self.storage_warning = _RoleLabel(
            t("Could not read or save translation history."), "warning", 12, parent=self
        )
        self.storage_warning.setContentsMargins(20, 10, 20, 0)
        self.storage_warning.setWordWrap(True)
        self.storage_warning.setVisible(False)
        root.addWidget(self.storage_warning)

        body = QWidget(self)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 14, 20, 20)
        body_layout.setSpacing(0)

        self.surface = Card("", parent=body, padding=0, spacing=0)
        body_layout.addWidget(self.surface, 1)

        self.stack = QStackedWidget(self.surface)
        self.stack.setObjectName("historyStack")

        self.scroll = QScrollArea(self.stack)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._rows_host = QWidget(self.scroll)
        self._rows_layout = QVBoxLayout(self._rows_host)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)
        self._rows_layout.addStretch(1)
        self.scroll.setWidget(self._rows_host)
        self.stack.addWidget(self.scroll)

        self.empty_state = EmptyState(
            "history",
            t("History is empty"),
            t("Translations will be saved here automatically."),
            self.stack,
        )
        self.stack.addWidget(self.empty_state)

        self.surface.add(self.stack, 1)
        root.addWidget(body, 1)

        self.controller.historyChanged.connect(self.refresh)
        self.controller.interfaceLanguageChanged.connect(self._on_language_changed)
        Theme.changed.connect(self._on_theme_changed)

        self.refresh()

    # -- construction -------------------------------------------------------
    def _build_header(self) -> QWidget:
        header = QWidget(self)
        header.setObjectName("historyHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)

        self.title_label = _RoleLabel(t("History"), "text", 18, 600, header)
        layout.addWidget(self.title_label)

        self.count_label = _RoleLabel("0", "faint", 12, parent=header, mono=True)
        self.count_label.setMinimumWidth(18)
        layout.addWidget(self.count_label)
        layout.addStretch(1)

        self.search = SearchField(t("Search in history"), header)
        self.search.setFixedWidth(250)
        self.search.textChanged.connect(self._on_query_changed)
        layout.addWidget(self.search)

        self.clear_button = SecondaryButton(
            t("Clear"), header, icon_name="trash"
        )
        self.clear_button.setObjectName("clearHistoryButton")
        self.clear_button.setAccessibleName(t("Clear history"))
        self.clear_button.setToolTip(t("Clear history"))
        self.clear_history_button = self.clear_button
        self.clear_button.clicked.connect(self.confirm_clear)
        layout.addWidget(self.clear_button)
        return header

    # -- data ---------------------------------------------------------------
    def entries(self) -> list[object]:
        return list(self.controller.history.entries)

    def visible_rows(self) -> list[_HistoryRow]:
        return [row for row in self.rows if not row.isHidden()]

    def visible_entry_ids(self) -> list[str]:
        return [row.entry.id for row in self.rows if not row.isHidden()]

    def refresh(self) -> None:
        """Synchronise the row widgets with the store.

        Existing rows are reused by entry id.  A normal translation therefore
        adds one row instead of rebuilding all 400, and typing in the search
        box never touches the row widgets at all.
        """
        entries = self.entries()
        existing = {row.entry.id: row for row in self.rows}
        self._rows_host.setUpdatesEnabled(False)
        try:
            while self._rows_layout.count():
                self._rows_layout.takeAt(0)
            rows: list[_HistoryRow] = []
            for entry in entries:
                row = existing.pop(entry.id, None)
                if row is None:
                    row = _HistoryRow(self.controller, entry, self._rows_host)
                    row.copyRequested.connect(self._copy_entry)
                    row.restoreRequested.connect(self._restore_entry)
                    row.deleteRequested.connect(self._delete_entry)
                elif row.entry is not entry:
                    row.update_entry(entry)
                self._rows_layout.addWidget(row)
                rows.append(row)
            for stale in existing.values():
                stale.setParent(None)
                stale.deleteLater()
            self._rows_layout.addStretch(1)
            self.rows = rows
        finally:
            self._rows_host.setUpdatesEnabled(True)
            self._rows_host.updateGeometry()

        self.storage_warning.setVisible(bool(self.controller.history.has_storage_error))
        self.clear_button.setEnabled(bool(entries))
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self._query.strip().casefold()
        visible = 0
        for row in self.rows:
            match = not needle or row.matches(needle)
            row.setVisible(match)
            if match:
                visible += 1
        total = len(self.rows)
        self.count_label.setText(f"{visible}/{total}" if needle else str(total))

        if total and visible:
            self.stack.setCurrentWidget(self.scroll)
        else:
            if not total:
                self.empty_state.set_title(t("History is empty"))
                self.empty_state.set_subtitle(
                    t("Translations will be saved here automatically.")
                )
            else:
                self.empty_state.set_title(t("Nothing found"))
                self.empty_state.set_subtitle(t("Try another query."))
            self.empty_state.retranslate_ui()
            self.stack.setCurrentWidget(self.empty_state)

    # -- actions ------------------------------------------------------------
    def _entry_for(self, entry_id: str) -> object | None:
        return next((row.entry for row in self.rows if row.entry.id == entry_id), None)

    def _copy_entry(self, entry_id: str) -> None:
        entry = self._entry_for(entry_id)
        if entry is None or not entry.translated_text:
            return
        QGuiApplication.clipboard().setText(entry.translated_text)
        row = next((item for item in self.rows if item.entry.id == entry_id), None)
        if row is not None:
            row.show_copied()

    def _restore_entry(self, entry_id: str) -> None:
        self.controller.load_history_entry(entry_id)

    def _delete_entry(self, entry_id: str) -> None:
        self.controller.history.remove(entry_id)
        self.controller.historyChanged.emit()

    def confirm_clear(self) -> None:
        """Ask before wiping the store, then refresh the empty state."""
        if not self.rows:
            return
        answer = QMessageBox.question(
            self,
            t("Clear history?"),
            t("All saved translations will be deleted permanently."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.history.clear()
            self.controller.historyChanged.emit()

    # -- events -------------------------------------------------------------
    def _on_query_changed(self, text: str) -> None:
        self._query = text or ""
        self._apply_filter()

    def _on_language_changed(self, _code: str) -> None:
        self.retranslate_ui()

    def _on_theme_changed(self, *_args: object) -> None:
        self._apply_background()
        self.update()

    def _apply_background(self) -> None:
        palette = Theme.palette()
        self.setStyleSheet(
            f"QWidget#historyView {{ background: {palette.bg}; }}"
            f"QWidget#historyHeader {{ background: {palette.bg}; }}"
        )

    # -- i18n ---------------------------------------------------------------
    def retranslate_ui(self) -> None:
        self.title_label.setText(t("History"))
        self.search.set_placeholder(t("Search in history"))
        self.clear_button.setText(t("Clear"))
        self.clear_button.setAccessibleName(t("Clear history"))
        self.clear_button.setToolTip(t("Clear history"))
        self.storage_warning.setText(t("Could not read or save translation history."))
        for row in self.rows:
            row.retranslate_ui()
        self._apply_filter()
        self._apply_background()

    def showEvent(self, event: object) -> None:  # noqa: N802
        self._apply_background()
        self.refresh()
        super().showEvent(event)
