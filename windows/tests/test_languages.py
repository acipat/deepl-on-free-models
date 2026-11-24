"""Tests for :mod:`deepl_ofm.core.languages` (port of ``LanguageTests.swift``)."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from deepl_ofm.core.languages import (
    ALL,
    AUTO,
    AppLanguage,
    Language,
    LanguageTable,
    coerce_app_language,
    detect_language,
    get_language,
)

# Order of the language table in Sources/HyMT/Models/Language.swift.
EXPECTED_CODES = [
    "zh", "en", "fr", "pt", "es", "ja", "tr", "ru", "ar", "ko",
    "th", "it", "de", "vi", "ms", "id", "tl", "hi", "zh-Hant", "pl",
    "cs", "nl", "km", "my", "fa", "gu", "ur", "te", "mr", "he",
    "bn", "ta", "uk", "bo", "kk", "mn", "ug", "yue",
]


def test_thirty_eight_languages_in_swift_order() -> None:
    assert len(ALL) == 38
    assert [language.code for language in ALL] == EXPECTED_CODES
    assert [language.code for language in LanguageTable.ALL] == EXPECTED_CODES


def test_every_language_has_names_and_bcp47() -> None:
    for language in ALL:
        assert isinstance(language, Language)
        assert language.code
        assert language.english_name
        assert language.local_name
        assert language.bcp47
        assert not language.is_auto


def test_auto_language() -> None:
    assert AUTO.code == "auto"
    assert AUTO.is_auto
    assert AUTO.bcp47 is None
    assert LanguageTable.AUTO == AUTO
    assert get_language("auto") is AUTO
    assert not ALL[0].is_auto


def test_lookup_accepts_codes_case_and_bcp47() -> None:
    assert get_language("de") == Language("de", "German", "німецька", "de-DE")
    assert get_language("zh-hant").code == "zh-Hant"
    assert get_language("ZH-TW").code == "zh-Hant"
    assert get_language("en-US").code == "en"
    assert get_language("fil-PH").code == "tl"
    assert get_language("nope") is None
    assert get_language("") is None
    assert get_language(None) is None  # type: ignore[arg-type]


def test_module_level_detect_shortcut() -> None:
    assert detect_language("Hello, this is a test").code == "en"
    assert LanguageTable.detect("Hello, this is a test").code == "en"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("こんにちは世界、今日はいい天気ですね。", "ja"),
        ("안녕하세요. 오늘 날씨가 좋네요.", "ko"),
        ("สวัสดีครับ วันนี้อากาศดี", "th"),
        ("مرحبا بالعالم، هذا اختبار.", "ar"),
        ("नमस्ते दुनिया, यह एक परीक्षण है।", "hi"),
        ("你好世界，这是一个测试。", "zh"),
        ("Це український текст про переклад", "uk"),
        ("Это русский текст про перевод", "ru"),
        ("Hello, this is a test", "en"),
    ],
)
def test_detects_scripts(text: str, expected: str) -> None:
    language = LanguageTable.detect(text)
    assert language is not None
    assert language.code == expected


def test_swift_language_tests() -> None:
    # Ported verbatim from Tests/HyMTTests/LanguageTests.swift.
    assert LanguageTable.detect(
        "Це український текст про переклад", AppLanguage.UK
    ).code == "uk"
    assert LanguageTable.detect(
        "Это русский текст про перевод", AppLanguage.RU
    ).code == "ru"
    assert LanguageTable.detect("Hello, this is a test").code == "en"
    assert LanguageTable.detect("ключ", AppLanguage.UK).code == "uk"
    assert LanguageTable.detect("ключ", AppLanguage.RU).code == "ru"


def test_ambiguous_cyrillic_uses_preferred_language() -> None:
    assert LanguageTable.detect("ключ", "ru").code == "ru"
    assert LanguageTable.detect("ключ", "uk").code == "uk"


def test_ukrainian_and_russian_scoring() -> None:
    # Distinctive letters weigh more than the word lists.
    assert LanguageTable.detect("їжа та ґанок").code == "uk"
    assert LanguageTable.detect("объём и этаж").code == "ru"


def test_detects_latin_languages_instead_of_calling_them_english() -> None:
    # Also ported from the Swift test suite.
    assert LanguageTable.detect(
        "Bonjour, je voudrais savoir à quelle heure commence la réunion."
    ).code == "fr"
    assert LanguageTable.detect(
        "Este documento explica cómo funciona el servicio de traducción."
    ).code == "es"
    assert LanguageTable.detect(
        "Este documento explica como funciona o serviço de tradução."
    ).code == "pt"
    assert LanguageTable.detect("Das ist ein guter Test für die Übersetzung.").code == "de"
    assert LanguageTable.detect("Dit is een goede test voor de vertaling.").code == "nl"
    assert LanguageTable.detect("La casa è bella e il giardino è grande.").code == "it"
    assert LanguageTable.detect("To jest dobry test tłumaczenia.").code == "pl"
    assert LanguageTable.detect("Bu bir çeviri testidir ve çok iyidir.").code == "tr"
    assert LanguageTable.detect("Đây là một bài kiểm tra bản dịch.").code == "vi"
    assert LanguageTable.detect("Ini adalah sebuah tes terjemahan yang baik.").code == "id"
    assert LanguageTable.detect("Ini ialah satu ujian terjemahan yang baik.").code == "ms"


def test_latin_text_without_known_words_falls_back_to_english() -> None:
    assert LanguageTable.detect("Xyzzy plugh foobar").code == "en"
    assert LanguageTable.detect("Hello, this is a test").code == "en"


def test_unknown_or_empty_text_returns_none() -> None:
    assert LanguageTable.detect("") is None
    assert LanguageTable.detect("12345 67890 !!!") is None
    assert LanguageTable.detect("ქართული") is None  # Georgian -> nil, like Swift
    assert LanguageTable.detect("Հայերեն") is None  # Armenian -> nil, like Swift


def test_hebrew_and_tamil_ranges() -> None:
    assert LanguageTable.detect("שלום עולם").code == "he"
    assert LanguageTable.detect("வணக்கம் உலகம்").code == "ta"


def test_display_name_uses_english_and_ukrainian_names() -> None:
    german = get_language("de")
    assert german.display_name(AppLanguage.EN) == "German"
    assert german.display_name(AppLanguage.UK) == "німецька"
    assert german.display_name("uk") == "німецька"
    assert german.display_name("en") == "German"


def test_display_name_is_localised_for_other_interface_languages() -> None:
    assert get_language("de").display_name(AppLanguage.DE) == "Deutsch"
    assert get_language("uk").display_name(AppLanguage.RU) == "украинский"
    assert get_language("zh-Hant").display_name(AppLanguage.FR) == "chinois traditionnel"
    assert get_language("yue").display_name(AppLanguage.IT) == "cantonese"


def test_display_name_falls_back_to_english_when_unknown() -> None:
    klingon = Language("xx", "Klingon", "клінгонська")
    assert klingon.display_name(AppLanguage.DE) == "Klingon"


def test_auto_display_name_is_translated() -> None:
    assert AUTO.display_name(AppLanguage.EN) == "Auto-detect"


def test_coerce_app_language() -> None:
    assert coerce_app_language(None) is AppLanguage.SYSTEM
    assert coerce_app_language("") is AppLanguage.SYSTEM
    assert coerce_app_language("uk_UA") is AppLanguage.UK
    assert coerce_app_language("ua") is AppLanguage.UK
    assert coerce_app_language("de-DE") is AppLanguage.DE
    assert coerce_app_language(AppLanguage.IT) is AppLanguage.IT
    assert coerce_app_language("klingon") is AppLanguage.SYSTEM


def test_app_language_locale_identifiers() -> None:
    assert AppLanguage.EN.locale_identifier == "en_US"
    assert AppLanguage.UK.locale_identifier == "uk_UA"
    assert AppLanguage.PT.locale_identifier == "pt_PT"
    assert (
        AppLanguage.SYSTEM.locale_identifier
        == AppLanguage.system_resolved().locale_identifier
    )


def test_app_language_resolved_and_titles() -> None:
    assert AppLanguage.UK.resolved is AppLanguage.UK
    assert AppLanguage.SYSTEM.resolved is AppLanguage.system_resolved()
    assert AppLanguage.system_resolved() is not AppLanguage.SYSTEM
    assert AppLanguage.EN.picker_title == "English"
    assert AppLanguage.UK.picker_title == "Українська"
    assert AppLanguage.IT.picker_title == "Italiano"
    assert isinstance(AppLanguage.SYSTEM.picker_title, str)
    assert AppLanguage.SYSTEM.picker_title


def test_language_is_hashable_and_frozen() -> None:
    codes = {language.code for language in ALL}
    assert len(codes) == 38
    with pytest.raises(FrozenInstanceError):
        ALL[0].code = "xx"  # type: ignore[misc]
