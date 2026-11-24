#!/usr/bin/env python3
"""Generate the Rust data modules of the ``ofm-i18n`` crate.

The port keeps every user-visible string and every word list as generated Rust
data so that no translation is ever retyped by hand.  Three read-only sources
in the repository are parsed mechanically:

* ``Sources/HyMT/Support/Localization.swift`` -- the eight ``[String: String]``
  dictionaries of the macOS app (302 English keys each), the authority for the
  wording of the interface.
* ``windows/deepl_ofm/i18n/extra.py`` -- the Windows-only strings (menu bar,
  tray, file saving, dates) that the macOS catalogue does not know about.
* ``windows/deepl_ofm/core/languages.py`` -- the 38-language registry, the
  curated localised language names and the stop-word lists used by the script
  detector.  The Python module is the behavioural spec, so its data is extracted
  with :mod:`ast` instead of being copied by hand.

Two files are written:

* ``rust/crates/i18n/src/catalog.rs`` -- the translation tables.
* ``rust/crates/i18n/src/language_data.rs`` -- language metadata, localised
  names, stop words and the Latin folding table that replaces
  ``unicodedata`` in the dependency-free Rust port.

Both are byte-for-byte reproducible and use LF line endings::

    python3 rust/scripts/gen_i18n.py          # regenerate
    python3 rust/scripts/gen_i18n.py --check  # fail if the files are stale

The script only needs the Python standard library.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import re
import sys
import unicodedata
from pathlib import Path

#: Swift variable name, ISO-639-1 code and Rust constant name, in the order of
#: the Swift ``L10n.t`` switch (which is also the ``AppLanguage`` order).
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

#: Language codes in table order; also the order of the generated arrays.
LANGUAGE_CODES: tuple[str, ...] = tuple(code for _swift, code, _const in SWIFT_TABLES)

SWIFT_RELATIVE_PATH = Path("Sources") / "HyMT" / "Support" / "Localization.swift"
EXTRA_RELATIVE_PATH = Path("windows") / "deepl_ofm" / "i18n" / "extra.py"
LANGUAGES_RELATIVE_PATH = Path("windows") / "deepl_ofm" / "core" / "languages.py"
CATALOG_RELATIVE_PATH = Path("rust") / "crates" / "i18n" / "src" / "catalog.rs"
LANGUAGE_DATA_RELATIVE_PATH = (
    Path("rust") / "crates" / "i18n" / "src" / "language_data.rs"
)

#: Maximum source line length used for the generated data files.
MAX_LINE = 100

#: ``printf`` placeholders used by the Swift catalogue (``%@``, ``%d``, ``%.1f``,
#: ``%%`` ...).  Identical to the grammar in ``deepl_ofm/i18n/_parse.py``.
PLACEHOLDER = re.compile(
    r"%(?:"
    r"%"
    r"|(?:\d+\$)?(?:hh|h|ll|l)?(?:@|d|i|u|s|f|F|g|G|e|E|x|X|o|c|p|a|A)"
    r"|\.\d+(?:f|F|g|G|e|E)"
    r")"
)

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

#: ``AppLanguage`` variant for an ISO-639-1 code (only the eight translated ones).
RUST_VARIANTS = {
    "en": "En",
    "uk": "Uk",
    "ru": "Ru",
    "de": "De",
    "fr": "Fr",
    "es": "Es",
    "pl": "Pl",
    "pt": "Pt",
    "it": "It",
}


class GeneratorError(RuntimeError):
    """Raised when a source file does not match the expected layout."""


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------


def repo_root() -> Path:
    """Return the checkout root (the directory that contains ``rust/``)."""
    # rust/scripts/gen_i18n.py -> rust/scripts -> rust -> <root>
    return Path(__file__).resolve().parents[2]


def find_source(relative: Path) -> Path:
    """Locate *relative* below the checkout root."""
    candidate = repo_root() / relative
    if candidate.is_file():
        return candidate
    raise GeneratorError(f"{relative} not found under {repo_root()}")


# ---------------------------------------------------------------------------
# Swift parser (ported from windows/deepl_ofm/i18n/_parse.py)
# ---------------------------------------------------------------------------


def read_swift_string(source: str, index: int) -> tuple[str, int]:
    """Read one Swift string literal starting at *index*; return (value, end)."""
    if source[index] != '"':
        raise GeneratorError(f"expected a string literal at offset {index}")
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
                raise GeneratorError(f"malformed unicode escape at offset {index}")
            closing = source.find("}", index + 2)
            if closing < 0:
                raise GeneratorError(f"unterminated unicode escape at offset {index}")
            codepoint = source[index + 2 : closing]
            try:
                out.append(chr(int(codepoint, 16)))
            except ValueError as exc:
                raise GeneratorError(f"bad unicode escape \\u{{{codepoint}}}") from exc
            index = closing + 1
        elif escape in _SIMPLE_ESCAPES:
            out.append(_SIMPLE_ESCAPES[escape])
            index += 1
        else:
            raise GeneratorError(f"unsupported escape \\{escape} at offset {index}")
    raise GeneratorError("unterminated string literal")


def skip_trivia(source: str, index: int) -> int:
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
                raise GeneratorError("unterminated block comment")
            index = closing + 2
        else:
            break
    return index


def parse_swift_table(source: str, index: int) -> dict[str, str]:
    """Parse a ``[String: String]`` literal body; *index* points after ``[``."""
    table: dict[str, str] = {}
    while True:
        index = skip_trivia(source, index)
        if index >= len(source):
            raise GeneratorError("unterminated dictionary literal")
        if source[index] == "]":
            return table
        key, index = read_swift_string(source, index)
        index = skip_trivia(source, index)
        if index >= len(source) or source[index] != ":":
            raise GeneratorError(f"expected ':' after key {key!r}")
        index = skip_trivia(source, index + 1)
        value, index = read_swift_string(source, index)
        if key in table and table[key] != value:
            raise GeneratorError(f"duplicate key {key!r} in one table")
        table[key] = value
        index = skip_trivia(source, index)
        if index < len(source) and source[index] == ",":
            index += 1


def parse_swift_source(source: str) -> dict[str, dict[str, str]]:
    """Return ``{language_code: {english_key: translation}}`` for all tables."""
    starts = {match.group(1): match.end() for match in _TABLE_START.finditer(source)}
    missing = [swift for swift, _code, _const in SWIFT_TABLES if swift not in starts]
    if missing:
        raise GeneratorError(f"tables not found in Swift source: {', '.join(missing)}")
    tables: dict[str, dict[str, str]] = {}
    for swift_name, code, _constant in SWIFT_TABLES:
        table = parse_swift_table(source, starts[swift_name])
        if not table:
            raise GeneratorError(f"table {swift_name!r} is empty")
        tables[code] = table
    return tables


# ---------------------------------------------------------------------------
# Python data extraction (extra.py and languages.py)
# ---------------------------------------------------------------------------


def load_extra(path: Path) -> dict[str, dict[str, str]]:
    """Execute *path* and return its ``EXTRA`` table.

    ``extra.py`` is pure data assembled with a couple of ``_merge`` helpers; its
    own module docstring says the tables must stay in sync, and importing it is
    more faithful (and less brittle) than re-implementing the merge in the
    generator.
    """
    spec = importlib.util.spec_from_file_location("_ofm_i18n_extra_source", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise GeneratorError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    extra = getattr(module, "EXTRA", None)
    if not isinstance(extra, dict):
        raise GeneratorError(f"{path} does not define an EXTRA dictionary")
    return {str(code): dict(table) for code, table in extra.items()}


def _parse_python(path: Path) -> ast.Module:
    """Parse *path* without importing it."""
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:  # pragma: no cover - defensive
        raise GeneratorError(f"cannot parse {path}: {exc}") from exc


def _assigned_value(tree: ast.Module, name: str) -> ast.expr:
    """Return the value assigned to module-level *name*."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                return node.value
    raise GeneratorError(f"{name} not found in the Python source")


def _class_attribute(tree: ast.Module, class_name: str, name: str) -> ast.expr:
    """Return the value assigned to *class_name*.*name*."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and statement.value is not None:
                target = statement.target
                if isinstance(target, ast.Name) and target.id == name:
                    return statement.value
            elif isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        return statement.value
    raise GeneratorError(f"{class_name}.{name} not found in the Python source")


def _string_literal(node: ast.AST) -> str:
    """Return the first string constant inside *node* (``"..."`` from ``.split()``)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            return sub.value
    raise GeneratorError("no string literal found")


def _call_name(node: ast.expr) -> str:
    """Return the bare name of a call target."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _language_registry(value: ast.expr) -> list[tuple[str, str, str, str | None]]:
    """Extract ``LanguageTable.ALL`` as tuples of (code, english, local, bcp47)."""
    if not isinstance(value, ast.List):
        raise GeneratorError("LanguageTable.ALL is not a list literal")
    entries: list[tuple[str, str, str, str | None]] = []
    for element in value.elts:
        if not isinstance(element, ast.Call) or _call_name(element.func) != "Language":
            raise GeneratorError("LanguageTable.ALL contains a non-Language entry")
        positional = [ast.literal_eval(argument) for argument in element.args]
        keywords = {keyword.arg: ast.literal_eval(keyword.value) for keyword in element.keywords}
        code = keywords.pop("code", positional[0] if positional else None)
        english = keywords.pop("english_name", positional[1] if len(positional) > 1 else None)
        local = keywords.pop("local_name", positional[2] if len(positional) > 2 else None)
        bcp47 = keywords.pop("bcp47", positional[3] if len(positional) > 3 else None)
        if keywords:
            raise GeneratorError(f"unexpected Language keywords: {sorted(keywords)}")
        if not all(isinstance(item, str) for item in (code, english, local)):
            raise GeneratorError(f"bad Language entry: {ast.dump(element)}")
        if bcp47 is not None and not isinstance(bcp47, str):
            raise GeneratorError(f"bad bcp47 for {code!r}")
        entries.append((code, english, local, bcp47))
    return entries


def read_language_source(path: Path) -> dict[str, object]:
    """Extract the metadata the Rust port needs from ``core/languages.py``."""
    tree = _parse_python(path)
    registry = _language_registry(_class_attribute(tree, "LanguageTable", "ALL"))
    names = ast.literal_eval(_assigned_value(tree, "_LOCALIZED_NAMES"))
    order = ast.literal_eval(_assigned_value(tree, "_LATIN_ORDER"))
    stops = ast.literal_eval(_assigned_value(tree, "_LATIN_STOPS"))
    ukrainian = _string_literal(_assigned_value(tree, "_UKRAINIAN_WORDS")).split()
    russian = _string_literal(_assigned_value(tree, "_RUSSIAN_WORDS")).split()
    if not isinstance(names, dict) or not isinstance(stops, dict):
        raise GeneratorError("unexpected shape for _LOCALIZED_NAMES / _LATIN_STOPS")
    if not isinstance(order, tuple) or not isinstance(stops, dict):
        raise GeneratorError("unexpected shape for _LATIN_ORDER")
    return {
        "registry": registry,
        "names": names,
        "order": [str(code) for code in order],
        "stops": {str(code): str(words) for code, words in stops.items()},
        "ukrainian": [str(word) for word in ukrainian],
        "russian": [str(word) for word in russian],
    }


# ---------------------------------------------------------------------------
# Matching helpers shared by the Python reference and the Rust port
# ---------------------------------------------------------------------------


def fold(value: str) -> str:
    """Lower-case and strip diacritics, exactly like ``_fold`` in the Python port."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def fold_pairs() -> list[tuple[str, str]]:
    """Return the single-character Latin foldings the Rust detector needs.

    ``_WORD_RE``/``str.lower`` remove the need for upper-case entries: the Rust
    port lower-cases while splitting words, so only lower-case letters can reach
    the folding table.  Multi-character foldings (``ß`` -> ``ss``, ligatures)
    cannot occur inside the stop-word lists and are therefore omitted.
    """
    pairs: list[tuple[str, str]] = []
    candidates = list(range(0x00A0, 0x0250)) + list(range(0x1E00, 0x1F00))
    for codepoint in candidates:
        char = chr(codepoint)
        if not char.isalpha() or not char.islower():
            continue
        folded = fold(char)
        if len(folded) == 1 and folded != char:
            pairs.append((char, folded))
    pairs.sort()
    return pairs


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _placeholders(text: str) -> list[str]:
    """Return the ``printf`` placeholders of *text*, in order."""
    return PLACEHOLDER.findall(text)


def check_catalog(tables: dict[str, dict[str, str]], extra: dict[str, dict[str, str]]) -> None:
    """Validate coverage, emptiness and placeholder parity; raise on any problem."""
    if set(tables) != set(LANGUAGE_CODES):
        raise GeneratorError(f"Swift tables cover {sorted(tables)}, expected {sorted(LANGUAGE_CODES)}")
    reference = set(tables[LANGUAGE_CODES[0]])
    if not reference:
        raise GeneratorError("the Swift catalogue is empty")
    for code in LANGUAGE_CODES:
        table = tables[code]
        if set(table) != reference:
            missing = sorted(reference - set(table))[:5]
            raise GeneratorError(f"Swift table {code!r} does not match the key set ({missing} ...)")
        _check_entries(f"Swift {code}", table)
    if set(extra) != set(LANGUAGE_CODES):
        raise GeneratorError(f"extra.py covers {sorted(extra)}, expected {sorted(LANGUAGE_CODES)}")
    extra_reference = set(extra[LANGUAGE_CODES[0]])
    for code in LANGUAGE_CODES:
        if set(extra[code]) != extra_reference:
            raise GeneratorError(f"extra table {code!r} does not match the key set")
        _check_entries(f"extra {code}", extra[code])
        conflicts = [
            key
            for key in set(extra[code]) & set(tables[code])
            if extra[code][key] != tables[code][key]
        ]
        if conflicts:
            raise GeneratorError(
                f"{code}: extra.py conflicts with the Swift catalogue for {conflicts[:3]}"
            )


def _check_entries(label: str, table: dict[str, str]) -> None:
    """Check one table for blank entries and placeholder mismatches."""
    for key, value in table.items():
        if not key.strip() or not value.strip():
            raise GeneratorError(f"{label}: blank key or value for {key!r}")
        if _placeholders(key) != _placeholders(value):
            raise GeneratorError(
                f"{label}: placeholder mismatch for {key!r} -> {value!r}"
            )


# ---------------------------------------------------------------------------
# Rust rendering
# ---------------------------------------------------------------------------


def rust_string(text: str) -> str:
    """Render *text* as a Rust string literal."""
    out: list[str] = ['"']
    for char in text:
        codepoint = ord(char)
        if char == '"':
            out.append('\\"')
        elif char == "\\":
            out.append("\\\\")
        elif char == "\n":
            out.append("\\n")
        elif char == "\r":
            out.append("\\r")
        elif char == "\t":
            out.append("\\t")
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
            out.append(f"\\u{{{codepoint:x}}}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def rust_char(char: str) -> str:
    """Render *char* as a Rust character literal."""
    if len(char) != 1:
        raise GeneratorError(f"expected one character, got {char!r}")
    if char == "'":
        return "'\\''"
    if char == "\\":
        return "'\\\\'"
    codepoint = ord(char)
    if char == "\n":
        return "'\\n'"
    if char == "\t":
        return "'\\t'"
    if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
        return f"'\\u{{{codepoint:x}}}'"
    return f"'{char}'"


def _wrapped_rust_strings(items: list[str], indent: str) -> list[str]:
    """Render *items* as comma-separated Rust literals wrapped to ``MAX_LINE``."""
    lines: list[str] = []
    current = indent
    for item in items:
        piece = rust_string(item) + ", "
        if current != indent and len(current) + len(piece) > MAX_LINE:
            lines.append(current.rstrip())
            current = indent
        current += piece
    if current != indent:
        lines.append(current.rstrip())
    return lines


def render_table(constant: str, doc: str, table: dict[str, str]) -> list[str]:
    """Render one ``&[(&str, &str)]`` table, sorted by English key."""
    lines = [f"/// {doc}", "#[rustfmt::skip]"]
    lines.append(f"pub(crate) static {constant}: &[(&str, &str)] = &[")
    for key, value in sorted(table.items()):
        lines.append(f"    ({rust_string(key)}, {rust_string(value)}),")
    lines.append("];")
    return lines


def render_catalog(
    tables: dict[str, dict[str, str]], extra: dict[str, dict[str, str]]
) -> str:
    """Render ``catalog.rs`` for the parsed tables."""
    keys = len(set().union(*(set(table) for table in tables.values())))
    extra_keys = len(set().union(*(set(table) for table in extra.values())))
    codes = ", ".join(LANGUAGE_CODES)
    lines: list[str] = [
        "//! Interface translation tables for the nine interface languages.",
        "//!",
        "//! **Generated file -- do not edit.**  Regenerate it with",
        "//! `python3 rust/scripts/gen_i18n.py` from the checkout root.",
        "//!",
        "//! The English source string *is* the key, so a missing translation falls",
        "//! back to the key itself; English therefore has no table at all.",
        "//!",
        "//! * [`TABLES`] holds the macOS catalogue from",
        f"//!   `Sources/HyMT/Support/Localization.swift` ({keys} keys per language).",
        "//! * [`EXTRA_TABLES`] holds the Windows-only strings from",
        f"//!   `windows/deepl_ofm/i18n/extra.py` ({extra_keys} keys per language).",
        "//!",
        f"//! Both arrays are indexed in this order: {codes}.",
        "//! Every table is sorted by its English key, which keeps this file stable",
        "//! regardless of the declaration order in the sources.",
        "",
    ]
    for _swift, code, constant in SWIFT_TABLES:
        language = code
        lines.extend(
            render_table(
                constant,
                f"Translations for `{language}`, sorted by English key.",
                tables[code],
            )
        )
        lines.append("")
    for _swift, code, constant in SWIFT_TABLES:
        language = code
        lines.extend(
            render_table(
                f"EXTRA_{constant}",
                f"Windows-only strings for `{language}`, sorted by English key.",
                extra[code],
            )
        )
        lines.append("")
    lines.append("/// Catalogue tables from `Localization.swift`, indexed by language.")
    lines.append("#[rustfmt::skip]")
    lines.append("pub(crate) static TABLES: [&[(&str, &str)]; 8] = [")
    for _swift, _code, constant in SWIFT_TABLES:
        lines.append(f"    {constant},")
    lines.append("];")
    lines.append("")
    lines.append("/// Windows-only tables from `extra.py`, indexed like [`TABLES`].")
    lines.append("#[rustfmt::skip]")
    lines.append("pub(crate) static EXTRA_TABLES: [&[(&str, &str)]; 8] = [")
    for _swift, _code, constant in SWIFT_TABLES:
        lines.append(f"    EXTRA_{constant},")
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


def render_language_data(data: dict[str, object], pairs: list[tuple[str, str]]) -> str:
    """Render ``language_data.rs`` for the extracted Python metadata."""
    registry = data["registry"]
    names = data["names"]
    order = data["order"]
    stops = data["stops"]
    ukrainian = data["ukrainian"]
    russian = data["russian"]
    assert isinstance(registry, list) and isinstance(names, dict)
    assert isinstance(order, list) and isinstance(stops, dict)
    assert isinstance(ukrainian, list) and isinstance(russian, list)

    columns = list(next(iter(names.values())).keys()) if names else []
    for code, entry in names.items():
        if list(entry) != columns:
            raise GeneratorError(f"_LOCALIZED_NAMES[{code!r}] uses a different column order")
    unknown_columns = [column for column in columns if column not in RUST_VARIANTS]
    if unknown_columns:
        raise GeneratorError(f"unsupported name columns: {unknown_columns}")

    lines: list[str] = [
        "//! Language metadata, localised display names and stop words.",
        "//!",
        "//! **Generated file -- do not edit.**  Regenerate it with",
        "//! `python3 rust/scripts/gen_i18n.py` from the checkout root.",
        "//!",
        "//! Everything here comes from `windows/deepl_ofm/core/languages.py`, the",
        "//! behavioural reference of the port; `language.rs` holds the algorithms",
        "//! that consume it.",
        "",
        "use crate::language::Language;",
        "use crate::AppLanguage;",
        "",
        "/// The 38 Hy-MT2 languages, in the order of the Swift `Language` enum.",
        "#[rustfmt::skip]",
        f"pub(crate) static ALL: [Language; {len(registry)}] = [",
    ]
    for code, english, local, bcp47 in registry:
        bcp47_literal = f"Some({rust_string(bcp47)})" if bcp47 else "None"
        lines.append(
            "    Language { "
            f"code: {rust_string(code)}, english_name: {rust_string(english)}, "
            f"local_name: {rust_string(local)}, bcp47: {bcp47_literal} "
            "},"
        )
    lines.append("];")
    lines.append("")
    lines.extend(
        [
            "/// Localised language names: `(code, [ru, de, fr, es, pl, pt, it])`.",
            "///",
            "/// Ported verbatim from `_LOCALIZED_NAMES`; the column order matches",
            "/// [`NAME_COLUMNS`].",
            "#[rustfmt::skip]",
            "pub(crate) static LOCALIZED_NAMES: &[(&str, [&str; "
            f"{len(columns)}])] = &[",
        ]
    )
    for code in sorted(names):
        rendered = ", ".join(rust_string(names[code][column]) for column in columns)
        lines.append(f"    ({rust_string(code)}, [{rendered}]),")
    lines.append("];")
    lines.append("")
    lines.append("/// Interface languages with curated display names, in column order.")
    lines.append("#[rustfmt::skip]")
    lines.append(f"pub(crate) static NAME_COLUMNS: [AppLanguage; {len(columns)}] = [")
    lines.append(
        "    " + ", ".join(f"AppLanguage::{RUST_VARIANTS[column]}" for column in columns) + ","
    )
    lines.append("];")
    lines.append("")
    lines.extend(
        [
            "/// Localised display name of `code` for the interface language `ui`.",
            "///",
            "/// `None` when the pair is not curated; the caller then falls back to",
            "/// [`Language::english_name`].",
            "pub(crate) fn localized_name(code: &str, ui: AppLanguage) -> Option<&'static str> {",
            "    let column = NAME_COLUMNS.iter().position(|language| *language == ui)?;",
            "    let (_, names) = LOCALIZED_NAMES",
            "        .iter()",
            "        .find(|(candidate, _)| *candidate == code)?;",
            "    names.get(column).copied()",
            "}",
            "",
        ]
    )
    lines.extend(
        [
            "/// Words that score Ukrainian in the Cyrillic heuristic.",
            "#[rustfmt::skip]",
            "pub(crate) static UKRAINIAN_WORDS: &[&str] = &[",
        ]
    )
    lines.extend(_wrapped_rust_strings(sorted(ukrainian), "    "))
    lines.append("];")
    lines.append("")
    lines.extend(
        [
            "/// Words that score Russian in the Cyrillic heuristic.",
            "#[rustfmt::skip]",
            "pub(crate) static RUSSIAN_WORDS: &[&str] = &[",
        ]
    )
    lines.extend(_wrapped_rust_strings(sorted(russian), "    "))
    lines.append("];")
    lines.append("")
    lines.append("/// Latin languages of the stop-word scorer, in tie-break order.")
    lines.append("#[rustfmt::skip]")
    lines.append(f"pub(crate) static LATIN_ORDER: [&str; {len(order)}] = [")
    lines.append("    " + ", ".join(rust_string(code) for code in order) + ",")
    lines.append("];")
    lines.append("")
    lines.append("/// Folded stop words for each [`LATIN_ORDER`] language.")
    lines.append("#[rustfmt::skip]")
    lines.append(f"pub(crate) static LATIN_STOP_WORDS: [&[&str]; {len(order)}] = [")
    for code in order:
        words = sorted({fold(word) for word in stops[code].split()})
        lines.append("    &[")
        lines.extend(_wrapped_rust_strings(words, "        "))
        lines.append("    ],")
    lines.append("];")
    lines.append("")
    lines.extend(
        [
            "/// Lower-case Latin characters whose NFKD decomposition starts with a",
            "/// different character, mapped to that base character (`'é' -> 'e'`).",
            "///",
            "/// Dependency-free stand-in for `unicodedata.normalize(\"NFKD\", ...)` plus",
            "/// `str.casefold()`, used by the stop-word scorer so that `cómo` matches",
            "/// the stop word `como`.  Sorted by source character; entries whose",
            "/// casefolded form has more than one character (`ß` -> `ss`) are omitted",
            "/// because no stop word depends on them.",
            "#[rustfmt::skip]",
            f"pub(crate) static FOLD_PAIRS: &[(char, char)] = &[",
        ]
    )
    chunk: list[str] = []
    for char, base in pairs:
        chunk.append(f"({rust_char(char)}, {rust_char(base)})")
        if len(chunk) == 5:
            lines.append("    " + ", ".join(chunk) + ",")
            chunk = []
    if chunk:
        lines.append("    " + ", ".join(chunk) + ",")
    lines.append("];")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def generate() -> dict[Path, str]:
    """Parse every source and return ``{output path: file contents}``."""
    root = repo_root()
    swift_path = find_source(SWIFT_RELATIVE_PATH)
    extra_path = find_source(EXTRA_RELATIVE_PATH)
    languages_path = find_source(LANGUAGES_RELATIVE_PATH)

    tables = parse_swift_source(swift_path.read_text(encoding="utf-8"))
    extra = load_extra(extra_path)
    check_catalog(tables, extra)
    data = read_language_source(languages_path)
    registry = data["registry"]
    if not isinstance(registry, list) or len(registry) != 38:
        raise GeneratorError(f"expected 38 languages, found {len(registry or [])}")
    codes = [entry[0] for entry in registry]
    if sorted(codes) != sorted(data["names"]):
        raise GeneratorError("_LOCALIZED_NAMES does not cover exactly the 38 languages")
    order = data["order"]
    if not isinstance(order, list) or set(order) != set(data["stops"]):
        raise GeneratorError("_LATIN_ORDER and _LATIN_STOPS disagree")

    return {
        root / CATALOG_RELATIVE_PATH: render_catalog(tables, extra),
        root / LANGUAGE_DATA_RELATIVE_PATH: render_language_data(data, fold_pairs()),
    }


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point: regenerate or check the generated modules."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the files are stale")
    args = parser.parse_args(argv)
    try:
        outputs = generate()
    except GeneratorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    stale = 0
    for path, content in outputs.items():
        if args.check:
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != content:
                print(f"error: {path} is stale; run python3 rust/scripts/gen_i18n.py", file=sys.stderr)
                stale += 1
            else:
                print(f"{path} is up to date")
        else:
            path.write_text(content, encoding="utf-8", newline="\n")
            print(f"wrote {path}")
    return 1 if stale else 0


if __name__ == "__main__":
    raise SystemExit(main())
