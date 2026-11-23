//! Markdown rendering for the clipboard and the result view.
//!
//! [`to_html`] produces a complete, theme-neutral HTML document; every piece of
//! user text is escaped before it is wrapped in a tag, so translated text can
//! never inject markup.  [`to_plain`] is the plain-text flavour: Markdown
//! markers are removed while paragraphs, list bullets and line breaks stay.
//!
//! The supported Markdown subset is the one produced by
//! [`crate::pasteboard::html_to_markdown`]: ATX headings, paragraphs, nested
//! lists, block quotes, fenced code, horizontal rules, emphasis, inline code,
//! links and images.

use crate::pasteboard::html::safe_href;

#[derive(Clone, Debug, PartialEq, Eq)]
enum Block {
    Heading(usize, String),
    Paragraph(String),
    Code(String),
    Rule,
    Quote(Vec<Block>),
    List {
        ordered: bool,
        start: i64,
        items: Vec<ListItem>,
    },
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct ListItem {
    number: Option<i64>,
    blocks: Vec<Block>,
}

// --------------------------------------------------------------------------- //
// Line helpers
// --------------------------------------------------------------------------- //

fn indent_of(line: &str) -> usize {
    line.len() - line.trim_start_matches(' ').len()
}

fn heading(line: &str) -> Option<(usize, &str)> {
    let hashes = line
        .chars()
        .take_while(|character| *character == '#')
        .count();
    if !(1..=6).contains(&hashes) {
        return None;
    }
    let rest = line[hashes..].strip_prefix(' ')?;
    Some((hashes, rest.trim_end()))
}

fn fence_length(line: &str) -> Option<usize> {
    let ticks = line
        .chars()
        .take_while(|character| *character == '`')
        .count();
    if ticks >= 3 {
        Some(ticks)
    } else {
        None
    }
}

fn closes_fence(line: &str, length: usize) -> bool {
    let trimmed = line.trim();
    trimmed.len() >= length && trimmed.chars().all(|character| character == '`')
}

fn is_rule(line: &str) -> bool {
    let trimmed = line.trim();
    if trimmed.len() < 3 {
        return false;
    }
    let first = match trimmed.chars().next() {
        Some(character @ ('-' | '*' | '_')) => character,
        _ => return false,
    };
    trimmed.chars().all(|character| character == first)
}

/// Parse a list marker, returning `(indent, ordered, content_start, number)`.
fn list_marker(line: &str) -> Option<(usize, bool, usize, i64)> {
    let indent = indent_of(line);
    let rest = &line[indent..];
    for marker in ["- ", "* ", "+ "] {
        if rest.starts_with(marker) {
            return Some((indent, false, indent + marker.len(), 0));
        }
    }
    let digits = rest
        .chars()
        .take_while(|character| character.is_ascii_digit())
        .count();
    if digits == 0 {
        return None;
    }
    let after = &rest[digits..];
    if let Some(tail) = after.strip_prefix(". ") {
        let _ = tail;
        let number = rest[..digits].parse::<i64>().unwrap_or(1);
        return Some((indent, true, indent + digits + 2, number));
    }
    None
}

fn is_block_start(line: &str) -> bool {
    let trimmed = line.trim_start();
    heading(trimmed).is_some()
        || fence_length(trimmed).is_some()
        || is_rule(trimmed)
        || trimmed.starts_with('>')
        || list_marker(line).is_some()
}

// --------------------------------------------------------------------------- //
// Block parsing
// --------------------------------------------------------------------------- //

fn parse_blocks(lines: &[&str]) -> Vec<Block> {
    let mut blocks = Vec::new();
    let mut index = 0usize;
    while index < lines.len() {
        if lines[index].trim().is_empty() {
            index += 1;
            continue;
        }
        let line = lines[index];
        let trimmed = line.trim_start();

        if let Some((level, text)) = heading(trimmed) {
            blocks.push(Block::Heading(level, text.to_string()));
            index += 1;
            continue;
        }
        if let Some(length) = fence_length(trimmed) {
            index += 1;
            let mut content: Vec<&str> = Vec::new();
            while index < lines.len() {
                if closes_fence(lines[index], length) {
                    index += 1;
                    break;
                }
                content.push(lines[index]);
                index += 1;
            }
            blocks.push(Block::Code(content.join("\n")));
            continue;
        }
        if is_rule(trimmed) {
            blocks.push(Block::Rule);
            index += 1;
            continue;
        }
        if trimmed.starts_with('>') {
            let mut quoted: Vec<&str> = Vec::new();
            while index < lines.len() && lines[index].trim_start().starts_with('>') {
                let inner = lines[index].trim_start();
                let inner = inner
                    .strip_prefix("> ")
                    .or_else(|| inner.strip_prefix('>'))
                    .unwrap_or("");
                quoted.push(inner);
                index += 1;
            }
            blocks.push(Block::Quote(parse_blocks(&quoted)));
            continue;
        }
        if let Some((indent, ordered, _, number)) = list_marker(line) {
            blocks.push(parse_list(lines, &mut index, indent, ordered, number));
            continue;
        }

        let mut paragraph: Vec<&str> = Vec::new();
        while index < lines.len()
            && !lines[index].trim().is_empty()
            && !is_block_start(lines[index])
        {
            paragraph.push(lines[index].trim_end());
            index += 1;
        }
        if paragraph.is_empty() {
            // Defensive: never loop forever on a line that looked like a block
            // start but produced no block.
            index += 1;
            continue;
        }
        blocks.push(Block::Paragraph(paragraph.join("\n")));
    }
    blocks
}

fn parse_list(
    lines: &[&str],
    index: &mut usize,
    base_indent: usize,
    ordered: bool,
    first_number: i64,
) -> Block {
    let mut items: Vec<ListItem> = Vec::new();
    while *index < lines.len() {
        let Some((indent, item_ordered, content_start, number)) = list_marker(lines[*index]) else {
            break;
        };
        if indent != base_indent || item_ordered != ordered {
            break;
        }
        let mut item_lines: Vec<&str> = vec![&lines[*index][content_start..]];
        *index += 1;
        while *index < lines.len() {
            if lines[*index].trim().is_empty() {
                item_lines.push("");
                *index += 1;
                continue;
            }
            let line_indent = indent_of(lines[*index]);
            if line_indent <= base_indent {
                break;
            }
            let cut = (base_indent + 2).min(line_indent);
            item_lines.push(&lines[*index][cut..]);
            *index += 1;
        }
        items.push(ListItem {
            number: if ordered { Some(number) } else { None },
            blocks: parse_blocks(&item_lines),
        });
    }
    Block::List {
        ordered,
        start: first_number,
        items,
    }
}

// --------------------------------------------------------------------------- //
// Inline parsing
// --------------------------------------------------------------------------- //

fn escape_html(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    for character in text.chars() {
        escape_char(&mut output, character);
    }
    output
}

fn escape_char(output: &mut String, character: char) {
    match character {
        '&' => output.push_str("&amp;"),
        '<' => output.push_str("&lt;"),
        '>' => output.push_str("&gt;"),
        '"' => output.push_str("&quot;"),
        '\'' => output.push_str("&#39;"),
        _ => output.push(character),
    }
}

fn count_run(characters: &[char], start: usize, needle: char) -> usize {
    characters[start..]
        .iter()
        .take_while(|character| **character == needle)
        .count()
}

fn find_run(characters: &[char], start: usize, length: usize) -> Option<usize> {
    let mut index = start;
    while index < characters.len() {
        if characters[index] == '`' {
            let run = count_run(characters, index, '`');
            if run == length {
                return Some(index);
            }
            index += run;
        } else {
            index += 1;
        }
    }
    None
}

fn find_pair(characters: &[char], start: usize, needle: char) -> Option<usize> {
    (start..characters.len()).find(|index| characters[*index] == needle)
}

fn find_double(characters: &[char], start: usize, needle: char) -> Option<usize> {
    let mut index = start;
    while index + 1 < characters.len() {
        if characters[index] == needle && characters[index + 1] == needle {
            return Some(index);
        }
        index += 1;
    }
    None
}

fn text_of(characters: &[char], start: usize, end: usize) -> String {
    characters[start..end].iter().collect()
}

/// Parse `[label](target)` starting at the opening bracket.
fn parse_link(characters: &[char], start: usize) -> Option<(String, String, usize)> {
    let label_end = find_pair(characters, start + 1, ']')?;
    if label_end + 1 >= characters.len() || characters[label_end + 1] != '(' {
        return None;
    }
    let target_end = find_pair(characters, label_end + 2, ')')?;
    let mut target = text_of(characters, label_end + 2, target_end);
    let trimmed = target.trim();
    if trimmed.starts_with('<') && trimmed.ends_with('>') && trimmed.len() >= 2 {
        target = trimmed[1..trimmed.len() - 1].to_string();
    } else {
        target = trimmed.to_string();
    }
    Some((
        text_of(characters, start + 1, label_end),
        target,
        target_end + 1,
    ))
}

fn render_inline(text: &str) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut output = String::with_capacity(text.len());
    let mut index = 0usize;
    while index < characters.len() {
        let character = characters[index];
        if character == '\\'
            && index + 1 < characters.len()
            && characters[index + 1].is_ascii_punctuation()
        {
            escape_char(&mut output, characters[index + 1]);
            index += 2;
            continue;
        }
        if character == '\n' {
            output.push_str("<br>");
            index += 1;
            continue;
        }
        if character == '`' {
            let run = count_run(&characters, index, '`');
            if let Some(end) = find_run(&characters, index + run, run) {
                output.push_str("<code style=\"font-family:monospace;\">");
                output.push_str(&escape_html(&text_of(&characters, index + run, end)));
                output.push_str("</code>");
                index = end + run;
            } else {
                for _ in 0..run {
                    escape_char(&mut output, '`');
                }
                index += run;
            }
            continue;
        }
        if character == '*' || character == '_' {
            let doubled = index + 1 < characters.len() && characters[index + 1] == character;
            if doubled {
                if let Some(end) = find_double(&characters, index + 2, character) {
                    output.push_str("<strong>");
                    output.push_str(&render_inline(&text_of(&characters, index + 2, end)));
                    output.push_str("</strong>");
                    index = end + 2;
                    continue;
                }
            } else if let Some(end) = find_pair(&characters, index + 1, character) {
                output.push_str("<em>");
                output.push_str(&render_inline(&text_of(&characters, index + 1, end)));
                output.push_str("</em>");
                index = end + 1;
                continue;
            }
            escape_char(&mut output, character);
            index += 1;
            continue;
        }
        if character == '~' && index + 1 < characters.len() && characters[index + 1] == '~' {
            if let Some(end) = find_double(&characters, index + 2, '~') {
                output.push_str("<del>");
                output.push_str(&render_inline(&text_of(&characters, index + 2, end)));
                output.push_str("</del>");
                index = end + 2;
                continue;
            }
        }
        if character == '!' && index + 1 < characters.len() && characters[index + 1] == '[' {
            if let Some((alt, source, next)) = parse_link(&characters, index + 1) {
                if let Some(url) = safe_href(&source) {
                    if !url.to_ascii_lowercase().starts_with("data:") {
                        output.push_str("<img src=\"");
                        output.push_str(&escape_html(&url));
                        output.push_str("\" alt=\"");
                        output.push_str(&escape_html(&strip_inline(&alt)));
                        output.push_str("\">");
                        index = next;
                        continue;
                    }
                }
                index = next;
                continue;
            }
        }
        if character == '[' {
            if let Some((label, target, next)) = parse_link(&characters, index) {
                let rendered = render_inline(&label);
                match safe_href(&target) {
                    Some(url) => {
                        output.push_str("<a href=\"");
                        output.push_str(&escape_html(&url));
                        output.push_str("\" style=\"text-decoration:underline;\">");
                        output.push_str(&rendered);
                        output.push_str("</a>");
                    }
                    None => output.push_str(&rendered),
                }
                index = next;
                continue;
            }
        }
        escape_char(&mut output, character);
        index += 1;
    }
    output
}

/// Remove inline Markdown markers, keeping the visible text.
fn strip_inline(text: &str) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut output = String::with_capacity(text.len());
    let mut index = 0usize;
    while index < characters.len() {
        let character = characters[index];
        if character == '\\'
            && index + 1 < characters.len()
            && characters[index + 1].is_ascii_punctuation()
        {
            output.push(characters[index + 1]);
            index += 2;
            continue;
        }
        if character == '`' {
            let run = count_run(&characters, index, '`');
            if let Some(end) = find_run(&characters, index + run, run) {
                output.push_str(&text_of(&characters, index + run, end));
                index = end + run;
            } else {
                index += run;
            }
            continue;
        }
        if character == '*' || character == '_' {
            let doubled = index + 1 < characters.len() && characters[index + 1] == character;
            if doubled {
                if let Some(end) = find_double(&characters, index + 2, character) {
                    output.push_str(&strip_inline(&text_of(&characters, index + 2, end)));
                    index = end + 2;
                    continue;
                }
            } else if let Some(end) = find_pair(&characters, index + 1, character) {
                output.push_str(&strip_inline(&text_of(&characters, index + 1, end)));
                index = end + 1;
                continue;
            }
            index += 1;
            continue;
        }
        if character == '~' && index + 1 < characters.len() && characters[index + 1] == '~' {
            if let Some(end) = find_double(&characters, index + 2, '~') {
                output.push_str(&strip_inline(&text_of(&characters, index + 2, end)));
                index = end + 2;
                continue;
            }
        }
        if character == '!' && index + 1 < characters.len() && characters[index + 1] == '[' {
            if let Some((alt, _, next)) = parse_link(&characters, index + 1) {
                output.push_str(&strip_inline(&alt));
                index = next;
                continue;
            }
        }
        if character == '[' {
            if let Some((label, _, next)) = parse_link(&characters, index) {
                output.push_str(&strip_inline(&label));
                index = next;
                continue;
            }
        }
        output.push(character);
        index += 1;
    }
    output
}

// --------------------------------------------------------------------------- //
// HTML rendering
// --------------------------------------------------------------------------- //

fn render_inline_block(tag: &str, style: &str, text: &str) -> String {
    format!("<{tag} style=\"{style}\">{}</{tag}>\n", render_inline(text))
}

fn render_list_item(item: &ListItem) -> String {
    let mut output = String::new();
    let mut paragraphs = 0usize;
    for block in &item.blocks {
        match block {
            Block::Paragraph(text) => {
                if paragraphs > 0 {
                    output.push_str("<br>");
                }
                output.push_str(&render_inline(text));
                paragraphs += 1;
            }
            other => output.push_str(&render_block(other)),
        }
    }
    output
}

fn render_block(block: &Block) -> String {
    match block {
        Block::Heading(level, text) => {
            let size = match level {
                1 => "2em",
                2 => "1.5em",
                3 => "1.25em",
                _ => "1em",
            };
            render_inline_block(
                &format!("h{level}"),
                &format!("font-size:{size};margin:0.8em 0 0.4em;"),
                text,
            )
        }
        Block::Paragraph(text) => render_inline_block("p", "margin:0 0 1em;", text),
        Block::Code(text) => {
            let escaped = escape_html(text);
            let style = "margin:0 0 1em;padding:0.75em;white-space:pre-wrap;font-family:monospace;";
            format!(
                "<pre style=\"{style}\"><code style=\"font-family:monospace;\">\
                 {escaped}</code></pre>\n"
            )
        }
        Block::Rule => {
            "<hr style=\"border:0;border-top:1px solid currentColor;margin:1.5em 0;\">\n"
                .to_string()
        }
        Block::Quote(blocks) => {
            let inner: String = blocks.iter().map(render_block).collect();
            format!(
                "<blockquote style=\"margin:0 0 1em;padding-left:1em;\
                 border-left:3px solid currentColor;\">\n{inner}</blockquote>\n"
            )
        }
        Block::List {
            ordered,
            start,
            items,
        } => {
            let tag = if *ordered { "ol" } else { "ul" };
            let start_attribute = if *ordered && *start != 1 {
                format!(" start=\"{start}\"")
            } else {
                String::new()
            };
            let mut output =
                format!("<{tag}{start_attribute} style=\"margin:0 0 1em;padding-left:1.5em;\">\n");
            for (index, item) in items.iter().enumerate() {
                let mut attribute = String::new();
                if *ordered {
                    if let Some(number) = item.number {
                        let expected = *start + index as i64;
                        if number != expected {
                            attribute = format!(" value=\"{number}\"");
                        }
                    }
                }
                output.push_str(&format!(
                    "<li{attribute} style=\"margin:0.25em 0;\">{}</li>\n",
                    render_list_item(item)
                ));
            }
            output.push_str(&format!("</{tag}>\n"));
            output
        }
    }
}

fn render_blocks(blocks: &[Block]) -> String {
    blocks.iter().map(render_block).collect()
}

/// Render Markdown to a complete, escaped HTML document.
///
/// The document is theme-neutral: it uses semantic tags with inline styles for
/// typography only, no colours and no scripts.  User text is HTML-escaped
/// before it is placed in a tag; link targets survive only when they use
/// `http`, `https`, `mailto` or a relative URL.
pub fn to_html(markdown: &str) -> String {
    let normalized = markdown.replace("\r\n", "\n").replace('\r', "\n");
    let lines: Vec<&str> = normalized.lines().collect();
    let body = render_blocks(&parse_blocks(&lines));
    let mut document = String::new();
    document.push_str("<!DOCTYPE html>\n<html>\n<head>\n<meta charset=\"utf-8\">\n");
    document.push_str("<title>DeepL-oFM</title>\n");
    document.push_str(
        "<style>body{margin:2em auto;max-width:46em;padding:0 1em;\
         font-family:system-ui,-apple-system,'Segoe UI',sans-serif;\
         line-height:1.6;font-size:16px;}</style>\n",
    );
    document.push_str("</head>\n<body>\n");
    document.push_str(&body);
    document.push_str("</body>\n</html>\n");
    document
}

// --------------------------------------------------------------------------- //
// Plain-text rendering
// --------------------------------------------------------------------------- //

fn tidy_plain(text: &str) -> String {
    let mut lines: Vec<String> = text
        .split('\n')
        .map(|line| line.trim_end().to_string())
        .collect();
    let mut output: Vec<String> = Vec::new();
    let mut blank_run = 0usize;
    for line in lines.drain(..) {
        if line.is_empty() {
            blank_run += 1;
            if blank_run > 1 {
                continue;
            }
        } else {
            blank_run = 0;
        }
        output.push(line);
    }
    output.join("\n").trim().to_string()
}

/// Strip Markdown markers, keeping paragraphs, list bullets and line breaks.
///
/// Fenced code keeps its content verbatim; links and images become their label
/// or alt text.
pub fn to_plain(markdown: &str) -> String {
    let normalized = markdown.replace("\r\n", "\n").replace('\r', "\n");
    let mut output: Vec<String> = Vec::new();
    let mut fence: Option<usize> = None;
    for line in normalized.split('\n') {
        if let Some(length) = fence {
            if closes_fence(line, length) {
                fence = None;
            } else {
                output.push(line.to_string());
            }
            continue;
        }
        let trimmed = line.trim_start();
        if let Some(length) = fence_length(trimmed) {
            fence = Some(length);
            continue;
        }
        if trimmed.is_empty() {
            output.push(String::new());
            continue;
        }
        let indent = &line[..line.len() - trimmed.len()];
        if let Some((_, text)) = heading(trimmed) {
            output.push(format!("{indent}{}", strip_inline(text)));
            continue;
        }
        if is_rule(trimmed) {
            output.push(format!("{indent}---"));
            continue;
        }
        if let Some(rest) = trimmed.strip_prefix("> ") {
            output.push(format!("{indent}{}", strip_inline(rest)));
            continue;
        }
        if trimmed == ">" {
            output.push(String::new());
            continue;
        }
        if let Some((_, _, content_start, _)) = list_marker(line) {
            let marker = &line[indent.len()..content_start];
            let rest = &line[content_start..];
            output.push(format!("{indent}{marker}{}", strip_inline(rest)));
            continue;
        }
        output.push(format!("{indent}{}", strip_inline(trimmed)));
    }
    tidy_plain(&output.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::pasteboard::html_to_markdown;

    fn round_trip(markdown: &str) {
        assert_eq!(html_to_markdown(&to_html(markdown)), markdown);
    }

    #[test]
    fn document_is_complete_and_escapes_text() {
        let html = to_html("hello <script>alert(1)</script> & bye");
        assert!(html.starts_with("<!DOCTYPE html>"));
        assert!(html.contains("<html>"));
        assert!(html.contains("<body>"));
        assert!(html.contains("</html>"));
        assert!(html.contains("&lt;script&gt;"));
        assert!(!html.contains("<script>"));
        assert!(html.contains("&amp;"));
    }

    #[test]
    fn unsafe_link_targets_are_dropped() {
        let html = to_html("[Bad](javascript:alert(1))");
        assert!(html.contains("Bad"));
        assert!(!html.contains("javascript:"));
        assert!(!html.contains("<a "));
    }

    #[test]
    fn attributes_are_escaped() {
        let html = to_html(r#"[x](https://example.com/?a=1&b="2")"#);
        assert!(html.contains("&amp;b=&quot;2&quot;"));
    }

    #[test]
    fn round_trip_headings() {
        round_trip("# Title\n\n### Sub");
        round_trip("###### Deep");
    }

    #[test]
    fn round_trip_paragraphs_and_breaks() {
        round_trip("First line\nsecond\n\nNext");
        round_trip("One\n\nTwo");
    }

    #[test]
    fn round_trip_emphasis_and_code() {
        round_trip("**Bold** and *italic* and `x = 1` plus `tt`");
        round_trip("**B** *I*");
        round_trip("~~gone~~");
    }

    #[test]
    fn round_trip_links() {
        round_trip("[Example](https://example.com)");
        round_trip("[Mail](mailto:x@example.com)");
        round_trip("[Docs](/docs/intro)");
    }

    #[test]
    fn round_trip_lists() {
        round_trip("- One\n  - Nested\n- Two");
        round_trip("1. First\n  1. Sub\n2. Second");
        round_trip("- a\n- b\n- c");
        round_trip("3. Three\n7. Seven\n8. Eight");
    }

    #[test]
    fn round_trip_quote_rule_and_code() {
        round_trip("> Quoted");
        round_trip("> One\n>\n> Two");
        round_trip("A\n\n---\n\nB");
        round_trip("```\ndef f():\n    return 1\n```");
        round_trip("````\na ``` b\n````");
    }

    #[test]
    fn round_trip_realistic_fragment() {
        round_trip(
            "## Release notes\n\n\
             Version **2.0** adds *dark mode* and [docs](https://example.com/docs).\n\n\
             - Faster startup\n\
             - Better search\n  - Fuzzy matching\n\n\
             > Ship it.\n\n\
             ```\n\
             pip install app\n\
             ```",
        );
    }

    #[test]
    fn plain_strips_markers_and_keeps_structure() {
        let markdown = "# Title\n\nSome **bold** and *italic* and `code`.\n\n\
                        - one\n- two\n\n> quote\n\n[link](https://example.com)";
        assert_eq!(
            to_plain(markdown),
            "Title\n\nSome bold and italic and code.\n\n- one\n- two\n\nquote\n\nlink"
        );
    }

    #[test]
    fn plain_keeps_code_verbatim_and_list_numbers() {
        assert_eq!(to_plain("```\na **b**\n```"), "a **b**");
        assert_eq!(to_plain("1. one\n2. two"), "1. one\n2. two");
        assert_eq!(to_plain("- a\n  - b"), "- a\n  - b");
    }

    #[test]
    fn plain_handles_empty_input() {
        assert_eq!(to_plain(""), "");
        assert_eq!(to_plain("   \n\n"), "");
    }

    #[test]
    fn plain_strips_images_and_escapes() {
        assert_eq!(to_plain("![Pic](https://example.com/a.png)"), "Pic");
        assert_eq!(to_plain(r"\*not emphasis\*"), "*not emphasis*");
    }
}
