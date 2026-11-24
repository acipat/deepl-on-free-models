//! Prompt selection shared by the translator and the CLI preview.
//!
//! The first prompt of a block is not just [`ofm_text::PromptBuilder::instruction`]:
//! a structurally recognised heading gets the heading wording, any other block
//! gets the style/tone ladder, and TranslateGemma gets the instruction published
//! by its model card. Keeping that decision in one place means `ofm prompt`
//! shows exactly what the engine will send.

use ofm_config::PromptFamily;
use ofm_i18n::Language;
use ofm_text::{PromptBuilder, TextChunker, TranslationStyle, TranslationTone};

use crate::pipeline::{contains_markdown, is_letter, split_mixed_line, with_source_language};

/// One block and the settings that choose its prompt ladder.
#[derive(Clone, Copy, Debug)]
pub struct PromptPlan<'a> {
    /// Block text, without its Markdown prefix.
    pub text: &'a str,
    /// Target language.
    pub target: &'a Language,
    /// Source language (may be [`ofm_i18n::LanguageTable::AUTO`]).
    pub source: &'a Language,
    /// True only when the user chose the source language explicitly.
    pub source_explicit: bool,
    /// Selected translation style.
    pub style: TranslationStyle,
    /// Selected tone.
    pub tone: TranslationTone,
    /// Prompt family published for the model.
    pub family: PromptFamily,
    /// Structural heading flag from [`ofm_text::TextChunk::is_heading`].
    pub is_heading: bool,
    /// Whether the source line contains Markdown syntax.
    pub preserve_markdown: bool,
}

impl PromptPlan<'_> {
    /// Every prompt tried for this block, in order, without the source prefix.
    ///
    /// The translator sends these with the block's language prefix applied;
    /// use [`Self::first_prompt`] for the exact first request body.
    pub fn ladder(&self) -> Vec<String> {
        let body = self.text.trim();
        let target = self.target.english_name;

        if let Some(prompt) = self.gemma_prompt(body) {
            return vec![prompt];
        }

        if self.is_heading {
            // The prefix is re-attached by the chunker, so the heading wording
            // never asks the model to preserve it.
            let heading = PromptBuilder::heading_prompt(body, self.style, self.tone, target, false);
            let plain = PromptBuilder::plain_prompt(body, target);
            return unique_prompts(vec![heading, plain]);
        }

        let styled =
            PromptBuilder::prompt(body, self.style, self.tone, target, self.preserve_markdown);
        let natural = PromptBuilder::prompt(
            body,
            TranslationStyle::Natural,
            self.tone,
            target,
            self.preserve_markdown,
        );
        let literal = PromptBuilder::prompt(
            body,
            TranslationStyle::Literal,
            TranslationTone::Standard,
            target,
            self.preserve_markdown,
        );
        let plain = PromptBuilder::plain_prompt(body, target);
        unique_prompts(match self.style {
            TranslationStyle::Auto => vec![styled, natural, plain],
            TranslationStyle::Natural => vec![styled, plain, literal],
            TranslationStyle::Literal => vec![styled, natural, plain],
        })
    }

    /// The exact first request body, including any source-language prefix.
    pub fn first_prompt(&self) -> String {
        let mut ladder = self.ladder();
        let first = if ladder.is_empty() {
            String::new()
        } else {
            ladder.remove(0)
        };
        with_source_language(first, self.source_hint())
    }

    pub(crate) fn gemma_prompt(&self, text: &str) -> Option<String> {
        // Keep the model card's format verbatim. Auto's Devanagari result
        // cannot distinguish Hindi from Marathi or other languages.
        (self.family == PromptFamily::TranslateGemma
            && !self.source.is_auto()
            && (self.source_explicit || self.source.code != "hi"))
            .then(|| PromptBuilder::translate_gemma_prompt(text, self.source, self.target))
    }

    pub(crate) fn source_hint(&self) -> Option<&Language> {
        // TranslateGemma already names its source in the instruction.
        (self.source_explicit && self.family != PromptFamily::TranslateGemma).then_some(self.source)
    }
}

/// The exact first prompt a translation of `text` would send, if any block is
/// translatable.
///
/// This mirrors the first step of [`crate::Translator::translate`] (chunking,
/// code and punctuation passthrough, the `id — description` split) so a preview
/// cannot drift from the real request.
#[allow(clippy::too_many_arguments)]
pub fn first_prompt_for_text(
    text: &str,
    source: &Language,
    source_explicit: bool,
    target: &Language,
    style: TranslationStyle,
    tone: TranslationTone,
    model: &str,
) -> Option<String> {
    let normalized = TextChunker::normalize(text);
    let chunks = TextChunker::split(&normalized);
    let family = PromptFamily::for_model(model);
    for chunk in &chunks {
        let body = &chunk.text;
        let line = format!("{}{}", chunk.prefix, body);
        if chunk.is_code || !body.chars().any(is_letter) {
            continue;
        }
        let translatable = match split_mixed_line(body) {
            Some((_, right)) => right,
            None => body.clone(),
        };
        let plan = PromptPlan {
            text: &translatable,
            target,
            source,
            source_explicit,
            style,
            tone,
            family,
            is_heading: chunk.is_heading,
            preserve_markdown: contains_markdown(&line),
        };
        return Some(plan.first_prompt());
    }
    None
}

/// Drop repeated prompts while keeping the order of first occurrence.
///
/// `Auto` and a non-standard tone describe the same style as `Natural`, so the
/// ladder would otherwise send a byte-identical request twice per block.
pub(crate) fn unique_prompts(prompts: Vec<String>) -> Vec<String> {
    let mut unique: Vec<String> = Vec::with_capacity(prompts.len());
    for prompt in prompts {
        if !unique.contains(&prompt) {
            unique.push(prompt);
        }
    }
    unique
}
