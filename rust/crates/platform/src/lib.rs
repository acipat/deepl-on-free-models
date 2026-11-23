//! Platform services for DeepL-oFM.
//!
//! * [`pasteboard`] — HTML/RTF clipboard flavours to Markdown.
//! * [`markdown`] — Markdown back to HTML (for copying) and to plain text.
//! * [`selection`] — capture the text selected in the foreground application.
//! * [`hotkeys`] — system-wide shortcuts.
//! * [`speech`] — text to speech.
//!
//! Everything compiles on Linux; unsupported features return `false`/`None`
//! and log once instead of failing.  The real implementations live behind
//! `#[cfg(windows)]` / `#[cfg(target_os = "macos")]`.

#![warn(missing_docs)]

pub mod hotkeys;
pub mod markdown;
pub mod pasteboard;
pub mod selection;
pub mod speech;
