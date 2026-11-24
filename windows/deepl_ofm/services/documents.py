"""Document translation for plain text, Markdown, Word (DOCX) and PDF files.

The module is deliberately free of Qt imports: it is used from worker threads and
must stay importable in a headless test run.  The behaviour mirrors
``Sources/HyMT/Services/DocumentTranslator.swift``:

* TXT/MD keep their line structure, blank lines and fenced code blocks.  Only
  paragraphs are handed to the translation callable.
* DOCX changes only the ``<w:t>`` text nodes of ``word/document.xml`` inside a
  copy of the original package; every other entry stays byte-for-byte intact.
* PDF keeps the original page as the background, extracts text blocks with
  ``pdfplumber``, and paints the translation into the same rectangles with a
  ``reportlab`` overlay that is merged into the page with ``pypdf``.  No
  redaction is performed, so the original text layer remains part of the file.

Only the public API documented in ``CONTRACTS.md`` section 14 is exported.
"""

from __future__ import annotations

import io
import itertools
import os
import re
import statistics
import tempfile
import threading
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

from deepl_ofm.i18n import t

if TYPE_CHECKING:  # pragma: no cover - imported only for type checkers
    from deepl_ofm.core.languages import Language
    from deepl_ofm.i18n import AppLanguage

__all__ = ["DocumentError", "DocumentKind", "DocumentTranslator", "OpenedDocument"]

_Translate = Callable[[str], str]
_Progress = Callable[[int, int], None]

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_XML_NS = "http://www.w3.org/XML/1998/namespace"
_DOCX_DOCUMENT = "word/document.xml"
_DOCX_ZIP_ERRORS = (
    OSError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    RuntimeError,
    NotImplementedError,
    ValueError,
)
# Same ceiling as the Swift ``unzipEntry`` guard, in bytes of compressed input.
_MAX_DOCX_XML = 32 * 1024 * 1024

_MESSAGES = {
    "unsupported": "This file type is not supported.",
    "unreadable": "The file could not be read.",
    "no_text": "No selectable text found. For a scanned PDF, run text recognition first.",
    "write_failed": "The file could not be translated.",
    "encrypted": "The PDF is password-protected and cannot be translated.",
    "cancelled": "Cancelled",
}


class DocumentKind(str, Enum):
    """File kinds the document engine can open, translate and write back."""

    TEXT = "txt"
    MARKDOWN = "md"
    PDF = "pdf"
    DOCX = "docx"

    @staticmethod
    def from_path(path: Path) -> DocumentKind | None:
        extension = Path(path).suffix.lower().lstrip(".")
        return {
            "txt": DocumentKind.TEXT,
            "text": DocumentKind.TEXT,
            "md": DocumentKind.MARKDOWN,
            "markdown": DocumentKind.MARKDOWN,
            "mdown": DocumentKind.MARKDOWN,
            "pdf": DocumentKind.PDF,
            "docx": DocumentKind.DOCX,
        }.get(extension)

    @property
    def pattern(self) -> str:
        """File-dialog glob for this kind (``*.txt``, ``*.pdf``, ...)."""
        return f"*.{self.value}"


class DocumentError(Exception):
    """A document could not be read, translated or written.

    ``kind`` is one of ``unsupported``, ``no_text``, ``unreadable``,
    ``write_failed``, ``encrypted`` and ``cancelled`` (the last one is raised
    when the caller's cancellation event is set between paragraphs).
    """

    def __init__(self, kind: str, detail: str = "") -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(kind if not detail else f"{kind}: {detail}")

    def message(self, language: AppLanguage | str | None = None) -> str:
        """Localised, user-facing explanation."""
        key = _MESSAGES.get(self.kind, "The file could not be translated.")
        return t(key, language)


@dataclass
class OpenedDocument:
    """A file that was inspected and is ready to be translated."""

    path: Path
    kind: DocumentKind
    source_text: str | None = None
    paragraphs: list[str] = field(default_factory=list)
    payload: object | None = None

    @property
    def text(self) -> str:
        """Whole source text (TXT/MD) or the paragraph texts joined by newlines."""
        if self.source_text is not None:
            return self.source_text
        return "\n".join(self.paragraphs)


@dataclass(frozen=True, slots=True)
class _TextUnit:
    text: str
    translate: bool


@dataclass(frozen=True, slots=True)
class _PdfLine:
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    font_size: float
    bold: bool
    font_name: str
    color: tuple[float, float, float]

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class _PdfBlock:
    page_index: int
    x0: float
    top: float
    x1: float
    bottom: float
    text: str
    font_size: float
    bold: bool
    font_name: str
    alignment: str
    line_pitch: float
    text_color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    background: tuple[float, float, float] = (1.0, 1.0, 1.0)

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.bottom - self.top


@dataclass(frozen=True, slots=True)
class _PdfLayout:
    page_count: int
    page_sizes: tuple[tuple[float, float], ...]
    blocks: tuple[_PdfBlock, ...]


class DocumentTranslator:
    """Read documents, hand their paragraphs to ``translate`` and write them back."""

    # ------------------------------------------------------------------ read

    @staticmethod
    def read(path: Path) -> OpenedDocument:
        path = Path(path)
        kind = DocumentKind.from_path(path)
        if kind is None:
            raise DocumentError("unsupported")

        if kind in (DocumentKind.TEXT, DocumentKind.MARKDOWN):
            text = _read_text_file(path)
            if not text.strip():
                raise DocumentError("no_text")
            return OpenedDocument(path=path, kind=kind, source_text=text)

        if kind is DocumentKind.PDF:
            layout = _read_pdf_layout(path)
            return OpenedDocument(
                path=path,
                kind=kind,
                paragraphs=[block.text for block in layout.blocks],
                payload=layout,
            )

        xml = _read_docx_xml(path)
        paragraphs = _docx_paragraphs(xml)
        if not any(paragraph.strip() for paragraph in paragraphs):
            raise DocumentError("no_text")
        return OpenedDocument(path=path, kind=kind, paragraphs=paragraphs, payload=xml)

    # -------------------------------------------------------------- suggested

    @staticmethod
    def suggested_path(path: Path, target: Language) -> Path:
        """Return ``report.pdf`` -> ``report_uk.pdf`` without touching the source.

        The target's language code is appended to the stem; the extension is
        normalised to the kind's canonical lower-case form (as the Swift app
        does when it builds its output file) and the source is never returned.
        """
        path = Path(path)
        code = getattr(target, "code", None)
        if not code:
            code = str(target).strip() if target is not None else ""
        code = code or "translated"
        kind = DocumentKind.from_path(path)
        suffix = f".{kind.value}" if kind is not None else path.suffix
        candidate = path.with_name(f"{path.stem}_{code}{suffix}")
        if _same_path(candidate, path):
            for index in range(1, 1000):
                candidate = path.with_name(f"{path.stem}_{code}_{index}{suffix}")
                if not _same_path(candidate, path):
                    break
        return candidate

    # ----------------------------------------------------------------- write

    @staticmethod
    def write(
        doc: OpenedDocument,
        out_path: Path,
        translate: _Translate,
        on_progress: _Progress | None = None,
        cancel: threading.Event | None = None,
    ) -> Path:
        """Translate ``doc`` and write the result to ``out_path``.

        ``translate`` is called once per source paragraph (and must return one
        translated paragraph).  ``on_progress(completed, total)`` is invoked
        after every paragraph; ``cancel`` is checked before each paragraph and
        before the output is written, aborting with
        ``DocumentError("cancelled")``.  Exceptions raised by ``translate``
        propagate unchanged and no output file is left behind.
        """
        out_path = Path(out_path)
        _check_cancel(cancel)

        if doc.kind in (DocumentKind.TEXT, DocumentKind.MARKDOWN):
            text = doc.source_text if doc.source_text is not None else doc.text
            translated = _translate_text(
                text,
                doc.kind is DocumentKind.MARKDOWN,
                translate,
                on_progress,
                cancel,
            )
            _check_cancel(cancel)
            _write_text(out_path, translated)
            return out_path

        if doc.kind is DocumentKind.DOCX:
            lines = _translate_paragraphs(doc.paragraphs, translate, on_progress, cancel)
            _check_cancel(cancel)
            _write_docx(doc.path, lines, out_path)
            return out_path

        if doc.kind is DocumentKind.PDF:
            layout = doc.payload
            if not isinstance(layout, _PdfLayout):
                raise DocumentError("unreadable")
            translations = _translate_paragraphs(
                [block.text for block in layout.blocks],
                translate,
                on_progress,
                cancel,
            )
            _check_cancel(cancel)
            _write_pdf(doc.path, layout, translations, out_path)
            return out_path

        raise DocumentError("unsupported")


# --------------------------------------------------------------------- helpers


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise _cancelled_error()


_CANCELLED_ERROR_CLASS: type[DocumentError] | None = None


def _cancelled_error() -> DocumentError:
    """Build a cancellation error the UI layer already understands.

    The controller treats ``services.translation.TranslationCancelled`` as a
    clean cancellation, while document callers expect ``DocumentError``.  A
    lazily built subclass satisfies both; if the translation module is not
    importable (circular import during start-up, stripped build) a plain
    ``DocumentError("cancelled")`` is raised instead.
    """
    global _CANCELLED_ERROR_CLASS
    if _CANCELLED_ERROR_CLASS is None:
        try:
            from deepl_ofm.services.translation import TranslationCancelled
        except Exception:
            return DocumentError("cancelled")
        _CANCELLED_ERROR_CLASS = type(
            "DocumentCancelled", (DocumentError, TranslationCancelled), {}
        )
    return _CANCELLED_ERROR_CLASS("cancelled")


def _same_path(first: Path, second: Path) -> bool:
    try:
        return os.path.normcase(os.path.abspath(first)) == os.path.normcase(
            os.path.abspath(second)
        )
    except OSError:
        return first == second


def _write_bytes(path: Path, data: bytes) -> None:
    """Write ``data`` atomically, so a failed write never truncates ``path``."""
    path = Path(path)
    parent = path.parent if str(path.parent) else Path(".")
    try:
        handle, temporary = tempfile.mkstemp(
            prefix=".deepl-ofm-", suffix=".tmp", dir=str(parent)
        )
    except OSError as exc:
        raise DocumentError("write_failed", str(exc)) from exc
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise DocumentError("write_failed", str(exc)) from exc


# ------------------------------------------------------------------ text/MD


#: Byte-order marks, checked before any heuristic decoding.
_BOMS: tuple[tuple[bytes, str], ...] = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def _plausibility(text: str) -> float:
    """Score a legacy decoding; higher means "looks like real prose".

    cp1251 and cp1252 both accept almost every byte sequence, so the choice
    cannot be made from exceptions alone.  Two signals separate them reliably:
    a mis-decoded Cyrillic file turns into a run of accented Latin-1 letters
    (ïðèâåò), and the wrong code page mixes Cyrillic and Latin letters inside
    single words (GrьЯe).
    """
    words = text.split()
    letters = [character for character in text if character.isalpha()]
    if not letters or not words:
        return 0.0
    total = len(letters)
    accented = sum(1 for character in letters if "\u00c0" <= character <= "\u00ff")
    cyrillic = sum(1 for character in letters if "\u0400" <= character <= "\u04ff")
    mixed = 0
    for word in words:
        has_latin = any("a" <= character.lower() <= "z" for character in word)
        has_cyrillic = any("\u0400" <= character <= "\u04ff" for character in word)
        if has_latin and has_cyrillic:
            mixed += 1
    score = 1.0 if cyrillic else 0.0
    score -= 2.5 * (accented / total)
    score -= 3.0 * (mixed / len(words))
    return score


def _decode_legacy(data: bytes) -> str:
    """Decode a Windows text file without a byte-order mark.

    Notepad on an older Russian or Ukrainian installation writes cp1251, a
    Western one writes cp1252.  Both are scored and the more plausible result
    wins; the interface language only breaks an exact tie.
    """
    try:
        from deepl_ofm.i18n import current_language

        cyrillic_first = current_language().value in ("uk", "ru")
    except Exception:  # pragma: no cover - i18n is always importable in the app
        cyrillic_first = False
    order = ("cp1251", "cp1252") if cyrillic_first else ("cp1252", "cp1251")
    best_text = ""
    best_score = float("-inf")
    for encoding in order:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        score = _plausibility(text)
        if score > best_score:
            best_text, best_score = text, score
    return best_text or data.decode("utf-8", "replace")


def _read_text_file(path: Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentError("unreadable", str(exc)) from exc
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data[len(bom):].decode(encoding) if encoding != "utf-8-sig" else data.decode(encoding)
            except UnicodeDecodeError:
                break
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return _decode_legacy(data)


def _write_text(path: Path, text: str) -> None:
    _write_bytes(path, text.encode("utf-8"))


def _text_units(text: str, markdown: bool) -> list[_TextUnit]:
    """Split text the same way ``DocumentTranslator.textUnits`` does.

    Only runs of non-blank lines are translated; blank lines, the bytes between
    paragraphs and (for Markdown) fenced code blocks are emitted as literal
    units so that joining all units reproduces ``text`` exactly.
    """
    units: list[_TextUnit] = []
    lines = _line_spans(text)
    cursor = 0
    paragraph_start: int | None = None
    paragraph_end = 0
    code_fence: tuple[str, int] | None = None

    def flush_paragraph() -> None:
        nonlocal cursor, paragraph_start
        if paragraph_start is None:
            return
        if cursor < paragraph_start:
            units.append(_TextUnit(text[cursor:paragraph_start], False))
        units.append(_TextUnit(text[paragraph_start:paragraph_end], True))
        cursor = paragraph_end
        paragraph_start = None

    for start, end in lines:
        indentation = 0
        while start + indentation < end and text[start + indentation] == " ":
            indentation += 1
        content = text[start + indentation : end]

        if markdown and indentation <= 3 and content[:1] in ("`", "~"):
            marker = content[0]
            count = len(content) - len(content.lstrip(marker))
            suffix = content[count:]
            if code_fence is not None:
                if (
                    marker == code_fence[0]
                    and count >= code_fence[1]
                    and not suffix.strip()
                ):
                    code_fence = None
                continue
            if count >= 3 and (marker != "`" or "`" not in suffix):
                flush_paragraph()
                code_fence = (marker, count)
                continue

        if code_fence is not None:
            continue

        if not content.strip():
            flush_paragraph()
        else:
            if paragraph_start is None:
                paragraph_start = start
            paragraph_end = end

    flush_paragraph()
    if cursor < len(text):
        units.append(_TextUnit(text[cursor:], False))
    return units


def _line_spans(text: str) -> list[tuple[int, int]]:
    """Line spans without their terminators, mirroring Swift's newline split.

    A trailing newline produces one final empty line, exactly like
    ``String.split(omittingEmptySubsequences: false)`` in the Swift original.
    """
    if not text:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    index = 0
    length = len(text)
    while index < length:
        character = text[index]
        if character == "\r":
            spans.append((start, index))
            index += 2 if index + 1 < length and text[index + 1] == "\n" else 1
            start = index
        elif character == "\n":
            spans.append((start, index))
            index += 1
            start = index
        else:
            index += 1
    if start < length:
        spans.append((start, length))
    elif start == length and text[-1:] in ("\n", "\r"):
        spans.append((start, start))
    return spans


def _translate_text(
    text: str,
    markdown: bool,
    translate: _Translate,
    on_progress: _Progress | None,
    cancel: threading.Event | None,
) -> str:
    units = _text_units(text, markdown)
    total = sum(1 for unit in units if unit.translate)
    completed = 0
    pieces: list[str] = []
    for unit in units:
        if not unit.translate:
            pieces.append(unit.text)
            continue
        _check_cancel(cancel)
        pieces.append(translate(unit.text))
        completed += 1
        if on_progress is not None:
            on_progress(completed, total)
    return "".join(pieces)


def _translate_paragraphs(
    paragraphs: list[str],
    translate: _Translate,
    on_progress: _Progress | None,
    cancel: threading.Event | None,
) -> list[str]:
    """Translate every paragraph, leaving whitespace-only ones untouched.

    Progress counts only the paragraphs that are actually sent to the model, so
    "X of Y" matches what the user sees in the macOS app (blank paragraphs are
    not translation units).
    """
    total = sum(1 for paragraph in paragraphs if paragraph.strip())
    translated: list[str] = []
    completed = 0
    for paragraph in paragraphs:
        _check_cancel(cancel)
        if paragraph.strip():
            translated.append(translate(paragraph))
            completed += 1
            if on_progress is not None:
                on_progress(completed, total)
        else:
            translated.append(paragraph)
    return translated


# --------------------------------------------------------------------- DOCX


def _read_docx_xml(path: Path) -> bytes:
    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(_DOCX_DOCUMENT)
            if info.file_size > _MAX_DOCX_XML:
                raise DocumentError("unreadable", "word/document.xml is too large")
            return archive.read(info)
    except DocumentError:
        raise
    except KeyError as exc:
        raise DocumentError("unreadable", "word/document.xml is missing") from exc
    except _DOCX_ZIP_ERRORS as exc:
        raise DocumentError("unreadable", str(exc)) from exc


def _parse_docx_xml(data: bytes, error_kind: str) -> ET.Element:
    try:
        parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True))
        return ET.fromstring(data, parser=parser)
    except ET.ParseError as exc:
        raise DocumentError(error_kind, str(exc)) from exc


def _register_docx_namespaces(data: bytes) -> None:
    """Keep the original prefix names (``w:``, ``mc:``, ...) when serialising."""
    for prefix, uri in _docx_namespace_declarations(data):
        try:
            ET.register_namespace(prefix, uri)
        except ValueError:
            continue


def _docx_paragraphs(data: bytes) -> list[str]:
    root = _parse_docx_xml(data, "unreadable")
    return [_paragraph_text(paragraph) for paragraph in _iter_elements(root, "p")]


def _iter_elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    tag = f"{{{_WORD_NS}}}{local_name}"
    return [element for element in root.iter(tag) if element is not root]


def _paragraph_text(paragraph: ET.Element) -> str:
    """Visible text of one paragraph; tabs and line breaks become spaces."""
    parts: list[str] = []
    for child in paragraph:
        if child.tag == f"{{{_WORD_NS}}}t":
            parts.append(child.text or "")
        elif child.tag in (
            f"{{{_WORD_NS}}}tab",
            f"{{{_WORD_NS}}}br",
            f"{{{_WORD_NS}}}cr",
        ):
            parts.append(" ")
        else:
            parts.append(_paragraph_text(child))
    return "".join(parts)


def _rewrite_docx_xml(data: bytes, lines: list[str]) -> bytes:
    root = _parse_docx_xml(data, "write_failed")
    for index, paragraph in enumerate(_iter_elements(root, "p")):
        if index >= len(lines):
            break
        texts = _iter_elements(paragraph, "t")
        if not texts:
            continue
        if lines[index] == _paragraph_text(paragraph):
            continue
        _distribute_text(texts, lines[index])
    return _serialize_docx_xml(root, data)


def _distribute_text(texts: list[ET.Element], line: str) -> None:
    """Spread a translated paragraph over the original runs by character weight.

    This keeps inline formatting (bold/italic/link runs) aligned with the
    original, like the Swift implementation.
    """
    weights = [len(node.text or "") for node in texts]
    total = sum(weights)
    length = len(line)
    position = 0
    consumed = 0
    for node, weight in zip(texts, weights):
        consumed += weight
        end = length * consumed // total if total > 0 else length
        fragment = line[position:end]
        node.text = fragment
        if fragment and (fragment[0].isspace() or fragment[-1].isspace()):
            node.set(f"{{{_XML_NS}}}space", "preserve")
        position = end


_DOCX_XML_LOCK = threading.Lock()


def _serialize_docx_xml(root: ET.Element, original: bytes) -> bytes:
    # ElementTree's prefix registry is process-global; holding the lock and
    # re-registering this document's prefixes keeps concurrent DOCX writes from
    # swapping each other's prefixes.
    with _DOCX_XML_LOCK:
        _register_docx_namespaces(original)
        body = ET.tostring(root, encoding="utf-8")
        # Declarations that are only referenced from values such as
        # ``mc:Ignorable="w14"`` are dropped by ElementTree; Word needs them.
        start_tag = body.split(b">", 1)[0]
        added = False
        for prefix, uri in _docx_namespace_declarations(original):
            marker = f'xmlns:{prefix}="'.encode()
            if marker not in start_tag:
                root.set(f"xmlns:{prefix}", uri)
                added = True
        if added:
            body = ET.tostring(root, encoding="utf-8")

    head = original[:256]
    standalone = b'standalone="yes"' in head or b"standalone='yes'" in head
    declaration = b'<?xml version="1.0" encoding="UTF-8"'
    if standalone:
        declaration += b' standalone="yes"'
    declaration += b"?>\n"
    return declaration + body


def _docx_namespace_declarations(data: bytes) -> list[tuple[str, str]]:
    """Original ``xmlns:prefix`` declarations, first occurrence per prefix."""
    declarations: dict[str, str] = {}
    try:
        for _event, namespace in ET.iterparse(io.BytesIO(data), events=("start-ns",)):
            prefix, uri = namespace
            if not prefix or prefix in ("xml", "xmlns"):
                continue
            declarations.setdefault(prefix, uri)
    except ET.ParseError:
        return []
    return list(declarations.items())


def _rebuild_docx(original: Path, document_xml: bytes) -> bytes:
    buffer = io.BytesIO()
    try:
        with zipfile.ZipFile(original, "r") as source, zipfile.ZipFile(
            buffer, "w"
        ) as target:
            for info in source.infolist():
                data = source.read(info.filename)
                if info.filename == _DOCX_DOCUMENT:
                    data = document_xml
                # ``writestr`` keeps zipinfo metadata and compress_type.
                target.writestr(info, data)
            target.comment = source.comment
    except _DOCX_ZIP_ERRORS + (KeyError,) as exc:
        raise DocumentError("write_failed", str(exc)) from exc
    return buffer.getvalue()


def _write_docx(original: Path, lines: list[str], out_path: Path) -> None:
    xml = _read_docx_xml(original)
    updated = _rewrite_docx_xml(xml, lines)
    _write_bytes(out_path, _rebuild_docx(original, updated))


# ---------------------------------------------------------------------- PDF


def _pdf_reader(data: bytes):
    """Build a pypdf reader, rejecting encrypted files."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise DocumentError("unreadable", "pypdf is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise DocumentError("unreadable", str(exc)) from exc
    if reader.is_encrypted:
        raise DocumentError("encrypted")
    return reader


def _open_pdf_reader(path: Path):
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise DocumentError("unreadable", str(exc)) from exc
    return _pdf_reader(data)


def _read_pdf_layout(path: Path) -> _PdfLayout:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise DocumentError("unreadable", "pdfplumber is not installed") from exc

    reader = _open_pdf_reader(path)
    try:
        reader_page_count = len(reader.pages)
    except Exception as exc:
        raise DocumentError("unreadable", str(exc)) from exc

    blocks: list[_PdfBlock] = []
    page_sizes: list[tuple[float, float]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_index, page in enumerate(pdf.pages):
                width = float(page.width)
                height = float(page.height)
                page_sizes.append((width, height))
                words = page.extract_words(
                    extra_attrs=["size", "fontname", "non_stroking_color"]
                )
                lines = _pdf_lines(words)
                fills = _pdf_fill_objects(page)
                blocks.extend(
                    replace(block, background=_pdf_background(block, fills))
                    for block in _pdf_blocks(lines, page_index, width)
                )
    except DocumentError:
        raise
    except Exception as exc:
        if _is_password_error(exc):
            raise DocumentError("encrypted", str(exc)) from exc
        raise DocumentError("unreadable", str(exc)) from exc

    try:
        while len(page_sizes) < reader_page_count:
            box = reader.pages[len(page_sizes)].mediabox
            page_sizes.append((float(box.width), float(box.height)))
    except Exception as exc:
        raise DocumentError("unreadable", str(exc)) from exc
    page_count = len(page_sizes)
    if page_count == 0:
        raise DocumentError("no_text")
    if not blocks:
        raise DocumentError("no_text")
    return _PdfLayout(
        page_count=page_count,
        page_sizes=tuple(page_sizes),
        blocks=tuple(blocks),
    )


def _is_password_error(error: BaseException) -> bool:
    if "PDFPasswordIncorrect" in type(error).__name__:
        return True
    cause = getattr(error, "args", ())
    return any("PDFPasswordIncorrect" in type(item).__name__ for item in cause)


def _pdf_lines(words: list[dict]) -> list[_PdfLine]:
    """Group words into visual lines (top-left origin, like pdfplumber)."""
    ordered = sorted(
        words,
        key=lambda word: (round(float(word.get("top", 0.0)), 2), float(word.get("x0", 0.0))),
    )
    grouped: list[dict] = []
    for word in ordered:
        text = str(word.get("text") or "")
        if not text.strip():
            continue
        top = float(word["top"])
        bottom = float(word["bottom"])
        height = max(0.1, bottom - top)
        if grouped and abs(top - grouped[-1]["top"]) <= max(1.5, height * 0.45):
            line = grouped[-1]
            line["words"].append(word)
            line["x0"] = min(line["x0"], float(word["x0"]))
            line["x1"] = max(line["x1"], float(word["x1"]))
            line["top"] = min(line["top"], top)
            line["bottom"] = max(line["bottom"], bottom)
            continue
        grouped.append(
            {
                "words": [word],
                "x0": float(word["x0"]),
                "x1": float(word["x1"]),
                "top": top,
                "bottom": bottom,
            }
        )

    lines: list[_PdfLine] = []
    for line in grouped:
        line_words = sorted(line["words"], key=lambda word: float(word["x0"]))
        sizes = [
            float(
                word.get("size")
                or (float(word["bottom"]) - float(word["top"]))
                or 12.0
            )
            for word in line_words
        ]
        lines.append(
            _PdfLine(
                text=_join_words(line_words),
                x0=line["x0"],
                top=line["top"],
                x1=line["x1"],
                bottom=line["bottom"],
                font_size=max(sizes),
                bold=_is_bold(str(line_words[0].get("fontname") or "")),
                font_name=str(line_words[0].get("fontname") or ""),
                color=_pdf_color(line_words[0].get("non_stroking_color"))
                or (0.0, 0.0, 0.0),
            )
        )
    return lines


def _join_words(words: list[dict]) -> str:
    text = str(words[0].get("text") or "")
    for previous, word in itertools.pairwise(words):
        height = max(float(word["bottom"]) - float(word["top"]), 1.0)
        gap = float(word["x0"]) - float(previous["x1"])
        separator = " " if gap > max(0.5, height * 0.15) else ""
        text += separator + str(word.get("text") or "")
    return text.strip()


def _is_bold(font_name: str) -> bool:
    lowered = font_name.lower()
    return any(token in lowered for token in ("bold", "black", "heavy", "semibold"))


def _pdf_blocks(lines: list[_PdfLine], page_index: int, page_width: float) -> list[_PdfBlock]:
    """Merge lines into paragraphs, mirroring Swift's grouping heuristics."""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda line: (line.top, line.x0))
    groups: list[list[_PdfLine]] = []
    for line in ordered:
        target: int | None = None
        for index, group in enumerate(groups):
            previous = group[-1]
            if previous.top >= line.top:
                continue
            if _same_block(previous, line):
                target = index
        if target is None:
            groups.append([line])
        else:
            groups[target].append(line)

    groups.sort(key=lambda group: (group[0].top, group[0].x0))
    blocks: list[_PdfBlock] = []
    for group in groups:
        text = " ".join(line.text for line in group).strip()
        if not text:
            continue
        x0 = min(line.x0 for line in group)
        x1 = max(line.x1 for line in group)
        top = min(line.top for line in group)
        bottom = max(line.bottom for line in group)
        if x1 - x0 <= 1 or bottom - top <= 1:
            continue

        alignment = "left"
        if x1 - x0 < page_width * 0.75:
            middle = (x0 + x1) / 2
            if abs(middle - page_width / 2) < page_width * 0.06:
                alignment = "center"
            elif x1 > page_width - page_width * 0.08:
                alignment = "right"

        pitch = 0.0
        if len(group) > 1:
            deltas = [
                second.top - first.top
                for first, second in itertools.pairwise(group)
                if second.top > first.top
            ]
            if deltas:
                pitch = float(statistics.median(deltas))

        blocks.append(
            _PdfBlock(
                page_index=page_index,
                x0=x0,
                top=top,
                x1=x1,
                bottom=bottom,
                text=text,
                font_size=max(line.font_size for line in group),
                bold=group[0].bold,
                font_name=group[0].font_name,
                alignment=alignment,
                line_pitch=pitch,
                text_color=group[0].color,
            )
        )
    return blocks


_PDF_WHITE = (1.0, 1.0, 1.0)


def _pdf_fill_objects(page) -> list[tuple[float, float, float, float, tuple[float, float, float]]]:
    """Filled rectangles/curves of a page, in content order, with RGB colours."""
    objects: list[tuple[float, float, float, float, tuple[float, float, float]]] = []
    for item in (*page.rects, *page.curves):
        if not item.get("fill"):
            continue
        color = _pdf_color(item.get("non_stroking_color"))
        if color is None:
            continue
        try:
            x0 = float(item["x0"])
            top = float(item["top"])
            x1 = float(item["x1"])
            bottom = float(item["bottom"])
        except (KeyError, TypeError, ValueError):
            continue
        if x1 <= x0 or bottom <= top:
            continue
        objects.append((x0, top, x1, bottom, color))
    return objects


def _pdf_background(
    block: _PdfBlock,
    objects: list[tuple[float, float, float, float, tuple[float, float, float]]],
) -> tuple[float, float, float]:
    """Topmost fill that covers at least 60 % of the block, else white.

    This approximates the Swift version, which renders the page and samples the
    pixels just outside the text rectangle; using the fill geometry avoids a
    rasteriser while keeping shaded panels and table headers.
    """
    background = _PDF_WHITE
    block_area = max(1.0, block.width * block.height)
    for x0, top, x1, bottom, color in objects:
        overlap_x = min(block.x1, x1) - max(block.x0, x0)
        overlap_y = min(block.bottom, bottom) - max(block.top, top)
        if overlap_x <= 0 or overlap_y <= 0:
            continue
        if overlap_x * overlap_y / block_area >= 0.6:
            background = color
    return background


def _pdf_color(value: object) -> tuple[float, float, float] | None:
    """Convert a pdfminer ``non_stroking_color`` to normalised RGB."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        components = [float(value)]
    else:
        try:
            components = [float(component) for component in value]  # type: ignore[union-attr]
        except (TypeError, ValueError):
            return None
    if not components:
        return None
    if any(component > 1.0 for component in components):
        components = [component / 255.0 for component in components]
    components = [min(1.0, max(0.0, component)) for component in components]
    if len(components) == 1:
        return (components[0], components[0], components[0])
    if len(components) == 3:
        return (components[0], components[1], components[2])
    if len(components) == 4:
        cyan, magenta, yellow, black = components
        return (
            (1.0 - cyan) * (1.0 - black),
            (1.0 - magenta) * (1.0 - black),
            (1.0 - yellow) * (1.0 - black),
        )
    return None


def _pdf_text_color(
    background: tuple[float, float, float],
    original: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[float, float, float]:
    """Keep the original text colour when it contrasts with the background.

    Mirrors ``DocumentTranslator.draw`` in Swift: if the original colour is too
    close to the background, switch to white on dark surfaces and black on
    light ones.
    """
    background_luminance = _pdf_luminance(background)
    if abs(_pdf_luminance(original) - background_luminance) > 0.25:
        return original
    return (1.0, 1.0, 1.0) if background_luminance < 0.55 else (0.0, 0.0, 0.0)


def _pdf_luminance(color: tuple[float, float, float]) -> float:
    return 0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]


def _pdf_leading(block: _PdfBlock, size: float) -> float:
    """Use the source line pitch for wrapped paragraphs, 1.2 × size otherwise."""
    if block.line_pitch > 0:
        return min(max(block.line_pitch, size * 1.05), size * 2.0)
    return size * 1.2


def _same_block(previous: _PdfLine, line: _PdfLine) -> bool:
    if abs(previous.font_size - line.font_size) >= 1.5:
        return False
    height = max(previous.height, line.height)
    gap = line.top - previous.bottom
    if gap > max(2.5, height * 0.45) or gap < -height * 1.2:
        return False
    overlap = min(previous.x1, line.x1) - max(previous.x0, line.x0)
    width = min(previous.width, line.width)
    if width <= 0:
        return True
    return overlap >= width * 0.35


def _write_pdf(
    source: Path,
    layout: _PdfLayout,
    translations: list[str],
    out_path: Path,
) -> None:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise DocumentError("write_failed", "pypdf is not installed") from exc

    try:
        data = source.read_bytes()
    except OSError as exc:
        raise DocumentError("unreadable", str(exc)) from exc
    reader = _pdf_reader(data)

    changed: dict[int, list[tuple[_PdfBlock, str]]] = {}
    for block, translation in zip(layout.blocks, translations):
        text = translation.strip()
        if text and text != block.text:
            changed.setdefault(block.page_index, []).append((block, text))

    if not changed:
        _write_bytes(out_path, data)
        return

    try:
        overlay_data, overlay_pages = _build_pdf_overlay(layout, changed)
        writer = PdfWriter(clone_from=reader)
        overlay = PdfReader(io.BytesIO(overlay_data))
        for page_index, overlay_index in overlay_pages.items():
            if page_index >= len(writer.pages) or overlay_index >= len(overlay.pages):
                continue
            writer.pages[page_index].merge_page(overlay.pages[overlay_index])
        buffer = io.BytesIO()
        writer.write(buffer)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError("write_failed", str(exc)) from exc
    _write_bytes(out_path, buffer.getvalue())


def _build_pdf_overlay(
    layout: _PdfLayout,
    changed: dict[int, list[tuple[_PdfBlock, str]]],
) -> tuple[bytes, dict[int, int]]:
    try:
        from reportlab.pdfgen import canvas
    except ImportError as exc:  # pragma: no cover - dependency is installed
        raise DocumentError("write_failed", "reportlab is not installed") from exc

    default_size = layout.page_sizes[0] if layout.page_sizes else (595.0, 842.0)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=default_size)
    pdf.setCreator("DeepL-oFM")
    mapping: dict[int, int] = {}
    for page_index in sorted(changed):
        if page_index < len(layout.page_sizes):
            width, height = layout.page_sizes[page_index]
        else:
            width, height = default_size
        pdf.setPageSize((width, height))
        for block, text in changed[page_index]:
            _draw_pdf_block(pdf, block, text, height)
        pdf.showPage()
        mapping[page_index] = len(mapping)
    pdf.save()
    return buffer.getvalue(), mapping


def _draw_pdf_block(pdf, block: _PdfBlock, text: str, page_height: float) -> None:
    rect_x = block.x0
    rect_width = max(1.0, block.width)
    rect_height = max(1.0, block.height)
    rect_bottom = page_height - block.bottom

    font_name = _pdf_font_for(text, block.bold)
    size = max(4.5, min(float(block.font_size or 12.0), 200.0))
    leading = size * 1.2
    lines = [text]
    while size >= 4.5:
        lines = _wrap_paragraph(text, font_name, size, rect_width)
        leading = _pdf_leading(block, size)
        if len(lines) * leading <= rect_height + 1.5 or size <= 4.6:
            break
        size -= 0.5

    # Cover the old glyphs; the original text layer stays extractable below.
    pdf.saveState()
    pdf.setFillColorRGB(*block.background)
    pdf.rect(
        rect_x - 2,
        rect_bottom - 1,
        rect_width + 4,
        rect_height + 2,
        stroke=0,
        fill=1,
    )
    pdf.restoreState()

    pdf.saveState()
    path = pdf.beginPath()
    path.rect(rect_x, rect_bottom, rect_width, rect_height)
    pdf.clipPath(path, stroke=0, fill=0)
    pdf.setFillColorRGB(*_pdf_text_color(block.background, block.text_color))
    pdf.setFont(font_name, size)
    baseline = rect_bottom + rect_height - _pdf_ascent(font_name, size)
    for line in lines:
        if baseline < rect_bottom - size:
            break
        if block.alignment == "center":
            pdf.drawCentredString(rect_x + rect_width / 2, baseline, line)
        elif block.alignment == "right":
            pdf.drawRightString(rect_x + rect_width, baseline, line)
        else:
            pdf.drawString(rect_x, baseline, line)
        baseline -= leading
    pdf.restoreState()


def _wrap_paragraph(
    text: str, font_name: str, size: float, max_width: float
) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        lines.extend(_wrap_line(raw, font_name, size, max_width))
    return lines or [""]


def _wrap_line(text: str, font_name: str, size: float, max_width: float) -> list[str]:
    if not text:
        return [""]
    width = max(1.0, max_width)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}" if current else word
        if _pdf_string_width(candidate, font_name, size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if _pdf_string_width(word, font_name, size) <= width:
            current = word
            continue
        chunks = _hard_split(word, font_name, size, width)
        lines.extend(chunks[:-1])
        current = chunks[-1]
    if current:
        lines.append(current)
    return lines or [""]


def _hard_split(word: str, font_name: str, size: float, max_width: float) -> list[str]:
    """Break a word that is wider than the block, character by character."""
    chunks: list[str] = []
    current = ""
    current_width = 0.0
    for character in word:
        character_width = _pdf_string_width(character, font_name, size)
        if current and current_width + character_width > max_width:
            chunks.append(current)
            current = character
            current_width = character_width
        else:
            current += character
            current_width += character_width
    if current:
        chunks.append(current)
    return chunks or [""]


def _pdf_font_for(text: str, bold: bool) -> str:
    """Pick a font that covers the translated script (CJK via CID fonts).

    Base-14 Helvetica only covers Windows-1252, so text outside that range
    (Cyrillic, Greek, Polish diacritics, ...) is drawn with a system TrueType
    font instead of producing missing glyphs.
    """
    if _HANGUL.search(text):
        return _cid_font("HYSMyeongJo-Medium", bold)
    if _KANA.search(text):
        return _cid_font("HeiseiMin-W3", bold)
    if _HAN.search(text):
        return _cid_font("STSong-Light", bold)
    if _needs_unicode_font(text):
        return _unicode_font(bold)
    return "Helvetica-Bold" if bold else "Helvetica"


_HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
_KANA = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")
_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_FONT_LOCK = threading.Lock()
_REGISTERED_CID_FONTS: set[str] = set()
_UNICODE_FONT_NAMES: dict[bool, str | None] = {}
_UNICODE_FONT_FILES = {
    False: (
        "DejaVuSans.ttf",
        "LiberationSans-Regular.ttf",
        "FreeSans.ttf",
        "segoeui.ttf",
        "arial.ttf",
        "Arial.ttf",
    ),
    True: (
        "DejaVuSans-Bold.ttf",
        "LiberationSans-Bold.ttf",
        "FreeSansBold.ttf",
        "segoeuib.ttf",
        "arialbd.ttf",
        "Arial Bold.ttf",
    ),
}


def _needs_unicode_font(text: str) -> bool:
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return True
    return False


def _unicode_font(bold: bool) -> str:
    """Register a system TrueType font that covers non-WinAnsi scripts."""
    fallback = "Helvetica-Bold" if bold else "Helvetica"
    with _FONT_LOCK:
        if bold in _UNICODE_FONT_NAMES:
            return _UNICODE_FONT_NAMES[bold] or fallback
        name = "DeepLUnicode-Bold" if bold else "DeepLUnicode"
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:  # pragma: no cover - dependency is installed
            _UNICODE_FONT_NAMES[bold] = None
            return fallback
        for path in _system_font_paths(bold):
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:
                continue
            _UNICODE_FONT_NAMES[bold] = name
            return name
        _UNICODE_FONT_NAMES[bold] = None
        return fallback


def _system_font_paths(bold: bool) -> list[Path]:
    directories = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/truetype/liberation2"),
        Path("/usr/share/fonts/truetype/freefont"),
        Path("/usr/share/fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/System/Library/Fonts"),
        Path("/Library/Fonts"),
    ]
    return [
        directory / filename
        for directory in directories
        for filename in _UNICODE_FONT_FILES[bold]
        if (directory / filename).is_file()
    ]


def _cid_font(name: str, bold: bool) -> str:
    """Register and return a CJK CID font, falling back to Helvetica."""
    fallback = "Helvetica-Bold" if bold else "Helvetica"
    with _FONT_LOCK:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        except ImportError:  # pragma: no cover - dependency is installed
            return fallback
        if name not in _REGISTERED_CID_FONTS:
            try:
                pdfmetrics.registerFont(UnicodeCIDFont(name))
            except Exception:
                return fallback
            _REGISTERED_CID_FONTS.add(name)
        return name


def _pdf_metrics():
    from reportlab.pdfbase import pdfmetrics

    return pdfmetrics


def _pdf_string_width(text: str, font_name: str, size: float) -> float:
    return _pdf_metrics().stringWidth(text, font_name, size)


def _pdf_ascent(font_name: str, size: float) -> float:
    return _pdf_metrics().getAscent(font_name, size)
