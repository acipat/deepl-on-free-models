"""Inline lucide-style icons rendered through QtSvg.

Icons are authored on the usual 24x24 grid with a 1.8 px round stroke.  The
rendered pixmaps are cached by ``(name, colour, size, device-pixel-ratio)`` so
paint-heavy toolbars never re-parse SVG.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .theme import Theme

# ---------------------------------------------------------------------------
# Path data.  Every entry is the inner markup of a 24x24 ``<svg>`` element.

_PATHS: dict[str, str] = {
    "translate": (
        '<path d="m5 8 6 6"/>'
        '<path d="m4 14 6-6 2-3"/>'
        '<path d="M2 5h12"/>'
        '<path d="M7 2h1"/>'
        '<path d="m22 22-5-10-5 10"/>'
        '<path d="M14 18h6"/>'
    ),
    "files": (
        '<path d="M15.5 2H8.6c-.4 0-.8.2-1.1.5-.3.3-.5.7-.5 1.1v12.8c0 .4.2.8.5 '
        '1.1.3.3.7.5 1.1.5h9.8c.4 0 .8-.2 1.1-.5.3-.3.5-.7.5-1.1V6.5L15.5 2z"/>'
        '<path d="M3 7.6v12.8c0 .4.2.8.5 1.1.3.3.7.5 1.1.5h9.8"/>'
    ),
    "write": (
        '<path d="M12 20h9"/>'
        '<path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>'
    ),
    "style": (
        '<path d="M4 7V4h16v3"/>'
        '<path d="M9 20h6"/>'
        '<path d="M12 4v16"/>'
    ),
    "tone": (
        '<path d="M2 12h2"/>'
        '<path d="M6 8v8"/>'
        '<path d="M10 5v14"/>'
        '<path d="M14 9v6"/>'
        '<path d="M18 7v10"/>'
        '<path d="M22 12h-2"/>'
    ),
    "history": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        '<path d="M3 3v5h5"/>'
        '<path d="M12 7v5l4 2"/>'
    ),
    "settings": (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 '
        '0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 '
        '1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73'
        'l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 '
        '2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22'
        '-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09'
        'a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25'
        'a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "copy": (
        '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/>'
        '<path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-8a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>'
    ),
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "swap": (
        '<path d="M8 3 4 7l4 4"/>'
        '<path d="M4 7h16"/>'
        '<path d="m16 21 4-4-4-4"/>'
        '<path d="M20 17H4"/>'
    ),
    "play": '<path d="M6 3l14 9-14 9V3z"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "speaker": (
        '<path d="M11 5 6 9H2v6h4l5 4V5z"/>'
        '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"/>'
        '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>'
    ),
    "search": (
        '<circle cx="11" cy="11" r="8"/>'
        '<path d="m21 21-4.3-4.3"/>'
    ),
    "download": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<path d="M7 10l5 5 5-5"/>'
        '<path d="M12 15V3"/>'
    ),
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "trash": (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        '<path d="M10 11v6"/><path d="M14 11v6"/>'
    ),
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-up": '<path d="m18 15-6-6-6 6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "sparkles": (
        '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 '
        '9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 0L14.063 8.5A2 2 0 0 0 '
        '15.5 9.937l6.135 1.581a.5.5 0 0 1 0 .964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 '
        '6.135a.5.5 0 0 1-.963 0z"/>'
        '<path d="M20 3v4"/><path d="M22 5h-4"/>'
        '<path d="M4 17v2"/><path d="M5 18H3"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/>'
        '<path d="M2 12h20"/>'
    ),
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-up-right": '<path d="M7 17 17 7"/><path d="M7 7h10v10"/>',
    "folder": (
        '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 '
        '3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'
    ),
    "folder-open": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 6a2 2 0 0 '
        '1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 '
        '0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    "file": (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
    ),
    "warning": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 '
        '1.73-3"/>'
        '<path d="M12 9v4"/>'
        '<path d="M12 17h.01"/>'
    ),
    "info": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 16v-4"/>'
        '<path d="M12 8h.01"/>'
    ),
    "refresh": (
        '<path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
    ),
    "external": (
        '<path d="M15 3h6v6"/>'
        '<path d="M10 14 21 3"/>'
        '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
    ),
    "eye": (
        '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 '
        '.696 10.75 10.75 0 0 1-19.876 0"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "eye-off": (
        '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 '
        '10.747 10.747 0 0 1-1.444 2.49"/>'
        '<path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>'
        '<path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 '
        '10.75 10.75 0 0 1 4.446-5.143"/>'
        '<path d="m2 2 20 20"/>'
    ),
    "clipboard": (
        '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>'
        '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
    ),
    "code": (
        '<path d="m16 18 6-6-6-6"/>'
        '<path d="m8 6-6 6 6 6"/>'
    ),
    "more-horizontal": (
        '<circle cx="12" cy="12" r="1"/>'
        '<circle cx="19" cy="12" r="1"/>'
        '<circle cx="5" cy="12" r="1"/>'
    ),
    "minus": '<path d="M5 12h14"/>',
    "key": (
        '<path d="m15.5 7.5 2.3 2.3a1 1 0 0 0 1.4 0l2.1-2.1a1 1 0 0 0 0-1.4L19 4"/>'
        '<path d="m21 2-9.6 9.6"/>'
        '<circle cx="7.5" cy="15.5" r="5.5"/>'
    ),
    "clock": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 6v6l4 2"/>'
    ),
}

_REQUIRED = (
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

_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{colour}" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# Renderers only depend on the icon name (the colour is injected into the SVG
# source, which QtSvg parses per colour), so keep a cached renderer per source.
_SVG_CACHE: dict[str, QByteArray] = {}
_PIXMAP_CACHE: dict[tuple[str, str, int, float], QPixmap] = {}
_RENDERER_CACHE: dict[tuple[str, str], QSvgRenderer] = {}


def available_icons() -> tuple[str, ...]:
    """Names accepted by :func:`icon` and :func:`pixmap`."""
    return tuple(sorted(_PATHS))


def has_icon(name: str) -> bool:
    return name in _PATHS


def _normalise_colour(colour: str | None) -> tuple[str, float]:
    value = colour if colour is not None else Theme.palette().muted
    parsed = QColor(value)
    if not parsed.isValid():
        parsed = QColor(Theme.palette().muted)
    alpha = parsed.alphaF()
    return parsed.name().upper(), alpha


def _svg_source(name: str, colour: str) -> QByteArray:
    key = f"{name}|{colour}"
    source = _SVG_CACHE.get(key)
    if source is None:
        body = _PATHS.get(name, _PATHS["info"])
        source = QByteArray(
            _SVG_TEMPLATE.format(colour=colour, body=body).encode("utf-8")
        )
        _SVG_CACHE[key] = source
    return source


def _renderer(name: str, colour: str) -> QSvgRenderer:
    key = (name, colour)
    renderer = _RENDERER_CACHE.get(key)
    if renderer is None:
        renderer = QSvgRenderer(_svg_source(name, colour))
        _RENDERER_CACHE[key] = renderer
    return renderer


def _device_ratio(dpr: float | None) -> float:
    if dpr is not None:
        return max(1.0, float(dpr))
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        try:
            return max(1.0, float(screen.devicePixelRatio()))
        except (AttributeError, TypeError):  # pragma: no cover - unusual Qt
            pass
    return 1.0


def pixmap(
    name: str,
    color: str | None = None,
    size: int = 16,
    dpr: float | None = None,
) -> QPixmap:
    """Render an icon into a device-ratio-aware transparent pixmap."""
    size = max(1, int(size))
    colour, alpha = _normalise_colour(color)
    ratio = _device_ratio(dpr)
    key = (name, colour, size, round(ratio, 2))
    cached = _PIXMAP_CACHE.get(key)
    if cached is not None:
        return cached

    device_size = max(1, int(round(size * ratio)))
    result = QPixmap(device_size, device_size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if alpha < 1.0:
            painter.setOpacity(alpha)
        painter.scale(ratio, ratio)
        _renderer(name, colour).render(
            painter, QRectF(0.0, 0.0, float(size), float(size))
        )
    finally:
        painter.end()
    result.setDevicePixelRatio(ratio)
    _PIXMAP_CACHE[key] = result
    return result


def icon(name: str, color: str | None = None, size: int = 16) -> QIcon:
    """Return a QIcon for *name* in the requested colour and logical size."""
    result = QIcon(pixmap(name, color=color, size=size))
    return result


def clear_cache() -> None:
    """Drop every cached pixmap; useful when the device scale changes."""
    _PIXMAP_CACHE.clear()
    _RENDERER_CACHE.clear()
    _SVG_CACHE.clear()
