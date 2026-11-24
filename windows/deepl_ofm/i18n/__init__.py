"""Interface localisation for the Windows port.

Ported counterpart: ``Sources/HyMT/Support/Localization.swift``.  The macOS app
keeps nine ``[String: String]`` dictionaries in ``L10n`` and looks strings up by
their English source text; this module reproduces that behaviour on top of the
generated :mod:`deepl_ofm.i18n.catalog` (see ``python -m deepl_ofm.i18n._parse``).

The English source string *is* the key, so :func:`t` returns the key unchanged
when a translation is missing.  The module is deliberately framework-free (no
PySide6 import) so core modules and tests can use it without a Qt application.

Swift ``printf`` placeholders (``%@``, ``%d``, ``%s`` ...) in the catalogue are
exposed through :func:`tf`, which converts them to Python ``{}`` fields and
formats defensively: it never raises, even for the wrong number of arguments.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.i18n import catalog
from deepl_ofm.i18n.extra import EXTRA

__all__ = [
    "AppLanguage",
    "available_languages",
    "current_language",
    "install_translator",
    "set_language",
    "t",
    "tf",
]

logger = logging.getLogger(__name__)

#: Language used until :func:`set_language` is called, and the identity mapping.
DEFAULT_LANGUAGE = AppLanguage.EN

#: Matches the ``printf`` placeholders used by the Swift catalogue.  ``%%`` is a
#: literal percent sign; the remaining alternatives cover the formats that occur
#: in ``Localization.swift`` (``%@``, ``%d``, ``%s``, ``%.1f`` ...) plus the
#: common length modifiers, so a future table entry cannot silently break ``tf``.
_PLACEHOLDER = re.compile(
    r"%(?:"
    r"%"
    r"|(?:\d+\$)?(?:hh|h|ll|l)?(?:@|d|i|u|s|f|F|g|G|e|E|x|X|o|c|p|a|A)"
    r"|\.\d+(?:f|F|g|G|e|E)"
    r")"
)

#: Sentinel protecting ``%%`` from the brace conversion step.
_LITERAL_PERCENT = "\x00i18n-percent\x00"

_current_language: AppLanguage = DEFAULT_LANGUAGE


def _coerce(language: AppLanguage | str | None) -> AppLanguage:
    """Return a member of :class:`AppLanguage` for arbitrary user input."""
    if isinstance(language, AppLanguage):
        return language
    if language is None:
        return AppLanguage.SYSTEM
    text = str(language).strip().lower().replace("-", "_")
    if text:
        code = text.split("_")[0]
        if code == "ua":  # legacy code used by older builds
            code = "uk"
        try:
            return AppLanguage(code)
        except ValueError:
            logger.warning("unknown interface language %r; falling back to English", language)
    return AppLanguage.EN


def _resolve(language: AppLanguage | str | None) -> AppLanguage:
    """Resolve ``system`` (and ``None``) to a concrete catalogue language."""
    member = _coerce(language)
    if member is AppLanguage.SYSTEM:
        member = AppLanguage.system_resolved()
        if member is AppLanguage.SYSTEM:  # defensive: a broken detection
            return AppLanguage.EN
    return member


def _table(language: AppLanguage | str | None) -> dict[str, str] | None:
    """Return the translation table in effect for ``language`` (None = English)."""
    if language is None:
        language = _current_language
    resolved = _resolve(language)
    return catalog.BY_LANGUAGE.get(resolved.value)


def t(key: str, language: AppLanguage | str | None = None) -> str:
    """Translate *key* to *language* (the current language when omitted).

    The English source string is the key.  Unknown keys, English and any value
    the catalogue does not know are returned unchanged, mirroring the Swift
    ``ukrainian[key] ?? key`` fallback.
    """
    if not key:
        return key
    resolved = _resolve(language if language is not None else _current_language)
    table = catalog.BY_LANGUAGE.get(resolved.value)
    if table is not None:
        translation = table.get(key)
        if translation:
            return translation
    # Windows-only strings (menu bar, tray, file saving) live in a small extra
    # table: the generated catalogue only knows the macOS interface.
    extra = EXTRA.get(resolved.value)
    if extra is not None:
        translation = extra.get(key)
        if translation:
            return translation
    return key


def _brace_template(template: str) -> str:
    """Convert Swift ``printf`` placeholders in *template* to Python ``{}`` fields."""
    pieces: list[str] = []
    position = 0
    for match in _PLACEHOLDER.finditer(template):
        pieces.append(template[position : match.start()])
        pieces.append(_LITERAL_PERCENT if match.group(0) == "%%" else "{}")
        position = match.end()
    pieces.append(template[position:])
    converted = "".join(pieces)
    return converted.replace(_LITERAL_PERCENT, "%")


def _sequential_format(template: str, args: Sequence[object]) -> str:
    """Substitute ``{}`` fields left to right, tolerating too few arguments."""
    pieces: list[str] = []
    position = 0
    index = 0
    while True:
        found = template.find("{}", position)
        if found < 0:
            pieces.append(template[position:])
            break
        pieces.append(template[position:found])
        pieces.append(str(args[index]) if index < len(args) else "{}")
        index += 1
        position = found + 2
    return "".join(pieces)


def tf(key: str, *args: object, language: AppLanguage | str | None = None) -> str:
    """Translate *key* and interpolate *args* into its ``printf`` placeholders.

    Swift spells placeholders as ``%@``/``%d``/``%s``; they become Python ``{}``
    fields and are filled in order.  Invalid templates or a wrong argument count
    fall back to literal substitution instead of raising, because UI code must
    never crash on a stray translation string.
    """
    template = t(key, language)
    if not args:
        return template
    brace = _brace_template(template)
    try:
        return brace.format(*args)
    except (IndexError, KeyError, ValueError):
        return _sequential_format(brace, args)


def set_language(language: AppLanguage | str | None) -> None:
    """Switch the global interface language (``system`` is resolved immediately)."""
    global _current_language
    _current_language = _resolve(language)


def install_translator(app_language: AppLanguage | str | None) -> None:
    """Alias of :func:`set_language`, kept for the documented contract."""
    set_language(app_language)


def current_language() -> AppLanguage:
    """Return the concrete language used by :func:`t` (never ``system``)."""
    return _current_language


def available_languages() -> list[AppLanguage]:
    """Return English plus every language with a generated translation table."""
    languages = [
        member
        for member in AppLanguage
        if member is not AppLanguage.SYSTEM
        and (member is AppLanguage.EN or member.value in catalog.BY_LANGUAGE)
    ]
    return languages
