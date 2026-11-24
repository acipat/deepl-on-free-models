"""Tests for :mod:`deepl_ofm.core.prompts`.

Ports ``Tests/HyMTTests/PromptBuilderTests.swift`` one-to-one and pins the
exact instruction strings so a well-meaning wording change cannot slip in:
Hy-MT2 was trained on these byte-for-byte.
"""

from __future__ import annotations

from deepl_ofm.core.prompts import (
    PromptBuilder,
    TranslationStyle,
    TranslationTone,
)

MARKDOWN_CLAUSE = (
    "Preserve Markdown syntax exactly (headings, lists, bold, italic, links, "
    "inline code); translate only the human-readable text."
)


def test_auto_standard_instruction() -> None:
    """PromptBuilderTests.testAutoStandardInstruction."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.AUTO, TranslationTone.STANDARD, "Ukrainian"
    )
    assert "into Ukrainian" in prompt
    assert "only output the translated result" in prompt
    assert "[literal" not in prompt


def test_literal_descriptor() -> None:
    """PromptBuilderTests.testLiteralDescriptor."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.LITERAL, TranslationTone.STANDARD, "English"
    )
    assert "[literal, word for word]" in prompt


def test_natural_formal_descriptor() -> None:
    """PromptBuilderTests.testNaturalFormalDescriptor."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.NATURAL, TranslationTone.FORMAL, "English"
    )
    assert "natural and idiomatic" in prompt
    assert "formal and professional" in prompt


def test_casual_descriptor() -> None:
    """PromptBuilderTests.testCasualDescriptor."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.AUTO, TranslationTone.CASUAL, "English"
    )
    assert "casual and conversational" in prompt


def test_markdown_clause_comes_before_the_final_colon() -> None:
    """PromptBuilderTests.testMarkdownClauseComesBeforeTheFinalColon."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.AUTO,
        TranslationTone.STANDARD,
        "English",
        preserve_markdown=True,
    )
    assert prompt.index("Preserve Markdown syntax") < prompt.rindex(":")


def test_no_markdown_clause_for_plain_text() -> None:
    """PromptBuilderTests.testNoMarkdownClauseForPlainText."""
    prompt = PromptBuilder.instruction(
        TranslationStyle.AUTO,
        TranslationTone.STANDARD,
        "English",
        preserve_markdown=False,
    )
    assert "Preserve Markdown" not in prompt


def test_heading_prompt_keeps_the_clause_before_the_colon() -> None:
    """PromptBuilderTests.testHeadingPromptKeepsTheClauseBeforeTheColon."""
    prompt = PromptBuilder.heading_prompt(
        "About",
        TranslationStyle.AUTO,
        TranslationTone.STANDARD,
        "Ukrainian",
        preserve_markdown=True,
    )
    assert prompt.startswith("Translate this heading into Ukrainian.")
    assert "Preserve Markdown syntax" in prompt
    assert prompt.endswith("\n\nAbout")


def test_preview_includes_the_sample() -> None:
    """PromptBuilderTests.testPreviewIncludesTheSample."""
    preview = PromptBuilder.preview(
        TranslationStyle.AUTO,
        TranslationTone.STANDARD,
        "English",
        sample="Зразок",
    )
    assert preview.endswith("\n\nЗразок")


def test_plain_prompt_is_style_free() -> None:
    """PromptBuilderTests.testPlainPromptIsStyleFree."""
    prompt = PromptBuilder.plain_prompt("Hello.", "Ukrainian")
    assert prompt.startswith("Translate the following text into Ukrainian.")
    assert "Output only the translated text" in prompt
    assert "[literal" not in prompt
    assert prompt.endswith("\n\nHello.")


def test_exact_auto_standard_instruction() -> None:
    """The exact Swift string, including the final colon and spacing."""
    assert PromptBuilder.instruction(
        TranslationStyle.AUTO, TranslationTone.STANDARD, "Ukrainian"
    ) == (
        "Translate the following text into Ukrainian. Note that you should only "
        "output the translated result without any additional explanation:"
    )


def test_exact_auto_standard_instruction_with_markdown() -> None:
    assert PromptBuilder.instruction(
        TranslationStyle.AUTO,
        TranslationTone.STANDARD,
        "English",
        preserve_markdown=True,
    ) == (
        f"Translate the following text into English. {MARKDOWN_CLAUSE} Note that "
        "you should only output the translated result without any additional "
        "explanation:"
    )


def test_exact_styled_instruction() -> None:
    assert PromptBuilder.instruction(
        TranslationStyle.LITERAL, TranslationTone.STANDARD, "English"
    ) == (
        "Please translate the following text into English. Note that the "
        "translation style must strictly conform to [literal, word for word]:"
    )


def test_exact_styled_instruction_with_tone_and_markdown() -> None:
    assert PromptBuilder.instruction(
        TranslationStyle.NATURAL,
        TranslationTone.FORMAL,
        "English",
        preserve_markdown=True,
    ) == (
        f"Please translate the following text into English. {MARKDOWN_CLAUSE} "
        "Note that the translation style must strictly conform to [natural and "
        "idiomatic, conveying the meaning rather than the wording; formal and "
        "professional]:"
    )


def test_auto_with_non_standard_tone_uses_the_styled_branch() -> None:
    prompt = PromptBuilder.instruction(
        TranslationStyle.AUTO, TranslationTone.CASUAL, "English"
    )
    assert prompt.startswith("Please translate the following text into English.")
    assert "natural and idiomatic" in prompt
    assert "casual and conversational" in prompt


def test_exact_heading_instructions() -> None:
    assert PromptBuilder.heading_instruction(
        TranslationStyle.AUTO, TranslationTone.STANDARD, "Ukrainian"
    ) == (
        "Translate this heading into Ukrainian. Output only the translated "
        "heading, without any additional explanation:"
    )
    assert PromptBuilder.heading_instruction(
        TranslationStyle.LITERAL,
        TranslationTone.STANDARD,
        "Ukrainian",
        preserve_markdown=True,
    ) == (
        f"Please translate this heading into Ukrainian. {MARKDOWN_CLAUSE} Note "
        "that the translation style must strictly conform to [literal, word for "
        "word] and output only the translated heading:"
    )


def test_exact_plain_instruction() -> None:
    assert PromptBuilder.plain_instruction("Ukrainian") == (
        "Translate the following text into Ukrainian. Output only the "
        "translated text, without any additional explanation:"
    )


def test_prompt_is_instruction_blank_line_and_text() -> None:
    instruction = PromptBuilder.instruction(
        TranslationStyle.NATURAL, TranslationTone.CASUAL, "German"
    )
    assert (
        PromptBuilder.prompt(
            "Hello", TranslationStyle.NATURAL, TranslationTone.CASUAL, "German"
        )
        == instruction + "\n\nHello"
    )


def test_preview_uses_the_default_sample_and_no_markdown_clause() -> None:
    preview = PromptBuilder.preview(
        TranslationStyle.AUTO, TranslationTone.STANDARD, "English"
    )
    assert preview.endswith("\n\nHello, world!")
    assert "Preserve Markdown" not in preview


def test_prompt_accepts_empty_and_whitespace_text() -> None:
    prompt = PromptBuilder.prompt(
        "", TranslationStyle.AUTO, TranslationTone.STANDARD, "English"
    )
    assert prompt.endswith("\n\n")
    spaces = PromptBuilder.prompt(
        "   ", TranslationStyle.AUTO, TranslationTone.STANDARD, "English"
    )
    assert spaces.endswith("\n\n   ")


def test_titles_and_details_match_swift() -> None:
    assert TranslationStyle.AUTO.title == "Auto"
    assert TranslationStyle.LITERAL.title == "Literal"
    assert TranslationStyle.NATURAL.title == "Natural"
    assert TranslationStyle.AUTO.detail == "The model picks a natural style"
    assert TranslationStyle.LITERAL.detail == "Word for word, without free paraphrase"
    assert TranslationStyle.NATURAL.detail == "Conveys meaning rather than wording"
    assert TranslationTone.STANDARD.title == "Default"
    assert TranslationTone.FORMAL.title == "Formal"
    assert TranslationTone.CASUAL.title == "Casual"
    assert TranslationTone.STANDARD.detail == "No extra tone"
    assert TranslationTone.FORMAL.detail == "Formal and professional"
    assert TranslationTone.CASUAL.detail == "Casual and conversational"
