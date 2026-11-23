//! Durable local state for DeepL-oFM: translation history and API keys.
//!
//! This crate is a Rust port of `windows/deepl_ofm/services/history.py` and
//! `windows/deepl_ofm/services/secrets.py`. It owns two small JSON documents
//! and nothing else, so it builds and tests without a network, a UI toolkit or
//! any platform credential library (see the fallback rules below).
//!
//! # Storage layout
//!
//! Both stores live in one folder: `%APPDATA%\DeepL-oFM` on Windows, and
//! `$XDG_CONFIG_HOME/DeepL-oFM` (or `~/.config/DeepL-oFM`) everywhere else.
//!
//! `history.json` is a JSON **array**, newest entry first, capped at
//! [`HistoryStore::LIMIT`] entries:
//!
//! ```json
//! [
//!   {
//!     "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
//!     "date": "2026-05-04T07:08:09Z",
//!     "source_text": "Hello",
//!     "translated_text": "Привіт",
//!     "source_code": "en",
//!     "target_code": "uk",
//!     "style": "auto",
//!     "tone": "standard",
//!     "engine": "ollama",
//!     "duration_ms": 830
//!   }
//! ]
//! ```
//!
//! The secret file is a JSON **object**. The `plain` backend stores the values
//! verbatim; the `dpapi` backend stores base64-encoded DPAPI blobs:
//!
//! ```json
//! {
//!   "version": 1,
//!   "backend": "plain",
//!   "values": { "provider:openai": "sk-…" }
//! }
//! ```
//!
//! # Failure rules
//!
//! * Files are written atomically (temporary sibling, `fsync`, `rename`), so a
//!   reader never observes a truncated document.
//! * A corrupt or unreadable file is logged, flagged through
//!   [`HistoryStore::has_storage_error`], and replaced only by the next
//!   successful write.
//! * Secret `read`/`write`/`delete` degrade to an empty value instead of
//!   panicking or propagating an error.
//!
//! # Platform notes
//!
//! `keyring` 3.x ships no credential backend unless a platform feature is
//! enabled (`windows-native`, `apple-native`, …); without one it hands out an
//! in-memory mock. [`SecretStore::new`] probes the active backend at runtime and
//! rejects non-persistent or mock backends, falling back to the file store:
//! DPAPI-encrypted `secrets.dat` on Windows, an owner-only `secrets.json`
//! elsewhere. Enabling the upstream features later makes the platform store win
//! automatically — no code change is needed here.
//!
//! # Deliberate differences from the Python port
//!
//! * `HistoryEntry::date` is UTC with a `Z` suffix (the contract asks for UTC;
//!   Python wrote local time with an offset). Sorting and display are unchanged
//!   because the format stays ISO-8601.
//! * `search` lower-cases with [`str::to_lowercase`] rather than Python's
//!   `str.casefold`; the two differ only for a few exotic code points (`ß`,
//!   Turkish dotted `İ`) and both match ASCII and Cyrillic text identically.
//! * No user-facing strings are produced here. The UI translates
//!   [`HistoryStore::STORAGE_ERROR_KEY`] with `ofm-i18n`; this crate must not
//!   depend on the translation layer.
//! * DPAPI is reached through a small hand-written `crypt32` binding instead of
//!   `windows-sys`, so the crate keeps building on Linux.

#![deny(missing_docs)]

use std::sync::{Mutex, MutexGuard};

mod atomic;
mod dpapi;
mod error;
mod history;
mod paths;
mod secrets;

#[cfg(test)]
mod test_support;

pub use history::{HistoryEntry, HistoryStore};
pub use secrets::SecretStore;

/// Lock a mutex, recovering the data when another thread panicked while
/// holding it.
///
/// The stores never panic while holding a lock, but treating poisoning as fatal
/// would let one unrelated panic permanently break the history UI.
pub(crate) fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}
