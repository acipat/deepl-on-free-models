//! Rich clipboard to Markdown conversion.
//!
//! Copying from a browser puts HTML on the clipboard and copying from a word
//! processor puts RTF there; converting both to Markdown before translation
//! keeps headings, lists, links and emphasis instead of flattening everything
//! to plain text.  The HTML and RTF converters are pure functions; the
//! clipboard helpers are the only part that touches the operating system.

pub mod clipboard;
pub mod html;
pub mod rtf;

pub use clipboard::{
    clipboard_markdown, clipboard_text, markdown_from_sources, set_clipboard_text,
};
pub use html::{html_to_markdown, looks_like_html};
pub use rtf::rtf_to_markdown;
