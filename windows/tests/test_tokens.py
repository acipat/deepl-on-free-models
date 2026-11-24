"""Tests for :mod:`deepl_ofm.core.tokens`.

Ports ``Tests/HyMTTests/TokenRestorerTests.swift`` one-to-one and adds edges
for empty input, punctuation-only input and every Unicode hyphen variant the
model likes to substitute (U+2010..U+2212).
"""

from __future__ import annotations

import pytest

from deepl_ofm.core.tokens import TokenRestorer

UNICODE_HYPHENS = ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212")


def test_restores_url() -> None:
    """TokenRestorerTests.testRestoresURL."""
    source = "Groq (ключ: console.groq.com/keys):"
    translated = "Groq (key: console.grole.com/keys)"
    assert (
        TokenRestorer.restore(source, translated)
        == "Groq (key: console.groq.com/keys)"
    )


def test_restores_model_ids() -> None:
    """TokenRestorerTests.testRestoresModelIDs."""
    source = "tencent/hy-mt2-7b, qwen/qwen3.7-flash — model"
    translated = "Tencent/HY-MT2-7B, QWEN/QWEN3.7-FLASH — model"
    assert (
        TokenRestorer.restore(source, translated)
        == "tencent/hy-mt2-7b, qwen/qwen3.7-flash — model"
    )


def test_mismatch_returns_none() -> None:
    """TokenRestorerTests.testMismatchReturnsNil."""
    source = "See console.groq.com/keys"
    translated = "No link here"
    assert TokenRestorer.restore(source, translated) is None


def test_punctuation_is_kept() -> None:
    """TokenRestorerTests.testPunctuationIsKept."""
    assert (
        TokenRestorer.preserve_trailing_punctuation("Cloud providers:", "Cloud providers")
        == "Cloud providers:"
    )


def test_wrong_punctuation_is_replaced() -> None:
    """TokenRestorerTests.testWrongPunctuationIsReplaced."""
    assert (
        TokenRestorer.preserve_trailing_punctuation("Cloud providers:", "Cloud providers.")
        == "Cloud providers:"
    )


def test_multi_label_domain_is_restored() -> None:
    """TokenRestorerTests.testMultiLabelDomainIsRestored."""
    source = "Сайт example.com.ua працює"
    translated = "The site example.com works"
    assert (
        TokenRestorer.restore(source, translated)
        == "The site example.com.ua works"
    )


def test_email_is_restored() -> None:
    """TokenRestorerTests.testEmailIsRestored."""
    source = "Напишіть на admin@example.com"
    translated = "Write to admin@example.org"
    assert TokenRestorer.restore(source, translated) == "Write to admin@example.com"


def test_sentence_period_is_not_part_of_url() -> None:
    """TokenRestorerTests.testSentencePeriodIsNotPartOfURL."""
    source = "Відкрийте https://example.com."
    translated = "Open https://example.com"
    restored = TokenRestorer.restore(source, translated)
    assert restored == "Open https://example.com"
    assert (
        TokenRestorer.preserve_trailing_punctuation(source, restored or "")
        == "Open https://example.com."
    )


def test_markdown_link_target_is_restored() -> None:
    """TokenRestorerTests.testMarkdownLinkTargetIsRestored."""
    source = "[key](https://example.com/keys)"
    translated = "[key](https://example.com/keys)"
    assert TokenRestorer.restore(source, translated) == translated


def test_inline_code_is_protected() -> None:
    """TokenRestorerTests.testInlineCodeIsProtected."""
    source = "Use `console.groq.com/keys` here"
    translated = "Use `console.groq.com/keys` here"
    assert TokenRestorer.restore(source, translated) == translated


def test_hyphenated_model_id_is_protected() -> None:
    """TokenRestorerTests.testHyphenatedModelIDIsProtected."""
    source = "gpt-oss-120b — ~3000 tokens per second"
    translated = "GPT-OSS-120B — ~3000 tokens per second"
    assert (
        TokenRestorer.restore(source, translated)
        == "gpt-oss-120b — ~3000 tokens per second"
    )


def test_unicode_hyphen_in_model_id_is_restored() -> None:
    """TokenRestorerTests.testUnicodeHyphenInModelIDIsRestored."""
    source = "Hy-MT2 7B model"
    translated = "Hy\u2011MT2 7B model"
    assert TokenRestorer.restore(source, translated) == "Hy-MT2 7B model"


def test_source_unicode_hyphen_survives() -> None:
    """TokenRestorerTests.testSourceUnicodeHyphenSurvives."""
    source = "Hy\u2011MT2 7B model"
    translated = "Hy-MT2 7B model"
    assert TokenRestorer.restore(source, translated) == "Hy\u2011MT2 7B model"


def test_model_id_at_end_of_sentence_is_restored() -> None:
    """TokenRestorerTests.testModelIDAtEndOfSentenceIsRestored."""
    source = (
        "Styles Auto / Literal / Natural and tones Default / Formal / Casual, "
        "matching the Hy-MT2 model card."
    )
    translated = (
        "Стилі Авто / Дослівний / Натуральний та тони За замовчуванням / "
        "Формальний / Неформальний, відповідно до картки моделі Hy-MT2."
    )
    assert TokenRestorer.restore(source, translated) == translated


def test_hyphenated_id_before_period_is_restored_exactly() -> None:
    """TokenRestorerTests.testHyphenatedIDBeforePeriodIsRestoredExactly."""
    source = "The engine is Hy-MT2."
    translated = "Рушій — hy\u2011mt2."
    assert TokenRestorer.restore(source, translated) == "Рушій — Hy-MT2."


def test_model_id_before_comma_is_restored() -> None:
    """TokenRestorerTests.testModelIDBeforeCommaIsRestored."""
    source = "Hy-MT2, our translator"
    translated = "hy-mt2, наш перекладач"
    assert TokenRestorer.restore(source, translated) == "Hy-MT2, наш перекладач"


def test_repeated_token_keeps_translation() -> None:
    """TokenRestorerTests.testRepeatedTokenKeepsTranslation."""
    source = "Model Hy-MT2 here"
    translated = "Модель Hy-MT2 (Hy-MT2) тут"
    assert TokenRestorer.restore(source, translated) == translated


def test_dropped_token_still_falls_back() -> None:
    """TokenRestorerTests.testDroppedTokenStillFallsBack."""
    source = "Download from example.com/keys now"
    translated = "Завантажте звідси зараз"
    assert TokenRestorer.restore(source, translated) is None


# --------------------------------------------------------------------------- #
# Additional edge cases
# --------------------------------------------------------------------------- #


def test_empty_source_returns_translation() -> None:
    assert TokenRestorer.restore("", "") == ""
    assert TokenRestorer.restore("", "Привіт") == "Привіт"


def test_whitespace_only_source_returns_translation() -> None:
    assert TokenRestorer.restore("   \n\t", "  hello  ") == "  hello  "


def test_text_without_tokens_is_untouched() -> None:
    source = "Просто речення без посилань"
    translated = "Just a sentence without links"
    assert TokenRestorer.restore(source, translated) == translated


def test_url_at_end_of_sentence_keeps_the_period() -> None:
    source = "Документація: https://example.com/docs."
    translated = "Documentation: https://example.com/docs"
    restored = TokenRestorer.restore(source, translated)
    assert restored == "Documentation: https://example.com/docs"
    assert (
        TokenRestorer.preserve_trailing_punctuation(source, restored or "")
        == "Documentation: https://example.com/docs."
    )


def test_trailing_punctuation_edge_cases() -> None:
    assert TokenRestorer.preserve_trailing_punctuation("", "Hello") == "Hello"
    assert TokenRestorer.preserve_trailing_punctuation("   ", "Hello") == "Hello"
    assert TokenRestorer.preserve_trailing_punctuation("Hi", "Hello") == "Hello"
    assert TokenRestorer.preserve_trailing_punctuation("Hi?", "Hello!") == "Hello?"
    assert TokenRestorer.preserve_trailing_punctuation("Hi?", "Hello") == "Hello?"


@pytest.mark.parametrize("hyphen", UNICODE_HYPHENS)
def test_every_unicode_hyphen_variant_is_normalised(hyphen: str) -> None:
    source = "Hy-MT2 model"
    translated = f"Hy{hyphen}MT2 model"
    assert TokenRestorer.restore(source, translated) == "Hy-MT2 model"


@pytest.mark.parametrize("hyphen", UNICODE_HYPHENS)
def test_source_hyphen_variant_is_restored(hyphen: str) -> None:
    source = f"Hy{hyphen}MT2 model"
    translated = "Hy-MT2 model"
    assert TokenRestorer.restore(source, translated) == f"Hy{hyphen}MT2 model"


def test_equal_token_counts_are_replaced_by_position() -> None:
    source = "alpha.com and beta.io"
    translated = "gamma.com und delta.io"
    assert TokenRestorer.restore(source, translated) == "alpha.com und beta.io"


def test_token_count_lost_with_empty_translation_returns_none() -> None:
    assert TokenRestorer.restore("Visit example.com", "") is None


def test_inline_code_with_period_inside_is_untouched() -> None:
    source = "Call `config.yaml.` first"
    translated = "Call `config.yaml.` first"
    assert TokenRestorer.restore(source, translated) == translated
