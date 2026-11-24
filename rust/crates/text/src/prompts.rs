//! Translation prompts and their UI metadata.
//!
//! Port of `windows/deepl_ofm/core/prompts.py`, which is itself a port of
//! `Sources/HyMT/Models/Prompt.swift`. The Hy-MT2 instruction strings are
//! byte-for-byte identical to the macOS app because Hy-MT2 was trained on this
//! exact wording; do not "fix" the grammar or the spacing.
//!
//! TranslateGemma publishes a different instruction (both language names and
//! codes). It is kept in [`PromptBuilder::translate_gemma_prompt`] and never
//! mixed into the Hy-MT2 strings.

use ofm_i18n::Language;

/// Markdown clause appended to the instruction when Markdown is preserved.
///
/// It is inserted *before* the final colon, see
/// [`PromptBuilder::instruction`].
pub const MARKDOWN_CLAUSE: &str = concat!(
    "Preserve Markdown syntax exactly (headings, lists, bold, italic, links, ",
    "inline code); translate only the human-readable text."
);

const STYLE_NATURAL: &str = "natural and idiomatic, conveying the meaning rather than the wording";
const STYLE_LITERAL: &str = "literal, word for word";
const TONE_FORMAL: &str = "formal and professional";
const TONE_CASUAL: &str = "casual and conversational";

/// How freely the model may paraphrase (Swift `TranslationStyle`).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TranslationStyle {
    /// Let the model pick a natural style (the default).
    Auto,
    /// Word for word, without free paraphrase.
    Literal,
    /// Convey meaning rather than wording.
    Natural,
}

impl TranslationStyle {
    /// English UI label; the interface localises it through `t()`.
    pub fn title(self) -> &'static str {
        match self {
            Self::Auto => "Auto",
            Self::Literal => "Literal",
            Self::Natural => "Natural",
        }
    }

    /// English one-line explanation; localised at the call site.
    pub fn detail(self) -> &'static str {
        match self {
            Self::Auto => "The model picks a natural style",
            Self::Literal => "Word for word, without free paraphrase",
            Self::Natural => "Conveys meaning rather than wording",
        }
    }

    /// Stable settings value (`"auto"`, `"literal"`, `"natural"`).
    pub fn value(self) -> &'static str {
        match self {
            Self::Auto => "auto",
            Self::Literal => "literal",
            Self::Natural => "natural",
        }
    }

    /// Parse a settings value; `None` for an unknown string.
    pub fn from_value(s: &str) -> Option<Self> {
        match s {
            "auto" => Some(Self::Auto),
            "literal" => Some(Self::Literal),
            "natural" => Some(Self::Natural),
            _ => None,
        }
    }

    /// Descriptor placed between `[...]` in the styled instruction.
    fn descriptor(self) -> &'static str {
        match self {
            Self::Literal => STYLE_LITERAL,
            Self::Auto | Self::Natural => STYLE_NATURAL,
        }
    }
}

/// Optional tone suffix appended to the style descriptor.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TranslationTone {
    /// No extra tone (the default).
    Standard,
    /// Formal and professional.
    Formal,
    /// Casual and conversational.
    Casual,
}

impl TranslationTone {
    /// English UI label; the interface localises it through `t()`.
    pub fn title(self) -> &'static str {
        match self {
            Self::Standard => "Default",
            Self::Formal => "Formal",
            Self::Casual => "Casual",
        }
    }

    /// English one-line explanation; localised at the call site.
    pub fn detail(self) -> &'static str {
        match self {
            Self::Standard => "No extra tone",
            Self::Formal => "Formal and professional",
            Self::Casual => "Casual and conversational",
        }
    }

    /// Stable settings value (`"standard"`, `"formal"`, `"casual"`).
    pub fn value(self) -> &'static str {
        match self {
            Self::Standard => "standard",
            Self::Formal => "formal",
            Self::Casual => "casual",
        }
    }

    /// Parse a settings value; `None` for an unknown string.
    pub fn from_value(s: &str) -> Option<Self> {
        match s {
            "standard" => Some(Self::Standard),
            "formal" => Some(Self::Formal),
            "casual" => Some(Self::Casual),
            _ => None,
        }
    }

    /// The tone clause, or `None` for [`TranslationTone::Standard`].
    fn suffix(self) -> Option<&'static str> {
        match self {
            Self::Standard => None,
            Self::Formal => Some(TONE_FORMAL),
            Self::Casual => Some(TONE_CASUAL),
        }
    }
}

/// Builds the exact instruction Hy-MT2 was trained on.
///
/// The instruction and the source text travel in a single user message: the
/// model has no default system prompt (see the model card).
pub struct PromptBuilder;

/// Sample text shown in the Settings preview.
pub const DEFAULT_SAMPLE: &str = "Hello, world!";

impl PromptBuilder {
    /// `" " + MARKDOWN_CLAUSE` or the empty string.
    fn clause(preserve_markdown: bool) -> String {
        if preserve_markdown {
            format!(" {MARKDOWN_CLAUSE}")
        } else {
            String::new()
        }
    }

    /// Descriptor for the styled instruction, including the tone suffix.
    fn descriptor(style: TranslationStyle, tone: TranslationTone) -> String {
        let mut descriptor = style.descriptor().to_string();
        if let Some(suffix) = tone.suffix() {
            descriptor.push_str("; ");
            descriptor.push_str(suffix);
        }
        descriptor
    }

    /// Translation instruction (no source text, no trailing newline).
    pub fn instruction(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: &str,
        preserve_markdown: bool,
    ) -> String {
        let clause = Self::clause(preserve_markdown);
        if style == TranslationStyle::Auto && tone == TranslationTone::Standard {
            return format!(
                "Translate the following text into {target_language}.{clause} \
                 Note that you should only output the translated result without any \
                 additional explanation:"
            );
        }
        let descriptor = Self::descriptor(style, tone);
        format!(
            "Please translate the following text into {target_language}.{clause} \
             Note that the translation style must strictly conform to [{descriptor}]:"
        )
    }

    /// Instruction + blank line + `text` (the single user message).
    pub fn prompt(
        text: &str,
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: &str,
        preserve_markdown: bool,
    ) -> String {
        let mut value = Self::instruction(style, tone, target_language, preserve_markdown);
        value.push_str("\n\n");
        value.push_str(text);
        value
    }

    /// Stricter instruction for headings and list items translated alone.
    pub fn heading_instruction(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: &str,
        preserve_markdown: bool,
    ) -> String {
        let clause = Self::clause(preserve_markdown);
        if style == TranslationStyle::Auto && tone == TranslationTone::Standard {
            return format!(
                "Translate this heading into {target_language}.{clause} \
                 Output only the translated heading, without any additional explanation:"
            );
        }
        let descriptor = Self::descriptor(style, tone);
        format!(
            "Please translate this heading into {target_language}.{clause} \
             Note that the translation style must strictly conform to [{descriptor}] \
             and output only the translated heading:"
        )
    }

    /// Heading instruction + blank line + `text`.
    pub fn heading_prompt(
        text: &str,
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: &str,
        preserve_markdown: bool,
    ) -> String {
        let mut value = Self::heading_instruction(style, tone, target_language, preserve_markdown);
        value.push_str("\n\n");
        value.push_str(text);
        value
    }

    /// Style-free fallback instruction for models that ignore the styled one.
    pub fn plain_instruction(target_language: &str) -> String {
        format!(
            "Translate the following text into {target_language}. \
             Output only the translated text, without any additional explanation:"
        )
    }

    /// Plain instruction + blank line + `text`.
    pub fn plain_prompt(text: &str, target_language: &str) -> String {
        let mut value = Self::plain_instruction(target_language);
        value.push_str("\n\n");
        value.push_str(text);
        value
    }

    /// TranslateGemma instruction, using both language names and codes.
    ///
    /// Published by the model card:
    /// <https://ollama.com/library/translategemma#prompt-guide>. The card asks
    /// for two blank lines before the text and has no style or tone variants,
    /// so this wording is used verbatim and must not be reused for Hy-MT2.
    pub fn translate_gemma_instruction(source: &Language, target: &Language) -> String {
        let source_name = source.english_name;
        let source_code = source.code;
        let target_name = target.english_name;
        let target_code = target.code;
        format!(
            "You are a professional {source_name} ({source_code}) to {target_name} \
             ({target_code}) translator. Your goal is to accurately convey the meaning and \
             nuances of the original {source_name} text while adhering to {target_name} \
             grammar, vocabulary, and cultural sensitivities.\n\
             Produce only the {target_name} translation, without any additional explanations \
             or commentary. Please translate the following {source_name} text into \
             {target_name}:"
        )
    }

    /// TranslateGemma instruction, two blank lines, then `text`.
    pub fn translate_gemma_prompt(text: &str, source: &Language, target: &Language) -> String {
        let mut value = Self::translate_gemma_instruction(source, target);
        // The model card requires *two blank lines* before the text.
        value.push_str("\n\n\n");
        value.push_str(text);
        value
    }

    /// Example prompt shown in Settings (no Markdown clause, like Swift).
    pub fn preview(
        style: TranslationStyle,
        tone: TranslationTone,
        target_language: &str,
        sample: &str,
    ) -> String {
        let mut value = Self::instruction(style, tone, target_language, false);
        value.push_str("\n\n");
        value.push_str(sample);
        value
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ofm_i18n::LanguageTable;

    fn auto_standard(target: &str) -> String {
        PromptBuilder::instruction(
            TranslationStyle::Auto,
            TranslationTone::Standard,
            target,
            false,
        )
    }

    #[test]
    fn auto_standard_instruction() {
        let prompt = auto_standard("Ukrainian");
        assert!(prompt.contains("into Ukrainian"));
        assert!(prompt.contains("only output the translated result"));
        assert!(!prompt.contains("[literal"));
    }

    #[test]
    fn literal_descriptor() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Literal,
            TranslationTone::Standard,
            "English",
            false,
        );
        assert!(prompt.contains("[literal, word for word]"));
    }

    #[test]
    fn natural_formal_descriptor() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Natural,
            TranslationTone::Formal,
            "English",
            false,
        );
        assert!(prompt.contains("natural and idiomatic"));
        assert!(prompt.contains("formal and professional"));
    }

    #[test]
    fn casual_descriptor() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Auto,
            TranslationTone::Casual,
            "English",
            false,
        );
        assert!(prompt.contains("casual and conversational"));
    }

    #[test]
    fn markdown_clause_comes_before_the_final_colon() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            true,
        );
        let clause = prompt.find("Preserve Markdown syntax").expect("clause");
        let colon = prompt.rfind(':').expect("colon");
        assert!(clause < colon);
    }

    #[test]
    fn no_markdown_clause_for_plain_text() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            false,
        );
        assert!(!prompt.contains("Preserve Markdown"));
    }

    #[test]
    fn heading_prompt_keeps_the_clause_before_the_colon() {
        let prompt = PromptBuilder::heading_prompt(
            "About",
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "Ukrainian",
            true,
        );
        assert!(prompt.starts_with("Translate this heading into Ukrainian."));
        assert!(prompt.contains("Preserve Markdown syntax"));
        assert!(prompt.ends_with("\n\nAbout"));
    }

    #[test]
    fn preview_includes_the_sample() {
        let preview = PromptBuilder::preview(
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            "Зразок",
        );
        assert!(preview.ends_with("\n\nЗразок"));
    }

    #[test]
    fn plain_prompt_is_style_free() {
        let prompt = PromptBuilder::plain_prompt("Hello.", "Ukrainian");
        assert!(prompt.starts_with("Translate the following text into Ukrainian."));
        assert!(prompt.contains("Output only the translated text"));
        assert!(!prompt.contains("[literal"));
        assert!(prompt.ends_with("\n\nHello."));
    }

    #[test]
    fn exact_auto_standard_instruction() {
        assert_eq!(
            auto_standard("Ukrainian"),
            "Translate the following text into Ukrainian. Note that you should only \
             output the translated result without any additional explanation:"
        );
    }

    #[test]
    fn exact_auto_standard_instruction_with_markdown() {
        assert_eq!(
            PromptBuilder::instruction(
                TranslationStyle::Auto,
                TranslationTone::Standard,
                "English",
                true,
            ),
            format!(
                "Translate the following text into English. {MARKDOWN_CLAUSE} Note that \
                 you should only output the translated result without any additional \
                 explanation:"
            )
        );
    }

    #[test]
    fn exact_styled_instruction() {
        assert_eq!(
            PromptBuilder::instruction(
                TranslationStyle::Literal,
                TranslationTone::Standard,
                "English",
                false,
            ),
            "Please translate the following text into English. Note that the \
             translation style must strictly conform to [literal, word for word]:"
        );
    }

    #[test]
    fn exact_styled_instruction_with_tone_and_markdown() {
        assert_eq!(
            PromptBuilder::instruction(
                TranslationStyle::Natural,
                TranslationTone::Formal,
                "English",
                true,
            ),
            format!(
                "Please translate the following text into English. {MARKDOWN_CLAUSE} \
                 Note that the translation style must strictly conform to [natural and \
                 idiomatic, conveying the meaning rather than the wording; formal and \
                 professional]:"
            )
        );
    }

    #[test]
    fn auto_with_non_standard_tone_uses_the_styled_branch() {
        let prompt = PromptBuilder::instruction(
            TranslationStyle::Auto,
            TranslationTone::Casual,
            "English",
            false,
        );
        assert!(prompt.starts_with("Please translate the following text into English."));
        assert!(prompt.contains("natural and idiomatic"));
        assert!(prompt.contains("casual and conversational"));
    }

    #[test]
    fn exact_heading_instructions() {
        assert_eq!(
            PromptBuilder::heading_instruction(
                TranslationStyle::Auto,
                TranslationTone::Standard,
                "Ukrainian",
                false,
            ),
            "Translate this heading into Ukrainian. Output only the translated \
             heading, without any additional explanation:"
        );
        assert_eq!(
            PromptBuilder::heading_instruction(
                TranslationStyle::Literal,
                TranslationTone::Standard,
                "Ukrainian",
                true,
            ),
            format!(
                "Please translate this heading into Ukrainian. {MARKDOWN_CLAUSE} Note \
                 that the translation style must strictly conform to [literal, word for \
                 word] and output only the translated heading:"
            )
        );
    }

    #[test]
    fn exact_plain_instruction() {
        assert_eq!(
            PromptBuilder::plain_instruction("Ukrainian"),
            "Translate the following text into Ukrainian. Output only the \
             translated text, without any additional explanation:"
        );
    }

    #[test]
    fn prompt_is_instruction_blank_line_and_text() {
        let instruction = PromptBuilder::instruction(
            TranslationStyle::Natural,
            TranslationTone::Casual,
            "German",
            false,
        );
        assert_eq!(
            PromptBuilder::prompt(
                "Hello",
                TranslationStyle::Natural,
                TranslationTone::Casual,
                "German",
                false,
            ),
            instruction + "\n\nHello"
        );
    }

    #[test]
    fn preview_uses_the_default_sample_and_no_markdown_clause() {
        let preview = PromptBuilder::preview(
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            DEFAULT_SAMPLE,
        );
        assert!(preview.ends_with("\n\nHello, world!"));
        assert!(!preview.contains("Preserve Markdown"));
    }

    #[test]
    fn translate_gemma_instruction_matches_the_model_card() {
        let english = LanguageTable::get("en").expect("en");
        let german = LanguageTable::get("de").expect("de");
        assert_eq!(
            PromptBuilder::translate_gemma_instruction(english, german),
            "You are a professional English (en) to German (de) translator. Your goal is \
             to accurately convey the meaning and nuances of the original English text \
             while adhering to German grammar, vocabulary, and cultural sensitivities.\n\
             Produce only the German translation, without any additional explanations or \
             commentary. Please translate the following English text into German:"
        );
    }

    #[test]
    fn translate_gemma_prompt_has_two_blank_lines_before_the_text() {
        let english = LanguageTable::get("en").expect("en");
        let german = LanguageTable::get("de").expect("de");
        let prompt = PromptBuilder::translate_gemma_prompt("Hello, world!", english, german);
        assert!(prompt.ends_with("\n\n\nHello, world!"));
        assert!(prompt.contains("You are a professional English (en) to German (de) translator."));
        assert!(prompt.contains("Please translate the following English text into German:"));
    }

    #[test]
    fn prompt_accepts_empty_and_whitespace_text() {
        let prompt = PromptBuilder::prompt(
            "",
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            false,
        );
        assert!(prompt.ends_with("\n\n"));
        let spaces = PromptBuilder::prompt(
            "   ",
            TranslationStyle::Auto,
            TranslationTone::Standard,
            "English",
            false,
        );
        assert!(spaces.ends_with("\n\n   "));
    }

    #[test]
    fn titles_and_details_match_swift() {
        assert_eq!(TranslationStyle::Auto.title(), "Auto");
        assert_eq!(TranslationStyle::Literal.title(), "Literal");
        assert_eq!(TranslationStyle::Natural.title(), "Natural");
        assert_eq!(
            TranslationStyle::Auto.detail(),
            "The model picks a natural style"
        );
        assert_eq!(
            TranslationStyle::Literal.detail(),
            "Word for word, without free paraphrase"
        );
        assert_eq!(
            TranslationStyle::Natural.detail(),
            "Conveys meaning rather than wording"
        );
        assert_eq!(TranslationTone::Standard.title(), "Default");
        assert_eq!(TranslationTone::Formal.title(), "Formal");
        assert_eq!(TranslationTone::Casual.title(), "Casual");
        assert_eq!(TranslationTone::Standard.detail(), "No extra tone");
        assert_eq!(TranslationTone::Formal.detail(), "Formal and professional");
        assert_eq!(
            TranslationTone::Casual.detail(),
            "Casual and conversational"
        );
    }

    #[test]
    fn values_round_trip() {
        for style in [
            TranslationStyle::Auto,
            TranslationStyle::Literal,
            TranslationStyle::Natural,
        ] {
            assert_eq!(TranslationStyle::from_value(style.value()), Some(style));
        }
        for tone in [
            TranslationTone::Standard,
            TranslationTone::Formal,
            TranslationTone::Casual,
        ] {
            assert_eq!(TranslationTone::from_value(tone.value()), Some(tone));
        }
        assert_eq!(TranslationStyle::from_value("bogus"), None);
        assert_eq!(TranslationTone::from_value(""), None);
    }

    #[test]
    fn empty_target_language_still_produces_a_colon() {
        let prompt = auto_standard("");
        assert!(prompt.starts_with("Translate the following text into ."));
        assert!(prompt.ends_with(':'));
    }
}
