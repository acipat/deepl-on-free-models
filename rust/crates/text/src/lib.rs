//! `ofm-text` — prompts, chunking, token protection and output sanitisation.
//!
//! This crate is a Rust port of the text-processing core of DeepL-oFM
//! (`windows/deepl_ofm/core/{prompts,chunker,tokens,sanitizer}.py`), which in
//! turn follows the macOS Swift implementation. The prompt strings are
//! byte-identical to `Sources/HyMT/Models/Prompt.swift` because Hy-MT2 was
//! trained on that exact wording.
//!
//! Modules:
//!
//! * [`prompts`] — the exact Hy-MT2 instructions plus style/tone metadata.
//! * [`chunker`] — line-oriented chunking, sentence splitting, recomposition.
//! * [`tokens`] — protection and restoration of URLs, e-mails and model ids.
//! * [`sanitizer`] — leaked-template cleanup and degenerate-output detection.

#![forbid(unsafe_code)]

pub mod chunker;
pub mod prompts;
pub mod sanitizer;
pub mod tokens;

pub use chunker::{ChunkError, TextChunk, TextChunker};
pub use prompts::{
    PromptBuilder, TranslationStyle, TranslationTone, DEFAULT_SAMPLE, MARKDOWN_CLAUSE,
};
pub use sanitizer::{uses_cjk_script, DegenerateReason, OutputSanitizer, TargetLanguage};
pub use tokens::TokenRestorer;
