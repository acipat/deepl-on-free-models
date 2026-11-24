"""Markdown rendering for the translation panes.

Three representations share one compact parser:

* ``preview``  - safe HTML rendered by a read-only QTextBrowser;
* ``text``     - the same content with every Markdown marker stripped;
* ``markdown`` - the raw source, shown in a monospaced editor.

No external Markdown library is used.  The converter escapes all user text,
allows links only for ``http``, ``https``, ``mailto`` and relative targets, and
produces a small RTF document for rich clipboard pastes.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Sequence
from urllib.parse import urlsplit

from PySide6.QtCore import QByteArray, QMimeData, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QPlainTextEdit,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import Palette, Theme

try:
    from deepl_ofm.i18n import t
except Exception:  # pragma: no cover - only before i18n lands
    def t(key: str, language: Any = None) -> str:  # type: ignore[misc]
        return key


# ---------------------------------------------------------------------------
# Safety helpers


_ALLOWED_SCHEMES = frozenset({"http", "https", "mailto"})
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def safe_href(raw: str | None) -> str | None:
    """Return a link target that is safe to render, else ``None``.

    Allowed: http, https, mailto and relative references (including anchors).
    Everything else - javascript:, data:, file:, protocol-relative URLs - is
    rejected.  HTML entities are decoded first so ``javascript&#58;`` cannot
    slip through.
    """
    if raw is None:
        return None
    value = html.unescape(str(raw)).strip()
    if not value or _CONTROL_CHARS.search(value):
        return None
    if value.startswith("//") or value.startswith("\\\\"):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    if scheme:
        return value if scheme in _ALLOWED_SCHEMES else None
    if "\\" in value:
        return None
    return value


def _escape_text(value: str) -> str:
    """Escape ordinary text, normalising HTML entities first."""
    return html.escape(html.unescape(value), quote=False)


def _escape_code(value: str) -> str:
    return html.escape(value, quote=False)


# ---------------------------------------------------------------------------
# Inline parsing


@dataclass(frozen=True)
class _Span:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    href: str | None = None


_INLINE_RE = re.compile(
    r"(?P<escape>\\[\\`*_{}\[\]()#+\-.!>~|])"
    r"|(?P<ticks>`+)(?P<code>.+?)(?P=ticks)"
    r"|!\[(?P<img_alt>[^\]]*)\]"
    r"\((?P<img_url>[^)\s]+)(?:\s+\"(?P<img_title>[^\"]*)\")?\)"
    r"|\[(?P<link_label>[^\]]*)\]"
    r"\((?P<link_url>[^)\s]+)(?:\s+\"(?P<link_title>[^\"]*)\")?\)"
    r"|(?P<strong1>\*\*(?P<strong1_text>.+?)\*\*)"
    r"|(?P<strong2>__(?P<strong2_text>.+?)__)"
    r"|(?P<em1>(?<!\*)\*(?!\*)(?P<em1_text>[^*\n]+?)\*(?!\*))"
    r"|(?P<em2>(?<!\w)_(?!_)(?P<em2_text>[^_\n]+?)_(?!\w))"
    r"|(?P<autolink><(?P<autolink_url>https?://[^>\s]+)>)"
)


def _decode_entities(value: str) -> str:
    return html.unescape(value)


def _tokenize_inline(
    text: str,
    bold: bool = False,
    italic: bool = False,
    href: str | None = None,
) -> list[_Span]:
    if not text:
        return []
    spans: list[_Span] = []
    position = 0

    for match in _INLINE_RE.finditer(text):
        if match.start() > position:
            spans.append(
                _Span(
                    _decode_entities(text[position:match.start()]),
                    bold=bold,
                    italic=italic,
                    href=href,
                )
            )
        groups = match.groupdict()

        if groups.get("escape"):
            spans.append(
                _Span(groups["escape"][1:], bold=bold, italic=italic, href=href)
            )
        elif groups.get("code") is not None:
            spans.append(
                _Span(groups["code"], bold=bold, italic=italic, code=True, href=href)
            )
        elif groups.get("strong1_text") is not None:
            spans.extend(
                _tokenize_inline(groups["strong1_text"], True, italic, href)
            )
        elif groups.get("strong2_text") is not None:
            spans.extend(
                _tokenize_inline(groups["strong2_text"], True, italic, href)
            )
        elif groups.get("em1_text") is not None:
            spans.extend(
                _tokenize_inline(groups["em1_text"], bold, True, href)
            )
        elif groups.get("em2_text") is not None:
            spans.extend(
                _tokenize_inline(groups["em2_text"], bold, True, href)
            )
        elif groups.get("link_label") is not None:
            target = safe_href(groups.get("link_url"))
            spans.extend(
                _tokenize_inline(groups["link_label"], bold, italic, target)
            )
        elif groups.get("img_alt") is not None:
            target = safe_href(groups.get("img_url"))
            spans.extend(
                _tokenize_inline(groups["img_alt"], bold, italic, target)
            )
        elif groups.get("autolink_url") is not None:
            url = groups["autolink_url"]
            spans.append(_Span(url, bold=bold, italic=italic, href=url))

        position = match.end()

    if position < len(text):
        spans.append(
            _Span(
                _decode_entities(text[position:]),
                bold=bold,
                italic=italic,
                href=href,
            )
        )
    return spans


def _spans_plain(spans: Sequence[_Span]) -> str:
    parts = []
    for span in spans:
        parts.append(span.text if span.code else _decode_entities(span.text))
    return "".join(parts)


def _spans_html(spans: Sequence[_Span], palette: Palette, mono: str) -> str:
    parts = []
    for span in spans:
        if span.code:
            text = _escape_code(span.text)
        else:
            text = _escape_text(span.text)
        text = text.replace("\n", "<br>")
        if span.code:
            text = (
                f'<code style="font-family: \'{mono}\'; font-size: 12px; '
                f"background-color: {palette.card_hover}; color: {palette.text};\">"
                f"{text}</code>"
            )
        if span.italic:
            text = f"<i>{text}</i>"
        if span.bold:
            text = f"<b>{text}</b>"
        if span.href:
            target = html.escape(span.href, quote=True)
            text = (
                f'<a href="{target}" style="color: {palette.accent_hover}; '
                f'text-decoration: underline;">{text}</a>'
            )
        parts.append(text)
    return "".join(parts)


def _rtf_escape(value: str) -> str:
    parts: list[str] = []
    for character in value:
        if character == "\\":
            parts.append("\\\\")
        elif character == "{":
            parts.append("\\{")
        elif character == "}":
            parts.append("\\}")
        elif character == "\n":
            parts.append("\\line ")
        elif character == "\t":
            parts.append("\\tab ")
        elif ord(character) < 0x80:
            parts.append(character)
        else:
            encoded = character.encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                unit = int.from_bytes(encoded[index:index + 2], "little")
                signed = unit if unit < 0x8000 else unit - 0x10000
                parts.append(f"\\u{signed}?")
    return "".join(parts)


def _spans_rtf(spans: Sequence[_Span], mono: str) -> str:
    parts = []
    for span in spans:
        value = span.text if span.code else _decode_entities(span.text)
        piece = _rtf_escape(value)
        if span.code:
            piece = r"{\f1\fs18 " + piece + "}"
        if span.italic:
            piece = r"{\i " + piece + "}"
        if span.bold:
            piece = r"{\b " + piece + "}"
        if span.href:
            target = _rtf_escape(span.href)
            piece = (
                r'{\field{\*\fldinst HYPERLINK "' + target + r'"}{\fldrslt '
                r"{\ul\cf1 " + piece + "}}}"
            )
        parts.append(piece)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Block parsing


@dataclass
class _Block:
    kind: str
    text: str = ""
    level: int = 0
    language: str = ""
    ordered: bool = False
    start: int = 1
    items: list[str] = field(default_factory=list)
    children: list["_Block"] = field(default_factory=list)


_FENCE_RE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*([^\s`]*)\s*$")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_HR_RE = re.compile(r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$")
_QUOTE_RE = re.compile(r"^\s{0,3}>\s?(.*)$")
_UL_RE = re.compile(r"^(\s*)[-+*]\s+(.*)$")
_OL_RE = re.compile(r"^(\s*)(\d{1,9})[.)]\s+(.*)$")


def _indent_width(line: str) -> int:
    width = 0
    for character in line:
        if character == " ":
            width += 1
        elif character == "\t":
            width += 4
        else:
            break
    return width


def _is_hr(line: str) -> bool:
    return bool(_HR_RE.match(line))


def _starts_block(line: str) -> bool:
    return bool(
        _FENCE_RE.match(line)
        or _HEADING_RE.match(line)
        or _is_hr(line)
        or _QUOTE_RE.match(line)
        or _UL_RE.match(line)
        or _OL_RE.match(line)
    )


def parse_blocks(text: str) -> list[_Block]:
    """Parse Markdown into a small block tree (used by all three renderers)."""
    source = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = source.split("\n")
    blocks: list[_Block] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            marker = fence.group(2)[0]
            length = len(fence.group(2))
            language = fence.group(3) or ""
            index += 1
            code_lines: list[str] = []
            while index < len(lines):
                closing = re.match(
                    rf"^\s*{re.escape(marker)}{{{length},}}\s*$", lines[index]
                )
                if closing:
                    index += 1
                    break
                code_lines.append(lines[index])
                index += 1
            blocks.append(
                _Block("code", "\n".join(code_lines), language=language)
            )
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            blocks.append(
                _Block(
                    "heading",
                    heading.group(2).strip(),
                    level=len(heading.group(1)),
                )
            )
            index += 1
            continue

        if _is_hr(line):
            blocks.append(_Block("hr"))
            index += 1
            continue

        if _QUOTE_RE.match(line):
            quoted: list[str] = []
            while index < len(lines):
                match = _QUOTE_RE.match(lines[index])
                if not match:
                    break
                quoted.append(match.group(1))
                index += 1
            blocks.append(_Block("quote", children=parse_blocks("\n".join(quoted))))
            continue

        unordered = _UL_RE.match(line)
        ordered = _OL_RE.match(line)
        if unordered or ordered:
            is_ordered = ordered is not None
            base = len((ordered or unordered).group(1).replace("\t", "    "))
            start = int(ordered.group(2)) if ordered else 1
            items: list[str] = []
            while index < len(lines):
                ul_match = _UL_RE.match(lines[index])
                ol_match = _OL_RE.match(lines[index])
                if is_ordered:
                    match = ol_match
                    if match is None:
                        break
                    content = match.group(3).strip()
                else:
                    match = ul_match
                    if match is None:
                        break
                    content = match.group(2).strip()
                if _indent_width(lines[index]) != base:
                    break
                index += 1

                continuation: list[str] = []
                while index < len(lines):
                    candidate = lines[index]
                    if not candidate.strip():
                        if (
                            index + 1 < len(lines)
                            and _indent_width(lines[index + 1]) > base
                        ):
                            continuation.append("")
                            index += 1
                            continue
                        break
                    if _indent_width(candidate) > base:
                        continuation.append(candidate.strip())
                        index += 1
                        continue
                    break
                if continuation:
                    content = content + "\n" + "\n".join(continuation)
                items.append(content)

                if index < len(lines) and not lines[index].strip():
                    lookahead = index + 1
                    if lookahead < len(lines):
                        next_match = (
                            _OL_RE if is_ordered else _UL_RE
                        ).match(lines[lookahead])
                        if next_match and _indent_width(lines[lookahead]) == base:
                            index = lookahead
                            continue
                    break
            blocks.append(
                _Block(
                    "list",
                    ordered=is_ordered,
                    start=start,
                    items=items,
                )
            )
            continue

        paragraph: list[str] = []
        while index < len(lines) and lines[index].strip() and not _starts_block(
            lines[index]
        ):
            paragraph.append(lines[index].strip())
            index += 1
        if paragraph:
            blocks.append(_Block("paragraph", "\n".join(paragraph)))
        else:
            # Defensive: never loop forever on a line that starts a block but
            # was not handled above.
            blocks.append(_Block("paragraph", lines[index].strip()))
            index += 1

    return blocks


# ---------------------------------------------------------------------------
# Renderers


def _inline(text: str) -> list[_Span]:
    return _tokenize_inline(text)


def _render_blocks_html(
    blocks: Sequence[_Block],
    palette: Palette,
    mono: str,
    text_colour: str | None = None,
) -> str:
    colour = text_colour or palette.text
    parts: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            level = max(1, min(6, block.level))
            sizes = {1: 22, 2: 18, 3: 16, 4: 14, 5: 13, 6: 12}
            size = sizes.get(level, 14)
            parts.append(
                f'<h{level} style="color: {colour}; '
                f"font-size: {size}px; font-weight: 600; "
                f'margin: 8px 0 10px 0;">{_spans_html(_inline(block.text), palette, mono)}'
                f"</h{level}>"
            )
        elif block.kind == "paragraph":
            parts.append(
                f'<p style="color: {colour}; font-size: 14px; line-height: 155%; '
                f'margin: 0 0 12px 0;">{_spans_html(_inline(block.text), palette, mono)}</p>'
            )
        elif block.kind == "code":
            parts.append(
                f'<pre style="font-family: \'{mono}\'; font-size: 12px; '
                f"background-color: {palette.card_hover}; color: {palette.text}; "
                f"margin: 0 0 12px 0; padding: 10px; white-space: pre-wrap;\">"
                f"{_escape_code(block.text)}</pre>"
            )
        elif block.kind == "quote":
            inner = _render_blocks_html(
                block.children, palette, mono, text_colour=palette.muted
            )
            parts.append(
                '<table width="100%" cellspacing="0" cellpadding="0" '
                'style="margin: 4px 0 12px 0;"><tr>'
                f'<td width="3" bgcolor="{palette.accent}" '
                f'style="background-color: {palette.accent};"></td>'
                '<td style="padding-left: 12px; padding-top: 2px; '
                f'padding-bottom: 2px;">{inner}</td>'
                '</tr></table>'
            )
        elif block.kind == "list":
            tag = "ol" if block.ordered else "ul"
            start = (
                f' start="{block.start}"'
                if block.ordered and block.start != 1
                else ""
            )
            items = "".join(
                f'<li style="color: {colour}; margin: 0 0 4px 0;">'
                f"{_spans_html(_inline(item), palette, mono)}</li>"
                for item in block.items
            )
            parts.append(
                f'<{tag}{start} style="margin: 0 0 12px 0; padding-left: 22px;">'
                f"{items}</{tag}>"
            )
        elif block.kind == "hr":
            parts.append(
                f'<hr style="border: none; border-top: 1px solid {palette.border}; '
                f'margin: 14px 0 14px 0;">'
            )
    return "".join(parts)


def _render_blocks_plain(blocks: Sequence[_Block]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.kind in ("heading", "paragraph"):
            text = _spans_plain(_inline(block.text))
            if text.strip():
                parts.append(text.strip())
        elif block.kind == "code":
            parts.append(block.text)
        elif block.kind == "quote":
            text = _render_blocks_plain(block.children)
            if text.strip():
                parts.append(text.strip())
        elif block.kind == "list":
            lines: list[str] = []
            for offset, item in enumerate(block.items):
                prefix = (
                    f"{block.start + offset}. " if block.ordered else "• "
                )
                text = _spans_plain(_inline(item)).strip()
                text = text.replace("\n", "\n" + " " * len(prefix))
                lines.append(prefix + text)
            if lines:
                parts.append("\n".join(lines))
        elif block.kind == "hr":
            continue
    return "\n\n".join(parts).strip()


def _render_blocks_rtf(
    blocks: Sequence[_Block],
    palette: Palette,
    mono: str,
) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.kind == "heading":
            level = max(1, min(6, block.level))
            sizes = {1: 40, 2: 32, 3: 26, 4: 22, 5: 21, 6: 21}
            parts.append(
                r"\pard\plain\sa120\b\f0\fs"
                + str(sizes.get(level, 21))
                + " "
                + _spans_rtf(_inline(block.text), mono)
                + r"\b0\par"
            )
        elif block.kind == "paragraph":
            parts.append(
                r"\pard\plain\sa160\f0\fs21 "
                + _spans_rtf(_inline(block.text), mono)
                + r"\par"
            )
        elif block.kind == "code":
            parts.append(
                r"\pard\plain\sa160\f1\fs18 "
                + _rtf_escape(block.text)
                + r"\f0\fs21\par"
            )
        elif block.kind == "quote":
            inner = _render_blocks_rtf(block.children, palette, mono)
            parts.append(
                r"\pard\plain\li360\sa160\i\cf2 " + inner + r"\i0\cf3\par"
            )
        elif block.kind == "list":
            for offset, item in enumerate(block.items):
                marker = (
                    str(block.start + offset) + ". "
                    if block.ordered
                    else "\\u8226?  "
                )
                parts.append(
                    r"\pard\plain\li360\fi-180\tx360\sa80\f0\fs21 "
                    + marker
                    + _spans_rtf(_inline(item), mono)
                    + r"\par"
                )
        elif block.kind == "hr":
            parts.append(r"\pard\plain\brdrb\brdrs\brdrw10\brsp20\par")
    return "".join(parts)


def _document_html(markdown: str) -> str:
    palette = Theme.palette()
    mono = Theme.mono_family()
    family = Theme.font_family()
    body = _render_blocks_html(parse_blocks(markdown), palette, mono)
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<style>"
        f"body {{ color: {palette.text}; font-family: '{family}'; "
        f"font-size: 14px; margin: 0; background: transparent; }}"
        "a { text-decoration: underline; }"
        "</style></head>"
        f'<body style="color: {palette.text}; font-family: \'{family}\'; '
        f'font-size: 14px; margin: 0;">{body}</body></html>'
    )


def _document_rtf(markdown: str) -> str:
    palette = Theme.palette(False)
    mono = Theme.mono_family()
    family = _rtf_escape(Theme.font_family())
    mono_name = _rtf_escape(mono)
    accent = palette.accent.lstrip("#")
    muted = palette.muted.lstrip("#")
    text = palette.text.lstrip("#")
    colours = "".join(
        f"\\red{int(value[0:2], 16)}\\green{int(value[2:4], 16)}"
        f"\\blue{int(value[4:6], 16)};"
        for value in (accent, muted, text)
    )
    body = _render_blocks_rtf(parse_blocks(markdown), palette, mono)
    return (
        "{\\rtf1\\ansi\\ansicpg1252\\deff0\\uc1"
        "{\\fonttbl"
        f"{{\\f0\\fswiss\\fcharset0 {family};}}"
        f"{{\\f1\\fmodern\\fcharset0 {mono_name};}}"
        "}"
        "{\\colortbl ;" + colours + "}"
        "\\viewkind4"
        "\\pard\\plain\\f0\\fs21 " + body + "}"
    )


# ---------------------------------------------------------------------------
# Widget


class _Browser(QTextBrowser):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)
        self.setStyleSheet(
            "QTextBrowser { background: transparent; border: none; "
            "padding: 0px; }"
        )
        self.document().setDocumentMargin(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)


class MarkdownView(QWidget):
    """Rendered / plain / raw Markdown with a copy hook.

    Modes
    -----
    ``"preview"``   rendered HTML (default)
    ``"text"``      markers stripped
    ``"markdown"``  the exact source
    """

    PREVIEW = "preview"
    TEXT = "text"
    MARKDOWN = "markdown"
    MODES = (PREVIEW, TEXT, MARKDOWN)

    copied = Signal()
    link_clicked = Signal(QUrl)

    def __init__(self, markdown: str = "", parent: QWidget | None = None) -> None:
        if isinstance(markdown, QWidget) and parent is None:
            parent = markdown
            markdown = ""
        super().__init__(parent)
        self._markdown = ""
        self._mode = self.PREVIEW
        self._plain_cache: str | None = None
        self._html_cache: str | None = None
        self._rtf_cache: str | None = None
        self._copy_flash = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._browser = _Browser(self)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        self._stack.addWidget(self._browser)

        self._text_editor = self._make_editor(False)
        self._stack.addWidget(self._text_editor)

        self._markdown_editor = self._make_editor(True)
        self._stack.addWidget(self._markdown_editor)

        layout.addWidget(self._stack, 1)

        self.copy_button = QToolButton(self)
        self.copy_button.setObjectName("markdownCopy")
        self.copy_button.setAutoRaise(True)
        self.copy_button.setFixedSize(28, 28)
        self.copy_button.setToolTip(t("Copy"))
        self.copy_button.setAccessibleName(t("Copy"))
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        self.copy_button.hide()

        self._copy_reset = QTimer(self)
        self._copy_reset.setSingleShot(True)
        self._copy_reset.setInterval(1200)
        self._copy_reset.timeout.connect(self._end_copy_flash)

        Theme.changed.connect(self._on_theme_changed)
        self._refresh_copy_icon()
        if markdown:
            self.set_markdown(markdown)

    # -- construction helpers ----------------------------------------------
    def _make_editor(self, mono: bool) -> QPlainTextEdit:
        editor = QPlainTextEdit(self)
        editor.setReadOnly(True)
        editor.setFrameShape(QFrame.Shape.NoFrame)
        editor.setStyleSheet(
            "QPlainTextEdit { background: transparent; border: none; "
            "padding: 0px; }"
        )
        editor.setFont(Theme.font(13 if mono else 14, mono=mono))
        editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        editor.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded if mono
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        return editor

    # -- content ------------------------------------------------------------
    def set_markdown(self, text: str | None) -> None:
        value = "" if text is None else str(text)
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        if value == self._markdown:
            return
        self._markdown = value
        self._plain_cache = None
        self._html_cache = None
        self._rtf_cache = None
        self._markdown_editor.setPlainText(self._markdown)
        if self._mode == self.PREVIEW:
            self._render_preview()
        elif self._mode == self.TEXT:
            self._text_editor.setPlainText(self.plain_text())

    def markdown(self) -> str:
        return self._markdown

    def plain_text(self) -> str:
        if self._plain_cache is None:
            self._plain_cache = _render_blocks_plain(parse_blocks(self._markdown))
        return self._plain_cache

    def html(self) -> str:
        if self._html_cache is None:
            self._html_cache = _document_html(self._markdown)
        return self._html_cache

    def rtf(self) -> str:
        if self._rtf_cache is None:
            self._rtf_cache = _document_rtf(self._markdown)
        return self._rtf_cache

    # -- modes --------------------------------------------------------------
    def set_mode(self, mode: str) -> None:
        value = str(mode).lower()
        if value not in self.MODES:
            raise ValueError(f"unknown Markdown mode: {mode!r}")
        self._mode = value
        if value == self.PREVIEW:
            self._stack.setCurrentWidget(self._browser)
            self._render_preview()
        elif value == self.TEXT:
            self._text_editor.setPlainText(self.plain_text())
            self._stack.setCurrentWidget(self._text_editor)
        else:
            self._markdown_editor.setPlainText(self._markdown)
            self._stack.setCurrentWidget(self._markdown_editor)

    def mode(self) -> str:
        return self._mode

    def current_text(self) -> str:
        """The text the current mode displays (handy for tests and footers)."""
        if self._mode == self.PREVIEW:
            return self.plain_text()
        if self._mode == self.TEXT:
            return self.plain_text()
        return self._markdown

    # -- copy ---------------------------------------------------------------
    def show_copy_button(self, visible: bool = True) -> None:
        """Reveal the built-in floating copy button (hidden by default)."""
        self.copy_button.setVisible(bool(visible))
        if visible:
            self.copy_button.raise_()
            self._position_copy_button()

    def copy_to_clipboard(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:  # pragma: no cover - defensive
            return
        mime = QMimeData()
        if self._mode == self.PREVIEW:
            mime.setText(self.plain_text())
            mime.setHtml(self.html())
            mime.setData("text/rtf", QByteArray(self.rtf().encode("ascii", "ignore")))
        elif self._mode == self.TEXT:
            mime.setText(self.plain_text())
        else:
            mime.setText(self._markdown)
        clipboard.setMimeData(mime)
        self.copied.emit()
        self._flash_copy_button()

    def _flash_copy_button(self) -> None:
        self._copy_flash = True
        self._refresh_copy_icon()
        self._copy_reset.start()

    def _end_copy_flash(self) -> None:
        self._copy_flash = False
        self._refresh_copy_icon()

    def _refresh_copy_icon(self) -> None:
        palette = Theme.palette()
        if self._copy_flash:
            self.copy_button.setIcon(icons.icon("check", palette.success, 15))
        else:
            self.copy_button.setIcon(icons.icon("copy", palette.muted, 15))

    # -- internals ----------------------------------------------------------
    def _render_preview(self) -> None:
        bar = self._browser.verticalScrollBar()
        position = bar.value()
        self._browser.setHtml(self.html())
        bar.setValue(min(position, bar.maximum()))

    def _on_anchor_clicked(self, url: QUrl) -> None:
        target = safe_href(url.toString())
        if target is None:
            return
        self.link_clicked.emit(QUrl(target))
        scheme = QUrl(target).scheme().lower()
        if scheme in {"http", "https", "mailto"}:
            QDesktopServices.openUrl(QUrl(target))

    def _on_theme_changed(self, dark: bool) -> None:
        self._html_cache = None
        self._rtf_cache = None
        self._browser.document().setDefaultFont(Theme.font(14))
        self._text_editor.setFont(Theme.font(14))
        self._markdown_editor.setFont(Theme.font(13, mono=True))
        self._refresh_copy_icon()
        if self._mode == self.PREVIEW:
            self._render_preview()

    def retranslate_ui(self) -> None:
        self.copy_button.setToolTip(t("Copy"))
        self.copy_button.setAccessibleName(t("Copy"))
        self._browser.setAccessibleName(t("Preview"))
        self._text_editor.setAccessibleName(t("Text only"))
        self._markdown_editor.setAccessibleName(t("Markdown"))

    def _position_copy_button(self) -> None:
        if self.copy_button.parent() is not self:
            return
        margin = 6
        self.copy_button.move(
            max(margin, self.width() - self.copy_button.width() - margin),
            margin,
        )

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_copy_button()


# Public conversions used by the clipboard code in the controller.
def markdown_to_plain(markdown: str) -> str:
    """Markdown with every marker removed, paragraphs separated by blank lines."""
    return _render_blocks_plain(parse_blocks(markdown or ""))


def markdown_to_html(markdown: str) -> str:
    """A complete, theme-styled HTML document for the rich clipboard."""
    return _document_html(markdown or "")


def markdown_to_rtf(markdown: str) -> str:
    """RTF for applications that only accept rich text."""
    return _document_rtf(markdown or "")
