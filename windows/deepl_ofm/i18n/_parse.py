"""Generator for :mod:`deepl_ofm.i18n.catalog`.

Ported counterpart: ``Sources/HyMT/Support/Localization.swift`` (the eight
``[String: String]`` tables inside the ``L10n`` enum).  This module parses the
Swift source mechanically and renders ``catalog.py``; it never runs at import
time, so importing :mod:`deepl_ofm.i18n` has no filesystem side effects.

Regenerate the catalogue from the repository root::

    windows/.venv/bin/python -m deepl_ofm.i18n._parse

The Swift file is located relative to this checkout by default; pass a path or
set ``DEEPL_OFM_SWIFT_SOURCE`` to override it.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

#: Swift variable name -> ISO-639-1 code used by :class:`AppLanguage`.
SWIFT_TABLES: tuple[tuple[str, str, str], ...] = (
    ("ukrainian", "uk", "UKRAINIAN"),
    ("russian", "ru", "RUSSIAN"),
    ("german", "de", "GERMAN"),
    ("french", "fr", "FRENCH"),
    ("spanish", "es", "SPANISH"),
    ("polish", "pl", "POLISH"),
    ("portuguese", "pt", "PORTUGUESE"),
    ("italian", "it", "ITALIAN"),
)

#: Path of the Swift source relative to the repository root (``windows/`` parent).
SWIFT_RELATIVE_PATH = Path("Sources") / "HyMT" / "Support" / "Localization.swift"

_MAX_LINE = 100
_INDENT = "    "

_ENV_SOURCE = "DEEPL_OFM_SWIFT_SOURCE"

_TABLE_START = re.compile(
    r"^\s*(?:private\s+)?static\s+let\s+(\w+)\s*:\s*\[\s*String\s*:\s*String\s*\]\s*=\s*\[",
    re.MULTILINE,
)

_SIMPLE_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "0": "\0",
    '"': '"',
    "\\": "\\",
    "'": "'",
}


class SwiftParseError(ValueError):
    """Raised when the Swift source does not match the expected table layout."""


def repo_root() -> Path:
    """Return the repository root (the directory that contains ``windows/``)."""
    # windows/deepl_ofm/i18n/_parse.py -> windows/deepl_ofm/i18n -> ... -> repo
    return Path(__file__).resolve().parents[3]


def find_swift_source(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Locate ``Localization.swift``; raise :class:`FileNotFoundError` if absent."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get(_ENV_SOURCE)
    if env:
        candidates.append(Path(env))
    candidates.append(repo_root() / SWIFT_RELATIVE_PATH)
    candidates.append(Path.cwd() / SWIFT_RELATIVE_PATH)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    searched = "\n  ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Localization.swift not found; looked in:\n  {searched}")


def _read_swift_string(source: str, index: int) -> tuple[str, int]:
    """Read one Swift string literal starting at ``index``; return (value, end)."""
    if source[index] != '"':
        raise SwiftParseError(f"expected a string literal at offset {index}")
    index += 1
    out: list[str] = []
    while index < len(source):
        char = source[index]
        if char == '"':
            return "".join(out), index + 1
        if char != "\\":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(source):
            break
        escape = source[index]
        if escape == "u":
            if index + 1 >= len(source) or source[index + 1] != "{":
                raise SwiftParseError(f"malformed unicode escape at offset {index}")
            closing = source.find("}", index + 2)
            if closing < 0:
                raise SwiftParseError(f"unterminated unicode escape at offset {index}")
            codepoint = source[index + 2 : closing]
            try:
                out.append(chr(int(codepoint, 16)))
            except ValueError as exc:
                raise SwiftParseError(f"bad unicode escape \\u{{{codepoint}}}") from exc
            index = closing + 1
        elif escape in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[escape])
            index += 1
        else:
            raise SwiftParseError(f"unsupported escape \\{escape} at offset {index}")
    raise SwiftParseError("unterminated string literal")


def _skip_trivia(source: str, index: int) -> int:
    """Skip whitespace and ``//`` / ``/* */`` comments."""
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
        elif source.startswith("//", index):
            newline = source.find("\n", index)
            index = len(source) if newline < 0 else newline + 1
        elif source.startswith("/*", index):
            closing = source.find("*/", index + 2)
            if closing < 0:
                raise SwiftParseError("unterminated block comment")
            index = closing + 2
        else:
            break
    return index


def _parse_table(source: str, index: int) -> dict[str, str]:
    """Parse a ``[String: String]`` literal body; ``index`` points after ``[``."""
    table: dict[str, str] = {}
    while True:
        index = _skip_trivia(source, index)
        if index >= len(source):
            raise SwiftParseError("unterminated dictionary literal")
        if source[index] == "]":
            return table
        key, index = _read_swift_string(source, index)
        index = _skip_trivia(source, index)
        if index >= len(source) or source[index] != ":":
            raise SwiftParseError(f"expected ':' after key {key!r}")
        index = _skip_trivia(source, index + 1)
        value, index = _read_swift_string(source, index)
        if key in table:
            raise SwiftParseError(f"duplicate key {key!r} in one table")
        table[key] = value
        index = _skip_trivia(source, index)
        if index < len(source) and source[index] == ",":
            index += 1


def parse_swift_source(source: str) -> dict[str, dict[str, str]]:
    """Return ``{language_code: {english_key: translation}}`` for all tables."""
    starts = {match.group(1): match.end() for match in _TABLE_START.finditer(source)}
    missing = [swift for swift, _code, _const in SWIFT_TABLES if swift not in starts]
    if missing:
        raise SwiftParseError(f"tables not found in Swift source: {', '.join(missing)}")
    tables: dict[str, dict[str, str]] = {}
    for swift_name, code, _constant in SWIFT_TABLES:
        table = _parse_table(source, starts[swift_name])
        if not table:
            raise SwiftParseError(f"table {swift_name!r} is empty")
        tables[code] = table
    return tables


# ---------------------------------------------------------------------------
# Code rendering
# ---------------------------------------------------------------------------


def _chunk_literal(text: str, max_repr: int) -> list[str]:
    """Split ``text`` into pieces whose ``repr`` fits into ``max_repr`` chars."""
    if len(repr(text)) <= max_repr:
        return [text]
    pieces: list[str] = []
    rest = text
    while rest:
        if len(repr(rest)) <= max_repr:
            pieces.append(rest)
            break
        cut = min(len(rest), max(1, max_repr - 2))
        while cut > 1 and len(repr(rest[:cut])) > max_repr:
            cut -= 1
        while cut < len(rest) and len(repr(rest[: cut + 1])) <= max_repr:
            cut += 1
        # Prefer a word boundary in the last part of the allowed span.
        floor = max(1, cut // 2)
        space = max(rest.rfind(" ", floor, cut), rest.rfind("\n", floor, cut))
        if space > 0:
            cut = space + 1
        pieces.append(rest[:cut])
        rest = rest[cut:]
    return pieces


def _render_entry(key: str, value: str, width: int = _MAX_LINE) -> list[str]:
    """Render one ``key: value`` dict entry, keeping lines within ``width``."""
    key_literal = repr(key)
    value_literal = repr(value)
    one_line = f"{_INDENT}{key_literal}: {value_literal},"
    if len(one_line) <= width:
        return [one_line]

    inner = _INDENT + "    "
    inner_budget = width - len(inner) - 1
    if len(f"{_INDENT}{key_literal}: (") <= width:
        lines = [f"{_INDENT}{key_literal}: ("]
        lines.extend(f"{inner}{repr(piece)}" for piece in _chunk_literal(value, inner_budget))
        lines.append(f"{_INDENT}),")
        return lines

    lines = [f"{_INDENT}("]
    lines.extend(
        f"{inner}{repr(piece)}" for piece in _chunk_literal(key, inner_budget)
    )
    lines.append(f"{_INDENT}): (")
    lines.extend(f"{inner}{repr(piece)}" for piece in _chunk_literal(value, inner_budget))
    lines.append(f"{_INDENT}),")
    return lines


def _check_tables(tables: dict[str, dict[str, str]]) -> list[str]:
    """Validate coverage/placeholders; return human-readable report lines."""
    report: list[str] = []
    english = set().union(*(set(table) for table in tables.values()))
    placeholder = re.compile(r"%(?:%|(?:\d+\$)?(?:hh|h|ll|l)?[@dsifgxXoOuc]|\.\d+[fFgGeE])")
    for code, table in tables.items():
        coverage = len(set(table) & english) / len(english) * 100 if english else 0.0
        report.append(f"{code}: {len(table)} keys, {coverage:.1f}% of {len(english)} English keys")
        if coverage < 90.0:
            raise SwiftParseError(f"{code} covers only {coverage:.1f}% of the English keys")
        for key, value in table.items():
            if not key or not value:
                raise SwiftParseError(f"{code}: empty key or value for {key!r}")
            if sorted(placeholder.findall(key)) != sorted(placeholder.findall(value)):
                raise SwiftParseError(
                    f"{code}: placeholder mismatch for {key!r}: {key!r} -> {value!r}"
                )
    report.append(f"total English keys: {len(english)}")
    return report


def render_catalog(tables: dict[str, dict[str, str]]) -> str:
    """Render the full ``catalog.py`` source for ``tables``."""
    english = set().union(*(set(table) for table in tables.values()))
    counts = ", ".join(f"{code}={len(tables[code])}" for _s, code, _c in SWIFT_TABLES)
    title = "Generated interface catalogue ported from Sources/HyMT/Support/Localization.swift."
    header = f'''"""{title}

Do not edit by hand: run ``python -m deepl_ofm.i18n._parse`` to regenerate.

Layout
------
English is the identity mapping (an English key is its own translation) and is
therefore not stored.  The eight translated tables are module-level dicts named
``UKRAINIAN``, ``RUSSIAN``, ``GERMAN``, ``FRENCH``, ``SPANISH``, ``POLISH``,
``PORTUGUESE`` and ``ITALIAN``; every one maps an English source string to the
translation used for that language.

``BY_LANGUAGE`` (aliased as ``TRANSLATIONS``) maps an ISO-639-1 code to its
table so callers can select one at runtime.  There is deliberately no ``"en"``
entry: :func:`deepl_ofm.i18n.t` falls back to the key for English.

{len(english)} English keys; per language: {counts}.
"""'''
    lines: list[str] = [header, "", "from __future__ import annotations", ""]
    for _swift, code, constant in SWIFT_TABLES:
        lines.append(f"{constant}: dict[str, str] = {{")
        for key, value in tables[code].items():
            lines.extend(_render_entry(key, value))
        lines.append("}")
        lines.append("")
    lines.append("BY_LANGUAGE: dict[str, dict[str, str]] = {")
    for _swift, code, constant in SWIFT_TABLES:
        lines.append(f'    "{code}": {constant},')
    lines.append("}")
    lines.append("")
    lines.append("#: Alias kept for callers that think of the catalogue as one mapping.")
    lines.append("TRANSLATIONS = BY_LANGUAGE")
    lines.append("")
    return "\n".join(lines)


def generate(source_path: str | os.PathLike[str] | None = None) -> str:
    """Parse the Swift file and return the ``catalog.py`` source text."""
    path = find_swift_source(source_path)
    tables = parse_swift_source(path.read_text(encoding="utf-8"))
    for line in _check_tables(tables):
        logger.info("%s", line)
    return render_catalog(tables)


def write_catalog(
    destination: str | os.PathLike[str] | None = None,
    source_path: str | os.PathLike[str] | None = None,
) -> Path:
    """Generate ``catalog.py`` and return the written path."""
    destination_path = Path(destination) if destination else Path(__file__).with_name("catalog.py")
    text = generate(source_path)
    for number, line in enumerate(text.splitlines(), start=1):
        if len(line) > _MAX_LINE:
            raise SwiftParseError(f"generated line {number} exceeds {_MAX_LINE} chars")
    destination_path.write_text(text, encoding="utf-8", newline="\n")
    return destination_path


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point used to regenerate the catalogue."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", help="path to Localization.swift")
    parser.add_argument("--output", help="path to write catalog.py")
    parser.add_argument("--check", action="store_true", help="verify without writing")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.check:
            text = generate(args.source)
            if args.output:
                destination = Path(args.output)
            else:
                destination = Path(__file__).with_name("catalog.py")
            current = destination.read_text(encoding="utf-8") if destination.is_file() else ""
            if current != text:
                print(f"{destination} is out of date; regenerate it")
                return 1
            print(f"{destination} is up to date")
            return 0
        destination = write_catalog(args.output, args.source)
    except (FileNotFoundError, SwiftParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
