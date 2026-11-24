"""Restores protected tokens (URLs, e-mail addresses, model ids, inline code).

Port of ``Sources/HyMT/Support/TokenRestorer.swift``.  The model tends to
change dots, slashes or capitalisation inside technical tokens while the
surrounding prose is translated normally; this module puts the source spelling
back and, when the token count changed, either accepts the translation (every
source token survived somewhere) or returns ``None`` so the caller can retry.
"""

from __future__ import annotations

import re

# The trailing lookahead allows a sentence period: ``Hy-MT2.`` at the end of a
# sentence is the same protected token as ``Hy-MT2 `` in the middle.  The dot
# is not part of the token and stays in the translation.
_PATTERN = (
    r"(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
    r"""|(?:https?://[^\s)\]>"']+)"""
    r"|(?:(?:[A-Za-z0-9][A-Za-z0-9-]*\.)+"
    r"(?:com|ai|org|io|dev|net|app|co|ua|me|info|biz|xyz|tech|cloud|pro)"
    r"\b(?:/[^\s)\]]*)?)"
    r"|(?:`[^`\n]+`)"
    r"|(?<![A-Za-z0-9._-])[A-Za-z0-9][A-Za-z0-9._-]*/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]*(?![A-Za-z0-9_-])"
    r"|(?<![A-Za-z0-9._-])(?=[A-Za-z0-9.-]*\d)"
    r"[A-Za-z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)+(?![A-Za-z0-9_-])"
)

_REGEX = re.compile(_PATTERN)

_TRAILING_PUNCTUATION = frozenset(".,;:!?…")
_TRAILING_PUNCTUATION_LOOSE = frozenset(":;,.:!?…")

# U+2011 non-breaking hyphen, U+2010 hyphen, U+2012 figure dash, U+2013 en
# dash, U+2014 em dash, U+2212 minus sign.
_HYPHENS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2212": "-",
}
_HYPHEN_TABLE = str.maketrans(_HYPHENS)


def _normalize_hyphens(text: str) -> str:
    """Map the Unicode dash variants models like to emit back to ASCII '-'."""
    return text.translate(_HYPHEN_TABLE)


class _Match:
    """One protected token and its span in the original (non-normalised) text."""

    __slots__ = ("end", "start", "token")

    def __init__(self, start: int, end: int, token: str) -> None:
        self.start = start
        self.end = end
        self.token = token


def _matches(text: str) -> list[_Match]:
    """Find protected tokens in ``text``, mirroring Swift ``matches(in:)``."""
    normalized = _normalize_hyphens(text)
    result: list[_Match] = []
    for match in _REGEX.finditer(normalized):
        start, end = match.span()
        token = match.group(0)
        original_length = len(token)

        # A URL at the end of a sentence must not swallow the full stop.
        while token and token[-1] in _TRAILING_PUNCTUATION:
            token = token[:-1]
        if not token:
            continue
        if len(token) != original_length:
            end = start + len(token)

        # Drop plain words (e.g. a bare ``foo/bar`` without digits) that only
        # matched through the path alternative.
        if not (
            token.startswith("`")
            or "@" in token
            or "." in token
            or any(character.isnumeric() or character in ":-" for character in token)
        ):
            continue
        result.append(_Match(start, end, token))
    return result


class TokenRestorer:
    """Byte-for-byte restoration of technical tokens after translation."""

    @staticmethod
    def restore(source: str, translated: str) -> str | None:
        """Restore source token spellings in ``translated``.

        Returns ``None`` when the number of protected tokens changed and not
        every source token survived somewhere in the translation: keeping a
        corrupted URL or model id is worse than asking for a retry.
        """
        source_tokens = _matches(source)
        if not source_tokens:
            return translated

        translated_tokens = _matches(translated)
        if len(source_tokens) == len(translated_tokens):
            result = translated
            for source_match, translated_match in reversed(
                list(zip(source_tokens, translated_tokens))
            ):
                # Preserve the source spelling, including Unicode hyphens.
                source_token = source[source_match.start : source_match.end]
                result = (
                    result[: translated_match.start]
                    + source_token
                    + result[translated_match.end :]
                )
            return result

        # Counts differ when the model repeats an id or writes it twice with
        # different casing.  Accept the line only when every token survived.
        normalized = _normalize_hyphens(translated).lower()
        kept_every_token = all(
            _normalize_hyphens(match.token).lower() in normalized
            for match in source_tokens
        )
        return translated if kept_every_token else None

    @staticmethod
    def preserve_trailing_punctuation(source: str, translated: str) -> str:
        """Keep the source line's final punctuation on the translation."""
        punctuation = _TRAILING_PUNCTUATION_LOOSE
        source_trimmed = source.strip()
        if not source_trimmed:
            return translated
        last_source = source_trimmed[-1]
        if last_source not in punctuation:
            return translated
        trimmed = translated.strip()
        if trimmed and trimmed[-1] in punctuation:
            return trimmed[:-1] + last_source
        return trimmed + last_source
