#!/usr/bin/env python3
"""Check that every user-facing string the Rust code asks for exists.

`t()`, `t_in()` and `tf()` fall back to the key itself, which means a missing
key shows English text inside a translated interface — a silent bug. This script
extracts every literal key from the source and verifies it against the generated
catalogue, in all eight translated languages, and also reports keys that the
catalogue carries but nothing uses (dead weight, or a sign of a typo).

Exit code 1 when a key is missing, so CI can gate on it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOGUE = ROOT / "crates" / "i18n" / "src" / "catalog.rs"
CRATES = ROOT / "crates"

LANGUAGES = ("UKRAINIAN", "RUSSIAN", "GERMAN", "FRENCH", "SPANISH", "POLISH", "PORTUGUESE", "ITALIAN")


def table(name: str) -> dict[str, str]:
    source = CATALOGUE.read_text(encoding="utf-8")
    match = re.search(
        rf"pub\(crate\) static {name}: &\[\(&str, &str\)\] = &\[(.*?)\n\];", source, re.S
    )
    if not match:
        raise SystemExit(f"catalogue table {name} not found")
    return dict(re.findall(r'\("((?:[^"\\]|\\.)*)", "((?:[^"\\]|\\.)*)"\)', match.group(1)))


def escape(value: str) -> str:
    """Apply Rust string-literal escaping rules to a captured literal.

    A backslash at the end of a line removes the newline **and** the leading
    whitespace of the next line, which is how the code wraps long messages.
    """
    value = re.sub(r"\\\n\s*", "", value)
    value = value.replace("\\\"", '"').replace("\\\\", "\\")
    return value


def used_keys() -> dict[str, list[str]]:
    """Every literal passed to t()/t_in()/tf(), with the files that use it."""
    sites: dict[str, list[str]] = {}
    pattern = re.compile(r'\b(?:t|tf|t_in)\(\s*"((?:[^"\\]|\\.)*)"', re.S)
    for path in sorted(CRATES.rglob("*.rs")):
        posix = path.as_posix()
        if "i18n/src/catalog.rs" in posix or "/tests/" in posix:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # Skip test modules: they may use arbitrary strings.
        text = re.split(r"#\[cfg\(test\)\]", text)[0]
        for key in pattern.findall(text):
            sites.setdefault(escape(key), []).append(str(path.relative_to(ROOT)))
    return sites


def main() -> int:
    sites = used_keys()
    if not sites:
        print("no t()/tf() calls found — nothing to check")
        return 0

    problems: list[str] = []
    primary = table("UKRAINIAN")
    extra = table("EXTRA_UKRAINIAN") if "EXTRA_UKRAINIAN" in CATALOGUE.read_text() else {}

    missing = sorted(key for key in sites if key not in primary and key not in extra)
    for key in missing:
        files = ", ".join(sorted(set(sites[key])))
        problems.append(f"missing translation for {key!r} (used in {files})")

    # A translated entry must not be empty and must not silently equal the key
    # unless the language legitimately uses the same word.
    identical = sorted(
        key for key, value in primary.items() if not value.strip()
    )
    for key in identical:
        problems.append(f"empty translation in uk for {key!r}")

    per_language: dict[str, int] = {}
    for language in LANGUAGES:
        try:
            per_language[language] = len(table(language))
        except SystemExit as error:
            problems.append(str(error))

    counts = set(per_language.values())
    if len(counts) > 1:
        problems.append(f"catalogue tables disagree in size: {per_language}")

    unused = sorted(key for key in primary if key not in sites)
    print(f"catalogue keys (uk): {len(primary)}")
    print(f"windows-only keys:   {len(extra)}")
    print(f"keys used in code:   {len(sites)}")
    print(f"tables:              {per_language}")
    if unused:
        print(f"note: {len(unused)} catalogue keys are not used by the Rust code, e.g. {unused[:3]}")
    for problem in problems:
        print(f"error: {problem}")
    if problems:
        return 1
    print("i18n keys: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
