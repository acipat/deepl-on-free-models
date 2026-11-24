"""Tests for :mod:`deepl_ofm.core.sanitizer`.

Ports the sanitizer-related cases from
``Tests/HyMTTests/TranslationServiceTests.swift`` (``hasTargetScript``,
``usesAllowedCyrillic``, ``usesCJKScript``, ``stripPreamble``) and exercises
the ``validated`` checks behind :meth:`OutputSanitizer.is_degenerate`.
"""

from __future__ import annotations

import pytest

from deepl_ofm.core.languages import Language, LanguageTable
from deepl_ofm.core.sanitizer import OutputSanitizer


def language(code: str) -> Language:
    found = LanguageTable.get(code)
    assert found is not None, f"language {code!r} missing from LanguageTable"
    return found


# --------------------------------------------------------------------------- #
# Script helpers (ported from TranslationServiceTests)
# --------------------------------------------------------------------------- #


def test_target_script_presence() -> None:
    """TranslationServiceTests.testTargetScriptPresence."""
    assert OutputSanitizer.script_ok("Привіт", language("uk"))
    assert not OutputSanitizer.script_ok("Hello", language("uk"))
    assert OutputSanitizer.script_ok("Hello", language("en"))
    assert not OutputSanitizer.script_ok("Привіт", language("en"))
    assert OutputSanitizer.script_ok("こんにちは", language("ja"))
    assert not OutputSanitizer.script_ok("Hello", language("ja"))


def test_cjk_script_includes_japanese() -> None:
    """TranslationServiceTests.testCJKScriptIncludesJapanese."""
    assert OutputSanitizer.uses_cjk_script("ja")
    assert OutputSanitizer.uses_cjk_script("zh-Hant")
    assert not OutputSanitizer.uses_cjk_script("en")


def test_ukrainian_alphabet() -> None:
    """TranslationServiceTests.testUkrainianAlphabet."""
    assert OutputSanitizer.uses_allowed_cyrillic(
        "Привіт, це український текст.", "uk"
    )
    assert not OutputSanitizer.uses_allowed_cyrillic("маў", "uk")
    assert not OutputSanitizer.uses_allowed_cyrillic("цѯнструмент", "uk")
    assert not OutputSanitizer.uses_allowed_cyrillic("коштуђуце", "uk")


def test_russian_alphabet() -> None:
    """TranslationServiceTests.testRussianAlphabet."""
    assert OutputSanitizer.uses_allowed_cyrillic(
        "Привет, это русский текст.", "ru"
    )
    assert not OutputSanitizer.uses_allowed_cyrillic("Привіт", "ru")


def test_script_ok_accepts_letterless_text() -> None:
    assert OutputSanitizer.script_ok("123 — 456", language("uk"))
    assert OutputSanitizer.script_ok("", language("uk"))


# --------------------------------------------------------------------------- #
# Preamble / wrapper stripping
# --------------------------------------------------------------------------- #


def test_preamble_is_stripped() -> None:
    """TranslationServiceTests.testPreambleIsStripped."""
    assert OutputSanitizer.strip_preamble(
        "Ось переклад тексту: «Привіт». Далі текст.",
        "Hello. More text.",
    ) == "Привіт. Далі текст."
    assert OutputSanitizer.strip_preamble(
        "Here is the translation: Hello.", "Привіт."
    ) == "Hello."
    assert OutputSanitizer.strip_preamble(
        "Звісно! Цей пакет коштує 57 доларів.", "The bundle costs $57."
    ) == "Цей пакет коштує 57 доларів."


def test_preamble_is_not_stripped_when_it_is_source_text() -> None:
    source = "Here is the translation: a phrase to translate"
    assert OutputSanitizer.strip_preamble(source, source) == source


def test_strip_preamble_english_and_russian_variants() -> None:
    assert OutputSanitizer.strip_preamble(
        "Here's the translation: Good morning.", ""
    ) == "Good morning."
    assert OutputSanitizer.strip_preamble(
        "The translation is: Good morning.", ""
    ) == "Good morning."
    assert OutputSanitizer.strip_preamble("Вот перевод: Доброе утро.", "") == (
        "Доброе утро."
    )


def test_strip_wrappers_removes_known_leaks() -> None:
    known = [
        "<｜hy_place▁holder▁no▁2｜>",
        "<｜hy_place▁holder▁no▁8｜>",
        "<｜hy_end▁of▁sentence｜>",
        "｜hy_end▁of▁sentence｜",
        "｜hy_end",
        "hy-Assistant",
        "hy-User",
        "hy_Assistant",
        "hy_User",
    ]
    for token in known:
        assert OutputSanitizer.strip_wrappers("Привіт" + token) == "Привіт"
        assert OutputSanitizer.strip_wrappers(token + "Привіт") == "Привіт"


def test_strip_wrappers_removes_generic_hy_fragments() -> None:
    assert OutputSanitizer.strip_wrappers("Hello<hy_token>") == "Hello"
    assert OutputSanitizer.strip_wrappers("Hello<｜hy_end▁of▁sentence｜>") == "Hello"
    assert OutputSanitizer.strip_wrappers("Hello｜hy_end") == "Hello"
    assert OutputSanitizer.strip_wrappers("Hello<") == "Hello"


def test_strip_wrappers_removes_replacement_and_nul() -> None:
    assert OutputSanitizer.strip_wrappers("При\uFFFDвіт\x00") == "Привіт"


def test_strip_wrappers_trims_whitespace() -> None:
    assert OutputSanitizer.strip_wrappers("  \n Hello \n ") == "Hello"
    assert OutputSanitizer.strip_wrappers("") == ""
    assert OutputSanitizer.clean("Hi｜hy_end") == "Hi"


def test_has_role_tokens() -> None:
    for value in (
        "hy-Assistant",
        "hy-User",
        "hy_end",
        "<|im_end|>",
        "<|start_header_id|>",
        "｜hy",
        "</|",
    ):
        assert OutputSanitizer.has_role_tokens("Text " + value)
    assert not OutputSanitizer.has_role_tokens("Just a normal translation.")


# --------------------------------------------------------------------------- #
# is_degenerate
# --------------------------------------------------------------------------- #


def test_valid_translation_is_not_degenerate() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello, world!", "Привіт, світе!", language("uk")
    ) == (False, "")


def test_empty_output() -> None:
    assert OutputSanitizer.is_degenerate("Hello.", "", language("en")) == (
        True,
        "empty",
    )
    assert OutputSanitizer.is_degenerate("Hello.", "   \n\t ", language("en")) == (
        True,
        "empty",
    )


def test_replacement_character_is_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello", "При\uFFFDвіт", language("uk")
    ) == (True, "repetition")


def test_script_mismatch() -> None:
    # The model echoed English into a Ukrainian target.
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Hello.", language("uk")
    ) == (True, "script")
    # Cyrillic text targeting English.
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Привіт.", language("en")
    ) == (True, "script")
    # CJK text targeting a non-CJK language.
    assert OutputSanitizer.is_degenerate(
        "Hello.", "你好。", language("en")
    ) == (True, "script")


def test_cjk_targets_accept_cjk() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello.", "你好。", language("zh")
    ) == (False, "")
    assert OutputSanitizer.is_degenerate(
        "Hello.", "こんにちは。", language("ja")
    ) == (False, "")
    assert OutputSanitizer.is_degenerate(
        "Hello.", "안녕하세요.", language("ko")
    ) == (False, "")


def test_disallowed_cyrillic_letters_are_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Привіт.", "маў", language("uk")
    ) == (True, "script")
    assert OutputSanitizer.is_degenerate(
        "Привет.", "Привіт", language("ru")
    ) == (True, "script")


def test_role_tokens_are_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Hello <|im_end|>", language("en")
    ) == (True, "role_tokens")
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Hello <|start_header_id|>assistant", language("en")
    ) == (True, "role_tokens")


def test_known_leaks_are_cleaned_before_validation() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Привіт｜hy_end", language("uk")
    ) == (False, "")


def test_instruction_echo_is_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Привіт.", "Here is the translation: Hello.", language("en")
    ) == (True, "echo")
    assert OutputSanitizer.is_degenerate(
        "Hello.", "Preserve Markdown syntax exactly", language("en")
    ) == (True, "echo")
    assert OutputSanitizer.is_degenerate(
        "Hello.", "The translation style must strictly conform to [literal]", language("en")
    ) == (True, "echo")


def test_instruction_marker_in_source_is_allowed() -> None:
    source = "The translation is a complex subject."
    assert OutputSanitizer.is_degenerate(
        source, "Переклад — це складна тема.", language("uk")
    ) == (False, "")


def test_first_person_meta_answer_is_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Купити цей продукт.", "I recommend this product.", language("en")
    ) == (True, "echo")
    assert OutputSanitizer.is_degenerate(
        "Купи цей продукт.", "Я можу допомогти з цим.", language("uk")
    ) == (True, "echo")


def test_first_person_source_allows_first_person_translation() -> None:
    source = "I recommend this product because it works."
    assert OutputSanitizer.is_degenerate(
        source, "I recommend this product because it works.", language("en")
    ) == (False, "")


def test_short_output_is_rejected() -> None:
    source = "This is a long source sentence that has plenty of words in it. " * 2
    assert OutputSanitizer.is_degenerate(
        source, "Short.", language("en")
    ) == (True, "length")


def test_collapsed_sentences_are_rejected() -> None:
    source = (
        "This is sentence number one of the text. "
        "This is sentence number two of the text."
    )
    translated = "This is a short one."
    assert OutputSanitizer.is_degenerate(
        source, translated, language("en")
    ) == (True, "length")


def test_excessive_length_is_rejected() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hello.", "x" * 121, language("en")
    ) == (True, "length")
    long_source = "A sentence with enough characters to cross forty. " * 2
    assert OutputSanitizer.is_degenerate(
        long_source, "y" * (len(long_source) * 4 + 1), language("en")
    ) == (True, "length")


def test_repetition_is_rejected() -> None:
    repeated = "abcdefghij" * 20
    assert OutputSanitizer.is_degenerate(
        repeated, repeated, language("en")
    ) == (True, "repetition")


def test_short_source_and_short_translation_pass() -> None:
    assert OutputSanitizer.is_degenerate(
        "Hi.", "Привіт.", language("uk")
    ) == (False, "")


@pytest.mark.parametrize("code", ["uk", "ru", "en", "ja", "zh", "de"])
def test_language_lookup_used_by_the_sanitizer(code: str) -> None:
    assert OutputSanitizer.script_ok("Hello", language(code)) is (
        code not in ("uk", "ru", "ja", "zh")
    )
