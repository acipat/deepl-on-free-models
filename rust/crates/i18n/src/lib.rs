//! Interface localisation, language metadata and script based detection for
//! DeepL-oFM.
//!
//! This crate is the Rust port of `windows/deepl_ofm/core/languages.py` and
//! `windows/deepl_ofm/i18n/`, which in turn mirror the Swift
//! `Sources/HyMT/Support/Localization.swift` and
//! `Sources/HyMT/Models/Language.swift`.
//!
//! * [`AppLanguage`] — the nine interface languages plus `System`.
//! * [`Language`] / [`LanguageTable`] — the 38 translation languages and the
//!   script based detector.
//! * [`t`] / [`t_in`] / [`tf`] — catalogue lookup with `printf` placeholders.
//!
//! The catalogue, the language registry, the localised display names and the
//! detector's word lists are **generated** by `rust/scripts/gen_i18n.py` and
//! committed as `catalog.rs` / `language_data.rs`; nothing in this crate is
//! retyped from a source table by hand.
//!
//! # Examples
//!
//! ```
//! use ofm_i18n::{t_in, AppLanguage, LanguageTable};
//!
//! // English is the identity mapping, so a key translates to itself.
//! assert_eq!(t_in("Settings", AppLanguage::En), "Settings");
//! assert_eq!(t_in("Settings", AppLanguage::Uk), "Налаштування");
//!
//! let language = LanguageTable::detect("Это русский текст про перевод", AppLanguage::En);
//! assert_eq!(language.map(|found| found.code), Some("ru"));
//! ```

#![deny(missing_docs)]
#![deny(rustdoc::broken_intra_doc_links)]

mod app_language;
mod catalog;
mod language;
mod language_data;
mod localize;

pub use app_language::AppLanguage;
pub use language::{Language, LanguageTable};
pub use localize::{available_languages, catalogue, current_language, set_language, t, t_in, tf};
