"""Line-oriented chunking and recomposition for the translation pipeline.

Port of ``Sources/HyMT/Services/TranslationService.swift`` (``TextChunk`` /
``TextChunker``, lines ~63-167) with the Markdown prefix parsing that the Swift
service performs through ``parseSegment``.  Every non-empty source line becomes
a chunk; lines longer than 3200 characters are additionally split by sentences,
and a fenced code block stays a single chunk.  The Markdown marker (``## `` /
``- `` / ``1. `` / ``> `` / ``- [ ] ``) is kept aside so it can be re-attached
to the translated text, and the exact number of newlines between lines is
stored on the chunk so ``compose`` renders the original layout again.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_PREFIX = re.compile(r"^(\s*#{1,6}\s+)(.+)$")
_QUOTE_PREFIX = re.compile(r"^(\s*>\s+)(.+)$")
_LIST_PREFIX = re.compile(
    r"^(\s*(?:[-*\u2022\u2013\u2014]|\d+[.)])\s+(?:\[[ xX]\]\s+)?)(.+)$"
)

#: Swift's ``TextChunker.limit``: longer lines are split by sentences.
LINE_LIMIT = 3200

_SENTENCE_TERMINATORS = frozenset(".!?\u2026\u3002\uFF01\uFF1F")
_CLOSING_CHARACTERS = frozenset("\"'\u201d\u2019\u00bb)]")

_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "vs",
        "etc",
        "fig",
        "figs",
        "no",
        "vol",
        "pp",
        "inc",
        "ltd",
        "corp",
        "approx",
        "dept",
        "al",
        "e.g",
        "i.e",
    }
)
_WORD_BEFORE = re.compile(r"([A-Za-z\u0400-\u04FF]+)$")


@dataclass
class TextChunk:
    """One translatable unit: a Markdown prefix plus the text to translate.

    ``separator_before`` and ``is_code`` are port additions needed to rebuild
    the source layout (the Swift struct called the first one ``separatorBefore``)
    and to let callers skip fenced code blocks.  Both have defaults, so the
    four documented fields can still be passed positionally.
    """

    prefix: str
    text: str
    is_heading: bool
    index: int
    separator_before: str = field(default="\n", compare=False)
    is_code: bool = field(default=False, compare=False)


def _segment_sentences(text: str) -> list[str]:
    """Split ``text`` at sentence boundaries, keeping terminal punctuation.

    A pragmatic replacement for Foundation's ``.bySentences`` enumeration: a
    terminator is followed by whitespace (or a line break) and a character
    that does not start a lowercase word.  Single-letter abbreviations and a
    small list of common ones ("Mr.", "Dr.", "etc.") do not end a sentence.
    """
    segments: list[str] = []
    start = 0
    length = len(text)
    index = 0
    while index < length:
        character = text[index]
        if character not in _SENTENCE_TERMINATORS:
            index += 1
            continue
        end = index + 1
        while end < length and text[end] in _SENTENCE_TERMINATORS:
            end += 1
        while end < length and text[end] in _CLOSING_CHARACTERS:
            end += 1
        if end >= length or not text[end].isspace():
            index = end
            continue
        next_index = end
        while next_index < length and text[next_index].isspace():
            next_index += 1
        if next_index >= length:
            break
        contains_newline = "\n" in text[end:next_index]
        next_character = text[next_index]
        starts_sentence = (
            contains_newline
            or next_character.isupper()
            or not next_character.islower()
        )
        if starts_sentence and not _is_abbreviation(text, start, index):
            segments.append(text[start:end])
            start = next_index
            index = next_index
            continue
        index = end
    tail = text[start:]
    if tail:
        segments.append(tail)
    return segments


def _is_abbreviation(text: str, start: int, terminator: int) -> bool:
    """True when the period at ``terminator`` closes a known abbreviation."""
    if text[terminator] != ".":
        return False
    match = _WORD_BEFORE.search(text[start:terminator])
    if match is None:
        return False
    word = match.group(1)
    if len(word) == 1:
        return True
    return word.lower() in _ABBREVIATIONS


def _fence_marker(line: str) -> tuple[str, int] | None:
    """Return ``(character, length)`` when ``line`` opens a fenced code block."""
    stripped = line.lstrip()
    for marker in ("`", "~"):
        if stripped.startswith(marker * 3):
            count = 0
            while count < len(stripped) and stripped[count] == marker:
                count += 1
            return marker, count
    return None


def _closes_fence(line: str, marker: tuple[str, int]) -> bool:
    """True when ``line`` is a closing fence for the opening ``marker``."""
    character, minimum = marker
    stripped = line.lstrip()
    if not stripped.startswith(character * minimum):
        return False
    count = 0
    while count < len(stripped) and stripped[count] == character:
        count += 1
    return stripped[count:].strip() == ""


def _parse_prefix(line: str) -> tuple[str, str, bool]:
    """Split a Markdown marker off ``line`` (``parseSegment`` in Swift)."""
    for pattern in (_HEADING_PREFIX, _QUOTE_PREFIX, _LIST_PREFIX):
        match = pattern.match(line)
        if match is None:
            continue
        body = match.group(2)
        if not body.strip():
            continue
        prefix = match.group(1)
        is_heading = prefix.lstrip().startswith("#")
        return prefix, body, is_heading
    return "", line, False


def _split_limited(line: str, limit: int) -> list[str]:
    """Split an over-long line by sentences, then by raw length (Swift logic)."""
    segments = _segment_sentences(line) or [line]
    pieces: list[str] = []
    for segment in segments:
        if len(segment) <= limit:
            pieces.append(segment)
        else:
            pieces.extend(
                segment[offset : offset + limit]
                for offset in range(0, len(segment), limit)
            )
    return [piece.strip() for piece in pieces if piece.strip()]


class TextChunker:
    """Splits source text into chunks and rebuilds the document from them."""

    limit = LINE_LIMIT

    @staticmethod
    def normalize(text: str) -> str:
        """Normalise CRLF and CR line endings to LF."""
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def split(text: str, *, keep_whole_lines: set[int] | None = None) -> list[TextChunk]:
        """Split ``text`` into one chunk per non-empty line.

        Leading and trailing blank lines are dropped (Swift behaviour); the
        number of blank lines between two chunks is preserved in
        ``separator_before``.  A fenced code block becomes a single chunk with
        ``is_code=True`` so it is never sentence-split. Line indices in
        ``keep_whole_lines`` are zero-based in the original input.
        """
        normalized = TextChunker.normalize(text)
        lines = normalized.split("\n")
        chunks: list[TextChunk] = []
        pending_line_breaks = 0
        started = False
        position = 0

        while position < len(lines):
            line = lines[position]
            if not line.strip():
                if started:
                    pending_line_breaks += 1
                position += 1
                continue

            separator = ""
            if chunks:
                separator = "\n" * max(1, pending_line_breaks + 1)

            fence = _fence_marker(line)
            if fence is not None:
                block = [line]
                position += 1
                while position < len(lines):
                    block.append(lines[position])
                    if _closes_fence(lines[position], fence):
                        position += 1
                        break
                    position += 1
                chunks.append(
                    TextChunk(
                        prefix="",
                        text="\n".join(block),
                        is_heading=False,
                        index=0,
                        separator_before=separator,
                        is_code=True,
                    )
                )
                started = True
                pending_line_breaks = 0
                continue

            trimmed = line.rstrip()
            if len(trimmed) <= TextChunker.limit or (
                keep_whole_lines is not None and position in keep_whole_lines
            ):
                prefix, body, is_heading = _parse_prefix(trimmed)
                chunks.append(
                    TextChunk(
                        prefix=prefix,
                        text=body,
                        is_heading=is_heading,
                        index=0,
                        separator_before=separator,
                    )
                )
            else:
                for piece_index, piece in enumerate(
                    _split_limited(trimmed, TextChunker.limit)
                ):
                    prefix, body, is_heading = _parse_prefix(piece)
                    piece_separator = separator if not chunks or piece_index == 0 else " "
                    chunks.append(
                        TextChunk(
                            prefix=prefix,
                            text=body,
                            is_heading=is_heading,
                            index=0,
                            separator_before=piece_separator,
                        )
                    )
            started = True
            pending_line_breaks = 0
            position += 1

        if not chunks:
            # Swift returns one chunk carrying the original text for an empty
            # or whitespace-only document; keep that so compose() round-trips.
            return [TextChunk(prefix="", text=normalized, is_heading=False, index=0)]

        for index, chunk in enumerate(chunks):
            chunk.index = index
        return chunks

    @staticmethod
    def compose(
        chunks: list[TextChunk],
        translated: list[str],
        leading_blank_line: bool = False,
    ) -> str:
        """Reassemble ``translated`` using the layout stored on ``chunks``.

        The first chunk has no separator of its own; ``leading_blank_line``
        prefixes the result with a single blank line for callers that translate
        paragraphs separately.  Trailing blank lines are not reproduced (the
        chunks never store them), matching the Swift streaming output.
        """
        if len(chunks) != len(translated):
            raise ValueError(
                f"expected {len(chunks)} translated chunks, got {len(translated)}"
            )
        if not chunks:
            return ""
        parts: list[str] = []
        if leading_blank_line:
            parts.append("\n")
        for index, (chunk, text) in enumerate(zip(chunks, translated)):
            if index:
                parts.append(chunk.separator_before or "\n")
            parts.append(chunk.prefix + text)
        return "".join(parts)

    @staticmethod
    def split_sentences(text: str) -> list[str]:
        """Split a block into trimmed, non-empty sentences (long-line fallback)."""
        segments = _segment_sentences(text)
        if not segments:
            segments = [text]
        return [segment.strip() for segment in segments if segment.strip()]
