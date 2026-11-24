"""Output cleanup and translation validation for the translation pipeline.

Port of ``Sources/HyMT/Support/OutputSanitizer.swift`` (leaked chat-template
tokens) plus the block validation helpers from
``Sources/HyMT/Services/TranslationService.swift`` (``validated`` /
``translateBlock``: empty, repetition, script, role-token, instruction-echo,
meta-answer and length checks).  Every check mirrors the Swift thresholds and
marker lists; the reasons returned by :meth:`OutputSanitizer.is_degenerate` are
the compact set documented in ``CONTRACTS.md``.
"""

from __future__ import annotations

import re

from deepl_ofm.core.chunker import TextChunker
from deepl_ofm.core.languages import Language

# --------------------------------------------------------------------------- #
# Token / wrapper cleanup (OutputSanitizer.clean)
# --------------------------------------------------------------------------- #

_KNOWN_LEAKS = (
    "<｜hy_place\u2581holder\u2581no\u25812｜>",
    "<｜hy_place\u2581holder\u2581no\u25818｜>",
    "<｜hy_end\u2581of\u2581sentence｜>",
    "｜hy_end\u2581of\u2581sentence｜",
    "｜hy_end",
    "hy-Assistant",
    "hy-User",
    "hy_Assistant",
    "hy_User",
)

_RE_HY_TOKEN = re.compile(r"[<｜|]hy_[A-Za-z0-9_▁]*[>|]?")
_RE_HY_TAIL = re.compile(r"[<｜|]\s*hy[-_/]?[A-Za-z]*[^>]*")
_RE_OPEN_ANGLE = re.compile(r"<｜[^>]*$")
_RE_OPEN_CLOSE = re.compile(r"</｜[^>]*$")
_RE_TRAILING_HY = re.compile(r"｜hy[^\s]*$")
# An ASCII pipe may close a Markdown table row.
_RE_TRAILING_BRACKET = re.compile(r"[<｜]\s*$")


# --------------------------------------------------------------------------- #
# Preamble stripping (TranslationService.stripPreamble)
# --------------------------------------------------------------------------- #

_PREAMBLE_COLON = re.compile(
    r"^(?:"
    r"Ось\s+(?:ваш\s+|твій\s+)?(?:переклад|текст\s+у\s+перекладі)"
    r"(?:[^:\n]{0,50})?"
    r"|Звісно,?\s+ось(?:[^:\n]{0,50})?"
    r"|Here(?:'s|\s+is)\s+(?:the\s+|your\s+)?translation(?:[^:\n]{0,50})?"
    r"|The\s+translation\s+is"
    r"|Translation"
    r"|Вот\s+перевод"
    r"|Перевод\s+текста"
    r")\s*:\s*",
    re.IGNORECASE,
)
_PREAMBLE_FILLER = re.compile(r"^(?:Звісно|Звичайно|Ось)[!,.]\s*", re.IGNORECASE)
_OPEN_QUOTES = frozenset("«“\"")
_CLOSE_QUOTES = frozenset("»”\"")


# --------------------------------------------------------------------------- #
# Validation markers and script tables (TranslationService.validated)
# --------------------------------------------------------------------------- #

_CJK_TARGET_CODES = frozenset({"zh", "zh-hant", "zh-hans", "yue", "ja"})
_CYRILLIC_TARGETS = frozenset({"uk", "ru", "be", "bg", "mk", "sr", "kk", "mn"})

_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))
_CYRILLIC_RANGES = ((0x0400, 0x04FF),)
_LATIN_RANGES = ((0x0041, 0x024F),)

_SCRIPT_RANGES: dict[str, tuple[tuple[int, int], ...]] = {
    "uk": _CYRILLIC_RANGES,
    "ru": _CYRILLIC_RANGES,
    "be": _CYRILLIC_RANGES,
    "bg": _CYRILLIC_RANGES,
    "mk": _CYRILLIC_RANGES,
    "kk": _CYRILLIC_RANGES,
    "mn": _CYRILLIC_RANGES,
    "sr": ((0x0400, 0x04FF), (0x0041, 0x024F)),
    "zh": _CJK_RANGES,
    "zh-hant": _CJK_RANGES,
    "zh-hans": _CJK_RANGES,
    "yue": _CJK_RANGES,
    "ja": ((0x3040, 0x30FF), (0x4E00, 0x9FFF)),
    "ko": ((0xAC00, 0xD7AF), (0x1100, 0x11FF)),
    "ar": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "fa": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "ur": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "ug": ((0x0600, 0x06FF), (0x0750, 0x077F)),
    "he": ((0x0590, 0x05FF),),
    "th": ((0x0E00, 0x0E7F),),
    "hi": ((0x0900, 0x097F),),
    "mr": ((0x0900, 0x097F),),
    "bn": ((0x0980, 0x09FF),),
    "ta": ((0x0B80, 0x0BFF),),
    "te": ((0x0C00, 0x0C7F),),
    "gu": ((0x0A80, 0x0AFF),),
    "km": ((0x1780, 0x17FF),),
    "my": ((0x1000, 0x109F),),
    "bo": ((0x0F00, 0x0FFF),),
}

_UKRAINIAN_ALPHABET = frozenset(
    "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"
    "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
)
_RUSSIAN_ALPHABET = frozenset(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
)

_INSTRUCTION_MARKERS = (
    "preserve markdown syntax",
    "translate only the human-readable text",
    "translation style must strictly conform",
    "output only the translated heading",
    "output only the translated text",
    "here is the translation",
    "here's the translation",
    "the translation is",
    "ось переклад",
    "звісно, ось",
    "переклад тексту",
    "вот перевод",
    "перевод текста",
)

_FIRST_PERSON_SOURCE = (
    " i ",
    "i'",
    " me ",
    " my ",
    " we ",
    "we'",
    " us ",
    " our ",
    " я ",
    " мене ",
    " мені ",
    " мій ",
    " моя ",
    " ми ",
    " нас ",
    " наш ",
    " меня ",
    " мне ",
    " мой ",
    " мы ",
)

_META_MARKERS = (
    "я рекомендую",
    "я реком",
    "я можу допомогти",
    "я не можу",
    "якщо вам потрібно",
    "сподіваюся",
    "надіюся",
    "i recommend",
    "i can help",
    "i cannot",
    "let me know",
)


def _target_code(target: Language | str) -> str:
    """Language code for ``target``; strings are accepted for test convenience."""
    if isinstance(target, str):
        return target
    return str(getattr(target, "code", "") or "")


def _is_cjk_code(code: str) -> bool:
    return code.lower() in _CJK_TARGET_CODES


def _has_ranges(text: str, ranges: tuple[tuple[int, int], ...]) -> bool:
    for character in text:
        value = ord(character)
        for low, high in ranges:
            if low <= value <= high:
                return True
    return False


def _count_repetitions(text: str) -> int:
    """Number of repeated 40-character shingles sampled every 20 characters."""
    characters = list(text)
    shingles: set[str] = set()
    duplicates = 0
    index = 0
    while index + 40 <= len(characters):
        shingle = "".join(characters[index : index + 40])
        if shingle in shingles:
            duplicates += 1
        shingles.add(shingle)
        index += 20
    return duplicates


class OutputSanitizer:
    """Removes leaked template tokens and rejects degenerate model output."""

    @staticmethod
    def strip_wrappers(text: str) -> str:
        """Remove chat-template / special-token wrappers and surrounding space.

        Byte-for-byte port of ``OutputSanitizer.clean``.  It removes known
        Hy-MT leaks (``<｜hy_place▁holder▁no▁2｜>``, ``｜hy_end``,
        ``hy-Assistant`` ...), generic ``hy_*`` fragments, a dangling partial
        token at the end of the stream, U+FFFD and NUL characters.

        "Here is the translation:" preambles are handled separately by
        :meth:`strip_preamble`, mirroring ``TranslationService.stripPreamble``.
        """
        value = text
        for token in _KNOWN_LEAKS:
            value = value.replace(token, "")
        value = _RE_HY_TOKEN.sub("", value)
        value = _RE_HY_TAIL.sub("", value)
        value = _RE_OPEN_ANGLE.sub("", value)
        value = _RE_OPEN_CLOSE.sub("", value)
        value = _RE_TRAILING_HY.sub("", value)
        value = _RE_TRAILING_BRACKET.sub("", value)
        value = value.replace("\ufffd", "").replace("\x00", "")
        return value.strip()

    @staticmethod
    def clean(text: str) -> str:
        """Swift-compatible alias of :meth:`strip_wrappers`."""
        return OutputSanitizer.strip_wrappers(text)

    @staticmethod
    def strip_preamble(text: str, source: str = "") -> str:
        """Remove "Here is the translation:" / "Ось переклад тексту:" wrappers.

        Port of ``TranslationService.stripPreamble``.  A preamble that is also
        present in ``source`` is left alone, and the closing quote of a quoted
        translation is removed together with the opening one.
        """
        value = text.strip()
        source_lower = source.lower()
        removed_preamble = False
        for pattern in (_PREAMBLE_COLON, _PREAMBLE_FILLER):
            match = pattern.search(value)
            if match is None:
                continue
            matched = match.group(0)
            if matched.lower() in source_lower:
                continue
            value = (value[: match.start()] + value[match.end() :]).strip()
            removed_preamble = True

        if removed_preamble and value and value[0] in _OPEN_QUOTES:
            value = value[1:]
            for position, character in enumerate(value):
                if character in _CLOSE_QUOTES:
                    value = value[:position] + value[position + 1 :]
                    break
            value = value.strip()
        return value

    @staticmethod
    def has_role_tokens(text: str) -> bool:
        """True when chat-template role or special tokens are still present."""
        lower = text.lower()
        if "hy-assistant" in lower or "hy-user" in lower or "hy_end" in lower:
            return True
        return (
            "<｜" in text
            or "<|" in text
            or "</|" in text
            or "｜hy" in text
        )

    @staticmethod
    def uses_cjk_script(code: str) -> bool:
        """True for targets written with CJK ideographs (Japanese included)."""
        return code.lower() in _CJK_TARGET_CODES

    @staticmethod
    def script_ok(text: str, target: Language | str) -> bool:
        """True when ``text`` contains at least one character of the target script.

        Port of ``TranslationService.hasTargetScript``: a text without any
        letters passes (there is nothing to translate), otherwise it must
        contain a character from the script expected for the target code.
        """
        if not any(character.isalpha() for character in text):
            return True
        code = _target_code(target)
        ranges = _SCRIPT_RANGES.get(code.lower(), _LATIN_RANGES)
        return _has_ranges(text, ranges)

    @staticmethod
    def uses_allowed_cyrillic(text: str, target: Language | str) -> bool:
        """True when every Cyrillic character belongs to the target alphabet.

        Ukrainian and Russian have well-defined alphabets; Belarusian or
        Serbian letters inside a Ukrainian word indicate degeneration.
        """
        code = _target_code(target)
        if code == "uk":
            alphabet = _UKRAINIAN_ALPHABET
        elif code == "ru":
            alphabet = _RUSSIAN_ALPHABET
        else:
            return True
        for character in text:
            if 0x0400 <= ord(character) <= 0x04FF and character not in alphabet:
                return False
        return True

    @staticmethod
    def is_degenerate(
        source: str,
        translated: str,
        target: Language | str,
    ) -> tuple[bool, str]:
        """Validate one translated block.

        Returns ``(False, "")`` for acceptable output, otherwise
        ``(True, reason)`` with ``reason`` one of ``"empty"``, ``"repetition"``,
        ``"script"``, ``"role_tokens"``, ``"echo"`` or ``"length"``.

        The checks and their order follow ``TranslationService.validated``:
        replacement characters, empty output, short output, target script,
        role tokens, instruction echo, first-person meta answers, foreign
        script contamination, excessive length and internal repetition.
        Wrapper tokens are stripped before the textual checks, exactly like
        Swift's ``OutputSanitizer.clean`` call inside ``validated``.

        Call :meth:`strip_preamble` on the raw model output first (as Swift's
        ``bufferedTranslation`` does): this method deliberately reports a
        remaining "Here is the translation:" preamble as an ``"echo"`` failure.
        """
        original = translated or ""
        if "\ufffd" in original:
            return True, "repetition"

        cleaned = OutputSanitizer.strip_wrappers(original)
        if not cleaned:
            return True, "empty"

        source = source or ""
        code = _target_code(target)
        source_count = len(source)
        cleaned_count = len(cleaned)

        if source_count >= 60 and cleaned_count < source_count // 4:
            return True, "length"
        if (
            source_count >= 60
            and cleaned_count < source_count // 2
            and not _is_cjk_code(code)
            and len(TextChunker.split_sentences(source)) > 1
            and len(TextChunker.split_sentences(cleaned)) == 1
        ):
            return True, "length"

        if not OutputSanitizer.script_ok(cleaned, target):
            return True, "script"
        if OutputSanitizer.has_role_tokens(cleaned):
            return True, "role_tokens"

        lower = cleaned.lower()
        source_lower = source.lower()
        for marker in _INSTRUCTION_MARKERS:
            if marker in lower and marker not in source_lower:
                return True, "echo"

        padded_source = " " + source_lower + " "
        if not any(marker in padded_source for marker in _FIRST_PERSON_SOURCE):
            if any(marker in lower for marker in _META_MARKERS):
                return True, "echo"

        if not _is_cjk_code(code) and _has_ranges(cleaned, _CJK_RANGES):
            return True, "script"
        if code not in _CYRILLIC_TARGETS:
            if _has_ranges(cleaned, _CYRILLIC_RANGES):
                return True, "script"
        elif code in ("uk", "ru") and not OutputSanitizer.uses_allowed_cyrillic(
            cleaned, code
        ):
            return True, "script"

        if source_count >= 40 and cleaned_count > source_count * 4:
            return True, "length"
        if source_count < 40 and cleaned_count > max(120, source_count * 8):
            return True, "length"

        if cleaned_count > 120 and _count_repetitions(cleaned) > 1:
            return True, "repetition"

        return False, ""
