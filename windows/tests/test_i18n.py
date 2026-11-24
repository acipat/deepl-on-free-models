"""Tests for the nine-language interface catalogue ported from Localization.swift."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from deepl_ofm.core.languages import AppLanguage
from deepl_ofm.i18n import (
    available_languages,
    catalog,
    current_language,
    install_translator,
    set_language,
    t,
    tf,
)
from deepl_ofm.i18n._parse import (
    SWIFT_TABLES,
    SwiftParseError,
    _read_swift_string,
    find_swift_source,
    generate,
    parse_swift_source,
)

#: Languages with a generated table, in the order of the Swift ``L10n`` enum.
LANGUAGE_CODES = ("uk", "ru", "de", "fr", "es", "pl", "pt", "it")

#: Number of English keys in the eight dictionaries of Localization.swift.
EXPECTED_KEYS = 305

#: Values copied from Sources/HyMT/Support/Localization.swift (verified by the
#: round-trip test below as well).
SPOT_CHECKS: dict[str, dict[str, str]] = {
    "uk": {
        "Settings": "Налаштування",
        "Copy": "Копіювати",
        "Cancel": "Скасувати",
        "History": "Історія",
        "Translate to": "Перекласти на",
    },
    "ru": {
        "Settings": "Настройки",
        "Copy": "Копировать",
        "Cancel": "Отмена",
        "History": "История",
        "Translate to": "Перевести на",
    },
    "de": {
        "Settings": "Einstellungen",
        "Copy": "Kopieren",
        "Cancel": "Abbrechen",
        "History": "Verlauf",
        "Translate to": "Übersetzen nach",
    },
    "fr": {
        "Settings": "Paramètres",
        "Copy": "Copier",
        "Cancel": "Annuler",
        "History": "Historique",
        "Translate to": "Traduire vers",
    },
    "es": {
        "Settings": "Configuración",
        "Copy": "Copiar",
        "Cancel": "Cancelar",
        "History": "Historial",
        "Translate to": "Traducir a",
    },
    "pl": {
        "Settings": "Ustawienia",
        "Copy": "Kopiuj",
        "Cancel": "Anuluj",
        "History": "Historia",
        "Translate to": "Przetłumacz na",
    },
    "pt": {
        "Settings": "Configurações",
        "Copy": "Copiar",
        "Cancel": "Cancelar",
        "History": "Histórico",
        "Translate to": "Traduzir para",
    },
    "it": {
        "Settings": "Impostazioni",
        "Copy": "Copia",
        "Cancel": "Annulla",
        "History": "Cronologia",
        "Translate to": "Traduci in",
    },
}

#: Same placeholder grammar as the generator, used to prove data integrity.
PLACEHOLDER = re.compile(
    r"%(?:%|(?:\d+\$)?(?:hh|h|ll|l)?[@dsifgxXoOuc]|\.\d+[fFgGeE])"
)


def _synthetic_swift_source() -> str:
    """Build a minimal eight-table Swift source that exercises every escape form."""
    entries = "\n".join(
        (
            r'        "Greeting": "Привіт \"світ\"",',
            r'        "Path": "C:\\tmp",',
            r'        "Line": "one\ntwo",',
            r'        "Tab": "a\tb",',
            r'        "Dots": "…\u{2026}",',
        )
    )
    blocks = [
        f"    private static let {swift_name}: [String: String] = [\n{entries}\n    ]"
        for swift_name, _code, _constant in SWIFT_TABLES
    ]
    return "enum L10n {\n" + "\n".join(blocks) + "\n}\n"


@pytest.fixture(autouse=True)
def _reset_interface_language() -> object:
    """Keep the module-level language from leaking between tests."""
    set_language(AppLanguage.EN)
    yield
    set_language(AppLanguage.EN)


# ---------------------------------------------------------------------------
# Catalogue shape and coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_language_table_is_non_empty(code: str) -> None:
    table = catalog.BY_LANGUAGE[code]
    assert isinstance(table, dict)
    assert table, f"{code} table must not be empty"


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_key_count_per_language(code: str) -> None:
    assert len(catalog.BY_LANGUAGE[code]) == EXPECTED_KEYS, (
        f"{code}: expected {EXPECTED_KEYS} keys from Localization.swift, "
        f"found {len(catalog.BY_LANGUAGE[code])}"
    )


def test_all_languages_share_the_same_key_set() -> None:
    reference = set(catalog.UKRAINIAN)
    for code in LANGUAGE_CODES[1:]:
        assert set(catalog.BY_LANGUAGE[code]) == reference, code


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_every_language_covers_the_english_keys(code: str) -> None:
    # English is implicit (key == value); the "English keys" are the union of
    # the eight tables, which is exactly what t() can look up.
    english = set().union(*(set(table) for table in catalog.BY_LANGUAGE.values()))
    table = catalog.BY_LANGUAGE[code]
    covered = len(set(table) & english)
    assert covered / len(english) >= 0.90, (
        f"{code}: only {covered}/{len(english)} English keys covered"
    )
    assert covered == len(english), f"{code}: missing {sorted(english - set(table))[:5]}"


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_keys_and_values_are_well_formed(code: str) -> None:
    for key, value in catalog.BY_LANGUAGE[code].items():
        assert isinstance(key, str) and key.strip(), f"{code}: blank key"
        assert isinstance(value, str) and value.strip(), f"{code}: blank value for {key!r}"


def test_catalog_layout() -> None:
    assert len(catalog.BY_LANGUAGE) == len(LANGUAGE_CODES)
    assert "en" not in catalog.BY_LANGUAGE  # English is the identity mapping
    assert catalog.TRANSLATIONS is catalog.BY_LANGUAGE
    for constant in ("UKRAINIAN", "RUSSIAN", "GERMAN", "FRENCH", "SPANISH",
                     "POLISH", "PORTUGUESE", "ITALIAN"):
        table = getattr(catalog, constant)
        assert isinstance(table, dict) and len(table) == EXPECTED_KEYS, constant


def test_english_key_count() -> None:
    english = set().union(*(set(table) for table in catalog.BY_LANGUAGE.values()))
    assert len(english) == EXPECTED_KEYS


def test_swift_escapes_are_decoded() -> None:
    # The current tables contain no escapes, so exercise the parser on a
    # synthetic source that uses every escape form from the brief.
    source = _synthetic_swift_source()
    tables = parse_swift_source(source)
    assert tables["uk"]["Greeting"] == 'Привіт "світ"'
    assert tables["uk"]["Path"] == "C:\\tmp"
    assert tables["uk"]["Line"] == "one\ntwo"
    assert tables["uk"]["Tab"] == "a\tb"
    assert tables["uk"]["Dots"] == "……"  # "…" plus \u{2026}


def test_swift_parser_rejects_unknown_escapes() -> None:
    with pytest.raises(SwiftParseError):
        _read_swift_string(r'"bad \q escape"', 0)


def test_swift_parser_reports_missing_tables() -> None:
    with pytest.raises(SwiftParseError):
        parse_swift_source("enum L10n {}")


@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_placeholders_match_between_key_and_translation(code: str) -> None:
    for key, value in catalog.BY_LANGUAGE[code].items():
        expected = Counter(PLACEHOLDER.findall(key))
        actual = Counter(PLACEHOLDER.findall(value))
        assert actual == expected, f"{code}: placeholder mismatch for {key!r} -> {value!r}"


# ---------------------------------------------------------------------------
# Spot checks against the Swift source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("code", LANGUAGE_CODES)
@pytest.mark.parametrize("key", ("Settings", "Copy", "Cancel", "History", "Translate to"))
def test_spot_check_from_swift_source(code: str, key: str) -> None:
    assert t(key, code) == SPOT_CHECKS[code][key]


def test_translate_is_a_windows_only_key() -> None:
    # The macOS app has no standalone "Translate" entry (its tabs use
    # "Translate text", "Translate file…" and "Translate to"), so the Windows
    # port keeps it in its own extra table.  A key that exists nowhere must
    # still come back unchanged rather than crash.
    from deepl_ofm.i18n.extra import EXTRA

    assert "Translate" not in catalog.UKRAINIAN
    assert "Translate" in EXTRA["uk"]
    assert t("Translate", "uk") == "Перекласти"
    assert t("Translate text", "uk") == "Перекласти текст"
    assert t("A string nobody translated", "uk") == "A string nobody translated"


def test_catalog_matches_swift_source() -> None:
    try:
        source_path = find_swift_source()
    except FileNotFoundError:
        pytest.skip("macOS Swift source is not available in this checkout")
    parsed = parse_swift_source(source_path.read_text(encoding="utf-8"))
    assert set(parsed) == set(LANGUAGE_CODES)
    for code in LANGUAGE_CODES:
        assert catalog.BY_LANGUAGE[code] == parsed[code], f"{code} drifted from the Swift source"


def test_generated_catalog_file_is_up_to_date() -> None:
    try:
        expected = generate()
    except FileNotFoundError:
        pytest.skip("macOS Swift source is not available in this checkout")
    current = Path(catalog.__file__).read_text(encoding="utf-8")
    assert current == expected, "catalog.py is stale; run python -m deepl_ofm.i18n._parse"


# ---------------------------------------------------------------------------
# t(): lookup, fallback and global language
# ---------------------------------------------------------------------------


def test_english_is_the_identity_mapping() -> None:
    for key in catalog.UKRAINIAN:
        assert t(key, AppLanguage.EN) == key
        assert t(key, "en") == key


def test_unknown_key_returns_the_key_itself() -> None:
    missing = "This string does not exist in the Swift catalogue"
    for language in ("en", "uk", "ru", "de", "fr", "es", "pl", "pt", "it", "xx"):
        assert t(missing, language) == missing


def test_language_codes_are_tolerant() -> None:
    assert t("Settings", "uk-UA") == "Налаштування"
    assert t("Settings", "UA") == "Налаштування"  # legacy code used by older builds
    assert t("Settings", "pt_BR") == "Configurações"
    assert t("Settings", "DE") == "Einstellungen"


def test_unknown_language_falls_back_to_english(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="deepl_ofm.i18n"):
        assert t("Settings", "zz") == "Settings"
    assert any("zz" in record.getMessage() for record in caplog.records)


def test_set_language_switches_results() -> None:
    set_language(AppLanguage.UK)
    assert current_language() is AppLanguage.UK
    assert t("Settings") == "Налаштування"
    assert t("History") == "Історія"

    set_language("de")
    assert current_language() is AppLanguage.DE
    assert t("Settings") == "Einstellungen"
    assert t("Cancel") == "Abbrechen"

    set_language(AppLanguage.FR)
    assert current_language() is AppLanguage.FR
    assert t("Copy") == "Copier"


def test_install_translator_is_an_alias_of_set_language() -> None:
    install_translator("it")
    assert current_language() is AppLanguage.IT
    assert t("Cancel") == "Annulla"


def test_system_language_is_resolved_immediately() -> None:
    set_language("system")
    assert current_language() is not AppLanguage.SYSTEM
    assert current_language() is AppLanguage.system_resolved()
    assert t("Settings") == t("Settings", current_language())


def test_available_languages_lists_english_first() -> None:
    languages = available_languages()
    assert languages[0] is AppLanguage.EN
    assert AppLanguage.SYSTEM not in languages
    assert [member.value for member in languages] == [
        "en", "uk", "ru", "de", "fr", "es", "pl", "pt", "it",
    ]


# ---------------------------------------------------------------------------
# tf(): Swift printf placeholders
# ---------------------------------------------------------------------------


def test_tf_formats_integer_placeholders() -> None:
    assert tf("Translating… %d of %d", 3, 10, language="uk") == "Перекладаю… 3 з 10"
    assert tf("Models: %d", 7, language="de") == "Modelle: 7"
    assert tf("Some paragraphs are still in the original language (%d).", 2,
              language="de") == "Einige Absätze sind noch in der Originalsprache (2)."


def test_tf_preserves_non_breaking_spaces_from_the_swift_source() -> None:
    # The French table uses a narrow no-break space before the colon.
    assert tf("Models: %d", 7, language="fr") == "Modèles\xa0: 7"


def test_tf_formats_object_placeholders() -> None:
    assert tf("Translate clipboard (%@)", "Ctrl+Alt+T", language="uk") == (
        "Перекласти буфер обміну (Ctrl+Alt+T)"
    )
    assert tf("Model “%@” not found", "llama3", language="de") == (
        "Modell “llama3” nicht gefunden"
    )
    assert tf("Server returned error %@: %@", 500, "boom", language="de") == (
        "Server gab Fehler 500 zurück: boom"
    )


def test_tf_uses_the_current_language_when_omitted() -> None:
    set_language("uk")
    assert tf("Models: %d", 3) == "Моделей: 3"


def test_tf_formats_english_keys_in_place() -> None:
    assert tf("Models: %d", 4, language="en") == "Models: 4"
    assert tf("Translate clipboard (%@)", "Ctrl+Alt+T") == "Translate clipboard (Ctrl+Alt+T)"


def test_tf_without_arguments_returns_the_translation() -> None:
    assert tf("Models: %d", language="de") == "Modelle: %d"


@pytest.mark.parametrize(
    ("key", "args"),
    [
        ("Translating… %d of %d", (3,)),          # too few arguments
        ("Models: %d", (1, 2, 3)),                # too many arguments
        ("Literal {braces} and %@", ("x",)),      # braces must not be interpreted
        ("No placeholders at all", (1,)),          # no fields to fill
        ("Unknown %@ key", ("x",)),                # unknown key still formats
        ("", ("x",)),                             # empty key
        ("100%% done %d", (50,)),                 # literal percent + integer
    ],
)
def test_tf_never_raises(key: str, args: tuple[object, ...]) -> None:
    result = tf(key, *args, language="de")
    assert isinstance(result, str)


def test_tf_converts_double_percent_to_a_literal_percent() -> None:
    assert tf("100%% done %d", 50, language="en") == "100% done 50"


def test_tf_leaves_missing_arguments_visible() -> None:
    # Defensive behaviour: fewer arguments than fields must not raise; the
    # remaining fields stay as "{}" so the bug is visible instead of silent.
    assert tf("Translating… %d of %d", 3, language="de") == "Übersetze… 3 von {}"
