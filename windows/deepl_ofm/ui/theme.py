"""Design tokens, fonts and the global stylesheet for DeepL-oFM.

Every colour in the application originates here. Widgets resolve
:meth:`Theme.palette` at paint time instead of caching colours, so switching
between the light and the dark scheme takes effect without rebuilding the UI.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class Palette:
    """The complete colour set of one interface scheme."""

    bg: str
    panel: str
    card: str
    card_hover: str
    border: str
    text: str
    muted: str
    faint: str
    accent: str
    accent_hover: str
    accent_soft: str
    danger: str
    success: str
    warning: str
    selection: str


_LIGHT = Palette(
    bg="#F6F7F9",
    panel="#FFFFFF",
    card="#FFFFFF",
    card_hover="#F2F4F8",
    border="#E3E6EB",
    text="#14161A",
    muted="#6B7280",
    faint="#98A0AE",
    accent="#2F6BFF",
    accent_hover="#2457DB",
    accent_soft="#E9EFFF",
    danger="#C43D3D",
    success="#167A4E",
    warning="#956000",
    selection="#DCE7FF",
)

_DARK = Palette(
    bg="#15171C",
    panel="#191C22",
    card="#1D2027",
    card_hover="#242832",
    border="#2A2E37",
    text="#F2F4F8",
    muted="#9AA1AE",
    faint="#6C7482",
    accent="#2F6BFF",
    accent_hover="#5B8BFF",
    accent_soft="#1D2B48",
    danger="#F26D6D",
    success="#3ECF8E",
    warning="#E5B454",
    selection="#243A63",
)


class _ThemeEvents(QObject):
    """Process-wide notification used by custom-painted widgets."""

    changed = Signal(bool)


_EVENTS = _ThemeEvents()
_dark_override: bool | None = None


class Theme:
    """Static access to the design system."""

    radius: int = 10
    radius_small: int = 8
    spacing: int = 12

    #: Emitted with the resolved darkness after :meth:`apply`/:meth:`set_dark`.
    changed = _EVENTS.changed

    # ------------------------------------------------------------------ state
    @staticmethod
    def _system_is_dark() -> bool:
        hints = QGuiApplication.styleHints() if QGuiApplication.instance() else None
        if hints is not None:
            try:
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Dark:
                    return True
                if scheme == Qt.ColorScheme.Light:
                    return False
            except AttributeError:  # pragma: no cover - older Qt
                pass
        app = QGuiApplication.instance()
        if app is not None:
            return app.palette().color(QPalette.ColorRole.Window).lightness() < 128
        return False

    @staticmethod
    def is_dark() -> bool:
        if _dark_override is not None:
            return _dark_override
        return Theme._system_is_dark()

    @staticmethod
    def palette(dark: bool | None = None) -> Palette:
        """Return the palette for *dark*, or for the current scheme when None."""
        resolved = Theme.is_dark() if dark is None else bool(dark)
        return _DARK if resolved else _LIGHT

    @staticmethod
    def set_dark(dark: bool | None) -> None:
        """Force a scheme (``None`` follows the operating system)."""
        global _dark_override
        _dark_override = None if dark is None else bool(dark)
        app = QApplication.instance()
        if app is not None:
            Theme._install(app, emit=True)

    # ----------------------------------------------------------------- theme
    @staticmethod
    def apply(app: QApplication, dark: bool | None = None) -> None:
        """Install the palette, fonts and global stylesheet on *app*."""
        global _dark_override
        if dark is not None:
            _dark_override = bool(dark)
        Theme._install(app, emit=True)

    @staticmethod
    def _install(app: QApplication, emit: bool) -> None:
        dark = Theme.is_dark()
        palette = Theme.palette(dark)

        try:
            app.setStyle("Fusion")
        except Exception:  # pragma: no cover - a custom style may refuse
            pass

        base = QFont(Theme.font_family())
        base.setPixelSize(14)
        base.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        app.setFont(base)
        app.setPalette(Theme._qt_palette(palette, dark))
        app.setStyleSheet(
            Theme._stylesheet(palette, dark, _combo_arrow_paths(palette))
        )

        for widget in app.allWidgets():
            widget.update()
        if emit:
            _EVENTS.changed.emit(dark)

    @staticmethod
    def _qt_palette(palette: Palette, dark: bool) -> QPalette:
        qt = QPalette()
        role = QPalette.ColorRole
        group = QPalette.ColorGroup
        qt.setColor(role.Window, QColor(palette.bg))
        qt.setColor(role.WindowText, QColor(palette.text))
        qt.setColor(role.Base, QColor(palette.card))
        qt.setColor(role.AlternateBase, QColor(palette.card_hover))
        qt.setColor(role.Text, QColor(palette.text))
        qt.setColor(role.Button, QColor(palette.card))
        qt.setColor(role.ButtonText, QColor(palette.text))
        qt.setColor(role.BrightText, QColor("#FFFFFF"))
        qt.setColor(role.Highlight, QColor(palette.accent))
        qt.setColor(role.HighlightedText, QColor("#FFFFFF"))
        qt.setColor(role.ToolTipBase, QColor(palette.card))
        qt.setColor(role.ToolTipText, QColor(palette.text))
        qt.setColor(role.PlaceholderText, QColor(palette.muted))
        qt.setColor(role.Link, QColor(palette.accent_hover if dark else palette.accent))
        qt.setColor(role.Mid, QColor(palette.border))
        qt.setColor(role.Dark, QColor(palette.border))
        qt.setColor(role.Shadow, QColor(palette.border))
        for disabled_role in (
            role.WindowText,
            role.Text,
            role.ButtonText,
            role.PlaceholderText,
        ):
            qt.setColor(group.Disabled, disabled_role, QColor(palette.faint))
        qt.setColor(group.Disabled, role.Base, QColor(palette.card_hover))
        qt.setColor(group.Disabled, role.Button, QColor(palette.card_hover))
        return qt

    # ------------------------------------------------------------------ fonts
    @staticmethod
    def font(size: int = 14, weight: int = 400, *, mono: bool = False,
             italic: bool = False) -> QFont:
        """Convenience font factory using the resolved families."""
        font = QFont(Theme.mono_family() if mono else Theme.font_family())
        font.setPixelSize(int(size))
        try:
            font.setWeight(QFont.Weight(int(weight)))
        except (TypeError, ValueError):  # pragma: no cover - unusual Qt build
            font.setWeight(QFont.Weight.Normal)
        font.setItalic(bool(italic))
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        return font

    @staticmethod
    def font_family() -> str:
        return _resolve_family(
            (
                "Segoe UI Variable Text",
                "Segoe UI Variable",
                "Segoe UI",
                "Inter",
                "Ubuntu Sans",
                "Noto Sans",
                "DejaVu Sans",
                "Liberation Sans",
            )
        )

    @staticmethod
    def mono_family() -> str:
        family = _resolve_family(
            (
                "Cascadia Mono",
                "Cascadia Code",
                "Consolas",
                "JetBrains Mono",
                "Ubuntu Sans Mono",
                "Noto Sans Mono",
                "DejaVu Sans Mono",
                "Liberation Mono",
                "Courier New",
            ),
            QFontDatabase.SystemFont.FixedFont,
        )
        # On a system with no usable font database (headless CI) every family
        # resolves to the same generic; a monospace generic is the honest answer.
        return "Monospace" if family == Theme.font_family() else family

    # ---------------------------------------------------------------- colours
    @staticmethod
    def on_accent() -> str:
        """Foreground colour for text and icons on the accent fill."""
        return "#FFFFFF"

    @staticmethod
    def qcolor(value: str, alpha: float | None = None) -> QColor:
        """Build a QColor from a palette hex string with an optional alpha."""
        colour = QColor(value)
        if alpha is not None:
            colour.setAlphaF(max(0.0, min(1.0, float(alpha))))
        return colour

    @staticmethod
    def mix(first: str, second: str, amount: float) -> str:
        """Blend two hex colours (0 -> first, 1 -> second) and return hex."""
        amount = max(0.0, min(1.0, float(amount)))
        a = QColor(first)
        b = QColor(second)
        mixed = QColor(
            round(a.red() + (b.red() - a.red()) * amount),
            round(a.green() + (b.green() - a.green()) * amount),
            round(a.blue() + (b.blue() - a.blue()) * amount),
        )
        return mixed.name().upper()

    @staticmethod
    def relative_luminance(value: str) -> float:
        """WCAG relative luminance of a hex colour."""
        colour = QColor(value)
        channels = []
        for component in (colour.redF(), colour.greenF(), colour.blueF()):
            channels.append(
                component / 12.92
                if component <= 0.04045
                else ((component + 0.055) / 1.055) ** 2.4
            )
        red, green, blue = channels
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    @staticmethod
    def contrast_ratio(foreground: str, background: str) -> float:
        """WCAG contrast ratio between two hex colours."""
        first = Theme.relative_luminance(foreground)
        second = Theme.relative_luminance(background)
        lighter, darker = max(first, second), min(first, second)
        return (lighter + 0.05) / (darker + 0.05)

    # -------------------------------------------------------------------- qss
    @staticmethod
    def _stylesheet(
        p: Palette,
        dark: bool,
        arrows: dict[str, str] | None = None,
    ) -> str:
        font = Theme.font_family()
        mono = Theme.mono_family()
        link = p.accent_hover if dark else p.accent
        if arrows:
            combo_rules = f"""
        QComboBox::drop-down {{
            border: none;
            width: 24px;
            background: transparent;
        }}
        QComboBox::down-arrow {{
            image: url("{arrows['normal']}");
            width: 12px;
            height: 12px;
            margin-right: 8px;
        }}
        QComboBox::down-arrow:on {{
            image: url("{arrows['active']}");
        }}
        QComboBox::down-arrow:focus {{
            image: url("{arrows['active']}");
        }}
        QComboBox::down-arrow:disabled {{
            image: url("{arrows['disabled']}");
        }}
        """
        else:
            combo_rules = """
        QComboBox::drop-down {
            border: none;
            width: 24px;
            background: transparent;
        }
        """
        return f"""
        QMainWindow, QDialog {{
            background: {p.bg};
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 8px;
            padding: 6px 10px;
            selection-background-color: {p.selection};
            selection-color: {p.text};
        }}
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
            font-family: "{font}";
            font-size: 13px;
        }}
        QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover {{
            border-color: {p.faint};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
        QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
            border: 1px solid {p.accent};
        }}
        QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
        QComboBox:disabled {{
            color: {p.faint};
            background: {p.card_hover};
            border-color: {p.border};
        }}
        QLineEdit[embedded="true"] {{
            background: {p.card_hover};
            border-color: transparent;
        }}
        QLineEdit[embedded="true"]:focus {{
            background: {p.card};
            border-color: {p.accent};
        }}
        QListWidget[flat="true"], QListView[flat="true"] {{
            background: transparent;
            border: none;
            border-radius: 0px;
        }}
        {combo_rules}
        QComboBox QAbstractItemView {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 8px;
            padding: 4px;
            outline: none;
            selection-background-color: {p.accent_soft};
            selection-color: {p.text};
        }}
        QPushButton {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 8px;
            padding: 7px 14px;
            font-family: "{font}";
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: {p.card_hover};
        }}
        QPushButton:pressed {{
            background: {p.selection};
        }}
        QPushButton:disabled {{
            color: {p.faint};
            background: {p.card_hover};
        }}
        QPushButton:focus {{
            border-color: {p.accent};
        }}
        QPushButton[appButton="true"] {{
            background: transparent;
            border: none;
            padding: 0px;
        }}
        QToolButton {{
            background: transparent;
            border: none;
            border-radius: 6px;
            padding: 4px;
            color: {p.muted};
        }}
        QToolButton:hover {{
            background: {p.card_hover};
            color: {p.text};
        }}
        QToolButton:pressed {{
            background: {p.selection};
        }}
        QToolButton:disabled {{
            color: {p.faint};
        }}
        QToolTip {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 6px;
            padding: 5px 8px;
            font-family: "{font}";
            font-size: 11px;
        }}
        QMenu {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 10px;
            padding: 6px;
            font-family: "{font}";
            font-size: 13px;
        }}
        QMenu::item {{
            background: transparent;
            padding: 6px 26px 6px 10px;
            border-radius: 6px;
            margin: 1px 2px;
        }}
        QMenu::item:selected {{
            background: {p.accent_soft};
            color: {p.text};
        }}
        QMenu::item:disabled {{
            color: {p.faint};
        }}
        QMenu::separator {{
            height: 1px;
            background: {p.border};
            margin: 5px 8px;
        }}
        QMenu::indicator {{
            width: 14px;
            height: 14px;
        }}
        QScrollArea, QAbstractScrollArea {{
            border: none;
            background: transparent;
        }}
        QScrollArea > QWidget > QWidget {{
            background: transparent;
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px 2px 2px 0px;
        }}
        QScrollBar::handle:vertical {{
            background: {p.border};
            border-radius: 4px;
            min-height: 30px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {p.faint};
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0px 2px 2px 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {p.border};
            border-radius: 4px;
            min-width: 30px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: {p.faint};
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
        }}
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: transparent;
        }}
        QHeaderView::section {{
            background: {p.panel};
            color: {p.muted};
            border: none;
            border-bottom: 1px solid {p.border};
            padding: 6px 8px;
            font-family: "{font}";
            font-size: 12px;
        }}
        QTableView, QTreeView, QListView {{
            background: {p.card};
            color: {p.text};
            border: 1px solid {p.border};
            border-radius: 8px;
            alternate-background-color: {p.card_hover};
            selection-background-color: {p.accent_soft};
            selection-color: {p.text};
            outline: none;
            font-family: "{font}";
            font-size: 13px;
        }}
        QCheckBox, QRadioButton {{
            color: {p.text};
            spacing: 8px;
            font-family: "{font}";
            font-size: 13px;
        }}
        QCheckBox:disabled, QRadioButton:disabled {{
            color: {p.faint};
        }}
        QSlider::groove:horizontal {{
            height: 4px;
            background: {p.border};
            border-radius: 2px;
        }}
        QSlider::sub-page:horizontal {{
            background: {p.accent};
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            width: 14px;
            height: 14px;
            margin: -5px 0px;
            border-radius: 7px;
            background: {p.accent};
        }}
        QSlider::handle:horizontal:hover {{
            background: {p.accent_hover};
        }}
        QSplitter::handle {{
            background: {p.border};
        }}
        QSplitter::handle:horizontal {{
            width: 1px;
        }}
        QSplitter::handle:vertical {{
            height: 1px;
        }}
        QProgressBar {{
            background: {p.card_hover};
            border: none;
            border-radius: 3px;
            text-align: center;
            color: {p.muted};
            font-family: "{font}";
            font-size: 11px;
        }}
        QProgressBar::chunk {{
            background: {p.accent};
            border-radius: 3px;
        }}
        QLabel[role="mono"] {{
            font-family: "{mono}";
        }}
        QLabel[role="link"] {{
            color: {link};
        }}
        """


# --------------------------------------------------------------------------
# QComboBox chevron

_ARROW_DIRECTORY = Path(tempfile.gettempdir()) / "deepl_ofm_ui"
_ARROW_CACHE: dict[str, str] = {}


def _combo_arrow_paths(palette: Palette) -> dict[str, str]:
    """Render small chevrons for QComboBox, keyed by palette colour.

    Styling ``QComboBox`` with QSS suppresses the native arrow, so the global
    sheet points ``down-arrow`` at these 4x pixmaps (scaled down by QSS).
    """
    if QGuiApplication.instance() is None:
        return {}
    try:
        _ARROW_DIRECTORY.mkdir(parents=True, exist_ok=True)
    except OSError:
        return {}

    paths: dict[str, str] = {}
    for key, colour in (
        ("normal", palette.muted),
        ("active", palette.accent),
        ("disabled", palette.faint),
    ):
        cached = _ARROW_CACHE.get(colour)
        if cached and Path(cached).exists():
            paths[key] = cached
            continue
        destination = _ARROW_DIRECTORY / f"chevron-down-{colour.lstrip('#').upper()}.png"
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.scale(4.0, 4.0)
            pen = QPen(QColor(colour), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                [QPointF(3.0, 4.5), QPointF(6.0, 7.5), QPointF(9.0, 4.5)]
            )
        finally:
            painter.end()
        if not pixmap.save(str(destination), "PNG"):
            continue
        resolved = destination.as_posix()
        _ARROW_CACHE[colour] = resolved
        paths[key] = resolved
    if set(paths) != {"normal", "active", "disabled"}:
        return {}
    return paths


# --------------------------------------------------------------------------
# Font resolution


def _installed_families() -> dict[str, str]:
    app = QGuiApplication.instance()
    if app is None:
        return {}
    families = QFontDatabase.families()
    return {name.lower(): name for name in families}


_FAMILY_CACHE: dict[tuple[str, ...], str] = {}


def _resolve_family(
    preferred: tuple[str, ...],
    system: "QFontDatabase.SystemFont | None" = None,
) -> str:
    app = QGuiApplication.instance()
    if app is not None:
        cached = _FAMILY_CACHE.get(preferred)
        if cached:
            return cached
    installed = _installed_families()
    for candidate in preferred:
        match = installed.get(candidate.lower())
        if match:
            if app is not None:
                _FAMILY_CACHE[preferred] = match
            return match
    if app is not None:
        queried = system or QFontDatabase.SystemFont.GeneralFont
        fallback = QFontDatabase.systemFont(queried)
        if fallback.family():
            _FAMILY_CACHE[preferred] = fallback.family()
            return fallback.family()
    return "Segoe UI"
