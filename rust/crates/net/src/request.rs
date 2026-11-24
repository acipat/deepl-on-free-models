//! Public request, output and cancellation types.

use std::sync::atomic::AtomicBool;
use std::sync::Arc;

use ofm_config::BackendConfig;
use ofm_i18n::Language;
use ofm_text::{TranslationStyle, TranslationTone};

/// Cancellation flag polled between chunks and between blocks.
///
/// The desktop app owns one flag per job and sets it from the UI thread; the
/// translator only ever loads it.
pub type CancelFlag = Arc<AtomicBool>;

/// `(completed, total)` progress callback, called after every block.
pub type ProgressFn = Arc<dyn Fn(usize, usize) + Send + Sync>;

/// Partial-result callback, called with the text translated so far.
pub type PartialFn = Arc<dyn Fn(&str) + Send + Sync>;

/// One translation job: text, languages, style and backend configuration.
///
/// The structure is borrowed so a caller can start several jobs without
/// cloning the configuration; the callbacks and the cancel flag are shared.
pub struct TranslateRequest<'a> {
    /// Source text; may span several lines.
    pub text: &'a str,
    /// Source language (`LanguageTable::AUTO` when the caller did not detect
    /// one).
    pub source: &'a Language,
    /// Whether the user explicitly chose [`Self::source`].
    ///
    /// Generic instructions only state a source language when this flag is
    /// true. TranslateGemma may also use a detected language for its required
    /// source field. `false` covers `LanguageTable::AUTO`.
    pub source_explicit: bool,
    /// Target language.
    pub target: &'a Language,
    /// How freely the model may paraphrase.
    pub style: TranslationStyle,
    /// Optional tone suffix.
    pub tone: TranslationTone,
    /// Primary backend configuration.
    pub config: &'a BackendConfig,
    /// Retried once with the whole job when the primary fails.
    pub fallback: Option<&'a BackendConfig>,
    /// Set to abort the job between chunks and between blocks.
    pub cancel: Option<CancelFlag>,
    /// Called with `(completed, total)` after every block.
    pub on_progress: Option<ProgressFn>,
    /// Called with the translated text accumulated so far.
    pub on_partial: Option<PartialFn>,
}

/// Result of one translation or rewrite job.
#[derive(Clone, Debug, Default)]
pub struct TranslationOutput {
    /// Translated (or rewritten) text.
    pub text: String,
    /// Lines that stayed in the source language.
    pub warnings: usize,
    /// Generation rate based on the server's token counts and decode timings.
    pub tokens_per_second: Option<f64>,
    /// Wall-clock duration of the whole job including retries.
    pub duration_ms: Option<u64>,
    /// True when the job succeeded on the fallback configuration.
    pub used_fallback: bool,
}
