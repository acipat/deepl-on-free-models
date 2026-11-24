//! Operating-system clipboard access.
//!
//! Rich clipboard flavours are converted to Markdown by [`super::html`] and
//! [`super::rtf`]; this module only moves data in and out of the clipboard.
//!
//! **Known approximation:** `arboard` exposes the HTML and plain-text flavours
//! but not the `text/rtf` flavour, so [`clipboard_markdown`] cannot read RTF
//! from the system clipboard.  The RTF converter is still public and is used by
//! callers that have the raw data (and by the tests).

use arboard::Clipboard;
use log::debug;

use super::html::{html_to_markdown, looks_like_html};
use super::rtf::rtf_to_markdown;

/// Pick Markdown from the clipboard flavours that are available.
///
/// Mirrors the Python `mime_to_markdown`: HTML wins over RTF, an empty or
/// failed conversion falls back to the next flavour, and plain text is the last
/// resort.
pub fn markdown_from_sources(plain: &str, html: Option<&str>, rtf: Option<&str>) -> String {
    if let Some(html) = html {
        if looks_like_html(html) {
            let converted = html_to_markdown(html);
            if !converted.trim().is_empty() {
                return converted;
            }
        }
    }
    if let Some(rtf) = rtf {
        if !rtf.is_empty() {
            let converted = rtf_to_markdown(rtf);
            if !converted.trim().is_empty() {
                return converted;
            }
        }
    }
    plain.to_string()
}

/// Markdown for the current clipboard contents, or `None` when it is empty.
///
/// HTML is converted when present and looks like markup; otherwise the plain
/// text flavour is returned unchanged.  Clipboard access failures are logged at
/// debug level and reported as `None`, never as a panic.
pub fn clipboard_markdown() -> Option<String> {
    let mut clipboard = match Clipboard::new() {
        Ok(clipboard) => clipboard,
        Err(error) => {
            debug!("clipboard is unavailable: {error}");
            return None;
        }
    };
    let html = clipboard.get().html().ok();
    let plain = clipboard.get_text().unwrap_or_default();
    if let Some(html) = html {
        if looks_like_html(&html) {
            let converted = html_to_markdown(&html);
            if !converted.trim().is_empty() {
                return Some(converted);
            }
        }
    }
    if plain.is_empty() {
        None
    } else {
        Some(plain)
    }
}

/// Plain text from the clipboard, or `None` when it holds no text.
pub fn clipboard_text() -> Option<String> {
    let mut clipboard = Clipboard::new().ok()?;
    clipboard.get_text().ok()
}

/// Put `text` on the clipboard, with optional HTML and RTF flavours.
///
/// The HTML flavour also carries `text` as its plain-text alternative.  `rtf`
/// is accepted for API compatibility but `arboard` cannot publish a `text/rtf`
/// flavour, so it is ignored with a debug log.
pub fn set_clipboard_text(text: &str, html: Option<&str>, rtf: Option<&str>) {
    let mut clipboard = match Clipboard::new() {
        Ok(clipboard) => clipboard,
        Err(error) => {
            debug!("clipboard is unavailable: {error}");
            return;
        }
    };
    let result = match html {
        Some(html) => clipboard.set_html(html, Some(text)),
        None => clipboard.set_text(text),
    };
    if let Err(error) = result {
        debug!("could not write the clipboard: {error}");
    }
    if rtf.is_some() {
        debug!("arboard cannot publish a text/rtf clipboard flavour; ignoring RTF");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn html_wins_over_plain_text() {
        assert_eq!(
            markdown_from_sources("Title Body", Some("<h2>Title</h2><p>Body</p>"), None),
            "## Title\n\nBody"
        );
    }

    #[test]
    fn html_that_is_plain_text_falls_back() {
        assert_eq!(
            markdown_from_sources("plain", Some("not markup"), None),
            "plain"
        );
    }

    #[test]
    fn rtf_only_flavour_is_converted() {
        assert_eq!(
            markdown_from_sources("", None, Some(r"{\rtf1 Hello \b bold\b0!}")),
            "Hello **bold**!"
        );
    }

    #[test]
    fn empty_rtf_conversion_falls_back() {
        assert_eq!(
            markdown_from_sources("fallback", None, Some(r"{\rtf1\par}")),
            "fallback"
        );
    }

    #[test]
    fn empty_html_conversion_falls_back() {
        assert_eq!(
            markdown_from_sources("fallback", Some("<script>var x = 1;</script>"), None),
            "fallback"
        );
    }

    #[test]
    fn plain_text_only_and_empty() {
        assert_eq!(markdown_from_sources("Hello", None, None), "Hello");
        assert_eq!(markdown_from_sources("", None, None), "");
    }

    #[test]
    fn clipboard_access_never_panics_without_a_display() {
        let _ = clipboard_text();
        let _ = clipboard_markdown();
    }
}
