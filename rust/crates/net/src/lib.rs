//! `ofm-net` — streaming translators, model discovery and transport errors.
//!
//! This crate is the Rust port of `windows/deepl_ofm/services/translation.py`
//! and `probe.py`, which in turn follow `Sources/HyMT/Services/TranslationService.swift`
//! and `Probe.swift`. It owns both wire protocols (Ollama `/api/chat` NDJSON
//! and the OpenAI-compatible `/chat/completions` SSE stream), the streaming
//! byte budget, the per-block retry ladder, the fallback configuration and the
//! cancel flag. It has no UI dependencies.
//!
//! # Overview
//!
//! * [`Translator`] — translate, rewrite, list models and warm a model up.
//! * [`TranslateRequest`] — everything one translation job needs.
//! * [`PromptPlan`] — the per-block prompt ladder, also used by `ofm prompt`.
//! * [`TranslationOutput`] — translated text plus warnings and metrics.
//! * [`TranslationError`] / [`ErrorKind`] — typed, localisable failures.
//! * [`model_listed`] — tolerant model-id matching for the Settings screen.
//!
//! # Example
//!
//! ```no_run
//! use ofm_config::{BackendConfig, BackendKind};
//! use ofm_i18n::LanguageTable;
//! use ofm_net::{TranslateRequest, Translator};
//! use ofm_text::{TranslationStyle, TranslationTone};
//!
//! # async fn run() -> Result<(), ofm_net::TranslationError> {
//! let config = BackendConfig {
//!     kind: BackendKind::Ollama,
//!     base_url: "http://127.0.0.1:11434".to_string(),
//!     model: "hy-mt2:7b".to_string(),
//!     ..BackendConfig::default()
//! };
//! let source = LanguageTable::get("uk").expect("ukrainian");
//! let target = LanguageTable::get("en").expect("english");
//! let output = Translator::new()
//!     .translate(TranslateRequest {
//!         text: "Привіт, світе.",
//!         source,
//!         source_explicit: true,
//!         target,
//!         style: TranslationStyle::Auto,
//!         tone: TranslationTone::Standard,
//!         config: &config,
//!         fallback: None,
//!         cancel: None,
//!         on_progress: None,
//!         on_partial: None,
//!     })
//!     .await?;
//! assert_eq!(output.text, "Hello, world.");
//! # Ok(())
//! # }
//! ```

#![forbid(unsafe_code)]
#![deny(missing_docs)]

mod budget;
mod error;
mod pipeline;
mod probe;
mod prompt;
mod request;
mod translator;
mod wire;

pub use crate::error::{ErrorKind, TranslationError};
pub use crate::probe::model_listed;
pub use crate::prompt::{first_prompt_for_text, PromptPlan};
pub use crate::request::{CancelFlag, PartialFn, ProgressFn, TranslateRequest, TranslationOutput};
pub use crate::translator::Translator;
pub use ofm_config::PromptFamily;
