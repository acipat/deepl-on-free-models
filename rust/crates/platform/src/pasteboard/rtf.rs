//! RTF to Markdown conversion.
//!
//! A compact tokenizer rather than a full RTF implementation: it recovers
//! paragraphs and character runs, skips the destination groups that only carry
//! metadata, and decodes byte escapes with a cp1252/cp1251 heuristic.  Unknown
//! control words are ignored, so malformed input degrades to its visible text
//! instead of failing.

use encoding_rs::{Encoding, UTF_8, WINDOWS_1251, WINDOWS_1252};

/// Groups that carry document metadata rather than visible text.
const SKIP_DESTINATIONS: &[&str] = &[
    "colortbl",
    "fonttbl",
    "footer",
    "footerf",
    "footerl",
    "footerr",
    "header",
    "headerf",
    "headerl",
    "headerr",
    "info",
    "object",
    "pict",
    "stylesheet",
];

/// Marker characters used to defer `\'hh` bytes until the codec is known.
const BYTE_OPEN: char = '\u{e000}';
const BYTE_CLOSE: char = '\u{e001}';

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct Style {
    bold: bool,
    italic: bool,
    underline: bool,
}

impl Style {
    fn is_plain(self) -> bool {
        !(self.bold || self.italic || self.underline)
    }
}

#[derive(Clone, Copy)]
enum StyleAttribute {
    Bold,
    Italic,
    Underline,
}

impl StyleAttribute {
    fn get(self, style: Style) -> bool {
        match self {
            Self::Bold => style.bold,
            Self::Italic => style.italic,
            Self::Underline => style.underline,
        }
    }

    fn set(self, style: &mut Style, value: bool) {
        match self {
            Self::Bold => style.bold = value,
            Self::Italic => style.italic = value,
            Self::Underline => style.underline = value,
        }
    }
}

#[derive(Clone, Copy, Debug)]
struct RtfState {
    style: Style,
    skip: bool,
    uc: usize,
}

impl Default for RtfState {
    fn default() -> Self {
        Self {
            style: Style::default(),
            skip: false,
            uc: 1,
        }
    }
}

type Run = (String, Style);

/// Mutable state shared by the tokenizer helpers.
struct RtfBuilder {
    states: Vec<RtfState>,
    runs: Vec<Run>,
    buffer: String,
    raw_bytes: Vec<u8>,
}

impl RtfBuilder {
    fn new() -> Self {
        Self {
            states: vec![RtfState::default()],
            runs: Vec::new(),
            buffer: String::new(),
            raw_bytes: Vec::new(),
        }
    }

    fn state(&self) -> RtfState {
        self.states.last().copied().unwrap_or_default()
    }

    fn state_mut(&mut self) -> Option<&mut RtfState> {
        self.states.last_mut()
    }

    fn flush(&mut self) {
        if self.buffer.is_empty() {
            return;
        }
        let text = std::mem::take(&mut self.buffer);
        let style = self.state().style;
        if let Some((last_text, last_style)) = self.runs.last_mut() {
            if *last_style == style {
                last_text.push_str(&text);
                return;
            }
        }
        self.runs.push((text, style));
    }

    fn emit(&mut self, text: &str) {
        if !self.state().skip {
            self.buffer.push_str(text);
        }
    }

    fn emit_char(&mut self, character: char) {
        if !self.state().skip {
            self.buffer.push(character);
        }
    }

    fn emit_break(&mut self, text: &str) {
        self.flush();
        if !self.state().skip {
            self.runs.push((text.to_string(), Style::default()));
        }
    }

    fn set_style(&mut self, attribute: StyleAttribute, value: bool) {
        if self.state().skip {
            if let Some(state) = self.state_mut() {
                attribute.set(&mut state.style, value);
            }
            return;
        }
        if attribute.get(self.state().style) == value {
            return;
        }
        self.flush();
        if let Some(state) = self.state_mut() {
            attribute.set(&mut state.style, value);
        }
    }

    fn record_byte(&mut self, value: u8) {
        if self.state().skip {
            return;
        }
        self.raw_bytes.push(value);
        self.buffer.push(BYTE_OPEN);
        self.buffer
            .push_str(&(self.raw_bytes.len() - 1).to_string());
        self.buffer.push(BYTE_CLOSE);
    }

    fn open_group(&mut self) {
        self.flush();
        let state = self.state();
        self.states.push(state);
    }

    fn close_group(&mut self) {
        self.flush();
        if self.states.len() > 1 {
            self.states.pop();
        }
    }
}

fn is_hex_digit(character: char) -> bool {
    character.is_ascii_hexdigit()
}

fn hex_value(character: char) -> Option<u8> {
    character.to_digit(16).map(|value| value as u8)
}

/// Decode a control word parameter, if one is present at `index`.
fn parse_parameter(chars: &[char], index: &mut usize) -> Option<i64> {
    let length = chars.len();
    if *index >= length || (chars[*index] != '-' && !chars[*index].is_ascii_digit()) {
        return None;
    }
    let number_start = *index;
    if chars[*index] == '-' {
        *index += 1;
    }
    let digit_start = *index;
    while *index < length && chars[*index].is_ascii_digit() {
        *index += 1;
    }
    if *index == digit_start {
        return None;
    }
    chars[number_start..*index]
        .iter()
        .collect::<String>()
        .parse()
        .ok()
}

fn parse_rtf(rtf: &str) -> RtfBuilder {
    let chars: Vec<char> = rtf.chars().collect();
    let length = chars.len();
    let mut builder = RtfBuilder::new();
    let mut fallback_skip = 0usize;
    let mut index = 0usize;

    while index < length {
        let character = chars[index];

        if fallback_skip > 0 {
            if character == '\\' && index + 1 < length && chars[index + 1] == '\'' {
                index += 4;
                fallback_skip -= 1;
                continue;
            }
            if matches!(character, '\\' | '{' | '}' | '\r' | '\n') {
                fallback_skip = 0;
            } else {
                index += 1;
                fallback_skip -= 1;
                continue;
            }
        }

        match character {
            '{' => {
                builder.open_group();
                index += 1;
                continue;
            }
            '}' => {
                builder.close_group();
                index += 1;
                continue;
            }
            '\r' | '\n' => {
                index += 1;
                continue;
            }
            '\\' => {}
            _ => {
                builder.emit_char(character);
                index += 1;
                continue;
            }
        }

        // Control symbol or control word.
        index += 1;
        if index >= length {
            break;
        }
        let symbol = chars[index];

        if symbol == '\'' {
            let digits: Vec<char> = chars[index + 1..length.min(index + 3)].to_vec();
            if digits.len() == 2 && digits.iter().all(|digit| is_hex_digit(*digit)) {
                let value =
                    (hex_value(digits[0]).unwrap_or(0) << 4) | hex_value(digits[1]).unwrap_or(0);
                builder.record_byte(value);
                index += 3;
            } else {
                index += 1;
            }
            continue;
        }
        if matches!(symbol, '\\' | '{' | '}') {
            builder.emit_char(symbol);
            index += 1;
            continue;
        }
        if symbol == '~' {
            builder.emit(" ");
            index += 1;
            continue;
        }
        if symbol == '_' {
            builder.emit("-");
            index += 1;
            continue;
        }
        if symbol == '-' {
            index += 1;
            continue;
        }
        if symbol == '*' {
            builder.flush();
            if let Some(state) = builder.state_mut() {
                state.skip = true;
            }
            index += 1;
            continue;
        }
        if matches!(symbol, '\r' | '\n') {
            builder.emit_break("\n\n");
            index += 1;
            continue;
        }
        if !symbol.is_ascii_alphabetic() {
            index += 1;
            continue;
        }

        let word_start = index;
        while index < length && chars[index].is_ascii_alphabetic() {
            index += 1;
        }
        let word: String = chars[word_start..index]
            .iter()
            .collect::<String>()
            .to_ascii_lowercase();
        let parameter = parse_parameter(&chars, &mut index);
        if index < length && chars[index] == ' ' {
            index += 1;
        }

        if SKIP_DESTINATIONS.contains(&word.as_str()) {
            if !builder.state().skip {
                builder.flush();
            }
            if let Some(state) = builder.state_mut() {
                state.skip = true;
            }
            continue;
        }

        match word.as_str() {
            "par" => builder.emit_break("\n\n"),
            "line" => builder.emit_break("\n"),
            "tab" => builder.emit("\t"),
            "b" | "i" | "ul" => {
                let enabled = parameter != Some(0);
                let attribute = match word.as_str() {
                    "b" => StyleAttribute::Bold,
                    "i" => StyleAttribute::Italic,
                    _ => StyleAttribute::Underline,
                };
                builder.set_style(attribute, enabled);
            }
            "ulnone" => builder.set_style(StyleAttribute::Underline, false),
            "plain" => {
                builder.set_style(StyleAttribute::Bold, false);
                builder.set_style(StyleAttribute::Italic, false);
                builder.set_style(StyleAttribute::Underline, false);
            }
            "uc" => {
                if let Some(value) = parameter {
                    if let Some(state) = builder.state_mut() {
                        state.uc = value.max(0) as usize;
                    }
                }
            }
            "u" => {
                if let Some(value) = parameter {
                    let value = if value < 0 { value + 65_536 } else { value };
                    if (0..=0xFFFF).contains(&value) {
                        if let Some(character) = char::from_u32(value as u32) {
                            builder.emit_char(character);
                        }
                    }
                    fallback_skip = builder.state().uc;
                }
            }
            // Every other control word is layout metadata and is dropped.
            _ => {}
        }
    }

    builder.flush();
    builder
}

/// Find the codec declared by an `\ansicpg` control word.
fn declared_encoding(rtf: &str) -> Option<&'static Encoding> {
    let position = rtf.find("\\ansicpg")?;
    let digits: String = rtf[position + 8..]
        .chars()
        .take_while(|character| character.is_ascii_digit())
        .collect();
    if digits.is_empty() {
        return None;
    }
    let codepage: u32 = digits.parse().ok()?;
    if codepage == 65001 {
        return Some(UTF_8);
    }
    let label = format!("windows-{codepage}");
    if let Some(encoding) = Encoding::for_label(label.as_bytes()) {
        return Some(encoding);
    }
    // Unknown legacy code page: fall back like the Python implementation does.
    Some(WINDOWS_1252)
}

fn looks_cyrillic(text: &str) -> bool {
    let letters: Vec<char> = text
        .chars()
        .filter(|character| character.is_alphabetic())
        .collect();
    if letters.is_empty() {
        return false;
    }
    let cyrillic = letters
        .iter()
        .filter(|character| ('\u{0400}'..='\u{04ff}').contains(*character))
        .count();
    cyrillic >= 2 && (cyrillic as f64) / (letters.len() as f64) >= 0.5
}

fn byte_encoding(rtf: &str, data: &[u8]) -> &'static Encoding {
    if let Some(encoding) = declared_encoding(rtf) {
        return encoding;
    }
    if WINDOWS_1252
        .decode_without_bom_handling_and_without_replacement(data)
        .is_some()
    {
        let cyrillic = WINDOWS_1251.decode(data).0;
        if looks_cyrillic(&cyrillic) {
            WINDOWS_1251
        } else {
            WINDOWS_1252
        }
    } else {
        WINDOWS_1251
    }
}

/// Render one run, keeping surrounding spaces outside the emphasis markers.
fn render_run(text: &str, style: Style) -> String {
    if text.is_empty() {
        return String::new();
    }
    if style.is_plain() || text.trim().is_empty() {
        return text.to_string();
    }
    let start = text.len() - text.trim_start().len();
    let end = text.trim_end().len();
    let mut body = text[start..end].to_string();
    if style.underline {
        body = format!("_{body}_");
    }
    if style.italic {
        body = format!("*{body}*");
    }
    if style.bold {
        body = format!("**{body}**");
    }
    format!("{}{}{}", &text[..start], body, &text[end..])
}

fn render_runs(runs: &[Run]) -> String {
    let mut output = String::new();
    for (text, style) in runs {
        output.push_str(&render_run(text, *style));
    }
    output
}

/// Replace the deferred byte markers with text decoded in `encoding`.
fn replace_byte_markers(text: &str, raw: &[u8], encoding: &'static Encoding) -> String {
    let mut output = String::with_capacity(text.len());
    let mut characters = text.chars().peekable();
    while let Some(character) = characters.next() {
        if character == BYTE_CLOSE {
            continue;
        }
        if character != BYTE_OPEN {
            output.push(character);
            continue;
        }
        let mut bytes: Vec<u8> = Vec::new();
        loop {
            let mut digits = String::new();
            let mut closed = false;
            while let Some(&next) = characters.peek() {
                if next == BYTE_CLOSE {
                    characters.next();
                    closed = true;
                    break;
                }
                if next.is_ascii_digit() {
                    digits.push(next);
                    characters.next();
                } else {
                    break;
                }
            }
            if !closed {
                break;
            }
            if let Ok(index) = digits.parse::<usize>() {
                if let Some(byte) = raw.get(index) {
                    bytes.push(*byte);
                }
            }
            if characters.peek() != Some(&BYTE_OPEN) {
                break;
            }
            characters.next();
        }
        if !bytes.is_empty() {
            output.push_str(&encoding.decode(&bytes).0);
        }
    }
    output
}

fn collapse_spaces(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut previous_space = false;
    for character in text.chars() {
        if character == ' ' {
            if previous_space {
                continue;
            }
            previous_space = true;
        } else {
            previous_space = false;
        }
        output.push(character);
    }
    output
}

fn trim_line_edges(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut after_newline = true;
    for character in text.chars() {
        if character == '\n' {
            while output.ends_with([' ', '\t']) {
                output.pop();
            }
            output.push('\n');
            after_newline = true;
            continue;
        }
        if after_newline && matches!(character, ' ' | '\t') {
            continue;
        }
        after_newline = false;
        output.push(character);
    }
    output
}

fn collapse_newlines(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut newlines = 0usize;
    for character in text.chars() {
        if character == '\n' {
            newlines += 1;
            if newlines > 2 {
                continue;
            }
        } else {
            newlines = 0;
        }
        output.push(character);
    }
    output
}

fn tidy_rtf(text: &str) -> String {
    let text = text.replace('\u{00a0}', " ");
    let text = collapse_spaces(&text);
    let text = trim_line_edges(&text);
    collapse_newlines(&text).trim().to_string()
}

/// Convert a compact subset of RTF to Markdown.
///
/// Only the constructs word processors emit for ordinary prose are understood:
/// paragraphs, line/tab breaks, bold/italic/underline runs and escaped Unicode
/// or ANSI bytes.  Unknown control words are ignored.
pub fn rtf_to_markdown(rtf: &str) -> String {
    if rtf.is_empty() {
        return String::new();
    }
    let builder = parse_rtf(rtf);
    let encoding = byte_encoding(rtf, &builder.raw_bytes);
    let rendered = render_runs(&builder.runs);
    tidy_rtf(&replace_byte_markers(
        &rendered,
        &builder.raw_bytes,
        encoding,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bold_and_italic_runs() {
        let rtf = r"{\rtf1\ansi{\fonttbl{\f0 Arial;}}\f0\fs24 Hello ".to_string()
            + r"\b bold\b0  and \i italic\i0 !\par}";
        assert_eq!(rtf_to_markdown(&rtf), "Hello **bold** and *italic*!");
    }

    #[test]
    fn underline() {
        assert_eq!(
            rtf_to_markdown(r"{\rtf1\ul underlined\ulnone  plain}"),
            "_underlined_ plain"
        );
    }

    #[test]
    fn paragraphs_line_and_tab() {
        assert_eq!(
            rtf_to_markdown(r"{\rtf1 First\par Second\par}"),
            "First\n\nSecond"
        );
        assert_eq!(rtf_to_markdown(r"{\rtf1 one\line two}"), "one\ntwo");
        assert_eq!(rtf_to_markdown(r"{\rtf1 a\tab b}"), "a\tb");
    }

    #[test]
    fn unicode_escapes() {
        let rtf = r"{\rtf1 \u1055?\u1088?\u1080?\u1074?\u1077?\u1090?}";
        assert_eq!(rtf_to_markdown(rtf), "Привет");
        assert_eq!(rtf_to_markdown(r"{\rtf1 \u8212?}"), "—");
    }

    #[test]
    fn cyrillic_byte_escapes() {
        let rtf = r"{\rtf1\ansi\ansicpg1251 \'cf\'f0\'e8\'e2\'e5\'f2}";
        assert_eq!(rtf_to_markdown(rtf), "Привет");
        // Without a declared codepage the cp1251 heuristic still picks Cyrillic.
        assert_eq!(
            rtf_to_markdown(r"{\rtf1\ansi \'cf\'f0\'e8\'e2\'e5\'f2}"),
            "Привет"
        );
    }

    #[test]
    fn cp1252_byte_escapes() {
        assert_eq!(rtf_to_markdown(r"{\rtf1 caf\'e9}"), "café");
    }

    #[test]
    fn skips_font_table_color_table_and_generator() {
        let rtf = r"{\rtf1{\fonttbl{\f0 Times New Roman;}}".to_string()
            + r"{\colortbl;\red0\green0\blue0;}"
            + r"{\*\generator Riched20;}\f0 Visible text}";
        assert_eq!(rtf_to_markdown(&rtf), "Visible text");
    }

    #[test]
    fn malformed_input_degrades_to_text() {
        assert_eq!(rtf_to_markdown(""), "");
        assert_eq!(rtf_to_markdown("plain text"), "plain text");
        let result = rtf_to_markdown(r"{\rtf1 \b broken");
        assert!(result.contains("broken"));
        assert!(!result.contains('\\'));
    }

    #[test]
    fn escaped_braces_and_backslashes() {
        assert_eq!(rtf_to_markdown(r"{\rtf1 a\{b\}c\\d}"), "a{b}c\\d");
        assert_eq!(rtf_to_markdown(r"{\rtf1 a\~b\_c}"), "a b-c");
    }

    #[test]
    fn uc_skips_the_fallback_character() {
        assert_eq!(rtf_to_markdown(r"{\rtf1 \uc1\u1074?x}"), "вx");
        assert_eq!(rtf_to_markdown(r"{\rtf1 \uc2\u1074??x}"), "вx");
    }

    #[test]
    fn plain_resets_emphasis() {
        assert_eq!(
            rtf_to_markdown(r"{\rtf1 \b bold \plain plain}"),
            "**bold** plain"
        );
    }

    #[test]
    fn codec_helpers() {
        assert_eq!(
            declared_encoding(r"{\rtf1\ansicpg1251}"),
            Some(WINDOWS_1251)
        );
        assert_eq!(declared_encoding(r"{\rtf1\ansicpg65001}"), Some(UTF_8));
        assert_eq!(declared_encoding(r"{\rtf1}"), None);
        assert!(looks_cyrillic("Привет"));
        assert!(!looks_cyrillic("café"));
    }
}
