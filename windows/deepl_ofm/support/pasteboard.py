"""Rich clipboard to Markdown conversion.

Port of ``Sources/HyMT/Support/RichTextPasteboard.swift``
(``RichTextPasteboard`` and ``AttributedMarkdown``).  Copying from a browser
puts HTML on the clipboard and copying from a word processor puts RTF there;
converting both to Markdown before translation keeps headings, lists, links
and emphasis instead of flattening everything to plain text.

The HTML side builds a small element tree with :mod:`html.parser` and renders
it structurally.  The RTF side is a compact tokenizer rather than a full RTF
implementation: it recovers paragraphs and character runs, skips the
destination groups that only carry metadata, and decodes byte escapes with a
cp1252/cp1251 heuristic.  Only Qt's ``QMimeData`` is referenced for typing, so
the conversion helpers themselves are pure stdlib.
"""

from __future__ import annotations

import codecs
import contextlib
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - Qt is only needed by mime_to_markdown
    from PySide6.QtCore import QMimeData

# --------------------------------------------------------------------------- #
# HTML: tree building
# --------------------------------------------------------------------------- #

_HEADINGS = frozenset({f"h{level}" for level in range(1, 7)})
_VOID_TAGS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)
# Text inside these elements never belongs in the converted document.
_SKIP_CONTENT = frozenset({"head", "noscript", "script", "style", "template", "title"})
_BLOCK_CONTAINERS = frozenset(
    {
        "address",
        "article",
        "aside",
        "body",
        "caption",
        "center",
        "dd",
        "details",
        "dialog",
        "div",
        "dl",
        "dt",
        "fieldset",
        "figcaption",
        "figure",
        "footer",
        "form",
        "header",
        "hgroup",
        "html",
        "li",
        "main",
        "nav",
        "section",
        "summary",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
    }
)
_BLOCK_TAGS = _HEADINGS | _BLOCK_CONTAINERS | frozenset(
    {"blockquote", "hr", "ol", "p", "pre", "table", "ul"}
)

# Elements that implicitly close an open element of the same kind.
_IMPLIED_CLOSERS: dict[str, frozenset[str]] = {
    "dd": frozenset({"dd", "dt"}),
    "dt": frozenset({"dd", "dt"}),
    "li": frozenset({"li"}),
    "option": frozenset({"option"}),
    "p": frozenset({"p"}),
    "td": frozenset({"td", "th"}),
    "th": frozenset({"td", "th"}),
    "tr": frozenset({"tr"}),
}

_HTML_TAG = re.compile(
    r"<(?:!--.*?--|!doctype\b[^<>]*"
    r"|/?[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*?)?/?)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_UNICODE_SPACES = re.compile("[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]")
_ZERO_WIDTH = str.maketrans("", "", "\u200b\u200c\u200d\u2060\ufeff")
_SPACE_RUN = re.compile(r"[ \t\r\n\f\v]+")
_INLINE_SPACE_RUN = re.compile(r"[ \t\f\v]+")


@dataclass
class _Node:
    """One HTML element; children are either text strings or nested nodes."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node | str] = field(default_factory=list)


class _TreeBuilder(HTMLParser):
    """Collects a tolerant element tree from an HTML fragment."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self._stack: list[_Node] = [self.root]
        self._skip_depth = 0

    def _current(self) -> _Node:
        return self._stack[-1]

    def _close_implied(self, tag: str) -> None:
        closers = _IMPLIED_CLOSERS.get(tag)
        if closers is None:
            return
        while len(self._stack) > 1 and self._current().tag in closers:
            self._stack.pop()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _SKIP_CONTENT and tag not in _VOID_TAGS:
                self._skip_depth += 1
            return
        if tag in _SKIP_CONTENT:
            if tag not in _VOID_TAGS:
                self._skip_depth = 1
            return

        self._close_implied(tag)
        # Browsers close a paragraph when another block starts inside it.
        if tag in _BLOCK_TAGS and self._current().tag == "p":
            self._stack.pop()

        node = _Node(tag, {name.lower(): value or "" for name, value in attrs})
        self._current().children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            return
        lower = tag.lower()
        if lower in _SKIP_CONTENT:
            return
        self.handle_starttag(tag, attrs)
        if lower not in _VOID_TAGS and self._stack[-1].tag == lower:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag in _SKIP_CONTENT and tag not in _VOID_TAGS:
                self._skip_depth -= 1
            return
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if self._skip_depth or not data:
            return
        children = self._current().children
        if children and isinstance(children[-1], str):
            children[-1] += data
        else:
            children.append(data)

    def handle_comment(self, data: str) -> None:
        """Comments are not document content."""

    def handle_decl(self, decl: str) -> None:
        """Doctype declarations are not document content."""

    def handle_pi(self, data: str) -> None:
        """Processing instructions are not document content."""


# --------------------------------------------------------------------------- #
# HTML: inline rendering
# --------------------------------------------------------------------------- #


def _collapse_text(text: str) -> str:
    text = text.translate(_ZERO_WIDTH)
    text = _UNICODE_SPACES.sub(" ", text)
    return _SPACE_RUN.sub(" ", text)


def _clean_inline(text: str) -> str:
    text = _INLINE_SPACE_RUN.sub(" ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _wrap(text: str, prefix: str, suffix: str | None = None) -> str:
    """Apply an inline marker while keeping surrounding spaces outside it."""
    if not text:
        return ""
    suffix = prefix if suffix is None else suffix
    core = text.strip()
    if not core:
        return text
    leading = text[: len(text) - len(text.lstrip())]
    trailing = text[len(text.rstrip()) :]
    return f"{leading}{prefix}{core}{suffix}{trailing}"


def _code_span(text: str) -> str:
    text = _clean_inline(text)
    if not text:
        return ""
    if "`" not in text:
        return f"`{text}`"
    fence = "``"
    while fence in text:
        fence += "`"
    return f"{fence} {text} {fence}"


def _safe_href(value: str) -> str | None:
    """Return a URL that is safe to put in a Markdown link, else ``None``.

    Only http(s), mailto and relative targets survive; ``javascript:`` and
    other schemes are dropped like the Swift renderer does.
    """
    url = value.strip()
    if not url:
        return None
    probe = re.sub(r"[\x00-\x20]+", "", url).lower()
    if probe.startswith(("#", "/", "?", "./", "../")):
        return url
    match = re.match(r"([a-z][a-z0-9+.-]*):", probe)
    if match and match.group(1) not in {"http", "https", "mailto"}:
        return None
    return url


def _link_target(url: str) -> str:
    if any(character in url for character in (" ", "(", ")", "<", ">")):
        return f"<{url}>"
    return url


def _image_markdown(node: _Node) -> str:
    source = node.attrs.get("src", "").strip()
    if not source or source.lower().startswith("data:"):
        return ""
    if _safe_href(source) is None:
        return ""
    alt = _clean_inline(_collapse_text(node.attrs.get("alt", "")))
    return f"![{alt}]({_link_target(source)})"


def _inline_node(node: _Node) -> str:
    tag = node.tag
    if tag == "br":
        return "\n"
    if tag == "img":
        return _image_markdown(node)
    if tag in {"strong", "b"}:
        return _wrap(_inline(node.children), "**")
    if tag in {"em", "i"}:
        return _wrap(_inline(node.children), "*")
    if tag in {"code", "tt"}:
        return _code_span(_inline(node.children))
    if tag in {"del", "s", "strike"}:
        return _wrap(_inline(node.children), "~~")
    if tag == "a":
        label = _clean_inline(_inline(node.children))
        href = _safe_href(node.attrs.get("href", ""))
        if href is None:
            return label
        if not label:
            label = href
        return f"[{label}]({_link_target(href)})"
    return _inline(node.children)


def _inline(children: list[_Node | str]) -> str:
    parts: list[str] = []
    for child in children:
        if isinstance(child, str):
            parts.append(_collapse_text(child))
        else:
            parts.append(_inline_node(child))
    return "".join(parts)


# --------------------------------------------------------------------------- #
# HTML: block rendering
# --------------------------------------------------------------------------- #


def _children_with_tag(node: _Node, tag: str) -> list[_Node]:
    return [
        child
        for child in node.children
        if isinstance(child, _Node) and child.tag == tag
    ]


def _raw_text(node: _Node) -> str:
    """Text of a ``pre`` subtree, with its whitespace untouched."""
    parts: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.tag == "br":
            parts.append("\n")
        else:
            parts.append(_raw_text(child))
    return "".join(parts)


def _render_heading(node: _Node) -> list[str]:
    level = int(node.tag[1])
    text = _clean_inline(_inline(node.children))
    text = re.sub(r"\s*\n\s*", " ", text)
    return [f"{'#' * level} {text}"] if text else []


def _render_pre(node: _Node) -> list[str]:
    raw = _raw_text(node).replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.replace("\u00a0", " ")
    raw = raw.removeprefix("\n")
    raw = raw.rstrip("\n")
    if not raw.strip():
        return []
    fence = "```"
    while fence in raw:
        fence += "`"
    return [f"{fence}\n{raw}\n{fence}"]


def _render_list(node: _Node, depth: int) -> list[str]:
    ordered = node.tag == "ol"
    indent = "  " * depth
    try:
        number = int(node.attrs.get("start", "1"))
    except ValueError:
        number = 1
    lines: list[str] = []

    for child in node.children:
        if not isinstance(child, _Node):
            continue
        if child.tag in {"ul", "ol"}:
            # Some editors emit a nested list as the next sibling instead of
            # nesting it inside the previous <li>; keep its indentation.
            lines.extend(_render_list(child, depth + 1))
            continue
        if child.tag != "li":
            continue

        nested: list[str] = []
        rest: list[_Node | str] = []
        for item_child in child.children:
            if isinstance(item_child, _Node) and item_child.tag in {"ul", "ol"}:
                nested.extend(_render_list(item_child, depth + 1))
            else:
                rest.append(item_child)

        if ordered:
            try:
                number = int(child.attrs.get("value", number))
            except ValueError:
                pass
            marker = f"{number}. "
            number += 1
        else:
            marker = "- "

        blocks = _render_blocks(rest)
        if not blocks:
            lines.extend(nested)
            continue

        first_lines = blocks[0].split("\n")
        lines.append(f"{indent}{marker}{first_lines[0]}")
        for line in first_lines[1:]:
            lines.append(f"{indent}  {line}")
        for block in blocks[1:]:
            for line in block.split("\n"):
                lines.append(f"{indent}  {line}")
        lines.extend(nested)
    return lines


def _render_blockquote(node: _Node) -> list[str]:
    inner = _render_blocks(node.children)
    if not inner:
        text = _clean_inline(_inline(node.children))
        inner = [text] if text else []
    lines: list[str] = []
    for index, block in enumerate(inner):
        if index:
            lines.append(">")
        for line in block.split("\n"):
            lines.append(f"> {line}" if line else ">")
    return ["\n".join(lines)] if lines else []


def _table_rows(node: _Node) -> list[_Node]:
    rows: list[_Node] = []
    for child in node.children:
        if not isinstance(child, _Node):
            continue
        if child.tag == "tr":
            rows.append(child)
        elif child.tag in {"thead", "tbody", "tfoot"}:
            rows.extend(_table_rows(child))
    return rows


def _cell_text(cell: _Node) -> str:
    blocks = _render_blocks(cell.children)
    text = " ".join(block.replace("\n", " ") for block in blocks)
    return _clean_inline(text)


def _render_table(node: _Node) -> list[str]:
    rows = _table_rows(node)
    if not rows:
        return _render_blocks(node.children)
    lines: list[str] = []
    for row in rows:
        cells = [
            child
            for child in row.children
            if isinstance(child, _Node) and child.tag in {"td", "th"}
        ]
        line = "\t".join(_cell_text(cell) for cell in cells)
        if line.strip():
            lines.append(line)
    return ["\n".join(lines)] if lines else []


def _render_block_node(node: _Node) -> list[str]:
    tag = node.tag
    if tag in _HEADINGS:
        return _render_heading(node)
    if tag == "p":
        text = _clean_inline(_inline(node.children))
        return [text] if text else []
    if tag in {"ul", "ol"}:
        lines = _render_list(node, 0)
        return ["\n".join(lines)] if lines else []
    if tag == "blockquote":
        return _render_blockquote(node)
    if tag == "pre":
        return _render_pre(node)
    if tag == "hr":
        return ["---"]
    if tag == "table":
        return _render_table(node)
    return _render_blocks(node.children)


def _render_blocks(children: list[_Node | str]) -> list[str]:
    blocks: list[str] = []
    inline: list[str] = []

    def flush() -> None:
        text = _clean_inline("".join(inline))
        inline.clear()
        if text:
            blocks.append(text)

    for child in children:
        if isinstance(child, str):
            inline.append(_collapse_text(child))
            continue
        if child.tag in _BLOCK_TAGS:
            flush()
            blocks.extend(_render_block_node(child))
        else:
            inline.append(_inline_node(child))
    flush()
    return [block for block in blocks if block.strip()]


def _tidy(text: str) -> str:
    """Trim trailing spaces and collapse blank-line runs outside code fences."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    output: list[str] = []
    fence_length = 0
    in_fence = False
    blank_run = 0
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("```"):
            run = len(stripped) - len(stripped.lstrip("`"))
            if fence_length == 0:
                fence_length = run
                in_fence = True
            elif run >= fence_length:
                fence_length = 0
                in_fence = False
        else:
            in_fence = fence_length > 0
        if not in_fence and not line.strip():
            blank_run += 1
            if blank_run > 1:
                continue
        else:
            blank_run = 0
        output.append(line)
    return "\n".join(output).strip()


def html_to_markdown(html: str) -> str:
    """Convert an HTML fragment to Markdown.

    Counterpart of ``AttributedMarkdown.convert`` reached through
    ``RichTextPasteboard.markdown(fromHTML:)``.  The result uses plain
    Markdown only; tables become tab-separated rows because inventing a
    table dialect would change the text sent to the translator.
    """
    if not html or not html.strip():
        return ""
    builder = _TreeBuilder()
    with contextlib.suppress(Exception):  # malformed fragments: keep what parsed
        builder.feed(html)
        builder.close()
    return _tidy("\n\n".join(_render_blocks(builder.root.children)))


# --------------------------------------------------------------------------- #
# RTF
# --------------------------------------------------------------------------- #

# Groups that carry document metadata rather than visible text.
_RTF_SKIP_DESTINATIONS = frozenset(
    {
        "colortbl",
        "fonttbl",
        "footer",
        "footerf",
        "footerl",
        "footerr",
        "header",
        "headerf",
        "headerl",
        "headerr",
        "info",
        "object",
        "pict",
        "stylesheet",
    }
)
_ANSICPG = re.compile(r"\\ansicpg(\d+)")
_BYTE_MARKER = re.compile("(?:\ue000(\\d+)\ue001)+")
_MARKER = "\ue000{}\ue001"


@dataclass
class _RtfState:
    bold: bool = False
    italic: bool = False
    underline: bool = False
    skip: bool = False
    uc: int = 1


_RtfRun = tuple[str, tuple[bool, bool, bool]]


def _declared_codec(rtf: str) -> str:
    match = _ANSICPG.search(rtf)
    if match is None:
        return ""
    codepage = int(match.group(1))
    if codepage == 65001:
        return "utf-8"
    name = f"cp{codepage}"
    try:
        codecs.lookup(name)
    except LookupError:
        return "cp1252"
    return name


def _looks_cyrillic(text: str) -> bool:
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return False
    cyrillic = sum("\u0400" <= character <= "\u04ff" for character in letters)
    return cyrillic >= 2 and cyrillic / len(letters) >= 0.5


def _byte_codec(rtf: str, data: bytes) -> str:
    declared = _declared_codec(rtf)
    if declared:
        return declared
    try:
        data.decode("cp1252")
    except UnicodeDecodeError:
        return "cp1251"
    cyrillic = data.decode("cp1251", errors="replace")
    return "cp1251" if _looks_cyrillic(cyrillic) else "cp1252"


def _replace_byte_markers(text: str, raw: bytes, codec: str) -> str:
    def substitute(match: re.Match[str]) -> str:
        indices = [
            int(part) for part in re.findall(r"\ue000(\d+)\ue001", match.group(0))
        ]
        data = bytes(raw[index] for index in indices if index < len(raw))
        return data.decode(codec, errors="replace")

    text = _BYTE_MARKER.sub(substitute, text)
    return text.replace("\ue000", "").replace("\ue001", "")


def _render_runs(runs: list[_RtfRun]) -> str:
    parts: list[str] = []
    for text, (bold, italic, underline) in runs:
        if not text:
            continue
        if not (bold or italic or underline) or not text.strip():
            parts.append(text)
            continue
        core = text.strip()
        leading = text[: len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()) :]
        body = core
        if underline:
            body = f"_{body}_"
        if italic:
            body = f"*{body}*"
        if bold:
            body = f"**{body}**"
        parts.append(f"{leading}{body}{trailing}")
    return "".join(parts)


def _tidy_rtf(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def rtf_to_markdown(rtf: str) -> str:
    """Convert a compact subset of RTF to Markdown.

    Counterpart of ``RichTextPasteboard.markdown(fromRTF:)``.  Only the
    constructs word processors emit for ordinary prose are understood:
    paragraphs, line/tab breaks, bold/italic/underline runs and escaped
    Unicode or ANSI bytes.  Unknown control words are ignored, so malformed
    input degrades to its visible text instead of raising.
    """
    if not rtf:
        return ""

    states: list[_RtfState] = [_RtfState()]
    runs: list[_RtfRun] = []
    buffer: list[str] = []
    raw_bytes = bytearray()
    fallback_skip = 0

    def flush() -> None:
        if not buffer:
            return
        text = "".join(buffer)
        buffer.clear()
        if not text:
            return
        state = states[-1]
        style = (state.bold, state.italic, state.underline)
        if runs and runs[-1][1] == style:
            runs[-1] = (runs[-1][0] + text, style)
        else:
            runs.append((text, style))

    def emit(text: str) -> None:
        if not states[-1].skip:
            buffer.append(text)

    def emit_break(text: str) -> None:
        flush()
        if not states[-1].skip:
            runs.append((text, (False, False, False)))

    def set_style(attribute: str, value: bool) -> None:
        state = states[-1]
        if state.skip:
            setattr(state, attribute, value)
            return
        if getattr(state, attribute) == value:
            return
        flush()
        setattr(state, attribute, value)

    index = 0
    length = len(rtf)
    while index < length:
        character = rtf[index]

        if fallback_skip > 0:
            if character == "\\" and index + 1 < length and rtf[index + 1] == "'":
                index += 4
                fallback_skip -= 1
                continue
            if character in "\\{}" or character in "\r\n":
                fallback_skip = 0
            else:
                index += 1
                fallback_skip -= 1
                continue

        if character == "{":
            flush()
            states.append(_RtfState(**vars(states[-1])))
            index += 1
            continue
        if character == "}":
            flush()
            if len(states) > 1:
                states.pop()
            index += 1
            continue
        if character in "\r\n":
            index += 1
            continue
        if character != "\\":
            emit(character)
            index += 1
            continue

        # Control symbol or control word.
        index += 1
        if index >= length:
            break
        symbol = rtf[index]

        if symbol == "'":
            digits = rtf[index + 1 : index + 3]
            if len(digits) == 2 and all(
                digit in "0123456789abcdefABCDEF" for digit in digits
            ):
                value = int(digits, 16)
                if not states[-1].skip:
                    raw_bytes.append(value)
                    buffer.append(_MARKER.format(len(raw_bytes) - 1))
                index += 3
            else:
                index += 1
            continue
        if symbol == "\\" or symbol == "{" or symbol == "}":
            emit(symbol)
            index += 1
            continue
        if symbol == "~":
            emit(" ")
            index += 1
            continue
        if symbol == "_":
            emit("-")
            index += 1
            continue
        if symbol == "-":
            index += 1
            continue
        if symbol == "*":
            flush()
            states[-1].skip = True
            index += 1
            continue
        if symbol in "\r\n":
            emit_break("\n\n")
            index += 1
            continue
        if not (symbol.isascii() and symbol.isalpha()):
            index += 1
            continue

        start = index
        while index < length and rtf[index].isascii() and rtf[index].isalpha():
            index += 1
        word = rtf[start:index].lower()

        parameter: int | None = None
        if index < length and (rtf[index] == "-" or rtf[index].isdigit()):
            number_start = index
            if rtf[index] == "-":
                index += 1
            digit_start = index
            while index < length and rtf[index].isdigit():
                index += 1
            if index > digit_start:
                parameter = int(rtf[number_start:index])
        if index < length and rtf[index] == " ":
            index += 1

        if word in _RTF_SKIP_DESTINATIONS:
            if not states[-1].skip:
                flush()
            states[-1].skip = True
            continue
        if word == "par":
            emit_break("\n\n")
        elif word == "line":
            emit_break("\n")
        elif word == "tab":
            emit("\t")
        elif word in {"b", "i", "ul"}:
            enabled = parameter is None or parameter != 0
            set_style({"b": "bold", "i": "italic", "ul": "underline"}[word], enabled)
        elif word == "ulnone":
            set_style("underline", False)
        elif word == "plain":
            for attribute in ("bold", "italic", "underline"):
                set_style(attribute, False)
        elif word == "uc":
            if parameter is not None:
                states[-1].uc = max(0, parameter)
        elif word == "u" and parameter is not None:
            value = parameter + 65536 if parameter < 0 else parameter
            if 0 <= value <= 0xFFFF:
                emit(chr(value))
            fallback_skip = states[-1].uc
        # Every other control word is layout metadata and is dropped.

    flush()
    codec = _byte_codec(rtf, bytes(raw_bytes))
    text = _replace_byte_markers(_render_runs(runs), bytes(raw_bytes), codec)
    return _tidy_rtf(text)


# --------------------------------------------------------------------------- #
# MIME dispatch
# --------------------------------------------------------------------------- #


def looks_like_html(value: str) -> bool:
    """Return whether ``value`` contains at least one HTML-looking tag.

    ``text/html`` clipboard flavours are sometimes just a plain string, and
    ``QMimeData`` can also expose a plain fragment with no markup at all.
    """
    return bool(value) and _HTML_TAG.search(value) is not None


def mime_to_markdown(mime: QMimeData) -> str:
    """Markdown for a Qt ``QMimeData``, or its plain text when unavailable.

    Mirrors ``RichTextPasteboard.markdown(from:)``: HTML wins over RTF, and
    an empty or failed conversion falls back to ``mime.text()``.  Parser
    problems never propagate to the paste handler.
    """
    plain = ""
    with contextlib.suppress(Exception):
        plain = mime.text() or ""

    with contextlib.suppress(Exception):
        if mime.hasHtml():
            html = mime.html() or ""
            if looks_like_html(html):
                converted = html_to_markdown(html)
                if converted.strip():
                    return converted

    with contextlib.suppress(Exception):
        if mime.hasFormat("text/rtf"):
            data = bytes(mime.data("text/rtf"))
            if data:
                converted = rtf_to_markdown(data.decode("latin-1"))
                if converted.strip():
                    return converted

    return plain
