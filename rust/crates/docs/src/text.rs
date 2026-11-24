//! Paragraph splitting for plain text and Markdown.
//!
//! Only runs of non-blank lines are translation units; blank lines, the bytes
//! between paragraphs, fenced code blocks and (for Markdown) indented code are
//! emitted verbatim so that concatenating every unit reproduces the input
//! exactly. Inside a unit, every line is split into `leading + body + trailing`
//! layout; only the body reaches the translation callable and the original
//! separators are re-attached byte-for-byte, so CRLF and trailing spaces
//! survive a round trip.

use std::path::Path;
use std::sync::atomic::AtomicBool;

use crate::encoding;
use crate::error::{unreadable, DocumentError};
use crate::io;

/// One physical line inside a translatable unit, with its layout offsets.
#[derive(Debug)]
struct UnitLine {
    start: usize,
    body_start: usize,
    body_end: usize,
    end: usize,
}

/// One piece of a text file: either a paragraph to translate or literal text.
#[derive(Debug)]
pub(crate) struct TextUnit {
    /// Exact source slice of the unit.
    pub text: String,
    /// Whether the unit is handed to the translation callable.
    pub translate: bool,
    /// Per-line layout offsets: only `body_start..body_end` is prose.
    lines: Vec<UnitLine>,
    /// Dominant line terminator inside the unit, re-applied after translation.
    terminator: Option<&'static str>,
}

impl TextUnit {
    fn literal(text: String) -> Self {
        Self {
            text,
            translate: false,
            lines: Vec::new(),
            terminator: None,
        }
    }

    fn paragraph(text: String) -> Self {
        let lines = line_spans(&text)
            .into_iter()
            .map(|(start, end)| {
                let content = &text[start..end];
                let without_leading = content.trim_start_matches(is_indent);
                let body_start = start + (content.len() - without_leading.len());
                let body_end = body_start + without_leading.trim_end_matches(is_indent).len();
                UnitLine {
                    start,
                    body_start,
                    body_end,
                    end,
                }
            })
            .collect::<Vec<UnitLine>>();
        let translate = lines
            .iter()
            .any(|line| !text[line.body_start..line.body_end].trim().is_empty());
        let terminator = if translate {
            dominant_terminator(&text)
        } else {
            None
        };
        Self {
            text,
            translate,
            lines,
            terminator,
        }
    }

    /// The prose of the unit, one source line per output line.
    pub fn body(&self) -> String {
        self.lines
            .iter()
            .map(|line| &self.text[line.body_start..line.body_end])
            .collect::<Vec<&str>>()
            .join("\n")
    }

    /// Re-attach the layout to a translation of [`TextUnit::body`].
    fn compose(&self, translated: &str) -> String {
        let pieces = translated_lines(translated);
        if pieces.len() == self.lines.len() {
            let mut output = String::with_capacity(self.text.len());
            for (index, line) in self.lines.iter().enumerate() {
                output.push_str(&self.text[line.start..line.body_start]);
                if let Some(piece) = pieces.get(index) {
                    output.push_str(piece);
                }
                output.push_str(&self.text[line.body_end..line.end]);
                if let Some(next) = self.lines.get(index + 1) {
                    // Separators are byte-identical to the source, so CRLF and
                    // blank-ish gaps survive untouched.
                    output.push_str(&self.text[line.end..next.start]);
                }
            }
            output
        } else {
            // The model changed the line count (wrapping, joining, ...): keep
            // the unit's outer layout and normalise line ends instead.
            let mut output = String::new();
            if let Some(first) = self.lines.first() {
                output.push_str(&self.text[first.start..first.body_start]);
            }
            output.push_str(&apply_terminator(translated, self.terminator));
            if let Some(last) = self.lines.last() {
                output.push_str(&self.text[last.body_end..last.end]);
            }
            output
        }
    }
}

/// Split a translation into lines, dropping one trailing empty line.
fn translated_lines(text: &str) -> Vec<String> {
    let normalized = if text.contains('\r') {
        text.replace("\r\n", "\n").replace('\r', "\n")
    } else {
        text.to_string()
    };
    let mut pieces: Vec<String> = normalized.split('\n').map(str::to_string).collect();
    if pieces.len() > 1 && pieces.last().is_some_and(String::is_empty) {
        pieces.pop();
    }
    pieces
}

fn is_indent(character: char) -> bool {
    character == ' ' || character == '\t'
}

/// Most common line terminator inside `text`, if it contains one.
fn dominant_terminator(text: &str) -> Option<&'static str> {
    let bytes = text.as_bytes();
    let mut crlf = 0usize;
    let mut lf = 0usize;
    let mut cr = 0usize;
    let mut index = 0usize;
    while index < bytes.len() {
        match bytes[index] {
            b'\r' if index + 1 < bytes.len() && bytes[index + 1] == b'\n' => {
                crlf += 1;
                index += 2;
            }
            b'\r' => {
                cr += 1;
                index += 1;
            }
            b'\n' => {
                lf += 1;
                index += 1;
            }
            _ => index += 1,
        }
    }
    let most = crlf.max(lf).max(cr);
    if most == 0 {
        None
    } else if crlf == most {
        Some("\r\n")
    } else if lf == most {
        Some("\n")
    } else {
        Some("\r")
    }
}

/// Normalise the newlines a model produced to the source unit's terminator.
fn apply_terminator(text: &str, terminator: Option<&'static str>) -> String {
    match terminator {
        None => text.to_string(),
        Some("\n") => {
            if text.contains('\r') {
                text.replace("\r\n", "\n").replace('\r', "\n")
            } else {
                text.to_string()
            }
        }
        Some(terminator) => text
            .replace("\r\n", "\n")
            .replace('\r', "\n")
            .replace('\n', terminator),
    }
}

/// Read a TXT/Markdown file and decode it to UTF-8.
pub(crate) fn read(path: &Path) -> Result<String, DocumentError> {
    let data = std::fs::read(path).map_err(|error| unreadable(error.to_string()))?;
    Ok(encoding::decode_text(&data))
}

/// Line spans without their terminators, mirroring Swift's newline split.
///
/// A trailing newline produces one final empty line, exactly like
/// `String.split(omittingEmptySubsequences: false)` in the Swift original.
pub(crate) fn line_spans(text: &str) -> Vec<(usize, usize)> {
    if text.is_empty() {
        return Vec::new();
    }
    let bytes = text.as_bytes();
    let length = bytes.len();
    let mut spans = Vec::new();
    let mut start = 0usize;
    let mut index = 0usize;
    while index < length {
        match bytes[index] {
            b'\r' => {
                spans.push((start, index));
                index += if index + 1 < length && bytes[index + 1] == b'\n' {
                    2
                } else {
                    1
                };
                start = index;
            }
            b'\n' => {
                spans.push((start, index));
                index += 1;
                start = index;
            }
            _ => index += 1,
        }
    }
    if start < length {
        spans.push((start, length));
    } else if start == length && matches!(bytes.last(), Some(b'\n' | b'\r')) {
        spans.push((start, start));
    }
    spans
}

/// Split text into translation units, like `DocumentTranslator.textUnits`.
pub(crate) fn text_units(text: &str, markdown: bool) -> Vec<TextUnit> {
    let mut units: Vec<TextUnit> = Vec::new();
    let spans = line_spans(text);
    let mut cursor = 0usize;
    let mut paragraph_start: Option<usize> = None;
    let mut paragraph_end = 0usize;
    let mut code_fence: Option<(u8, usize)> = None;

    for (start, end) in spans {
        let mut indentation = 0usize;
        while start + indentation < end && text.as_bytes()[start + indentation] == b' ' {
            indentation += 1;
        }
        let content = &text[start + indentation..end];

        if markdown && indentation <= 3 && matches!(content.as_bytes().first(), Some(b'`' | b'~')) {
            let marker = content.as_bytes()[0];
            let count = content.bytes().take_while(|byte| *byte == marker).count();
            let suffix = &content[count..];
            if let Some((fence_marker, fence_count)) = code_fence {
                if marker == fence_marker && count >= fence_count && suffix.trim().is_empty() {
                    code_fence = None;
                }
                continue;
            }
            if count >= 3 && (marker != b'`' || !suffix.contains('`')) {
                flush_paragraph(
                    text,
                    &mut units,
                    &mut cursor,
                    &mut paragraph_start,
                    paragraph_end,
                );
                code_fence = Some((marker, count));
                continue;
            }
        }

        if code_fence.is_some() {
            continue;
        }

        // Indented Markdown code (4 spaces or a tab) is layout, not prose; it
        // is passed through exactly like a fenced block.
        if markdown && (indentation >= 4 || text.as_bytes().get(start).copied() == Some(b'\t')) {
            flush_paragraph(
                text,
                &mut units,
                &mut cursor,
                &mut paragraph_start,
                paragraph_end,
            );
            continue;
        }

        if content.trim().is_empty() {
            flush_paragraph(
                text,
                &mut units,
                &mut cursor,
                &mut paragraph_start,
                paragraph_end,
            );
        } else {
            if paragraph_start.is_none() {
                paragraph_start = Some(start);
            }
            paragraph_end = end;
        }
    }

    flush_paragraph(
        text,
        &mut units,
        &mut cursor,
        &mut paragraph_start,
        paragraph_end,
    );
    if cursor < text.len() {
        units.push(TextUnit::literal(text[cursor..].to_string()));
    }
    units
}

fn flush_paragraph(
    text: &str,
    units: &mut Vec<TextUnit>,
    cursor: &mut usize,
    paragraph_start: &mut Option<usize>,
    paragraph_end: usize,
) {
    let Some(start) = *paragraph_start else {
        return;
    };
    if *cursor < start {
        units.push(TextUnit::literal(text[*cursor..start].to_string()));
    }
    units.push(TextUnit::paragraph(text[start..paragraph_end].to_string()));
    *cursor = paragraph_end;
    *paragraph_start = None;
}

/// Translate each paragraph unit and stitch the file back together.
pub(crate) fn translate_text(
    text: &str,
    markdown: bool,
    translate: &mut dyn FnMut(&str) -> Result<String, String>,
    on_progress: Option<&dyn Fn(usize, usize)>,
    cancel: Option<&AtomicBool>,
) -> Result<String, DocumentError> {
    let units = text_units(text, markdown);
    let total = units.iter().filter(|unit| unit.translate).count();
    let mut completed = 0usize;
    let mut output = String::with_capacity(text.len());
    for unit in &units {
        if !unit.translate {
            output.push_str(&unit.text);
            continue;
        }
        io::check_cancel(cancel)?;
        let translated = translate(&unit.body()).map_err(|detail| {
            DocumentError::new(crate::error::DocumentErrorKind::WriteFailed, detail)
        })?;
        output.push_str(&unit.compose(&translated));
        completed += 1;
        if let Some(progress) = on_progress {
            progress(completed, total);
        }
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_units_group_lines_like_the_swift_original() {
        let source = "\r\nTitle\r\nline 2\r\n \r\n\r\n````swift\r\n\r\n```\r\nlet n = 10\r\n\
                      ````\r\nNext\r\n";
        let units = text_units(source, true);
        let translated: Vec<&str> = units
            .iter()
            .filter(|unit| unit.translate)
            .map(|unit| unit.text.as_str())
            .collect();
        assert_eq!(translated, vec!["Title\r\nline 2", "Next"]);
        let joined: String = units.iter().map(|unit| unit.text.as_str()).collect();
        assert_eq!(joined, source);

        let unclosed = "Start\n~~~sh\n\nprintf 'hello'\n";
        let units = text_units(unclosed, true);
        let translated: Vec<&str> = units
            .iter()
            .filter(|unit| unit.translate)
            .map(|unit| unit.text.as_str())
            .collect();
        assert_eq!(translated, vec!["Start"]);
        let joined: String = units.iter().map(|unit| unit.text.as_str()).collect();
        assert_eq!(joined, unclosed);
    }

    #[test]
    fn blank_lines_between_paragraphs_are_literal_units() {
        let source = "a\n\n\nb\n";
        let units = text_units(source, false);
        let translated: Vec<&str> = units
            .iter()
            .filter(|unit| unit.translate)
            .map(|unit| unit.text.as_str())
            .collect();
        assert_eq!(translated, vec!["a", "b"]);
        let joined: String = units.iter().map(|unit| unit.text.as_str()).collect();
        assert_eq!(joined, source);
    }

    #[test]
    fn markdown_indented_code_is_literal_and_whitespace_survives() {
        let source = concat!(
            "# Heading with trailing spaces   \n",
            "\n",
            "    four-space indented code line\n",
            "\n",
            "  leading spaces plain paragraph.\n",
            "\tTab-indented line.\n",
            "\n",
            "Trailing spaces at the end.   \n",
            "\n",
            "Final line without newline",
        );
        let mut seen: Vec<String> = Vec::new();
        let mut translate = |body: &str| {
            seen.push(body.to_string());
            Ok(body.to_uppercase())
        };
        let output = translate_text(source, true, &mut translate, None, None).unwrap();
        assert_eq!(
            seen,
            vec![
                "# Heading with trailing spaces",
                "leading spaces plain paragraph.",
                "Trailing spaces at the end.",
                "Final line without newline",
            ]
        );
        let expected = concat!(
            "# HEADING WITH TRAILING SPACES   \n",
            "\n",
            "    four-space indented code line\n",
            "\n",
            "  LEADING SPACES PLAIN PARAGRAPH.\n",
            "\tTab-indented line.\n",
            "\n",
            "TRAILING SPACES AT THE END.   \n",
            "\n",
            "FINAL LINE WITHOUT NEWLINE",
        );
        assert_eq!(output, expected);
    }

    #[test]
    fn plain_text_keeps_indentation_and_trailing_spaces() {
        let source = "    indented plain text   \n\nsecond paragraph\n";
        let mut seen: Vec<String> = Vec::new();
        let mut translate = |body: &str| {
            seen.push(body.to_string());
            Ok(body.to_uppercase())
        };
        let output = translate_text(source, false, &mut translate, None, None).unwrap();
        assert_eq!(seen, vec!["indented plain text", "second paragraph"]);
        assert_eq!(output, "    INDENTED PLAIN TEXT   \n\nSECOND PARAGRAPH\n");
    }

    #[test]
    fn multi_line_paragraph_keeps_per_line_layout() {
        let source = "First line.  \r\n  second line\t\r\nthird line";
        let mut seen = String::new();
        let mut translate = |body: &str| {
            seen = body.to_string();
            Ok(body.to_uppercase())
        };
        let output = translate_text(source, false, &mut translate, None, None).unwrap();
        assert_eq!(seen, "First line.\nsecond line\nthird line");
        assert_eq!(output, "FIRST LINE.  \r\n  SECOND LINE\t\r\nTHIRD LINE");
    }

    #[test]
    fn crlf_inside_a_multi_line_paragraph_is_reapplied() {
        let source = concat!(
            "First line of a paragraph.\r\n",
            "Second line of the same paragraph.\r\n",
            "\r\n",
            "Separate paragraph after a blank line.\r\n",
        );
        // The model-facing path normalises line ends, like the CLI translator.
        let mut translate = |body: &str| Ok(body.replace("\r\n", "\n").to_uppercase());
        let output = translate_text(source, false, &mut translate, None, None).unwrap();
        let expected = concat!(
            "FIRST LINE OF A PARAGRAPH.\r\n",
            "SECOND LINE OF THE SAME PARAGRAPH.\r\n",
            "\r\n",
            "SEPARATE PARAGRAPH AFTER A BLANK LINE.\r\n",
        );
        assert_eq!(output, expected);
    }

    #[test]
    fn line_spans_keep_a_trailing_empty_line() {
        assert_eq!(line_spans("a\n"), vec![(0, 1), (2, 2)]);
        assert_eq!(line_spans("a\r\nb"), vec![(0, 1), (3, 4)]);
        assert!(line_spans("").is_empty());
    }
}
