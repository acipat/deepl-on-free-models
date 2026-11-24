"""Shared widgets for the DeepL-oFM interface.

The components deliberately paint their own surfaces so that every colour is
read from :meth:`deepl_ofm.ui.theme.Theme.palette` at paint time.  Standard
input controls rely on the global stylesheet built in ``theme.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import Palette, Theme

try:  # The catalogue is being produced in parallel; never fail at import.
    from deepl_ofm.i18n import t
except Exception:  # pragma: no cover - only before i18n lands
    def t(key: str, language: Any = None) -> str:  # type: ignore[misc]
        return key


# ---------------------------------------------------------------------------
# Language table access


@dataclass(frozen=True)
class _LanguageEntry:
    code: str
    label: str
    search: str
    language: Any | None = None


_LANGUAGE_TABLE: Any | None = None


def _language_table() -> Any | None:
    """Resolve ``core.languages.LanguageTable`` lazily.

    The languages module is written by another agent and may still be a
    placeholder when this module is imported, hence the tolerant import.
    """
    global _LANGUAGE_TABLE
    if _LANGUAGE_TABLE is not None:
        return _LANGUAGE_TABLE
    try:
        from deepl_ofm.core import languages as module

        table = getattr(module, "LanguageTable", None)
        if table is not None and getattr(table, "ALL", None):
            _LANGUAGE_TABLE = table
            return table
        all_languages = getattr(module, "ALL", None)
        if all_languages:
            _LANGUAGE_TABLE = _SimpleTable(all_languages)
            return _LANGUAGE_TABLE
    except Exception:
        pass
    return None


class _SimpleTable:
    """Fallback holder when languages are exposed as ``ALL`` only."""

    def __init__(self, languages: Sequence[Any]) -> None:
        self.ALL = list(languages)
        self.AUTO = next(
            (item for item in languages if _is_auto(item)),
            None,
        )


def _is_auto(language: Any) -> bool:
    if language is None:
        return False
    if getattr(language, "is_auto", False):
        return True
    return str(getattr(language, "code", "")) == "auto"


def _language_name(language: Any | None, app_language: Any = None) -> str:
    if language is None:
        return t("Auto-detect")
    display = getattr(language, "display_name", None)
    if callable(display):
        try:
            return str(display(app_language))
        except TypeError:
            try:
                return str(display())
            except Exception:
                pass
        except Exception:
            pass
    for attribute in ("local_name", "english_name", "code"):
        value = getattr(language, attribute, "")
        if value:
            return str(value)
    return t("Auto-detect") if _is_auto(language) else ""


def _language_keywords(language: Any) -> str:
    parts = []
    for attribute in ("code", "local_name", "english_name", "bcp47"):
        value = getattr(language, attribute, None)
        if value:
            parts.append(str(value))
    display = getattr(language, "display_name", None)
    if callable(display):
        try:
            parts.append(str(display()))
        except Exception:
            pass
    return " ".join(parts).lower()


def _resolve_colour(value: str | Callable[[Palette], str], palette: Palette) -> str:
    return value(palette) if callable(value) else value


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _font(size: int, weight: int = 400, *, mono: bool = False) -> QFont:
    return Theme.font(size, weight, mono=mono)


def _text_width(font: QFont, text: str) -> int:
    return QFontMetrics(font).horizontalAdvance(text)


def _role_colour(palette: Palette, role: str) -> str:
    if role == "accent":
        return palette.accent_hover
    if role == "faint":
        return palette.faint
    if role == "muted":
        return palette.muted
    if role == "danger":
        return palette.danger
    if role == "success":
        return palette.success
    if role == "warning":
        return palette.warning
    return palette.text


# ---------------------------------------------------------------------------
# Small internal primitives


class _Glyph(QWidget):
    """A tiny paint-time icon; resolves its colour on every repaint."""

    def __init__(
        self,
        name: str = "info",
        size: int = 16,
        colour: str | Callable[[Palette], str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._size = int(size)
        self._colour = colour if colour is not None else (lambda p: p.muted)
        self.setFixedSize(self._size, self._size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_name(self, name: str) -> None:
        if name != self._name:
            self._name = name
            self.update()

    def name(self) -> str:
        return self._name

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802 - Qt naming
        palette = Theme.palette()
        colour = _resolve_colour(self._colour, palette)
        rendered = icons.pixmap(
            self._name, colour, self._size, self.devicePixelRatioF()
        )
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawPixmap(0, 0, rendered)
        finally:
            painter.end()


class _ThemedLabel(QLabel):
    """QLabel whose colour follows the palette without a global QSS rule."""

    def __init__(
        self,
        text: str = "",
        role: str = "text",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._role = role
        self._apply_colour()
        Theme.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, dark: bool) -> None:
        self._apply_colour()

    def _apply_colour(self) -> None:
        colour = _role_colour(Theme.palette(), self._role)
        self.setStyleSheet(f"color: {colour}; background: transparent;")

    def set_role(self, role: str) -> None:
        self._role = role
        self._apply_colour()


class _Bar(QWidget):
    """The small accent rule used by settings cards."""

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            palette = Theme.palette()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.accent))
            painter.drawRoundedRect(
                QRectF(0.0, 0.0, 3.0, float(self.height())), 1.5, 1.5
            )
        finally:
            painter.end()


class _IconBadge(QWidget):
    def __init__(
        self,
        name: str = "sparkles",
        size: int = 52,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        self.setFixedSize(size, size)

    def set_name(self, name: str) -> None:
        self._name = name
        self.setVisible(bool(name))
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette.accent_soft))
            painter.drawEllipse(QRectF(self.rect()))
            icon_size = max(18, self._size // 2)
            rendered = icons.pixmap(
                self._name,
                palette.accent_hover,
                icon_size,
                self.devicePixelRatioF(),
            )
            x = (self.width() - icon_size) / 2.0
            y = (self.height() - icon_size) / 2.0
            painter.drawPixmap(QPointF(x, y), rendered)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Card


class Card(QFrame):
    """A calm rounded surface with an optional header (title + actions)."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
        *,
        icon_name: str = "",
        padding: int = 16,
        spacing: int = 12,
        accent_bar: bool = False,
    ) -> None:
        if isinstance(subtitle, QWidget) and parent is None:
            parent = subtitle
            subtitle = ""
        if isinstance(title, QWidget) and parent is None:
            parent = title
            title = ""
        super().__init__(parent)
        self._title_text = str(title)
        self._subtitle_text = str(subtitle)
        self._icon_name = str(icon_name)
        self._show_accent_bar = bool(accent_bar)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding, padding, padding)
        outer.setSpacing(spacing)

        self._header = QWidget(self)
        header_layout = QHBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        self._accent = _Bar(self._header)
        self._accent.setFixedWidth(3)
        self._accent.setFixedHeight(32)
        header_layout.addWidget(self._accent, 0, Qt.AlignmentFlag.AlignTop)

        self._icon = _Glyph(self._icon_name or "info", 16, lambda p: p.muted, self._header)
        header_layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(3)
        self._title = _ThemedLabel(self._title_text, "text", self._header)
        self._title.setFont(_font(15, 600))
        self._subtitle = _ThemedLabel(self._subtitle_text, "muted", self._header)
        self._subtitle.setFont(_font(12))
        self._subtitle.setWordWrap(True)
        text_column.addWidget(self._title)
        text_column.addWidget(self._subtitle)
        header_layout.addLayout(text_column, 1)

        self._header_actions = QHBoxLayout()
        self._header_actions.setContentsMargins(0, 0, 0, 0)
        self._header_actions.setSpacing(2)
        header_layout.addLayout(self._header_actions, 0)

        outer.addWidget(self._header)

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(spacing)
        outer.addLayout(self.body, 1)

        self._sync_header()

    # -- public API ---------------------------------------------------------
    @property
    def content_layout(self) -> QVBoxLayout:
        """Layout where view content belongs."""
        return self.body

    @property
    def header_actions(self) -> QHBoxLayout:
        """Layout for compact header buttons; call :meth:`add_header_widget`."""
        return self._header_actions

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_header_widget(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self._header_actions.addWidget(widget, stretch)
        self.show_header()
        return widget

    def show_header(self) -> None:
        self._header.setVisible(True)
        self.updateGeometry()

    def set_title(self, title: str) -> None:
        self._title_text = str(title)
        self._title.setText(self._title_text)
        self._sync_header()

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle_text = str(subtitle)
        self._subtitle.setText(self._subtitle_text)
        self._sync_header()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = str(name)
        self._icon.set_name(name or "info")
        self._sync_header()

    def title(self) -> str:
        return self._title_text

    def set_accent_bar(self, visible: bool) -> None:
        self._show_accent_bar = bool(visible)
        self._sync_header()

    def retranslate_ui(self) -> None:
        self._title.setText(self._title_text)
        self._subtitle.setText(self._subtitle_text)
        self._sync_header()

    # -- internals ----------------------------------------------------------
    def _sync_header(self) -> None:
        has_text = bool(self._title_text or self._subtitle_text)
        has_icon = bool(self._icon_name)
        has_actions = self._header_actions.count() > 0
        self._title.setVisible(bool(self._title_text))
        self._subtitle.setVisible(bool(self._subtitle_text))
        self._icon.setVisible(has_icon)
        self._accent.setVisible(self._show_accent_bar)
        self._header.setVisible(
            has_text or has_icon or has_actions or self._show_accent_bar
        )
        self.updateGeometry()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            paintable = _rounded(rect, float(Theme.radius))
            painter.fillPath(paintable, QColor(palette.card))
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawPath(paintable)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Progress


class ProgressBar(QWidget):
    """A slim determinate/indeterminate progress indicator."""

    value_changed = Signal(int)

    def __init__(self, value: int = 0, parent: QWidget | None = None) -> None:
        if isinstance(value, QWidget) and parent is None:
            parent = value
            value = 0
        super().__init__(parent)
        self._value = 0
        self._indeterminate = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.set_value(value)

    def set_value(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        changed = clamped != self._value
        self._value = clamped
        self.setAccessibleDescription(f"{clamped}%")
        if changed:
            self.value_changed.emit(clamped)
            self.update()

    #: Qt-style alias used by some views.
    setValue = set_value

    def value(self) -> int:
        return self._value

    def indeterminate(self, enabled: bool = True) -> None:
        self._indeterminate = bool(enabled)
        if self._indeterminate:
            self._phase = 0.18
        if self._indeterminate and self.isVisible():
            self._timer.start()
        elif not self._indeterminate:
            self._timer.stop()
        self.update()

    def is_indeterminate(self) -> bool:
        return self._indeterminate

    def retranslate_ui(self) -> None:
        self.update()

    def showEvent(self, event: QEvent) -> None:  # noqa: N802
        super().showEvent(event)
        if self._indeterminate:
            self._timer.start()

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        self._timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self._phase = (self._phase + 0.018) % 1.0
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            track = QRectF(0.0, 0.0, float(self.width()), float(self.height()))
            radius = track.height() / 2.0
            painter.setBrush(QColor(palette.card_hover))
            painter.drawRoundedRect(track, radius, radius)

            if self._indeterminate:
                segment = max(48.0, track.width() * 0.32)
                start = (track.width() + segment) * self._phase - segment
                fill = QRectF(start, 0.0, segment, track.height())
                painter.save()
                painter.setClipPath(_rounded(track, radius))
                painter.setBrush(QColor(palette.accent))
                painter.drawRoundedRect(fill, radius, radius)
                painter.restore()
            elif self._value > 0:
                fill = QRectF(
                    0.0,
                    0.0,
                    max(track.height(), track.width() * self._value / 100.0),
                    track.height(),
                )
                painter.setBrush(QColor(palette.accent))
                painter.drawRoundedRect(fill, radius, radius)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Pills


_PILL_VARIANTS = ("accent", "muted", "success", "danger", "warning")


def _pill_colours(palette: Palette, variant: str) -> tuple[str, str]:
    if variant == "accent":
        return palette.accent_soft, palette.accent_hover
    if variant == "success":
        return Theme.mix(palette.card, palette.success, 0.14), palette.success
    if variant == "danger":
        return Theme.mix(palette.card, palette.danger, 0.14), palette.danger
    if variant == "warning":
        return Theme.mix(palette.card, palette.warning, 0.14), palette.warning
    return palette.card_hover, palette.muted


class Pill(QLabel):
    """A small status chip."""

    def __init__(
        self,
        text: str = "",
        variant: str = "muted",
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(variant, QWidget) and parent is None:
            parent = variant
            variant = "muted"
        if isinstance(text, QWidget) and parent is None:
            parent = text
            text = ""
        super().__init__(str(text), parent)
        self._pill_variant = variant if variant in _PILL_VARIANTS else "muted"
        self._text_key: str | None = None
        self.setFont(_font(11, 600))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def setText(self, text: str) -> None:  # noqa: N802 - QLabel API
        super().setText(str(text))
        self.updateGeometry()
        self.update()

    def set_variant(self, variant: str) -> None:
        self._pill_variant = variant if variant in _PILL_VARIANTS else "muted"
        self.update()

    def variant(self) -> str:
        return self._pill_variant

    def set_text_key(self, key: str | None) -> None:
        self._text_key = key
        if key is not None:
            self.setText(t(key))

    def retranslate_ui(self) -> None:
        if self._text_key is not None:
            self.setText(t(self._text_key))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        width = _text_width(self.font(), self.text()) + 18
        return QSize(max(24, width), 22)

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        background, foreground = _pill_colours(palette, self._pill_variant)
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect())
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(rect, rect.height() / 2.0, rect.height() / 2.0)
            painter.setPen(QColor(foreground))
            painter.setFont(self.font())
            painter.drawText(
                self.rect(),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextSingleLine,
                self.text(),
            )
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Search


class SearchField(QLineEdit):
    """A compact search input with a leading glyph and a clear button."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        if isinstance(placeholder, QWidget) and parent is None:
            parent = placeholder
            placeholder = ""
        super().__init__(parent)
        self._placeholder_key = str(placeholder) or "Search"
        self._search_action = self.addAction(
            icons.icon("search", Theme.palette().muted, 15),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(34)
        self.setFont(_font(13))
        self.setProperty("role", "search")
        self.style().unpolish(self)
        self.style().polish(self)
        self.setAccessibleName(t(self._placeholder_key))
        self.retranslate_ui()
        Theme.changed.connect(self._on_theme_changed)

    def set_placeholder(self, placeholder: str) -> None:
        self._placeholder_key = str(placeholder) or "Search"
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        text = t(self._placeholder_key)
        self.setPlaceholderText(text)
        self.setAccessibleName(text)

    def _on_theme_changed(self, dark: bool) -> None:
        colour = Theme.palette().muted
        self._search_action.setIcon(icons.icon("search", colour, 15))


class SearchBar(SearchField):
    """Alias-friendly search input for list panes."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(placeholder, parent)
        self.setObjectName("searchBar")


# ---------------------------------------------------------------------------
# Language picker


class _LanguageItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option: QStyleOptionViewItem, index: Any) -> QSize:  # noqa: N802
        return QSize(0, 32)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: Any,
    ) -> None:
        palette = Theme.palette()
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(option.rect).adjusted(3.0, 1.0, -3.0, -1.0)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
            if selected:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.accent_soft))
                painter.drawRoundedRect(rect, 7.0, 7.0)
            elif hovered:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.card_hover))
                painter.drawRoundedRect(rect, 7.0, 7.0)

            painter.setFont(_font(13, 600 if selected else 400))
            painter.setPen(QColor(palette.text))
            label_rect = rect.adjusted(10.0, 0.0, -30.0, 0.0)
            text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
            metrics = QFontMetrics(painter.font())
            elided = metrics.elidedText(
                text, Qt.TextElideMode.ElideRight, int(label_rect.width())
            )
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                elided,
            )
            if selected:
                check = icons.pixmap(
                    "check", palette.accent_hover, 14, painter.device().devicePixelRatioF()
                )
                painter.drawPixmap(
                    QPointF(rect.right() - 24.0, rect.center().y() - 7.0), check
                )
        finally:
            painter.restore()


class _LanguagePopup(QFrame):
    """A searchable command-palette-style popup anchored under the combo."""

    selected = Signal(str)
    dismissed = Signal()
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setObjectName("languagePopup")
        self._entries: list[_LanguageEntry] = []
        self._current_code = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search = SearchField(t("Search language"), self)
        self.search.setProperty("embedded", True)
        self.search.style().unpolish(self.search)
        self.search.style().polish(self.search)
        self.search.setFixedHeight(34)
        self.search.installEventFilter(self)
        self.search.returnPressed.connect(self._choose_current)
        layout.addWidget(self.search)

        self.list = QListWidget(self)
        self.list.setObjectName("languageList")
        self.list.setProperty("flat", True)
        self.list.style().unpolish(self.list)
        self.list.style().polish(self.list)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list.setItemDelegate(_LanguageItemDelegate(self.list))
        self.list.setUniformItemSizes(True)
        self.list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setMouseTracking(True)
        self.list.viewport().setMouseTracking(True)
        self.list.itemClicked.connect(self._choose_item)
        layout.addWidget(self.list, 1)

        self.search.textChanged.connect(self._filter)

    # -- population ---------------------------------------------------------
    def set_entries(self, entries: Sequence[_LanguageEntry], current: str) -> None:
        self._entries = list(entries)
        self.list.clear()
        for entry in self._entries:
            item = QListWidgetItem(entry.label)
            item.setData(Qt.ItemDataRole.UserRole, entry.code)
            item.setData(Qt.ItemDataRole.UserRole + 1, entry.search)
            item.setSizeHint(QSize(0, 32))
            self.list.addItem(item)
        self._current_code = current

    def prepare(self, initial: str) -> None:
        self.search.blockSignals(True)
        self.search.setText(initial)
        self.search.blockSignals(False)
        self._filter(initial)
        self.search.setFocus(Qt.FocusReason.PopupFocusReason)
        if initial:
            self.search.selectAll()

    def retranslate_ui(self) -> None:
        self.search.retranslate_ui()

    # -- filtering / selection ---------------------------------------------
    def _filter(self, query: str) -> None:
        needle = query.strip().lower()
        first_visible: QListWidgetItem | None = None
        current_visible: QListWidgetItem | None = None
        for row in range(self.list.count()):
            item = self.list.item(row)
            haystack = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").lower()
            label = str(item.text()).lower()
            visible = not needle or needle in haystack or needle in label
            item.setHidden(not visible)
            if visible:
                if first_visible is None:
                    first_visible = item
                if item.data(Qt.ItemDataRole.UserRole) == self._current_code:
                    current_visible = item
        target = current_visible or first_visible
        self.list.setCurrentItem(target)
        if target is not None:
            self.list.scrollToItem(target, QListWidget.ScrollHint.PositionAtCenter)

    def _visible_items(self) -> list[QListWidgetItem]:
        return [
            self.list.item(row)
            for row in range(self.list.count())
            if not self.list.item(row).isHidden()
        ]

    def _move_current(self, delta: int) -> None:
        items = self._visible_items()
        if not items:
            return
        current = self.list.currentItem()
        if current in items:
            index = items.index(current)
        else:
            index = 0
        target = items[max(0, min(len(items) - 1, index + delta))]
        self.list.setCurrentItem(target)
        self.list.scrollToItem(target, QListWidget.ScrollHint.PositionAtCenter)

    def _choose_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            visible = self._visible_items()
            item = visible[0] if visible else None
        if item is not None:
            self._choose_item(item)

    def _choose_item(self, item: QListWidgetItem) -> None:
        code = str(item.data(Qt.ItemDataRole.UserRole) or "")
        self.hide()
        self.selected.emit(code)

    # -- events -------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.dismissed.emit()
            return
        super().keyPressEvent(event)

    def hideEvent(self, event: QEvent) -> None:  # noqa: N802
        super().hideEvent(event)
        self.closed.emit()

    def eventFilter(self, watched: Any, event: QEvent) -> bool:  # noqa: N802
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._move_current(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._choose_current()
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                self.dismissed.emit()
                return True
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            path = _rounded(rect, float(Theme.radius))
            painter.fillPath(path, QColor(palette.card))
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawPath(path)
        finally:
            painter.end()


class LanguageCombo(QWidget):
    """A searchable language picker with a keyboard-friendly popup."""

    code_changed = Signal(str)

    def __init__(
        self,
        include_auto: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(include_auto, QWidget) and parent is None:
            parent = include_auto
            include_auto = True
        super().__init__(parent)
        self._include_auto = bool(include_auto)
        self._languages: list[Any] | None = None
        self._languages_explicit = False
        self._code = "auto" if self._include_auto else ""
        self._detected: Any | None = None
        self._hovered = False
        self._popup_open = False
        self._popup = _LanguagePopup(self)
        self._popup.selected.connect(self._on_popup_selected)
        self._popup.dismissed.connect(self._on_popup_dismissed)
        self._popup.closed.connect(self._on_popup_closed)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(140)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # -- data ---------------------------------------------------------------
    def _ensure_languages(self) -> None:
        if self._languages:
            return
        if self._languages is not None and self._languages_explicit:
            return
        table = _language_table()
        resolved = list(getattr(table, "ALL", []) or []) if table else []
        if resolved:
            self._languages = resolved
        elif self._languages is None:
            self._languages = []

    def _entries(self) -> list[_LanguageEntry]:
        self._ensure_languages()
        table = _language_table()
        entries: list[_LanguageEntry] = []
        if self._include_auto:
            auto = getattr(table, "AUTO", None) if table else None
            label = _language_name(auto)
            entries.append(
                _LanguageEntry(
                    "auto",
                    label,
                    f"auto detect auto-detect {label}".lower(),
                    auto,
                )
            )
        for language in self._languages or []:
            code = str(getattr(language, "code", ""))
            if not code or _is_auto(language):
                continue
            entries.append(
                _LanguageEntry(
                    code,
                    _language_name(language),
                    _language_keywords(language),
                    language,
                )
            )
        return entries

    def set_languages(self, languages: Sequence[Any]) -> None:
        self._languages = list(languages)
        self._languages_explicit = bool(self._languages)
        codes = {str(getattr(item, "code", "")) for item in self._languages}
        if self._include_auto:
            codes.add("auto")
        if self._code not in codes:
            self._code = "auto" if self._include_auto else next(iter(codes), "")
        self.update()
        self.updateGeometry()

    def set_include_auto(self, include: bool) -> None:
        if self._include_auto == bool(include):
            return
        self._include_auto = bool(include)
        if not self._include_auto and self._code == "auto":
            entries = [entry for entry in self._entries() if entry.code != "auto"]
            self._code = entries[0].code if entries else ""
        elif self._include_auto and not self._code:
            self._code = "auto"
        self.updateGeometry()
        self.update()

    def include_auto(self) -> bool:
        return self._include_auto

    def set_detected(self, language: Any | None) -> None:
        """Show ``Auto-detect · <language>`` once detection has run."""
        self._detected = language
        self.updateGeometry()
        self.update()

    def set_code(self, code: str | None) -> None:
        value = str(code) if code else ""
        if not self._include_auto and value == "auto":
            value = ""
        self._code = value
        if self._include_auto and self._code == "auto":
            self._detected = None
        self.update()

    def code(self) -> str:
        self._ensure_languages()
        entries = self._entries()
        if not self._code:
            self._code = "auto" if self._include_auto else (
                entries[0].code if entries else ""
            )
        return self._code

    # -- display ------------------------------------------------------------
    def display_text(self) -> str:
        """The full name drawn inside the picker (handy for tooltips)."""
        return self._display_text()

    def _display_text(self) -> str:
        code = self.code()
        entries = self._entries()
        entry = next((item for item in entries if item.code == code), None)
        if entry is None:
            return code.upper() if code else t("Language")
        if code == "auto" and self._detected is not None:
            detected = _language_name(self._detected)
            if detected and detected != entry.label:
                return f"{entry.label} · {detected}"
        return entry.label

    def sizeHint(self) -> QSize:  # noqa: N802
        width = _text_width(_font(13, 500), self._display_text()) + 44
        return QSize(max(150, width), 34)

    # -- interactions -------------------------------------------------------
    def _open_popup(self, initial: str = "") -> None:
        entries = self._entries()
        self._popup.set_entries(entries, self.code())

        anchor = self.mapToGlobal(QPoint(0, self.height() + 6))
        screen = QGuiApplication.screenAt(anchor) or self.screen()
        available = (
            screen.availableGeometry()
            if screen is not None
            else QRect(anchor.x(), anchor.y(), 420, 680)
        )
        width = max(self.width(), 300)
        height = min(380, max(240, available.height() - 36))
        self._popup.setFixedSize(width, height)
        x = min(max(anchor.x(), available.left() + 8), available.right() - width - 8)
        y = anchor.y()
        if y + height > available.bottom() - 8:
            y = self.mapToGlobal(QPoint(0, 0)).y() - height - 6
        y = min(max(y, available.top() + 8), available.bottom() - height - 8)
        self._popup.move(x, y)
        self._popup_open = True
        self._popup.show()
        self._popup.raise_()
        self._popup.prepare(initial)
        self.update()

    def _close_popup(self) -> None:
        if self._popup.isVisible():
            self._popup.hide()
        self._popup_open = False
        self.update()

    def _on_popup_selected(self, code: str) -> None:
        self._popup_open = False
        self._select(code, emit=True)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def _on_popup_dismissed(self) -> None:
        self._popup_open = False
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def _on_popup_closed(self) -> None:
        self._popup_open = False
        self.update()

    def _select(self, code: str, emit: bool) -> None:
        previous = self._code
        self._code = str(code)
        self.update()
        if emit and previous != self._code:
            self.code_changed.emit(self._code)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._popup_open:
                self._close_popup()
            else:
                self._open_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hovered = True
        self.update()

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self._hovered = False
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        if key in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
            Qt.Key.Key_Down,
            Qt.Key.Key_Up,
            Qt.Key.Key_F4,
        ):
            self._open_popup()
            event.accept()
            return
        modifiers = event.modifiers() & (
            Qt.KeyboardModifier.ControlModifier
            | Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
        )
        text = event.text()
        if text and not modifiers and text.isprintable() and text.strip():
            self._open_popup(text)
            event.accept()
            return
        super().keyPressEvent(event)

    def retranslate_ui(self) -> None:
        self._popup.retranslate_ui()
        self.updateGeometry()
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            focused = (
                self.hasFocus()
                or self._popup_open
                or (self._popup is not None and self._popup.isVisible())
            )
            rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            path = _rounded(rect, 9.0)
            painter.fillPath(path, QColor(palette.card))
            border = palette.accent if focused else (
                palette.faint if self._hovered else palette.border
            )
            painter.setPen(QPen(QColor(border), 1.0))
            painter.drawPath(path)
            if focused:
                ring = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
                painter.setPen(QPen(QColor(palette.accent), 1.0))
                painter.drawPath(_rounded(ring, 9.0))

            font = _font(13, 500)
            painter.setFont(font)
            painter.setPen(QColor(palette.text))
            metrics = QFontMetrics(font)
            text_rect = rect.adjusted(11.0, 0.0, -30.0, 0.0)
            label = metrics.elidedText(
                self._display_text(),
                Qt.TextElideMode.ElideRight,
                max(10, int(text_rect.width())),
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label,
            )
            chevron = "chevron-up" if self._popup_open else "chevron-down"
            rendered = icons.pixmap(
                chevron,
                palette.muted,
                12,
                self.devicePixelRatioF(),
            )
            painter.drawPixmap(
                QPointF(
                    rect.right() - 10.0 - 12.0,
                    rect.center().y() - 6.0,
                ),
                rendered,
            )
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Chips


class ChipGroup(QWidget):
    """A row of mutually exclusive chips with a string value."""

    changed = Signal(str)

    def __init__(
        self,
        options: Sequence[tuple[str, str]] | None = None,
        value: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(options, QWidget) and parent is None:
            parent = options
            options = None
        super().__init__(parent)
        self._options: list[tuple[str, str]] = list(options or [])
        self._value = value or (self._options[0][0] if self._options else "")
        self._hover = -1
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    # -- data ---------------------------------------------------------------
    def options(self) -> list[tuple[str, str]]:
        return list(self._options)

    def set_options(
        self,
        options: Sequence[tuple[str, str]],
        value: str | None = None,
    ) -> None:
        self._options = list(options)
        values = {option[0] for option in self._options}
        if value is not None and value in values:
            self._value = value
        elif self._value not in values:
            self._value = self._options[0][0] if self._options else ""
        self.updateGeometry()
        self.update()

    def value(self) -> str:
        return self._value

    def set_value(self, value: str) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()

    def retranslate_ui(self) -> None:
        self.update()

    # -- geometry -----------------------------------------------------------
    def _chip_rects(self) -> list[QRectF]:
        if not self._options:
            return []
        metrics = QFontMetrics(_font(12, 600))
        widths = [
            metrics.horizontalAdvance(label) + 22
            for _, label in self._options
        ]
        rects: list[QRectF] = []
        x = 3.0
        for width in widths:
            rects.append(QRectF(x, 3.0, float(width), self.height() - 6.0))
            x += width
        return rects

    def sizeHint(self) -> QSize:  # noqa: N802
        rects = self._chip_rects()
        width = int(rects[-1].right() + 3.0) if rects else 0
        return QSize(max(0, width), 32)

    def _index_at(self, position: QPointF) -> int:
        for index, rect in enumerate(self._chip_rects()):
            if rect.contains(position):
                return index
        return -1

    # -- events -------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position())
            if 0 <= index < len(self._options):
                code = self._options[index][0]
                if code != self._value:
                    self._value = code
                    self.update()
                    self.changed.emit(code)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._hover != -1:
            self._hover = -1
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._options:
            super().keyPressEvent(event)
            return
        values = [option[0] for option in self._options]
        index = values.index(self._value) if self._value in values else 0
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            index = max(0, index - 1)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            index = min(len(values) - 1, index + 1)
        elif event.key() == Qt.Key.Key_Home:
            index = 0
        elif event.key() == Qt.Key.Key_End:
            index = len(values) - 1
        else:
            super().keyPressEvent(event)
            return
        code = values[index]
        if code != self._value:
            self._value = code
            self.changed.emit(code)
        self.update()
        event.accept()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            outer_path = _rounded(outer, 9.0)
            painter.fillPath(outer_path, QColor(palette.card))
            border = palette.accent if self.hasFocus() else palette.border
            painter.setPen(QPen(QColor(border), 1.0))
            painter.drawPath(outer_path)

            for index, ((code, label), rect) in enumerate(
                zip(self._options, self._chip_rects())
            ):
                active = code == self._value
                if active:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(palette.accent_soft))
                    painter.drawRoundedRect(rect, 7.0, 7.0)
                elif index == self._hover:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(palette.card_hover))
                    painter.drawRoundedRect(rect, 7.0, 7.0)
                painter.setFont(_font(12, 600 if active else 500))
                painter.setPen(QColor(palette.accent_hover if active else palette.muted))
                painter.drawText(
                    rect,
                    Qt.AlignmentFlag.AlignCenter,
                    label,
                )
        finally:
            painter.end()


_STYLE_OPTIONS = (("auto", "Auto"), ("literal", "Literal"), ("natural", "Natural"))
_TONE_OPTIONS = (
    ("standard", "Default"),
    ("formal", "Formal"),
    ("casual", "Casual"),
)


def _localised(options: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(code, t(label)) for code, label in options]


class StyleChips(ChipGroup):
    def __init__(self, value: str = "auto", parent: QWidget | None = None) -> None:
        if isinstance(value, QWidget) and parent is None:
            parent = value
            value = "auto"
        super().__init__(_localised(_STYLE_OPTIONS), value, parent)
        self.setAccessibleName(t("Style"))

    def retranslate_ui(self) -> None:
        self.set_options(_localised(_STYLE_OPTIONS), self.value())
        self.setAccessibleName(t("Style"))


class ToneChips(ChipGroup):
    def __init__(
        self,
        value: str = "standard",
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(value, QWidget) and parent is None:
            parent = value
            value = "standard"
        super().__init__(_localised(_TONE_OPTIONS), value, parent)
        self.setAccessibleName(t("Tone"))

    def retranslate_ui(self) -> None:
        self.set_options(_localised(_TONE_OPTIONS), self.value())
        self.setAccessibleName(t("Tone"))


# ---------------------------------------------------------------------------
# Segmented control


class SegmentedControl(QWidget):
    """Equal-width segmented selector with an integer index."""

    changed = Signal(int)

    def __init__(
        self,
        labels: Sequence[str] | None = None,
        index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(labels, QWidget) and parent is None:
            parent = labels
            labels = None
        super().__init__(parent)
        self._labels = list(labels or [])
        self._index = 0
        self._hover = -1
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.set_index(index)

    def set_labels(self, labels: Sequence[str]) -> None:
        self._labels = list(labels)
        self._index = max(0, min(self._index, len(self._labels) - 1)) if self._labels else 0
        self.updateGeometry()
        self.update()

    def labels(self) -> list[str]:
        return list(self._labels)

    def set_index(self, index: int) -> None:
        if not self._labels:
            self._index = 0
        else:
            self._index = max(0, min(int(index), len(self._labels) - 1))
        self.update()

    def index(self) -> int:
        return self._index

    def current_index(self) -> int:
        return self._index

    def retranslate_ui(self) -> None:
        self.update()

    def _display_labels(self) -> list[str]:
        return [t(label) for label in self._labels]

    def _segment_rects(self) -> list[QRectF]:
        if not self._labels:
            return []
        inner = QRectF(3.0, 3.0, self.width() - 6.0, self.height() - 6.0)
        width = inner.width() / len(self._labels)
        return [
            QRectF(inner.left() + width * index, inner.top(), width, inner.height())
            for index in range(len(self._labels))
        ]

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetrics(_font(12, 500))
        width = max(
            [metrics.horizontalAdvance(label) + 34 for label in self._labels] or [0]
        )
        return QSize(max(120, width * max(1, len(self._labels))), 34)

    def _index_at(self, position: QPointF) -> int:
        for index, rect in enumerate(self._segment_rects()):
            if rect.contains(position):
                return index
        return -1

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position())
            if 0 <= index < len(self._labels):
                self._select(index)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        index = self._index_at(event.position())
        if index != self._hover:
            self._hover = index
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._hover != -1:
            self._hover = -1
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if not self._labels:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._select(max(0, self._index - 1))
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._select(min(len(self._labels) - 1, self._index + 1))
        elif event.key() == Qt.Key.Key_Home:
            self._select(0)
        elif event.key() == Qt.Key.Key_End:
            self._select(len(self._labels) - 1)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _select(self, index: int) -> None:
        if index == self._index:
            return
        self._index = index
        self.update()
        self.changed.emit(index)

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            outer_path = _rounded(outer, 8.0)
            painter.fillPath(outer_path, QColor(palette.card_hover))
            border = palette.accent if self.hasFocus() else palette.border
            painter.setPen(QPen(QColor(border), 1.0))
            painter.drawPath(outer_path)

            labels = self._display_labels()
            for index, rect in enumerate(self._segment_rects()):
                active = index == self._index
                if active:
                    painter.setPen(QPen(QColor(palette.border), 1.0))
                    painter.setBrush(QColor(palette.card))
                    painter.drawRoundedRect(rect, 6.0, 6.0)
                elif index == self._hover:
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(palette.card))
                    painter.drawRoundedRect(rect, 6.0, 6.0)
                painter.setFont(_font(12, 600 if active else 500))
                painter.setPen(QColor(palette.text if active else palette.muted))
                label = labels[index] if index < len(labels) else ""
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Form rows


class FormRow(QWidget):
    """Label + control + optional hint, aligned like a native settings form."""

    def __init__(
        self,
        label: str = "",
        control: QWidget | None = None,
        hint: str = "",
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(hint, QWidget) and parent is None:
            parent = hint
            hint = ""
        super().__init__(parent)
        self._label_text = str(label)
        self._hint_text = str(hint)
        self._control = control
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(5)
        grid.setColumnStretch(1, 1)

        self._label = _ThemedLabel(self._label_text, "muted", self)
        self._label.setFont(_font(12, 500))
        self._label.setFixedWidth(150)
        self._label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        self._label.setContentsMargins(0, 8, 0, 0)
        grid.addWidget(self._label, 0, 0)

        self._control_host = QWidget(self)
        host = QHBoxLayout(self._control_host)
        host.setContentsMargins(0, 0, 0, 0)
        host.setSpacing(8)
        if control is not None:
            host.addWidget(control, 1)
        grid.addWidget(self._control_host, 0, 1)

        self._hint = _ThemedLabel(self._hint_text, "muted", self)
        self._hint.setFont(_font(11))
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(self._hint_text))
        grid.addWidget(self._hint, 1, 1)
        self._grid = grid
        self._host = host
        self._sync_label()

    def set_label(self, label: str) -> None:
        self._label_text = str(label)
        self._label.setText(self._label_text)
        self._sync_label()

    def label(self) -> str:
        return self._label_text

    def set_hint(self, hint: str) -> None:
        self._hint_text = str(hint)
        self._hint.setText(self._hint_text)
        self._hint.setVisible(bool(self._hint_text))

    def hint(self) -> str:
        return self._hint_text

    def set_control(self, control: QWidget) -> None:
        while self._host.count():
            item = self._host.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._control = control
        if control is not None:
            self._host.addWidget(control, 1)

    def control(self) -> QWidget | None:
        return self._control

    def control_host(self) -> QWidget:
        return self._control_host

    def _sync_label(self) -> None:
        self._label.setVisible(bool(self._label_text))
        self._label.setFixedWidth(150 if self._label_text else 0)

    def retranslate_ui(self) -> None:
        self._label.setText(self._label_text)
        self._hint.setText(self._hint_text)
        self._sync_label()


# ---------------------------------------------------------------------------
# Toggle


class _Switch(QCheckBox):
    """A 38x22 pill switch, animated without external assets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(38, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = 1.0 if self.isChecked() else 0.0
        self._animation = QTimer(self)
        self._animation.setInterval(16)
        self._animation.timeout.connect(self._tick)
        self.toggled.connect(self._animate)

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        """The whole painted pill is clickable, not just the hidden indicator."""
        return self.rect().contains(pos)

    def _animate(self, checked: bool) -> None:
        self._target = 1.0 if checked else 0.0
        if abs(self._pos - self._target) < 0.01:
            return
        self._animation.start()

    def _tick(self) -> None:
        target = 1.0 if self.isChecked() else 0.0
        delta = target - self._pos
        if abs(delta) < 0.04:
            self._pos = target
            self._animation.stop()
        else:
            self._pos += delta * 0.34
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            track = QRectF(1.0, 2.0, self.width() - 2.0, self.height() - 4.0)
            off_track = Theme.mix(palette.card, palette.muted, 0.32)
            fill = Theme.mix(off_track, palette.accent, self._pos)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(fill))
            painter.drawRoundedRect(track, track.height() / 2.0, track.height() / 2.0)

            knob = 16.0
            x = 3.0 + (self.width() - knob - 6.0) * self._pos
            painter.setBrush(QColor(Theme.on_accent()))
            painter.setPen(QPen(QColor(palette.border), 1.0))
            painter.drawEllipse(QRectF(x, (self.height() - knob) / 2.0, knob, knob))

            if self.hasFocus():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(palette.accent), 1.4))
                focus = QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8)
                painter.drawRoundedRect(focus, focus.height() / 2.0, focus.height() / 2.0)
        finally:
            painter.end()


class ToggleRow(QWidget):
    """A settings row with a label and an animated switch."""

    toggled = Signal(bool)

    def __init__(
        self,
        label: str = "",
        checked: bool = False,
        parent: QWidget | None = None,
        *,
        hint: str = "",
    ) -> None:
        if isinstance(checked, QWidget) and parent is None:
            parent = checked
            checked = False
        super().__init__(parent)
        self._label_text = str(label)
        self._hint_text = str(hint)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        self._label = _ThemedLabel(self._label_text, "text", self)
        self._label.setFont(_font(13, 500))
        self._hint = _ThemedLabel(self._hint_text, "muted", self)
        self._hint.setFont(_font(11))
        self._hint.setWordWrap(True)
        self._hint.setVisible(bool(self._hint_text))
        text_column.addWidget(self._label)
        text_column.addWidget(self._hint)
        layout.addLayout(text_column, 1)

        self._switch = _Switch(self)
        self._switch.setChecked(bool(checked))
        self._switch.toggled.connect(self._on_switch)
        layout.addWidget(self._switch, 0, Qt.AlignmentFlag.AlignVCenter)

        self._label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def _on_switch(self, checked: bool) -> None:
        self.toggled.emit(checked)

    def is_checked(self) -> bool:
        return self._switch.isChecked()

    def set_checked(self, checked: bool) -> None:
        previous = self._switch.blockSignals(True)
        self._switch.setChecked(bool(checked))
        self._switch.blockSignals(previous)
        self._switch.update()

    def check_box(self) -> QCheckBox:
        return self._switch

    def set_label(self, label: str) -> None:
        self._label_text = str(label)
        self._label.setText(self._label_text)
        self._label.setVisible(bool(self._label_text))

    def label(self) -> str:
        return self._label_text

    def set_hint(self, hint: str) -> None:
        self._hint_text = str(hint)
        self._hint.setText(self._hint_text)
        self._hint.setVisible(bool(self._hint_text))

    def retranslate_ui(self) -> None:
        self._label.setText(self._label_text)
        self._hint.setText(self._hint_text)


# ---------------------------------------------------------------------------
# Buttons


class LinkButton(QPushButton):
    """Flat accent text button used for inline actions."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        if isinstance(text, QWidget) and parent is None:
            parent = text
            text = ""
        super().__init__(str(text), parent)
        self.setFlat(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFont(_font(12, 500))
        self.setMinimumHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        width = _text_width(self.font(), self.text()) + 8
        return QSize(max(24, width), 26)

    def retranslate_ui(self) -> None:
        self.updateGeometry()
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        enabled = self.isEnabled()
        accent = palette.accent_hover if enabled else palette.faint
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            if self.hasFocus():
                painter.setPen(QPen(QColor(palette.accent), 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect, 6.0, 6.0)
            if self.underMouse() and enabled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.accent_soft))
                painter.drawRoundedRect(rect, 6.0, 6.0)

            font = self.font()
            font.setUnderline(self.underMouse() and enabled)
            painter.setFont(font)
            painter.setPen(QColor(accent))
            offset = 1.0 if self.isDown() else 0.0
            painter.drawText(
                rect.translated(0.0, offset),
                Qt.AlignmentFlag.AlignCenter,
                self.text(),
            )
        finally:
            painter.end()


class _BaseButton(QPushButton):
    _primary = False

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        icon_name: str | None = None,
    ) -> None:
        if isinstance(text, QWidget) and parent is None:
            parent = text
            text = ""
        super().__init__(str(text), parent)
        self._icon_name = icon_name or ""
        self.setProperty("appButton", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(38)
        self.setFont(_font(13, 600 if self._primary else 500))
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(str(text))

    def set_icon_name(self, name: str | None) -> None:
        self._icon_name = name or ""
        self.updateGeometry()
        self.update()

    def icon_name(self) -> str:
        return self._icon_name

    def setText(self, text: str) -> None:  # noqa: N802 - QPushButton API
        super().setText(str(text))
        self.setAccessibleName(str(text))
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802
        width = _text_width(self.font(), self.text()) + 32
        if self._icon_name:
            width += 23
        return QSize(max(78, width), 38)

    def retranslate_ui(self) -> None:
        self.updateGeometry()
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        enabled = self.isEnabled()
        hovered = self.underMouse() and enabled
        pressed = self.isDown() and enabled
        focused = self.hasFocus()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            content_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            if focused:
                # Leave a palette gap between the accent ring and the fill so
                # the focus state is equally visible on filled primary buttons.
                content_rect = content_rect.adjusted(2.5, 2.5, -2.5, -2.5)

            if focused:
                painter.setPen(QPen(QColor(palette.accent), 1.4))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(
                    QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0),
                    float(Theme.radius_small),
                    float(Theme.radius_small),
                )

            path = _rounded(content_rect, float(Theme.radius_small))
            if self._primary:
                if not enabled:
                    fill = Theme.mix(palette.card, palette.accent, 0.22)
                elif pressed:
                    fill = QColor(palette.accent).darker(118).name()
                elif hovered:
                    fill = palette.accent_hover
                else:
                    fill = palette.accent
                foreground = palette.muted if not enabled else Theme.on_accent()
            else:
                if not enabled:
                    fill = palette.card_hover
                elif pressed:
                    fill = palette.selection
                elif hovered:
                    fill = palette.card_hover
                else:
                    fill = palette.card
                foreground = palette.faint if not enabled else palette.text

            painter.fillPath(path, QColor(fill))
            if not enabled:
                border_colour = palette.border
            elif focused or self._primary:
                border_colour = palette.accent
            else:
                border_colour = palette.border
            painter.setPen(QPen(QColor(border_colour), 1.0))
            painter.drawPath(path)

            font = self.font()
            painter.setFont(font)
            painter.setPen(QColor(foreground))
            metrics = QFontMetrics(font)
            text_width = metrics.horizontalAdvance(self.text())
            icon_width = 16 if self._icon_name else 0
            gap = 7 if self._icon_name else 0
            total = text_width + icon_width + gap
            start = content_rect.center().x() - total / 2.0
            offset_y = 1.0 if pressed else 0.0
            if self._icon_name:
                icon_colour = (
                    Theme.on_accent()
                    if self._primary and enabled
                    else (palette.muted if not enabled else foreground)
                )
                rendered = icons.pixmap(
                    self._icon_name,
                    icon_colour,
                    16,
                    self.devicePixelRatioF(),
                )
                painter.drawPixmap(
                    QPointF(start, content_rect.center().y() - 8.0 + offset_y),
                    rendered,
                )
                start += icon_width + gap
            text_rect = QRectF(
                start,
                content_rect.top() + offset_y,
                text_width + 2.0,
                content_rect.height(),
            )
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self.text(),
            )
        finally:
            painter.end()


class PrimaryButton(_BaseButton):
    """Filled accent button with a visible pressed state."""

    _primary = True

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        icon_name: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(text, parent, icon_name=icon_name or icon)


class SecondaryButton(_BaseButton):
    """Bordered neutral button for secondary actions."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        icon_name: str | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(text, parent, icon_name=icon_name or icon)


class IconButton(QPushButton):
    """A compact square icon button for pane toolbars."""

    def __init__(
        self,
        icon_name: str = "info",
        tooltip: str = "",
        parent: QWidget | None = None,
        *,
        size: int = 30,
        icon_size: int = 16,
    ) -> None:
        if isinstance(icon_name, QWidget) and parent is None:
            parent = icon_name
            icon_name = "info"
        if isinstance(tooltip, QWidget) and parent is None:
            parent = tooltip
            tooltip = ""
        super().__init__(parent)
        self._icon_name = str(icon_name)
        self._icon_size = int(icon_size)
        self._active = True
        self.setProperty("appButton", True)
        self.setFixedSize(int(size), int(size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(str(tooltip))
        self.setAccessibleName(str(tooltip))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = str(name)
        self.update()

    def icon_name(self) -> str:
        return self._icon_name

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self.setEnabled(bool(active))
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_tooltip(self, text: str) -> None:
        self.setToolTip(text)
        self.setAccessibleName(text)

    def retranslate_ui(self) -> None:
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
            if self.isDown() and self._active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.selection))
                painter.drawRoundedRect(rect, 7.0, 7.0)
            elif self.underMouse() and self._active:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(palette.card_hover))
                painter.drawRoundedRect(rect, 7.0, 7.0)
            if self.hasFocus():
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(palette.accent), 1.2))
                painter.drawRoundedRect(rect, 7.0, 7.0)
            colour = palette.text if self.underMouse() and self._active else palette.muted
            if not self._active or not self.isEnabled():
                colour = palette.faint
            rendered = icons.pixmap(
                self._icon_name,
                colour,
                self._icon_size,
                self.devicePixelRatioF(),
            )
            x = (self.width() - self._icon_size) / 2.0
            y = (self.height() - self._icon_size) / 2.0
            painter.drawPixmap(QPointF(x, y), rendered)
        finally:
            painter.end()


# ---------------------------------------------------------------------------
# Empty state


class EmptyState(QWidget):
    """Icon, title and subtitle for a pane that has nothing to show yet."""

    def __init__(
        self,
        icon_name: str = "sparkles",
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(icon_name, QWidget) and parent is None:
            parent = icon_name
            icon_name = "sparkles"
        super().__init__(parent)
        self._icon_name = str(icon_name)
        self._title_text = str(title)
        self._subtitle_text = str(subtitle)
        self._action: QWidget | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(8)
        outer.addStretch(1)
        self.setMinimumHeight(200)

        self._badge = _IconBadge(self._icon_name, 52, self)
        self._badge.setVisible(bool(self._icon_name))
        outer.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title = _ThemedLabel(self._title_text, "text", self)
        self._title.setFont(_font(14, 600))
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title.setWordWrap(True)
        self._title.setMinimumWidth(260)
        self._title.setMaximumWidth(380)
        self._title.setMinimumHeight(22)
        outer.addWidget(self._title, 0, Qt.AlignmentFlag.AlignHCenter)

        self._subtitle = _ThemedLabel(self._subtitle_text, "muted", self)
        self._subtitle.setFont(_font(12))
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._subtitle.setWordWrap(True)
        self._subtitle.setMinimumWidth(260)
        self._subtitle.setMaximumWidth(380)
        self._subtitle.setMinimumHeight(34)
        outer.addWidget(self._subtitle, 0, Qt.AlignmentFlag.AlignHCenter)

        self._action_host = QWidget(self)
        action_layout = QHBoxLayout(self._action_host)
        action_layout.setContentsMargins(0, 6, 0, 0)
        action_layout.setSpacing(8)
        action_layout.addStretch(1)
        self._action_layout = action_layout
        outer.addWidget(self._action_host, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(1)
        self._sync()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = str(name)
        self._badge.set_name(self._icon_name)
        self._badge.setVisible(bool(self._icon_name))

    def set_title(self, title: str) -> None:
        self._title_text = str(title)
        self._title.setText(self._title_text)

    def set_subtitle(self, subtitle: str) -> None:
        self._subtitle_text = str(subtitle)
        self._subtitle.setText(self._subtitle_text)

    def set_action(self, widget: QWidget | None) -> None:
        if self._action is not None:
            self._action_layout.removeWidget(self._action)
            self._action.setParent(None)
        self._action = widget
        if widget is not None:
            self._action_layout.addWidget(widget)
        self._sync()

    def _sync(self) -> None:
        self._title.setVisible(bool(self._title_text.strip()))
        self._subtitle.setVisible(bool(self._subtitle_text.strip()))
        self._action_host.setVisible(self._action is not None)

    def retranslate_ui(self) -> None:
        self._title.setText(self._title_text)
        self._subtitle.setText(self._subtitle_text)
        self._sync()


# ---------------------------------------------------------------------------
# Divider


class Divider(QWidget):
    """A 1 px rule using the palette border colour."""

    def __init__(
        self,
        orientation: str = "horizontal",
        parent: QWidget | None = None,
    ) -> None:
        if isinstance(orientation, QWidget) and parent is None:
            parent = orientation
            orientation = "horizontal"
        super().__init__(parent)
        self._horizontal = orientation != "vertical"
        if self._horizontal:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def retranslate_ui(self) -> None:
        self.update()

    def paintEvent(self, event: QEvent) -> None:  # noqa: N802
        palette = Theme.palette()
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), QColor(palette.border))
        finally:
            painter.end()
