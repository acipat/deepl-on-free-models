//! Per-line helpers: Markdown detection, mixed id/description lines, output
//! validation and source-language prefixes.
//!
//! These are the pure functions of `translation.py`; everything async lives in
//! [`crate::translator`].

use std::sync::OnceLock;

use fancy_regex::Regex;

use ofm_i18n::Language;
use ofm_text::OutputSanitizer;

/// Python's `str.isalpha()`: a letter of category `L*`.
///
/// Rust's [`char::is_alphabetic`] follows the Unicode `Alphabetic` property,
/// which also covers letter-numbers such as `Ⅻ` (Nl) and some combining marks.
/// Python's predicate does not, so a roman-numeral-only line is passed through
/// untranslated by the reference implementation and must be here too.
pub(crate) fn is_letter(character: char) -> bool {
    character.is_alphabetic() && !character.is_numeric()
}

/// Python's `str.isspace()`.
///
/// The Unicode `White_Space` property ([`char::is_whitespace`]) misses the
/// ASCII separators U+001C–U+001F, which Python counts as whitespace.
pub(crate) fn is_python_space(character: char) -> bool {
    character.is_whitespace() || matches!(character, '\u{1c}'..='\u{1f}')
}

/// Python's `str.strip()`.
pub(crate) fn trim_python(text: &str) -> &str {
    text.trim_matches(is_python_space)
}

/// Python's `str.isdigit()` for the digit loops of the port.
fn is_digit(character: char) -> bool {
    character.is_numeric()
}

/// Split `text` like Python's `str.splitlines()`.
///
/// Rust's [`str::lines`] only knows `\n` and `\r\n`; Python also breaks on
/// `\r`, `\v`, `\f`, U+001C–U+001E, U+0085, U+2028 and U+2029.
fn python_lines(text: &str) -> Vec<&str> {
    fn is_break(character: char) -> bool {
        matches!(
            character,
            '\n' | '\r'
                | '\u{0b}'
                | '\u{0c}'
                | '\u{1c}'
                | '\u{1d}'
                | '\u{1e}'
                | '\u{85}'
                | '\u{2028}'
                | '\u{2029}'
        )
    }

    let mut lines = Vec::new();
    let mut start = 0usize;
    let mut characters = text.char_indices().peekable();
    while let Some((offset, character)) = characters.next() {
        if !is_break(character) {
            continue;
        }
        lines.push(&text[start..offset]);
        let mut width = character.len_utf8();
        if character == '\r' {
            if let Some(&(_, next)) = characters.peek() {
                if next == '\n' {
                    characters.next();
                    width += 1;
                }
            }
        }
        start = offset + width;
    }
    if start < text.len() {
        lines.push(&text[start..]);
    }
    lines
}

/// True when `text` looks like Markdown and the prompt should ask the model to
/// preserve its syntax. Byte-for-byte port of `MarkdownDetector.swift`.
fn markdown_patterns() -> &'static [Regex] {
    static PATTERNS: OnceLock<Vec<Regex>> = OnceLock::new();
    PATTERNS.get_or_init(|| {
        [
            r"(?m)^\s{0,3}#{1,6}\s+\S",        // heading
            r"(?m)^\s{0,3}[-*+]\s+\S",         // unordered list
            r"(?m)^\s{0,3}\d+[.)]\s+\S",       // ordered list
            r"(?m)^\s{0,3}>\s+\S",             // block quote
            r"\*\*[^*\n]+\*\*",                // bold
            r"__[^_\n]+__",                    // bold
            r"(?<![\w*])\*[^*\n]+\*(?![\w*])", // italic
            r"(?<![\w_])_[^_\n]+_(?![\w_])",   // italic
            r"`[^`\n]+`",                      // inline code
            r"\[[^\]]+\]\([^)\s]+\)",          // link
        ]
        .iter()
        .filter_map(|pattern| Regex::new(pattern).ok())
        .collect()
    })
}

/// True when `text` contains Markdown structure or inline formatting.
pub(crate) fn contains_markdown(text: &str) -> bool {
    markdown_patterns()
        .iter()
        .any(|pattern| pattern.is_match(text).unwrap_or(false))
}

/// Collapse whitespace runs that contain a newline into a single space.
///
/// Port of `re.sub(r"\s*\n\s*", " ", cleaned)` from the Python validator.
fn collapse_line_breaks(text: &str) -> String {
    static COLLAPSE: OnceLock<Option<Regex>> = OnceLock::new();
    let pattern = COLLAPSE.get_or_init(|| Regex::new(r"\s*\n\s*").ok());
    match pattern {
        Some(pattern) => pattern.replace_all(text, " ").into_owned(),
        None => text.to_string(),
    }
}

/// Split `"id, id — description"` so the ids stay byte-for-byte.
///
/// Returns `(keep, translatable)`: the id list plus its separator, and the
/// description that may be translated.
pub(crate) fn split_mixed_line(text: &str) -> Option<(String, String)> {
    const MARKER: &str = " \u{2014} ";
    let index = text.find(MARKER)?;
    let left = &text[..index];
    let right = trim_python(&text[index + MARKER.len()..]);
    if right.is_empty() {
        return None;
    }

    let latin = left
        .chars()
        .filter(|character| matches!(character, 'A'..='Z' | 'a'..='z' | '0'..='9' | '['..='`'))
        .count();
    let cyrillic = left
        .chars()
        .filter(|character| ('\u{0400}'..='\u{04FF}').contains(character))
        .count();
    if latin < 8 || latin <= cyrillic * 2 {
        return None;
    }

    let pieces: Vec<&str> = left.split(',').map(trim_python).collect();
    let looks_like_ids = !pieces.is_empty()
        && pieces.iter().all(|piece| {
            !piece.is_empty()
                && !piece.chars().any(is_python_space)
                && piece
                    .chars()
                    .any(|character| matches!(character, '/' | ':' | '.' | '-'))
                && piece.chars().any(is_digit)
        });
    if !looks_like_ids {
        return None;
    }
    Some((format!("{left}{MARKER}"), right.to_string()))
}

/// Structural Markdown fingerprint (`#`, `>`, bullets and ordered list items).
///
/// Used to reject a translation that dropped or invented structure.
pub(crate) fn markdown_structure(text: &str) -> Vec<String> {
    let mut structure = Vec::new();
    for line in python_lines(text) {
        let body = line.trim_start_matches([' ', '\t']);
        if body.is_empty() {
            continue;
        }
        let characters: Vec<char> = body.chars().collect();
        let first = characters[0];
        let mut prefix_length = 0;
        while prefix_length < characters.len() && characters[prefix_length] == first {
            prefix_length += 1;
        }
        let rest = &characters[prefix_length..];
        if matches!(first, '#' | '>') {
            if rest
                .first()
                .is_some_and(|character| is_python_space(*character))
            {
                structure.push(characters[..prefix_length].iter().collect());
            }
            continue;
        }
        if matches!(first, '-' | '+' | '*')
            && prefix_length == 1
            && rest
                .first()
                .is_some_and(|character| is_python_space(*character))
        {
            structure.push("bullet".to_string());
            continue;
        }
        let mut digits = 0;
        while digits < characters.len() && is_digit(characters[digits]) {
            digits += 1;
        }
        if digits > 0
            && digits < characters.len()
            && matches!(characters[digits], '.' | ')')
            && characters
                .get(digits + 1)
                .is_some_and(|character| is_python_space(*character))
        {
            structure.push("number".to_string());
        }
    }
    structure
}

/// Prefix the prompt with the detected source language, unless it is unknown.
pub(crate) fn with_source_language(prompt: String, source: Option<&Language>) -> String {
    match source {
        Some(language) if !language.is_auto() => {
            format!("The source language is {}. {prompt}", language.english_name)
        }
        _ => prompt,
    }
}

/// Validate one candidate translation; `None` means "retry".
///
/// The U+FFFD guard runs on the raw stream first, then the preamble and the
/// chat-template wrappers are stripped, newlines are collapsed for single-line
/// blocks and [`OutputSanitizer::is_degenerate`] makes the final call.
pub(crate) fn validated(
    raw: &str,
    source: &str,
    target: &Language,
    preserve_line_breaks: bool,
) -> Option<String> {
    if raw.contains('\u{FFFD}') {
        return None;
    }
    let candidate = OutputSanitizer::strip_preamble(raw, source);
    let mut cleaned = OutputSanitizer::clean(&candidate);
    if !preserve_line_breaks {
        cleaned = collapse_line_breaks(&cleaned);
    }
    let cleaned = trim_python(&cleaned).to_string();
    if cleaned.is_empty() {
        return None;
    }
    if OutputSanitizer::is_degenerate(source, &cleaned, target).is_some() {
        return None;
    }
    Some(cleaned)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ofm_i18n::LanguageTable;

    fn language(code: &str) -> &'static Language {
        LanguageTable::get(code).expect("language")
    }

    #[test]
    fn detects_headings_lists_and_inline_markup() {
        assert!(contains_markdown("# Title"));
        assert!(contains_markdown("- item"));
        assert!(contains_markdown("1. item"));
        assert!(contains_markdown("> quote"));
        assert!(contains_markdown("some **bold** text"));
        assert!(contains_markdown("a [link](https://example.test)"));
        assert!(contains_markdown("`code`"));
        assert!(!contains_markdown("plain sentence without markup"));
        assert!(!contains_markdown("2 * 3 = 6"));
    }

    #[test]
    fn collapses_newlines_into_single_spaces() {
        assert_eq!(collapse_line_breaks("a \n b"), "a b");
        assert_eq!(collapse_line_breaks("a\n\nb"), "a b");
        assert_eq!(collapse_line_breaks("no break"), "no break");
    }

    #[test]
    fn splits_a_mixed_id_and_description_line() {
        let line = "item-1, item-2 \u{2014} two things to translate";
        let (keep, rest) = split_mixed_line(line).expect("mixed");
        assert_eq!(keep, "item-1, item-2 \u{2014} ");
        assert_eq!(rest, "two things to translate");
        assert!(split_mixed_line("no separator here").is_none());
        assert!(split_mixed_line("a \u{2014} ").is_none());
        assert!(
            split_mixed_line("\u{041f}\u{0440}\u{0438}\u{0432}\u{0456}\u{0442} \u{2014} x")
                .is_none()
        );
    }

    #[test]
    fn unicode_predicates_follow_python() {
        // Python's `str.isalpha()` is false for letter-numbers (`Ⅻ`, Nl).
        assert!(!is_letter('\u{216B}'));
        assert!(is_letter('A'));
        assert!(is_letter('\u{041F}'));
        // Python's `str.isspace()` includes the ASCII separators.
        assert!(is_python_space('\u{1f}'));
        assert!(is_python_space(' '));
        assert!(!is_python_space('a'));
        assert_eq!(trim_python(" \u{1f}x\u{1f} "), "x");
        // Python's `str.splitlines()` breaks on more than LF.
        assert_eq!(
            python_lines("a\u{0b}b\u{2028}c\rd\r\ne"),
            vec!["a", "b", "c", "d", "e"]
        );
        assert_eq!(python_lines("a\n"), vec!["a"]);
        assert!(python_lines("").is_empty());
    }

    #[test]
    fn split_mixed_line_uses_unicode_digit_and_space_rules() {
        // U+0661 (ARABIC-INDIC DIGIT ONE) is a digit for Python too.
        let line = "identifier-\u{0661}, id-2 \u{2014} desc";
        let (keep, rest) = split_mixed_line(line).expect("mixed");
        assert_eq!(keep, "identifier-\u{0661}, id-2 \u{2014} ");
        assert_eq!(rest, "desc");
        // U+001F is whitespace in Python, so the id list is rejected.
        assert!(split_mixed_line("ident\u{1f}ier-1, id-2 \u{2014} desc").is_none());
    }

    #[test]
    fn markdown_structure_tracks_headings_and_items() {
        assert_eq!(markdown_structure("# One\n## Two"), vec!["#", "##"]);
        assert_eq!(
            markdown_structure("- a\n1. b\n> q"),
            vec!["bullet", "number", ">"]
        );
        assert!(markdown_structure("plain").is_empty());
    }

    #[test]
    fn source_language_prefix_skips_auto() {
        assert_eq!(
            with_source_language("Translate.".to_string(), Some(language("uk"))),
            "The source language is Ukrainian. Translate."
        );
        assert_eq!(
            with_source_language("Translate.".to_string(), Some(language("auto"))),
            "Translate."
        );
        assert_eq!(
            with_source_language("Translate.".to_string(), None),
            "Translate."
        );
    }

    #[test]
    fn validation_rejects_replacement_characters_and_empty_output() {
        assert!(validated("Hello\u{FFFD}", "Привіт.", language("en"), false).is_none());
        assert!(validated("   ", "Привіт.", language("en"), false).is_none());
    }

    #[test]
    fn validation_accepts_a_normal_translation() {
        let cleaned = validated("Hello, world.", "Привіт, світе.", language("en"), false);
        assert_eq!(cleaned.as_deref(), Some("Hello, world."));
    }

    #[test]
    fn validation_strips_a_preamble() {
        let raw = "Here is the translation: Hello.";
        let cleaned = validated(raw, "Привіт.", language("en"), false);
        assert_eq!(cleaned.as_deref(), Some("Hello."));
    }

    #[test]
    fn validation_keeps_line_breaks_when_asked() {
        let cleaned = validated("line one\nline two", "a\nb", language("en"), true);
        assert_eq!(cleaned.as_deref(), Some("line one\nline two"));
    }
}
