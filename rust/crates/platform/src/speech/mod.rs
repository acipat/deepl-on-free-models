//! Text-to-speech for source and translation.
//!
//! macOS uses the built-in `/usr/bin/say` voices, Windows drives SAPI through
//! the `windows` crate, and every other platform degrades to a silent no-op so
//! headless builds (and CI) still start normally.  Speech is truncated to
//! 4000 characters like the Python implementation.

mod platform;

pub use platform::Speaker;

/// Maximum number of characters handed to the speech engine.
pub(crate) const MAX_CHARS: usize = 4000;

/// One voice reported by `say -v ?`.
#[derive(Clone, Debug, PartialEq, Eq)]
#[allow(dead_code)] // used by the macOS backend and by the parser tests
pub(crate) struct SayVoice {
    pub name: String,
    pub locale: String,
}

/// Parse the output of `/usr/bin/say -v ?`.
///
/// Lines look like `Alex                en_US    # Most people recognize me`.
/// The locale token separates the (possibly multi-word) voice name from the
/// comment; lines without a locale are skipped.
#[allow(dead_code)] // used by the macOS backend and by the parser tests
pub(crate) fn parse_say_voice_list(output: &str) -> Vec<SayVoice> {
    let mut voices = Vec::new();
    for line in output.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let mut name_parts: Vec<&str> = Vec::new();
        let mut locale: Option<&str> = None;
        for token in trimmed.split_whitespace() {
            if token.starts_with('#') {
                break;
            }
            if looks_like_locale(token) {
                locale = Some(token);
                break;
            }
            name_parts.push(token);
        }
        let (Some(locale), false) = (locale, name_parts.is_empty()) else {
            continue;
        };
        voices.push(SayVoice {
            name: name_parts.join(" "),
            locale: locale.to_string(),
        });
    }
    voices
}

#[allow(dead_code)]
fn looks_like_locale(token: &str) -> bool {
    let Some((language, region)) = token.split_once('_') else {
        return false;
    };
    (2..=3).contains(&language.len())
        && language.bytes().all(|byte| byte.is_ascii_alphabetic())
        && (2..=3).contains(&region.len())
        && region.bytes().all(|byte| byte.is_ascii_alphanumeric())
}

/// `(id, label)` pairs for the `say -v ?` output, sorted by label.
#[allow(dead_code)] // used by the parser tests
pub(crate) fn parse_say_voices(output: &str) -> Vec<(String, String)> {
    let mut voices: Vec<(String, String)> = parse_say_voice_list(output)
        .into_iter()
        .map(|voice| (voice.name.clone(), voice.name))
        .collect();
    voices.sort_by_key(|(_, label)| label.to_lowercase());
    voices
}

/// Whether `locale` (for example `pl_PL`) matches a language code (`pl`).
#[allow(dead_code)] // used by the macOS backend and by the parser tests
pub(crate) fn locale_matches(locale: &str, code: &str) -> bool {
    let locale = locale.to_ascii_lowercase().replace('-', "_");
    let code = code.to_ascii_lowercase().replace('-', "_");
    if code.is_empty() {
        return false;
    }
    locale == code || locale.starts_with(&format!("{code}_"))
}

/// Truncate `text` to [`MAX_CHARS`] characters, never splitting a code point.
#[allow(dead_code)] // used by the platform backends and by the tests
pub(crate) fn truncate(text: &str) -> &str {
    match text.char_indices().nth(MAX_CHARS) {
        Some((index, _)) => &text[..index],
        None => text,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "\
Alex                en_US    # Most people recognize me by my voice.
Alice               it_IT    # Ciao, mi chiamo Alice.
Bad News            en_US    # Hello, my name is Bad News.
Zosia               pl_PL    # Witaj, nazywam się Zosia.
# a comment line
";

    #[test]
    fn parses_say_voice_list() {
        let voices = parse_say_voice_list(SAMPLE);
        assert_eq!(voices.len(), 4);
        assert_eq!(voices[0].name, "Alex");
        assert_eq!(voices[0].locale, "en_US");
        assert_eq!(voices[2].name, "Bad News");
        assert_eq!(voices[2].locale, "en_US");
        assert_eq!(voices[3].name, "Zosia");
    }

    #[test]
    fn voice_pairs_are_sorted_by_label() {
        let voices = parse_say_voices(SAMPLE);
        let labels: Vec<&str> = voices.iter().map(|(_, label)| label.as_str()).collect();
        assert_eq!(labels, ["Alex", "Alice", "Bad News", "Zosia"]);
        assert_eq!(voices[0].0, "Alex");
    }

    #[test]
    fn malformed_voice_lines_are_skipped() {
        assert!(parse_say_voice_list("").is_empty());
        assert!(parse_say_voice_list("no locale here").is_empty());
        assert!(parse_say_voice_list("Name xx # comment").is_empty());
    }

    #[test]
    fn locale_matching() {
        assert!(locale_matches("pl_PL", "pl"));
        assert!(locale_matches("en-US", "en"));
        assert!(locale_matches("pt_BR", "pt_BR"));
        assert!(!locale_matches("pl_PL", "en"));
        assert!(!locale_matches("pl_PL", ""));
    }

    #[test]
    fn truncation_keeps_four_thousand_characters() {
        assert_eq!(MAX_CHARS, 4000);
        let short = "hello";
        assert_eq!(truncate(short), short);

        let long = "я".repeat(MAX_CHARS + 10);
        let cut = truncate(&long);
        assert_eq!(cut.chars().count(), MAX_CHARS);
        assert!(long.starts_with(cut));
    }

    #[cfg(not(any(windows, target_os = "macos")))]
    #[test]
    fn unsupported_platform_is_a_noop() {
        let speaker = Speaker::new();
        assert!(!speaker.is_available());
        assert!(speaker.voices().is_empty());
        assert!(!speaker.speak("Hello", "", "en"));
        assert!(!speaker.speak("Привіт", "any", ""));
        speaker.stop();
        assert!(!speaker.is_speaking());
        assert_eq!(Speaker::MAX_CHARS, MAX_CHARS);
    }
}
