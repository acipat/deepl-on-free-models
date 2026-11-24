//! Configuration model of DeepL-oFM: providers, the curated model catalogue,
//! keyboard shortcuts and the JSON backed application settings.
//!
//! This crate is a Rust port of `windows/deepl_ofm/core/providers.py`,
//! `catalog.py`, `keycombo.py` and `settings.py`, which are themselves ports of
//! the Swift models. It depends only on `ofm-i18n` (for interface languages and
//! provider descriptions), so the app layer can use it without a UI toolkit.
//!
//! ```no_run
//! use ofm_config::{AppSettings, Provider};
//!
//! let mut settings = AppSettings::load();
//! settings.apply_provider(Provider::Groq, Some("openai/gpt-oss-120b"));
//! let config = settings.snapshot();
//! assert_eq!(config.base_url, "https://api.groq.com/openai/v1");
//! ```
//!
//! API keys are deliberately **not** persisted here: the settings file never
//! contains one, and `ofm-store` owns the secret store. Style and tone are plain
//! strings so that this crate does not depend on `ofm-text`.

#![deny(missing_docs)]

pub mod catalog;
pub mod keycombo;
pub mod providers;
pub mod settings;

pub use catalog::{CatalogEntry, ModelCatalog, PromptFamily};
pub use keycombo::KeyCombo;
pub use providers::{BackendConfig, BackendKind, Provider};
pub use settings::AppSettings;

/// Interface language, re-exported so `AppSettings` users need one import less.
pub use ofm_i18n::AppLanguage;
