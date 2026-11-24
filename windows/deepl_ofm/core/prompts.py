"""Translation prompts and their UI metadata.

The Hy-MT2 instructions mirror ``Sources/HyMT/Models/Prompt.swift`` because
Hy-MT2 was trained on this exact wording. TranslateGemma uses its published
Ollama template.
"""

from __future__ import annotations

from enum import Enum

from deepl_ofm.core.languages import Language

MARKDOWN_CLAUSE = (
    "Preserve Markdown syntax exactly (headings, lists, bold, italic, links, "
    "inline code); translate only the human-readable text."
)


class TranslationStyle(str, Enum):
    """How freely the model may paraphrase (Swift ``TranslationStyle``)."""

    AUTO = "auto"
    LITERAL = "literal"
    NATURAL = "natural"

    @property
    def title(self) -> str:
        """English UI label; the interface localises it through ``t()``."""
        return {
            TranslationStyle.AUTO: "Auto",
            TranslationStyle.LITERAL: "Literal",
            TranslationStyle.NATURAL: "Natural",
        }[self]

    @property
    def detail(self) -> str:
        """English one-line explanation; localised at the call site."""
        return {
            TranslationStyle.AUTO: "The model picks a natural style",
            TranslationStyle.LITERAL: "Word for word, without free paraphrase",
            TranslationStyle.NATURAL: "Conveys meaning rather than wording",
        }[self]


class TranslationTone(str, Enum):
    """Optional tone suffix appended to the style descriptor."""

    STANDARD = "standard"
    FORMAL = "formal"
    CASUAL = "casual"

    @property
    def title(self) -> str:
        """English UI label; the interface localises it through ``t()``."""
        return {
            TranslationTone.STANDARD: "Default",
            TranslationTone.FORMAL: "Formal",
            TranslationTone.CASUAL: "Casual",
        }[self]

    @property
    def detail(self) -> str:
        """English one-line explanation; localised at the call site."""
        return {
            TranslationTone.STANDARD: "No extra tone",
            TranslationTone.FORMAL: "Formal and professional",
            TranslationTone.CASUAL: "Casual and conversational",
        }[self]


class PromptBuilder:
    """Builds translation instructions for Hy-MT2 and TranslateGemma.

    The instruction and the source text travel in a single user message: the
    model has no default system prompt (see the model card).
    """

    @staticmethod
    def style_descriptor(style: TranslationStyle) -> str:
        """Descriptor placed between ``[...]`` in the styled instruction."""
        if style == TranslationStyle.LITERAL:
            return "literal, word for word"
        return "natural and idiomatic, conveying the meaning rather than the wording"

    @staticmethod
    def tone_suffix(tone: TranslationTone) -> str | None:
        """The tone clause, or ``None`` for ``STANDARD``."""
        if tone == TranslationTone.FORMAL:
            return "formal and professional"
        if tone == TranslationTone.CASUAL:
            return "casual and conversational"
        return None

    @staticmethod
    def instruction(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: str,
        preserve_markdown: bool = False,
    ) -> str:
        """Return the translation instruction (no source text, no trailing newline)."""
        clause = " " + MARKDOWN_CLAUSE if preserve_markdown else ""
        if style == TranslationStyle.AUTO and tone == TranslationTone.STANDARD:
            return (
                f"Translate the following text into {target_language}.{clause} "
                "Note that you should only output the translated result without any "
                "additional explanation:"
            )
        descriptor = PromptBuilder.style_descriptor(style)
        suffix = PromptBuilder.tone_suffix(tone)
        if tone != TranslationTone.STANDARD and suffix is not None:
            descriptor += f"; {suffix}"
        return (
            f"Please translate the following text into {target_language}.{clause} "
            "Note that the translation style must strictly conform to "
            f"[{descriptor}]:"
        )

    @staticmethod
    def prompt(
        text: str,
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: str,
        preserve_markdown: bool = False,
    ) -> str:
        """Instruction + blank line + ``text`` (the single user message)."""
        return (
            PromptBuilder.instruction(
                style,
                tone,
                target_language,
                preserve_markdown,
            )
            + "\n\n"
            + text
        )

    @staticmethod
    def heading_instruction(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: str,
        preserve_markdown: bool = False,
    ) -> str:
        """Stricter instruction for headings and list items translated alone."""
        clause = " " + MARKDOWN_CLAUSE if preserve_markdown else ""
        if style == TranslationStyle.AUTO and tone == TranslationTone.STANDARD:
            return (
                f"Translate this heading into {target_language}.{clause} "
                "Output only the translated heading, without any additional explanation:"
            )
        descriptor = PromptBuilder.style_descriptor(style)
        suffix = PromptBuilder.tone_suffix(tone)
        if tone != TranslationTone.STANDARD and suffix is not None:
            descriptor += f"; {suffix}"
        return (
            f"Please translate this heading into {target_language}.{clause} "
            "Note that the translation style must strictly conform to "
            f"[{descriptor}] and output only the translated heading:"
        )

    @staticmethod
    def heading_prompt(
        text: str,
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: str,
        preserve_markdown: bool = False,
    ) -> str:
        """Heading instruction + blank line + ``text``."""
        return (
            PromptBuilder.heading_instruction(
                style,
                tone,
                target_language,
                preserve_markdown,
            )
            + "\n\n"
            + text
        )

    @staticmethod
    def plain_instruction(target_language: str) -> str:
        """Style-free fallback instruction for models that ignore the styled one."""
        return (
            f"Translate the following text into {target_language}. "
            "Output only the translated text, without any additional explanation:"
        )

    @staticmethod
    def plain_prompt(text: str, target_language: str) -> str:
        """Plain instruction + blank line + ``text``."""
        return PromptBuilder.plain_instruction(target_language) + "\n\n" + text

    @staticmethod
    def translate_gemma_prompt(text: str, source: Language, target: Language) -> str:
        """Ollama's published TranslateGemma template, with two blank lines."""
        return (
            f"You are a professional {source.english_name} ({source.code}) to "
            f"{target.english_name} ({target.code}) translator. Your goal is to "
            f"accurately convey the meaning and nuances of the original {source.english_name} "
            f"text while adhering to {target.english_name} grammar, vocabulary, and "
            "cultural sensitivities.\n"
            f"Produce only the {target.english_name} translation, without any additional "
            f"explanations or commentary. Please translate the following {source.english_name} "
            f"text into {target.english_name}:\n\n\n{text}"
        )

    @staticmethod
    def preview(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: str,
        sample: str = "Hello, world!",
    ) -> str:
        """Example prompt shown in Settings (no Markdown clause, like Swift)."""
        return (
            PromptBuilder.instruction(style, tone, target_language)
            + "\n\n"
            + sample
        )
