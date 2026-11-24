//! Line-oriented chunking and recomposition for the translation pipeline.
//!
//! Port of `windows/deepl_ofm/core/chunker.py`, which follows
//! `Sources/HyMT/Services/TranslationService.swift` (`TextChunk` /
//! `TextChunker`). Every non-empty source line becomes a chunk, lines longer
//! than [`TextChunker::LINE_LIMIT`] are additionally split by sentences, and a
//! fenced code block stays a single chunk. The Markdown marker (`## ` / `- ` /
//! `1. ` / `> ` / `- [ ] `) is kept aside so it can be re-attached to the
//! translated text, and the exact number of newlines between lines is stored on
//! the chunk so [`TextChunker::compose`] renders the original layout again.

use std::sync::OnceLock;

use regex::Regex;
use thiserror::Error;

const HEADING_PREFIX: &str = r"^(\s*#{1,6}\s+)(.+)$";
const QUOTE_PREFIX: &str = r"^(\s*>\s+)(.+)$";
const LIST_PREFIX: &str =
    r"^(\s*(?:[-*\u{2022}\u{2013}\u{2014}]|\d+[.)])\s+(?:\[[ xX]\]\s+)?)(.+)$";

/// Sentence terminators recognised by the sentence splitter.
const SENTENCE_TERMINATORS: [char; 7] = [
    '.', '!', '?', '\u{2026}', '\u{3002}', '\u{FF01}', '\u{FF1F}',
];

/// Characters that may trail a terminator without breaking the sentence.
const CLOSING_CHARACTERS: [char; 7] = ['"', '\'', '\u{201D}', '\u{2019}', '\u{00BB}', ')', ']'];

/// Longest plain-text line still recognised as a heading.
///
/// The old rule treated every block up to 80 characters as a heading, which
/// swallowed a short question and the selected style/tone with it. Only a line
/// that also looks like a title (no terminal punctuation, capitalised) keeps
/// the heading prompt now.
const PLAIN_HEADING_LIMIT: usize = 80;

/// Common abbreviations whose period does not end a sentence.
const ABBREVIATIONS: [&str; 22] = [
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "fig", "figs", "no", "vol",
    "pp", "inc", "ltd", "corp", "approx", "dept", "al", "e.g",
];

static HEADING_RE: OnceLock<Option<Regex>> = OnceLock::new();
static QUOTE_RE: OnceLock<Option<Regex>> = OnceLock::new();
static LIST_RE: OnceLock<Option<Regex>> = OnceLock::new();

/// Compile `pattern` once; a malformed pattern simply matches nothing.
fn compiled(slot: &'static OnceLock<Option<Regex>>, pattern: &str) -> Option<&'static Regex> {
    slot.get_or_init(|| Regex::new(pattern).ok()).as_ref()
}

/// One translatable unit: a Markdown prefix plus the text to translate.
#[derive(Clone, Debug, PartialEq)]
pub struct TextChunk {
    /// Markdown marker that is re-attached verbatim (`"## "`, `"- "`, …).
    pub prefix: String,
    /// Text without the prefix.
    pub text: String,
    /// Whether the prefix is an ATX heading marker.
    pub is_heading: bool,
    /// Fenced code block, passed through untranslated.
    pub is_code: bool,
    /// Separator rendered before this chunk (`"\n"` or `"\n\n"`).
    pub separator_before: String,
    /// Zero-based position in the chunk list.
    pub index: usize,
}

impl TextChunk {
    /// Build a chunk with the documented defaults (`"\n"`, not code, index 0).
    pub fn new(prefix: &str, text: &str, is_heading: bool, index: usize) -> Self {
        Self {
            prefix: prefix.to_string(),
            text: text.to_string(),
            is_heading,
            is_code: false,
            separator_before: "\n".to_string(),
            index,
        }
    }
}

/// Errors returned by [`TextChunker::compose`].
#[derive(Clone, Debug, PartialEq, Eq, Error)]
pub enum ChunkError {
    /// The caller supplied a different number of translations than chunks.
    #[error("expected {expected} translated chunks, got {got}")]
    LengthMismatch {
        /// Number of chunks.
        expected: usize,
        /// Number of translations supplied.
        got: usize,
    },
}

/// Splits source text into chunks and rebuilds the document from them.
pub struct TextChunker;

impl TextChunker {
    /// Longer lines are split by sentences (Swift's `TextChunker.limit`).
    pub const LINE_LIMIT: usize = 3200;

    /// Normalise CRLF and CR line endings to LF.
    pub fn normalize(text: &str) -> String {
        text.replace("\r\n", "\n").replace('\r', "\n")
    }

    /// Iterate over normalised lines and mark fenced code, including the fences.
    pub fn lines_with_code(text: &str) -> impl Iterator<Item = (&str, bool)> {
        let mut open = None;
        text.split('\n').map(move |line| {
            if let Some(marker) = open {
                if closes_fence(line, marker) {
                    open = None;
                }
                (line, true)
            } else {
                open = fence_marker(line);
                (line, open.is_some())
            }
        })
    }

    /// Split `text` into one chunk per non-empty line.
    ///
    /// Leading and trailing blank lines are dropped (Swift behaviour); the
    /// number of blank lines between two chunks is preserved in
    /// [`TextChunk::separator_before`]. A fenced code block becomes a single
    /// chunk with [`TextChunk::is_code`] set so it is never sentence-split.
    pub fn split(text: &str) -> Vec<TextChunk> {
        let normalized = Self::normalize(text);
        let lines: Vec<&str> = normalized.split('\n').collect();
        let mut chunks: Vec<TextChunk> = Vec::new();
        let mut pending_line_breaks = 0usize;
        let mut started = false;
        let mut position = 0usize;

        while position < lines.len() {
            let line = lines[position];
            if line.trim().is_empty() {
                if started {
                    pending_line_breaks += 1;
                }
                position += 1;
                continue;
            }

            let separator = if chunks.is_empty() {
                String::new()
            } else {
                "\n".repeat((pending_line_breaks + 1).max(1))
            };

            if let Some(marker) = fence_marker(line) {
                let mut block: Vec<&str> = vec![line];
                position += 1;
                while position < lines.len() {
                    block.push(lines[position]);
                    if closes_fence(lines[position], marker) {
                        position += 1;
                        break;
                    }
                    position += 1;
                }
                chunks.push(TextChunk {
                    prefix: String::new(),
                    text: block.join("\n"),
                    is_heading: false,
                    is_code: true,
                    separator_before: separator,
                    index: 0,
                });
                started = true;
                pending_line_breaks = 0;
                continue;
            }

            let trimmed = line.trim_end();
            if trimmed.chars().count() <= Self::LINE_LIMIT {
                let (prefix, body, is_heading) = parse_prefix(trimmed);
                chunks.push(TextChunk {
                    prefix,
                    text: body,
                    is_heading,
                    is_code: false,
                    separator_before: separator,
                    index: 0,
                });
            } else {
                for (piece_index, piece) in
                    split_limited(trimmed, Self::LINE_LIMIT).iter().enumerate()
                {
                    let (prefix, body, is_heading) = parse_prefix(piece);
                    let piece_separator = if chunks.is_empty() || piece_index == 0 {
                        separator.clone()
                    } else {
                        " ".to_string()
                    };
                    chunks.push(TextChunk {
                        prefix,
                        text: body,
                        is_heading,
                        is_code: false,
                        separator_before: piece_separator,
                        index: 0,
                    });
                }
            }
            started = true;
            pending_line_breaks = 0;
            position += 1;
        }

        if chunks.is_empty() {
            // Swift returns one chunk carrying the original text for an empty
            // or whitespace-only document; keep that so compose() round-trips.
            return vec![TextChunk::new("", &normalized, false, 0)];
        }

        for (index, chunk) in chunks.iter_mut().enumerate() {
            chunk.index = index;
        }
        chunks
    }

    /// Reassemble `translated` using the layout stored on `chunks`.
    ///
    /// The first chunk has no separator of its own. Trailing blank lines are
    /// not reproduced (the chunks never store them), matching the Swift
    /// streaming output. Returns [`ChunkError::LengthMismatch`] when the number
    /// of translations differs from the number of chunks.
    pub fn compose(chunks: &[TextChunk], translated: &[String]) -> Result<String, ChunkError> {
        Self::compose_with(chunks, translated, false)
    }

    /// [`TextChunker::compose`] with an optional leading blank line.
    ///
    /// `leading_blank_line` prefixes the result with a single blank line for
    /// callers that translate paragraphs separately.
    pub fn compose_with(
        chunks: &[TextChunk],
        translated: &[String],
        leading_blank_line: bool,
    ) -> Result<String, ChunkError> {
        if chunks.len() != translated.len() {
            return Err(ChunkError::LengthMismatch {
                expected: chunks.len(),
                got: translated.len(),
            });
        }
        if chunks.is_empty() {
            return Ok(String::new());
        }
        let mut parts: Vec<&str> = Vec::with_capacity(chunks.len() * 2 + 1);
        if leading_blank_line {
            parts.push("\n");
        }
        for (index, (chunk, text)) in chunks.iter().zip(translated).enumerate() {
            if index > 0 {
                parts.push(if chunk.separator_before.is_empty() {
                    "\n"
                } else {
                    chunk.separator_before.as_str()
                });
            }
            parts.push(&chunk.prefix);
            parts.push(text);
        }
        Ok(parts.concat())
    }

    /// Split a block into trimmed, non-empty sentences (long-line fallback).
    pub fn split_sentences(text: &str) -> Vec<String> {
        let mut segments = segment_sentences(text);
        if segments.is_empty() {
            segments.push(text.to_string());
        }
        segments
            .into_iter()
            .map(|segment| segment.trim().to_string())
            .filter(|segment| !segment.is_empty())
            .collect()
    }
}

/// Split `text` at sentence boundaries, keeping terminal punctuation.
///
/// A pragmatic replacement for Foundation's `.bySentences` enumeration: a
/// terminator is followed by whitespace (or a line break) and a character that
/// does not start a lowercase word. Single-letter abbreviations and a small
/// list of common ones ("Mr.", "Dr.", "etc.") do not end a sentence.
fn segment_sentences(text: &str) -> Vec<String> {
    let chars: Vec<char> = text.chars().collect();
    let length = chars.len();
    let mut segments: Vec<String> = Vec::new();
    let mut start = 0usize;
    let mut index = 0usize;

    while index < length {
        if !SENTENCE_TERMINATORS.contains(&chars[index]) {
            index += 1;
            continue;
        }
        let mut end = index + 1;
        while end < length && SENTENCE_TERMINATORS.contains(&chars[end]) {
            end += 1;
        }
        while end < length && CLOSING_CHARACTERS.contains(&chars[end]) {
            end += 1;
        }
        if end >= length || !chars[end].is_whitespace() {
            index = end;
            continue;
        }
        let mut next_index = end;
        while next_index < length && chars[next_index].is_whitespace() {
            next_index += 1;
        }
        if next_index >= length {
            break;
        }
        let contains_newline = chars[end..next_index].contains(&'\n');
        let next_character = chars[next_index];
        let starts_sentence =
            contains_newline || next_character.is_uppercase() || !next_character.is_lowercase();
        if starts_sentence && !is_abbreviation(&chars, start, index) {
            segments.push(chars[start..end].iter().collect());
            start = next_index;
            index = next_index;
            continue;
        }
        index = end;
    }

    let tail: String = chars[start..].iter().collect();
    if !tail.is_empty() {
        segments.push(tail);
    }
    segments
}

/// True when the period at `terminator` closes a known abbreviation.
fn is_abbreviation(chars: &[char], start: usize, terminator: usize) -> bool {
    if chars.get(terminator) != Some(&'.') {
        return false;
    }
    let mut word: Vec<char> = Vec::new();
    let mut position = terminator;
    while position > start {
        position -= 1;
        let character = chars[position];
        if character.is_ascii_alphabetic() || ('\u{0400}'..='\u{04FF}').contains(&character) {
            word.push(character);
        } else {
            break;
        }
    }
    if word.is_empty() {
        return false;
    }
    if word.len() == 1 {
        return true;
    }
    word.reverse();
    let word: String = word.into_iter().collect();
    ABBREVIATIONS.contains(&word.to_lowercase().as_str())
}

/// Return `(character, length)` when `line` opens a fenced code block.
fn fence_marker(line: &str) -> Option<(char, usize)> {
    let stripped = line.trim_start();
    let mut characters = stripped.chars();
    let character = characters.next()?;
    if character != '`' && character != '~' {
        return None;
    }
    let count = stripped.chars().take_while(|c| *c == character).count();
    if count < 3 {
        return None;
    }
    Some((character, count))
}

/// True when `line` is a closing fence for the opening `marker`.
fn closes_fence(line: &str, marker: (char, usize)) -> bool {
    let (character, minimum) = marker;
    let stripped = line.trim_start();
    let count = stripped.chars().take_while(|c| *c == character).count();
    if count < minimum {
        return false;
    }
    // The fence characters are ASCII, so the char count is a byte count.
    stripped[count..].trim().is_empty()
}

/// Split a Markdown marker off `line` (`parseSegment` in Swift).
fn parse_prefix(line: &str) -> (String, String, bool) {
    let patterns = [
        compiled(&HEADING_RE, HEADING_PREFIX),
        compiled(&QUOTE_RE, QUOTE_PREFIX),
        compiled(&LIST_RE, LIST_PREFIX),
    ];
    for pattern in patterns.iter().flatten() {
        let Some(captures) = pattern.captures(line) else {
            continue;
        };
        let body = captures.get(2).map_or("", |m| m.as_str());
        if body.trim().is_empty() {
            continue;
        }
        let prefix = captures.get(1).map_or("", |m| m.as_str());
        let is_heading = prefix.trim_start().starts_with('#');
        return (prefix.to_string(), body.to_string(), is_heading);
    }
    (String::new(), line.to_string(), looks_like_heading(line))
}

/// True when an unprefixed line is structurally a heading.
///
/// A heading is short, has no terminal punctuation and starts every word with
/// a capitalised (or caseless, e.g. CJK) letter. A question such as
/// `Could you send me the report?` therefore stays a normal block and keeps the
/// user's style and tone.
fn looks_like_heading(text: &str) -> bool {
    let trimmed = text.trim();
    if trimmed.is_empty() || trimmed.chars().count() > PLAIN_HEADING_LIMIT {
        return false;
    }
    if ends_with_terminal_punctuation(trimmed) {
        return false;
    }
    let mut has_letter = false;
    for word in trimmed.split_whitespace() {
        let Some(first) = word.chars().find(|character| character.is_alphabetic()) else {
            continue;
        };
        has_letter = true;
        if first.is_lowercase() {
            return false;
        }
    }
    has_letter
}

/// True when `text` ends with sentence punctuation, ignoring closing quotes.
fn ends_with_terminal_punctuation(text: &str) -> bool {
    let mut characters = text.chars().rev().peekable();
    while characters
        .peek()
        .is_some_and(|character| CLOSING_CHARACTERS.contains(character))
    {
        characters.next();
    }
    characters
        .next()
        .is_some_and(|character| SENTENCE_TERMINATORS.contains(&character))
}

/// Split an over-long line by sentences, then by raw length (Swift logic).
fn split_limited(line: &str, limit: usize) -> Vec<String> {
    let limit = limit.max(1);
    let mut segments = segment_sentences(line);
    if segments.is_empty() {
        segments.push(line.to_string());
    }
    let mut pieces: Vec<String> = Vec::new();
    for segment in segments {
        let chars: Vec<char> = segment.chars().collect();
        if chars.len() <= limit {
            pieces.push(segment);
        } else {
            for piece in chars.chunks(limit) {
                pieces.push(piece.iter().collect());
            }
        }
    }
    pieces
        .into_iter()
        .map(|piece| piece.trim().to_string())
        .filter(|piece| !piece.is_empty())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn blank_line_is_preserved() {
        let chunks = TextChunker::split("One\n\nTwo");
        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[0].text, "One");
        assert_eq!(chunks[0].separator_before, "");
        assert_eq!(chunks[1].text, "Two");
        assert_eq!(chunks[1].separator_before, "\n\n");
    }

    #[test]
    fn single_line_break() {
        let chunks = TextChunker::split("One\nTwo");
        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[1].separator_before, "\n");
    }

    #[test]
    fn multiple_blank_lines() {
        let chunks = TextChunker::split("One\n\n\nTwo");
        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[1].separator_before, "\n\n\n");
    }

    #[test]
    fn trailing_blank_lines_ignored() {
        let chunks = TextChunker::split("One\n\n");
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].text, "One");
    }

    #[test]
    fn long_line_splits_into_pieces() {
        let line = "word ".repeat(800);
        let chunks = TextChunker::split(&line);
        assert!(chunks.len() > 1);
        assert_eq!(chunks[1].separator_before, " ");
    }

    #[test]
    fn windows_line_endings_are_normalized() {
        let chunks = TextChunker::split("One\r\n\r\nTwo\r\nThree");
        assert_eq!(chunks.len(), 3);
        assert_eq!(chunks[0].text, "One");
        assert_eq!(chunks[1].separator_before, "\n\n");
        assert_eq!(chunks[2].separator_before, "\n");
        assert!(chunks.iter().all(|chunk| !chunk.text.contains('\r')));
    }

    #[test]
    fn sentence_splitter() {
        assert_eq!(
            TextChunker::split_sentences("First sentence. Second sentence! Third one?"),
            vec!["First sentence.", "Second sentence!", "Third one?"]
        );
    }

    #[test]
    fn empty_string_keeps_one_empty_chunk() {
        let chunks = TextChunker::split("");
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].text, "");
        assert_eq!(chunks[0].prefix, "");
        assert_eq!(
            TextChunker::compose(&chunks, &[String::new()]),
            Ok(String::new())
        );
    }

    #[test]
    fn whitespace_only_input_is_preserved() {
        let chunks = TextChunker::split("   \n  ");
        assert_eq!(chunks.len(), 1);
        assert_eq!(
            TextChunker::compose(&chunks, &[chunks[0].text.clone()]),
            Ok("   \n  ".to_string())
        );
    }

    #[test]
    fn normalize_handles_mixed_line_endings() {
        assert_eq!(
            TextChunker::normalize("a\r\nb\rc\nd\r\n\r\ne"),
            "a\nb\nc\nd\n\ne"
        );
    }

    #[test]
    fn normalize_is_idempotent() {
        let value = "One\r\nTwo\rThree\nFour";
        assert_eq!(
            TextChunker::normalize(&TextChunker::normalize(value)),
            "One\nTwo\nThree\nFour"
        );
    }

    #[test]
    fn short_questions_are_not_headings() {
        for text in [
            "Could you send me the report?",
            "Could you send me the report",
            "Is this ready?!",
            "Why\u{2026}",
        ] {
            let chunks = TextChunker::split(text);
            assert!(!chunks[0].is_heading, "{text:?} must stay a normal block");
        }
    }

    #[test]
    fn markdown_and_title_like_lines_are_headings() {
        for text in [
            "# Title",
            "## Section",
            "Introduction",
            "Report Summary",
            "  Overview",
        ] {
            let chunks = TextChunker::split(text);
            assert!(chunks[0].is_heading, "{text:?} must be a heading");
        }
        // Lists and quotes keep their own prefixes and are never headings.
        for text in ["- item", "1. step", "> quote", "lowercase fragment"] {
            let chunks = TextChunker::split(text);
            assert!(!chunks[0].is_heading, "{text:?} must not be a heading");
        }
    }

    #[test]
    fn long_title_like_lines_are_not_headings() {
        let text = "Word ".repeat(20);
        let chunks = TextChunker::split(&text);
        assert!(!chunks[0].is_heading);
    }

    #[test]
    fn markdown_prefixes_are_extracted() {
        let source = "# Title\n## Section\n- item\n1. step\n> quote\n- [ ] task\n* star";
        let chunks = TextChunker::split(source);
        let pairs: Vec<(String, String)> = chunks
            .iter()
            .map(|chunk| (chunk.prefix.clone(), chunk.text.clone()))
            .collect();
        assert_eq!(
            pairs,
            vec![
                ("# ".to_string(), "Title".to_string()),
                ("## ".to_string(), "Section".to_string()),
                ("- ".to_string(), "item".to_string()),
                ("1. ".to_string(), "step".to_string()),
                ("> ".to_string(), "quote".to_string()),
                ("- [ ] ".to_string(), "task".to_string()),
                ("* ".to_string(), "star".to_string()),
            ]
        );
        let headings: Vec<bool> = chunks.iter().map(|chunk| chunk.is_heading).collect();
        assert_eq!(
            headings,
            vec![true, true, false, false, false, false, false]
        );
    }

    #[test]
    fn checkbox_variants_are_prefixes() {
        let chunks = TextChunker::split("- [x] done\n- [X] also done");
        assert_eq!(chunks[0].prefix, "- [x] ");
        assert_eq!(chunks[1].prefix, "- [X] ");
    }

    #[test]
    fn nested_list_indentation_is_kept_in_the_prefix() {
        let chunks = TextChunker::split("  - nested");
        assert_eq!(chunks[0].prefix, "  - ");
        assert_eq!(chunks[0].text, "nested");
    }

    #[test]
    fn compose_restores_blank_lines_and_prefixes() {
        let source = "## Title\n\n- one\n1. two\n\n> quote";
        let chunks = TextChunker::split(source);
        let translated: Vec<String> = chunks
            .iter()
            .map(|chunk| chunk.text.to_uppercase())
            .collect();
        assert_eq!(
            TextChunker::compose(&chunks, &translated),
            Ok("## TITLE\n\n- ONE\n1. TWO\n\n> QUOTE".to_string())
        );
        let identical: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
        assert_eq!(
            TextChunker::compose(&chunks, &identical),
            Ok(source.to_string())
        );
    }

    #[test]
    fn compose_does_not_add_a_trailing_newline() {
        let chunks = TextChunker::split("One\nTwo\n\n");
        assert_eq!(
            TextChunker::compose(&chunks, &["1".to_string(), "2".to_string()]),
            Ok("1\n2".to_string())
        );
    }

    #[test]
    fn compose_leading_blank_line() {
        let chunks = TextChunker::split("One\nTwo");
        assert_eq!(
            TextChunker::compose_with(&chunks, &["One".to_string(), "Two".to_string()], true),
            Ok("\nOne\nTwo".to_string())
        );
    }

    #[test]
    fn compose_rejects_mismatched_lengths() {
        let chunks = TextChunker::split("One\nTwo");
        let error = TextChunker::compose(&chunks, &["only one".to_string()]);
        assert_eq!(
            error,
            Err(ChunkError::LengthMismatch {
                expected: 2,
                got: 1
            })
        );
        assert_eq!(
            error.map_err(|e| e.to_string()),
            Err("expected 2 translated chunks, got 1".to_string())
        );
    }

    #[test]
    fn indices_are_sequential() {
        let chunks = TextChunker::split("One\n\nTwo\n\nThree");
        let indices: Vec<usize> = chunks.iter().map(|chunk| chunk.index).collect();
        assert_eq!(indices, vec![0, 1, 2]);
    }

    #[test]
    fn fenced_code_block_is_one_chunk() {
        let source = "Before\n```python\nx = 1\n\nprint(x)\n```\nAfter";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 3);
        let flags: Vec<bool> = chunks.iter().map(|chunk| chunk.is_code).collect();
        assert_eq!(flags, vec![false, true, false]);
        assert_eq!(chunks[1].text, "```python\nx = 1\n\nprint(x)\n```");
        assert_eq!(chunks[1].separator_before, "\n");
        assert_eq!(chunks[2].separator_before, "\n");
        let identical: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
        assert_eq!(
            TextChunker::compose(&chunks, &identical),
            Ok(source.to_string())
        );
    }

    #[test]
    fn unclosed_fence_consumes_the_rest() {
        let source = "Intro\n```\ncode line\nmore code";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 2);
        assert!(chunks[1].is_code);
        assert_eq!(chunks[1].text, "```\ncode line\nmore code");
    }

    #[test]
    fn tilde_fenced_block() {
        let source = "~~~\na\n~~~";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 1);
        assert!(chunks[0].is_code);
        assert_eq!(chunks[0].text, source);
    }

    #[test]
    fn code_block_blank_lines_are_not_separators() {
        let source = "```\na\n\nb\n```";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].text, source);
    }

    #[test]
    fn long_markdown_line_keeps_its_prefix_on_the_first_piece() {
        let source = format!("## {}", "word ".repeat(800));
        let chunks = TextChunker::split(&source);
        assert!(chunks.len() > 1);
        assert_eq!(chunks[0].prefix, "## ");
        assert!(chunks[0].is_heading);
        assert!(chunks[1..].iter().all(|chunk| chunk.prefix.is_empty()));
        assert_eq!(chunks[1].separator_before, " ");
    }

    #[test]
    fn long_prose_paragraph_is_split_by_sentences() {
        let sentence = "This sentence is repeated to build a long paragraph of prose. ";
        let source = sentence.repeat(60);
        let chunks = TextChunker::split(&source);
        assert!(chunks.len() > 1, "long paragraph should be split");
        assert!(chunks
            .iter()
            .all(|chunk| chunk.text.chars().count() <= TextChunker::LINE_LIMIT));
        for chunk in &chunks[1..] {
            assert_eq!(chunk.separator_before, " ");
        }
    }

    #[test]
    fn split_sentences_edges() {
        assert_eq!(TextChunker::split_sentences(""), Vec::<String>::new());
        assert_eq!(TextChunker::split_sentences("   "), Vec::<String>::new());
        assert_eq!(
            TextChunker::split_sentences("No terminator here"),
            vec!["No terminator here"]
        );
        assert_eq!(
            TextChunker::split_sentences("One. Two."),
            vec!["One.", "Two."]
        );
        assert_eq!(
            TextChunker::split_sentences("Mr. Smith went home. He slept."),
            vec!["Mr. Smith went home.", "He slept."]
        );
        assert_eq!(
            TextChunker::split_sentences("He said \"Go.\" Then left."),
            vec!["He said \"Go.\"", "Then left."]
        );
    }

    #[test]
    fn sentence_split_keeps_ellipsis_and_closers() {
        assert_eq!(
            TextChunker::split_sentences("Wait... Really?! Yes."),
            vec!["Wait...", "Really?!", "Yes."]
        );
    }

    #[test]
    fn prefix_only_line_is_translatable_text() {
        let chunks = TextChunker::split("##");
        assert_eq!(chunks[0].prefix, "");
        assert_eq!(chunks[0].text, "##");
    }

    #[test]
    fn trailing_whitespace_is_dropped_like_swift() {
        let chunks = TextChunker::split("One   \nTwo\t");
        assert_eq!(chunks[0].text, "One");
        assert_eq!(chunks[1].text, "Two");
    }

    #[test]
    fn text_chunk_defaults() {
        let chunk = TextChunk::new("", "Hi", false, 0);
        assert_eq!(chunk.separator_before, "\n");
        assert!(!chunk.is_code);
        assert_eq!(chunk.index, 0);
    }

    #[test]
    fn mixed_line_endings_round_trip() {
        let source = "# Title\r\n\r\n- one\r\n- two\r\n\r\n> quote\r\n";
        let chunks = TextChunker::split(source);
        let identical: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
        let composed = TextChunker::compose(&chunks, &identical).expect("compose");
        assert!(!composed.contains('\r'));
        assert_eq!(composed, TextChunker::normalize(source).trim_end());
    }

    #[test]
    fn pathological_inputs_do_not_panic() {
        let cases = vec![
            String::new(),
            "\n".to_string(),
            "\n\n\n".to_string(),
            " \t \n \r\n".to_string(),
            "```".to_string(),
            "~~~".to_string(),
            "- ".to_string(),
            "#".to_string(),
            ">".to_string(),
            "\u{2010}\u{2011}\u{2012}".to_string(),
            "1.".to_string(),
            "\u{FEFF}text".to_string(),
            "word".repeat(5000),
        ];
        for case in &cases {
            let chunks = TextChunker::split(case);
            assert!(!chunks.is_empty(), "split must always return a chunk");
            let identical: Vec<String> = chunks.iter().map(|chunk| chunk.text.clone()).collect();
            if let Ok(composed) = TextChunker::compose(&chunks, &identical) {
                assert!(!composed.contains('\r'));
            }
            let _ = TextChunker::split_sentences(case);
            let _ = TextChunker::normalize(case);
        }
    }

    #[test]
    fn code_fence_with_trailing_info_and_indent() {
        let source = "  ```rust\n  let x = 1;\n  ```";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 1);
        assert!(chunks[0].is_code);
        assert_eq!(chunks[0].text, source);
    }

    #[test]
    fn mismatched_fence_length_does_not_close() {
        let source = "````\ncode\n```\nmore\n````";
        let chunks = TextChunker::split(source);
        assert_eq!(chunks.len(), 1);
        assert_eq!(chunks[0].text, source);
    }
}
