//! HTML fragment to Markdown conversion.
//!
//! This is a hand-written port of the `html.parser` based converter in
//! `windows/deepl_ofm/support/pasteboard.py`.  It builds a tolerant element
//! tree (implied end tags, void elements, dropped `script`/`style` content) and
//! renders it structurally.  Tables become tab-separated rows because inventing
//! a table dialect would change the text sent to the translator.

use std::collections::HashMap;

/// Elements whose text content never belongs in the converted document.
const SKIP_CONTENT: &[&str] = &["head", "noscript", "script", "style", "template", "title"];

/// Elements that do not have a closing tag.
const VOID_TAGS: &[&str] = &[
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
    "track", "wbr",
];

/// Elements rendered as a block (they flush the surrounding inline text).
const BLOCK_TAGS: &[&str] = &[
    "address",
    "article",
    "aside",
    "blockquote",
    "body",
    "caption",
    "center",
    "dd",
    "details",
    "dialog",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hgroup",
    "hr",
    "html",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "summary",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
];

/// Tags that implicitly close an open element of the same kind.
fn implied_closers(tag: &str) -> Option<&'static [&'static str]> {
    match tag {
        "dd" | "dt" => Some(&["dd", "dt"]),
        "li" => Some(&["li"]),
        "option" => Some(&["option"]),
        "p" => Some(&["p"]),
        "td" | "th" => Some(&["td", "th"]),
        "tr" => Some(&["tr"]),
        _ => None,
    }
}

fn is_heading(tag: &str) -> Option<usize> {
    let bytes = tag.as_bytes();
    if bytes.len() == 2 && bytes[0] == b'h' && (b'1'..=b'6').contains(&bytes[1]) {
        Some(usize::from(bytes[1] - b'0'))
    } else {
        None
    }
}

// --------------------------------------------------------------------------- //
// Tree building
// --------------------------------------------------------------------------- //

#[derive(Clone, Debug)]
enum Child {
    Text(String),
    Node(Node),
}

#[derive(Clone, Debug, Default)]
struct Node {
    tag: String,
    attrs: HashMap<String, String>,
    children: Vec<Child>,
}

impl Node {
    fn new(tag: String, attrs: HashMap<String, String>) -> Self {
        Self {
            tag,
            attrs,
            children: Vec::new(),
        }
    }
}

#[derive(Debug)]
struct TreeBuilder {
    /// `stack[0]` is the synthetic root; its tag is `#root`.
    stack: Vec<Node>,
}

impl TreeBuilder {
    fn new() -> Self {
        Self {
            stack: vec![Node::new("#root".to_string(), HashMap::new())],
        }
    }

    fn current_tag(&self) -> &str {
        self.stack
            .last()
            .map(|node| node.tag.as_str())
            .unwrap_or("")
    }

    /// Move the top of the stack into its parent.
    fn close_top(&mut self) {
        if self.stack.len() > 1 {
            if let Some(node) = self.stack.pop() {
                if let Some(parent) = self.stack.last_mut() {
                    parent.children.push(Child::Node(node));
                }
            }
        }
    }

    /// Close every element from the top down to (and including) `index`.
    fn close_to(&mut self, index: usize) {
        while self.stack.len() > index && self.stack.len() > 1 {
            self.close_top();
        }
    }

    fn close_implied(&mut self, tag: &str) {
        let Some(closers) = implied_closers(tag) else {
            return;
        };
        while self.stack.len() > 1 && closers.contains(&self.current_tag()) {
            self.close_top();
        }
    }

    fn start_tag(&mut self, tag: String, attrs: HashMap<String, String>, self_closing: bool) {
        self.close_implied(&tag);
        if BLOCK_TAGS.contains(&tag.as_str()) && self.current_tag() == "p" {
            self.close_top();
        }
        let void = VOID_TAGS.contains(&tag.as_str());
        let node = Node::new(tag, attrs);
        if void || self_closing {
            if let Some(parent) = self.stack.last_mut() {
                parent.children.push(Child::Node(node));
            }
        } else {
            self.stack.push(node);
        }
    }

    fn end_tag(&mut self, tag: &str) {
        if let Some(index) = self.stack.iter().rposition(|node| node.tag == tag) {
            if index > 0 {
                self.close_to(index);
            }
        }
    }

    fn text(&mut self, data: &str) {
        if data.is_empty() {
            return;
        }
        let data = decode_entities(data);
        if data.is_empty() {
            return;
        }
        let Some(current) = self.stack.last_mut() else {
            return;
        };
        match current.children.last_mut() {
            Some(Child::Text(existing)) => existing.push_str(&data),
            _ => current.children.push(Child::Text(data)),
        }
    }

    fn finish(mut self) -> Node {
        self.close_to(1);
        self.stack.remove(0)
    }
}

// --------------------------------------------------------------------------- //
// Tokenizer
// --------------------------------------------------------------------------- //

struct StartTag {
    name: String,
    attrs: HashMap<String, String>,
    self_closing: bool,
    next: usize,
}

fn is_name_start(byte: u8) -> bool {
    byte.is_ascii_alphabetic()
}

fn is_name_char(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b':' || byte == b'-'
}

fn parse_start_tag(html: &str, lt: usize) -> Option<StartTag> {
    let bytes = html.as_bytes();
    let len = bytes.len();
    let mut index = lt + 1;
    if index >= len || !is_name_start(bytes[index]) {
        return None;
    }
    let name_start = index;
    while index < len && is_name_char(bytes[index]) {
        index += 1;
    }
    let name = html[name_start..index].to_ascii_lowercase();
    let mut attrs = HashMap::new();
    loop {
        while index < len && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        if index >= len {
            return None;
        }
        if bytes[index] == b'>' {
            return Some(StartTag {
                name,
                attrs,
                self_closing: false,
                next: index + 1,
            });
        }
        if bytes[index] == b'/' {
            if index + 1 < len && bytes[index + 1] == b'>' {
                return Some(StartTag {
                    name,
                    attrs,
                    self_closing: true,
                    next: index + 2,
                });
            }
            index += 1;
            continue;
        }
        let attr_start = index;
        while index < len
            && !bytes[index].is_ascii_whitespace()
            && bytes[index] != b'='
            && bytes[index] != b'>'
            && bytes[index] != b'/'
        {
            index += 1;
        }
        if index == attr_start {
            index += 1;
            continue;
        }
        let attr_name = html[attr_start..index].to_ascii_lowercase();
        while index < len && bytes[index].is_ascii_whitespace() {
            index += 1;
        }
        let mut value = String::new();
        if index < len && bytes[index] == b'=' {
            index += 1;
            while index < len && bytes[index].is_ascii_whitespace() {
                index += 1;
            }
            if index >= len {
                return None;
            }
            if bytes[index] == b'"' || bytes[index] == b'\'' {
                let quote = bytes[index];
                index += 1;
                let value_start = index;
                while index < len && bytes[index] != quote {
                    index += 1;
                }
                if index >= len {
                    return None;
                }
                value = decode_entities(&html[value_start..index]);
                index += 1;
            } else {
                let value_start = index;
                while index < len && !bytes[index].is_ascii_whitespace() && bytes[index] != b'>' {
                    index += 1;
                }
                value = decode_entities(&html[value_start..index]);
            }
        }
        attrs.insert(attr_name, value);
    }
}

fn parse_end_tag(html: &str, lt: usize) -> Option<(String, usize)> {
    let bytes = html.as_bytes();
    let len = bytes.len();
    let mut index = lt + 2;
    if index >= len || !is_name_start(bytes[index]) {
        return None;
    }
    let name_start = index;
    while index < len && is_name_char(bytes[index]) {
        index += 1;
    }
    let name = html[name_start..index].to_ascii_lowercase();
    while index < len && bytes[index] != b'>' {
        index += 1;
    }
    if index >= len {
        return None;
    }
    Some((name, index + 1))
}

/// Skip the raw content of a `script`/`style`/`head`-like element.
///
/// Nested elements from the same set are counted the way `html.parser` counts
/// them, so a `title` inside `head` cannot end the skip early.
fn skip_raw_content(html: &str, from: usize) -> usize {
    let mut depth = 1usize;
    let mut index = from;
    while let Some(relative) = html[index..].find('<') {
        let at = index + relative;
        if html[at..].starts_with("<!--") {
            match html[at..].find("-->") {
                Some(end) => index = at + end + 3,
                None => return html.len(),
            }
            continue;
        }
        if html[at..].starts_with("</") {
            if let Some((name, next)) = parse_end_tag(html, at) {
                if SKIP_CONTENT.contains(&name.as_str()) {
                    depth -= 1;
                    if depth == 0 {
                        return next;
                    }
                }
            }
        } else if let Some(start) = parse_start_tag(html, at) {
            if SKIP_CONTENT.contains(&start.name.as_str()) && !start.self_closing {
                depth += 1;
            }
        }
        index = at + 1;
    }
    html.len()
}

fn build_tree(html: &str) -> Node {
    let mut builder = TreeBuilder::new();
    let bytes = html.as_bytes();
    let len = bytes.len();
    let mut index = 0;
    while index < len {
        let Some(relative) = html[index..].find('<') else {
            builder.text(&html[index..]);
            break;
        };
        let lt = index + relative;
        if lt > index {
            builder.text(&html[index..lt]);
        }
        if html[lt..].starts_with("<!--") {
            match html[lt..].find("-->") {
                Some(end) => index = lt + end + 3,
                None => break,
            }
            continue;
        }
        if html[lt..].starts_with("<!") || html[lt..].starts_with("<?") {
            match html[lt..].find('>') {
                Some(end) => index = lt + end + 1,
                None => break,
            }
            continue;
        }
        if html[lt..].starts_with("</") {
            if let Some((name, next)) = parse_end_tag(html, lt) {
                builder.end_tag(&name);
                index = next;
            } else {
                builder.text("<");
                index = lt + 1;
            }
            continue;
        }
        if let Some(start) = parse_start_tag(html, lt) {
            let skip = SKIP_CONTENT.contains(&start.name.as_str());
            if skip {
                if start.self_closing {
                    index = start.next;
                } else {
                    index = skip_raw_content(html, start.next);
                }
            } else {
                builder.start_tag(start.name, start.attrs, start.self_closing);
                index = start.next;
            }
            continue;
        }
        builder.text("<");
        index = lt + 1;
    }
    builder.finish()
}

// --------------------------------------------------------------------------- //
// Entities
// --------------------------------------------------------------------------- //

/// Common named character references understood by the converter.
///
/// Unknown names are left in the text exactly as written, which is what
/// `html.parser` does for references it does not recognise.
const NAMED_ENTITIES: &[(&str, &str)] = &[
    ("amp", "&"),
    ("lt", "<"),
    ("gt", ">"),
    ("quot", "\""),
    ("apos", "'"),
    ("nbsp", "\u{00a0}"),
    ("ensp", "\u{2002}"),
    ("emsp", "\u{2003}"),
    ("thinsp", "\u{2009}"),
    ("zwnj", "\u{200c}"),
    ("zwj", "\u{200d}"),
    ("lrm", "\u{200e}"),
    ("rlm", "\u{200f}"),
    ("ndash", "\u{2013}"),
    ("mdash", "\u{2014}"),
    ("horbar", "\u{2015}"),
    ("hellip", "\u{2026}"),
    ("lsquo", "\u{2018}"),
    ("rsquo", "\u{2019}"),
    ("sbquo", "\u{201a}"),
    ("ldquo", "\u{201c}"),
    ("rdquo", "\u{201d}"),
    ("bdquo", "\u{201e}"),
    ("dagger", "\u{2020}"),
    ("Dagger", "\u{2021}"),
    ("bull", "\u{2022}"),
    ("permil", "\u{2030}"),
    ("prime", "\u{2032}"),
    ("Prime", "\u{2033}"),
    ("lsaquo", "\u{2039}"),
    ("rsaquo", "\u{203a}"),
    ("oline", "\u{203e}"),
    ("frasl", "\u{2044}"),
    ("euro", "\u{20ac}"),
    ("trade", "\u{2122}"),
    ("larr", "\u{2190}"),
    ("uarr", "\u{2191}"),
    ("rarr", "\u{2192}"),
    ("darr", "\u{2193}"),
    ("harr", "\u{2194}"),
    ("crarr", "\u{21b5}"),
    ("forall", "\u{2200}"),
    ("part", "\u{2202}"),
    ("exist", "\u{2203}"),
    ("empty", "\u{2205}"),
    ("nabla", "\u{2207}"),
    ("isin", "\u{2208}"),
    ("notin", "\u{2209}"),
    ("ni", "\u{220b}"),
    ("prod", "\u{220f}"),
    ("sum", "\u{2211}"),
    ("minus", "\u{2212}"),
    ("lowast", "\u{2217}"),
    ("radic", "\u{221a}"),
    ("prop", "\u{221d}"),
    ("infin", "\u{221e}"),
    ("ang", "\u{2220}"),
    ("and", "\u{2227}"),
    ("or", "\u{2228}"),
    ("cap", "\u{2229}"),
    ("cup", "\u{222a}"),
    ("int", "\u{222b}"),
    ("there4", "\u{2234}"),
    ("sim", "\u{223c}"),
    ("cong", "\u{2245}"),
    ("asymp", "\u{2248}"),
    ("ne", "\u{2260}"),
    ("equiv", "\u{2261}"),
    ("le", "\u{2264}"),
    ("ge", "\u{2265}"),
    ("sub", "\u{2282}"),
    ("sup", "\u{2283}"),
    ("nsub", "\u{2284}"),
    ("sube", "\u{2286}"),
    ("supe", "\u{2287}"),
    ("oplus", "\u{2295}"),
    ("otimes", "\u{2297}"),
    ("perp", "\u{22a5}"),
    ("sdot", "\u{22c5}"),
    ("lceil", "\u{2308}"),
    ("rceil", "\u{2309}"),
    ("lfloor", "\u{230a}"),
    ("rfloor", "\u{230b}"),
    ("lang", "\u{2329}"),
    ("rang", "\u{232a}"),
    ("loz", "\u{25ca}"),
    ("spades", "\u{2660}"),
    ("clubs", "\u{2663}"),
    ("hearts", "\u{2665}"),
    ("diams", "\u{2666}"),
    ("OElig", "\u{0152}"),
    ("oelig", "\u{0153}"),
    ("Scaron", "\u{0160}"),
    ("scaron", "\u{0161}"),
    ("Yuml", "\u{0178}"),
    ("fnof", "\u{0192}"),
    ("circ", "\u{02c6}"),
    ("tilde", "\u{02dc}"),
    ("Agrave", "\u{00c0}"),
    ("Aacute", "\u{00c1}"),
    ("Acirc", "\u{00c2}"),
    ("Atilde", "\u{00c3}"),
    ("Auml", "\u{00c4}"),
    ("Aring", "\u{00c5}"),
    ("AElig", "\u{00c6}"),
    ("Ccedil", "\u{00c7}"),
    ("Egrave", "\u{00c8}"),
    ("Eacute", "\u{00c9}"),
    ("Ecirc", "\u{00ca}"),
    ("Euml", "\u{00cb}"),
    ("Igrave", "\u{00cc}"),
    ("Iacute", "\u{00cd}"),
    ("Icirc", "\u{00ce}"),
    ("Iuml", "\u{00cf}"),
    ("ETH", "\u{00d0}"),
    ("Ntilde", "\u{00d1}"),
    ("Ograve", "\u{00d2}"),
    ("Oacute", "\u{00d3}"),
    ("Ocirc", "\u{00d4}"),
    ("Otilde", "\u{00d5}"),
    ("Ouml", "\u{00d6}"),
    ("times", "\u{00d7}"),
    ("Oslash", "\u{00d8}"),
    ("Ugrave", "\u{00d9}"),
    ("Uacute", "\u{00da}"),
    ("Ucirc", "\u{00db}"),
    ("Uuml", "\u{00dc}"),
    ("Yacute", "\u{00dd}"),
    ("THORN", "\u{00de}"),
    ("szlig", "\u{00df}"),
    ("agrave", "\u{00e0}"),
    ("aacute", "\u{00e1}"),
    ("acirc", "\u{00e2}"),
    ("atilde", "\u{00e3}"),
    ("auml", "\u{00e4}"),
    ("aring", "\u{00e5}"),
    ("aelig", "\u{00e6}"),
    ("ccedil", "\u{00e7}"),
    ("egrave", "\u{00e8}"),
    ("eacute", "\u{00e9}"),
    ("ecirc", "\u{00ea}"),
    ("euml", "\u{00eb}"),
    ("igrave", "\u{00ec}"),
    ("iacute", "\u{00ed}"),
    ("icirc", "\u{00ee}"),
    ("iuml", "\u{00ef}"),
    ("eth", "\u{00f0}"),
    ("ntilde", "\u{00f1}"),
    ("ograve", "\u{00f2}"),
    ("oacute", "\u{00f3}"),
    ("ocirc", "\u{00f4}"),
    ("otilde", "\u{00f5}"),
    ("ouml", "\u{00f6}"),
    ("divide", "\u{00f7}"),
    ("oslash", "\u{00f8}"),
    ("ugrave", "\u{00f9}"),
    ("uacute", "\u{00fa}"),
    ("ucirc", "\u{00fb}"),
    ("uuml", "\u{00fc}"),
    ("yacute", "\u{00fd}"),
    ("thorn", "\u{00fe}"),
    ("yuml", "\u{00ff}"),
    ("cent", "\u{00a2}"),
    ("pound", "\u{00a3}"),
    ("curren", "\u{00a4}"),
    ("yen", "\u{00a5}"),
    ("brvbar", "\u{00a6}"),
    ("sect", "\u{00a7}"),
    ("uml", "\u{00a8}"),
    ("copy", "\u{00a9}"),
    ("ordf", "\u{00aa}"),
    ("laquo", "\u{00ab}"),
    ("not", "\u{00ac}"),
    ("shy", "\u{00ad}"),
    ("reg", "\u{00ae}"),
    ("macr", "\u{00af}"),
    ("deg", "\u{00b0}"),
    ("plusmn", "\u{00b1}"),
    ("sup2", "\u{00b2}"),
    ("sup3", "\u{00b3}"),
    ("acute", "\u{00b4}"),
    ("micro", "\u{00b5}"),
    ("para", "\u{00b6}"),
    ("middot", "\u{00b7}"),
    ("cedil", "\u{00b8}"),
    ("sup1", "\u{00b9}"),
    ("ordm", "\u{00ba}"),
    ("raquo", "\u{00bb}"),
    ("frac14", "\u{00bc}"),
    ("frac12", "\u{00bd}"),
    ("frac34", "\u{00be}"),
    ("iquest", "\u{00bf}"),
];

/// Remap the C1 range the way the HTML standard requires.
fn numeric_entity(value: u32) -> char {
    let mapped = match value {
        0x80 => 0x20ac,
        0x82 => 0x201a,
        0x83 => 0x0192,
        0x84 => 0x201e,
        0x85 => 0x2026,
        0x86 => 0x2020,
        0x87 => 0x2021,
        0x88 => 0x02c6,
        0x89 => 0x2030,
        0x8a => 0x0160,
        0x8b => 0x2039,
        0x8c => 0x0152,
        0x8e => 0x017d,
        0x91 => 0x2018,
        0x92 => 0x2019,
        0x93 => 0x201c,
        0x94 => 0x201d,
        0x95 => 0x2022,
        0x96 => 0x2013,
        0x97 => 0x2014,
        0x98 => 0x02dc,
        0x99 => 0x2122,
        0x9a => 0x0161,
        0x9b => 0x203a,
        0x9c => 0x0153,
        0x9e => 0x017e,
        0x9f => 0x0178,
        _ => value,
    };
    if mapped == 0 {
        return '\u{fffd}';
    }
    char::from_u32(mapped).unwrap_or('\u{fffd}')
}

/// Decode character references in text or attribute values.
fn decode_entities(text: &str) -> String {
    if !text.contains('&') {
        return text.to_string();
    }
    let mut output = String::with_capacity(text.len());
    let mut index = 0;
    while let Some(relative) = text[index..].find('&') {
        let amp = index + relative;
        output.push_str(&text[index..amp]);
        let Some(end_relative) = text[amp..].find(';') else {
            output.push_str(&text[amp..]);
            return output;
        };
        let end = amp + end_relative;
        let body = &text[amp + 1..end];
        if let Some(decoded) = decode_entity_body(body) {
            output.push(decoded);
            index = end + 1;
        } else {
            output.push('&');
            index = amp + 1;
        }
    }
    output.push_str(&text[index..]);
    output
}

fn decode_entity_body(body: &str) -> Option<char> {
    if let Some(rest) = body.strip_prefix('#') {
        let value = if let Some(hex) = rest.strip_prefix('x').or_else(|| rest.strip_prefix('X')) {
            u32::from_str_radix(hex, 16).ok()?
        } else {
            rest.parse::<u32>().ok()?
        };
        return Some(numeric_entity(value));
    }
    NAMED_ENTITIES
        .iter()
        .find(|(name, _)| *name == body)
        .and_then(|(_, value)| value.chars().next())
}

// --------------------------------------------------------------------------- //
// Inline rendering
// --------------------------------------------------------------------------- //

fn is_unicode_space(character: char) -> bool {
    matches!(
        character,
        '\u{00a0}' | '\u{1680}' | '\u{2000}'..='\u{200a}' | '\u{202f}' | '\u{205f}' | '\u{3000}'
    )
}

fn is_zero_width(character: char) -> bool {
    matches!(
        character,
        '\u{200b}' | '\u{200c}' | '\u{200d}' | '\u{2060}' | '\u{feff}'
    )
}

fn collapse_text(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut in_space = false;
    for character in text.chars() {
        if is_zero_width(character) {
            continue;
        }
        let character = if is_unicode_space(character) {
            ' '
        } else {
            character
        };
        if matches!(character, ' ' | '\t' | '\r' | '\n' | '\u{0c}' | '\u{0b}') {
            if !in_space {
                output.push(' ');
                in_space = true;
            }
        } else {
            output.push(character);
            in_space = false;
        }
    }
    output
}

fn collapse_inline_spaces(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut in_space = false;
    for character in text.chars() {
        if matches!(character, ' ' | '\t' | '\u{0c}' | '\u{0b}') {
            if !in_space {
                output.push(' ');
                in_space = true;
            }
        } else {
            output.push(character);
            in_space = false;
        }
    }
    output
}

fn clean_inline(text: &str) -> String {
    let collapsed = collapse_inline_spaces(text);
    let characters: Vec<char> = collapsed.chars().collect();
    let mut normalized = String::with_capacity(collapsed.len());
    let mut index = 0;
    while index < characters.len() {
        if characters[index] == '\n' {
            while normalized.ends_with(' ') {
                normalized.pop();
            }
            normalized.push('\n');
            index += 1;
            while index < characters.len() && characters[index] == ' ' {
                index += 1;
            }
        } else {
            normalized.push(characters[index]);
            index += 1;
        }
    }
    let mut output = String::with_capacity(normalized.len());
    let mut newlines = 0;
    for character in normalized.chars() {
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
    output.trim().to_string()
}

/// Apply an inline marker while keeping surrounding spaces outside it.
fn wrap_inline(text: &str, prefix: &str, suffix: Option<&str>) -> String {
    if text.is_empty() {
        return String::new();
    }
    let suffix = suffix.unwrap_or(prefix);
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return text.to_string();
    }
    let start = text.len() - text.trim_start().len();
    let end = text.trim_end().len();
    format!(
        "{}{}{}{}{}",
        &text[..start],
        prefix,
        &text[start..end],
        suffix,
        &text[end..]
    )
}

fn code_span(text: &str) -> String {
    let text = clean_inline(text);
    if text.is_empty() {
        return String::new();
    }
    if !text.contains('`') {
        return format!("`{text}`");
    }
    let mut fence = String::from("``");
    while text.contains(&fence) {
        fence.push('`');
    }
    format!("{fence} {text} {fence}")
}

/// Return a URL that is safe to put in a Markdown link, else `None`.
///
/// Only `http`, `https`, `mailto` and relative targets survive; `javascript:`
/// and every other scheme is dropped like the Swift renderer does.
pub(crate) fn safe_href(value: &str) -> Option<String> {
    let url = value.trim();
    if url.is_empty() {
        return None;
    }
    let probe: String = url
        .chars()
        .filter(|character| *character > '\u{20}')
        .collect::<String>()
        .to_ascii_lowercase();
    if probe.starts_with('#')
        || probe.starts_with('/')
        || probe.starts_with('?')
        || probe.starts_with("./")
        || probe.starts_with("../")
    {
        return Some(url.to_string());
    }
    if let Some(scheme) = scheme_of(&probe) {
        if !matches!(scheme, "http" | "https" | "mailto") {
            return None;
        }
    }
    Some(url.to_string())
}

fn scheme_of(probe: &str) -> Option<&str> {
    let mut characters = probe.char_indices();
    let (_, first) = characters.next()?;
    if !first.is_ascii_lowercase() {
        return None;
    }
    for (index, character) in characters {
        if character == ':' {
            return Some(&probe[..index]);
        }
        if !(character.is_ascii_lowercase()
            || character.is_ascii_digit()
            || matches!(character, '+' | '.' | '-'))
        {
            return None;
        }
    }
    None
}

fn link_target(url: &str) -> String {
    if url.contains([' ', '(', ')', '<', '>']) {
        format!("<{url}>")
    } else {
        url.to_string()
    }
}

fn image_markdown(node: &Node) -> String {
    let source = node.attrs.get("src").map(|s| s.trim()).unwrap_or("");
    if source.is_empty() || source.to_ascii_lowercase().starts_with("data:") {
        return String::new();
    }
    if safe_href(source).is_none() {
        return String::new();
    }
    let alt = clean_inline(&collapse_text(
        node.attrs.get("alt").map(String::as_str).unwrap_or(""),
    ));
    format!("![{alt}]({})", link_target(source))
}

fn render_inline_node(node: &Node) -> String {
    match node.tag.as_str() {
        "br" => "\n".to_string(),
        "img" => image_markdown(node),
        "strong" | "b" => wrap_inline(&render_inline(&node.children), "**", None),
        "em" | "i" => wrap_inline(&render_inline(&node.children), "*", None),
        "code" | "tt" => code_span(&render_inline(&node.children)),
        "del" | "s" | "strike" => wrap_inline(&render_inline(&node.children), "~~", None),
        "a" => {
            let label = clean_inline(&render_inline(&node.children));
            let href = safe_href(node.attrs.get("href").map(String::as_str).unwrap_or(""));
            let Some(href) = href else {
                return label;
            };
            let label = if label.is_empty() {
                href.clone()
            } else {
                label
            };
            format!("[{label}]({})", link_target(&href))
        }
        _ => render_inline(&node.children),
    }
}

fn render_inline(children: &[Child]) -> String {
    let mut output = String::new();
    for child in children {
        match child {
            Child::Text(text) => output.push_str(&collapse_text(text)),
            Child::Node(node) => output.push_str(&render_inline_node(node)),
        }
    }
    output
}

// --------------------------------------------------------------------------- //
// Block rendering
// --------------------------------------------------------------------------- //

/// Text of a `pre` subtree, with its whitespace untouched.
fn raw_text(node: &Node) -> String {
    let mut output = String::new();
    for child in &node.children {
        match child {
            Child::Text(text) => output.push_str(text),
            Child::Node(node) if node.tag == "br" => output.push('\n'),
            Child::Node(node) => output.push_str(&raw_text(node)),
        }
    }
    output
}

fn render_heading(node: &Node) -> Vec<String> {
    let Some(level) = is_heading(&node.tag) else {
        return Vec::new();
    };
    let text = clean_inline(&render_inline(&node.children));
    let text = collapse_newline_whitespace(&text);
    if text.is_empty() {
        Vec::new()
    } else {
        vec![format!("{} {}", "#".repeat(level), text)]
    }
}

fn collapse_newline_whitespace(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut pending_space = false;
    for character in text.chars() {
        if character == '\n' {
            while output.ends_with(char::is_whitespace) {
                output.pop();
            }
            pending_space = true;
            continue;
        }
        if pending_space {
            if character.is_whitespace() {
                continue;
            }
            if !output.is_empty() {
                output.push(' ');
            }
            pending_space = false;
        }
        output.push(character);
    }
    output.trim().to_string()
}

fn render_pre(node: &Node) -> Vec<String> {
    let mut raw = raw_text(node)
        .replace("\r\n", "\n")
        .replace('\r', "\n")
        .replace('\u{00a0}', " ");
    if let Some(rest) = raw.strip_prefix('\n') {
        raw = rest.to_string();
    }
    let raw = raw.trim_end_matches('\n');
    if raw.trim().is_empty() {
        return Vec::new();
    }
    let mut fence = String::from("```");
    while raw.contains(&fence) {
        fence.push('`');
    }
    vec![format!("{fence}\n{raw}\n{fence}")]
}

fn render_list(node: &Node, depth: usize) -> Vec<String> {
    let ordered = node.tag == "ol";
    let indent = "  ".repeat(depth);
    let mut number = node
        .attrs
        .get("start")
        .and_then(|value| value.trim().parse::<i64>().ok())
        .unwrap_or(1);
    let mut lines: Vec<String> = Vec::new();

    for child in &node.children {
        let Child::Node(child) = child else {
            continue;
        };
        if child.tag == "ul" || child.tag == "ol" {
            // Some editors emit a nested list as the next sibling instead of
            // nesting it inside the previous `<li>`; keep its indentation.
            lines.extend(render_list(child, depth + 1));
            continue;
        }
        if child.tag != "li" {
            continue;
        }

        let mut nested: Vec<String> = Vec::new();
        let mut rest: Vec<Child> = Vec::new();
        for item_child in &child.children {
            match item_child {
                Child::Node(item) if item.tag == "ul" || item.tag == "ol" => {
                    nested.extend(render_list(item, depth + 1));
                }
                other => rest.push(other.clone()),
            }
        }

        let marker = if ordered {
            if let Some(value) = child
                .attrs
                .get("value")
                .and_then(|value| value.trim().parse::<i64>().ok())
            {
                number = value;
            }
            let marker = format!("{number}. ");
            number += 1;
            marker
        } else {
            "- ".to_string()
        };

        let blocks = render_blocks(&rest);
        if blocks.is_empty() {
            lines.extend(nested);
            continue;
        }

        let first_lines: Vec<&str> = blocks[0].split('\n').collect();
        if let Some(first) = first_lines.first() {
            lines.push(format!("{indent}{marker}{first}"));
        }
        for line in first_lines.iter().skip(1) {
            lines.push(format!("{indent}  {line}"));
        }
        for block in blocks.iter().skip(1) {
            for line in block.split('\n') {
                lines.push(format!("{indent}  {line}"));
            }
        }
        lines.extend(nested);
    }
    lines
}

fn render_blockquote(node: &Node) -> Vec<String> {
    let mut inner = render_blocks(&node.children);
    if inner.is_empty() {
        let text = clean_inline(&render_inline(&node.children));
        if !text.is_empty() {
            inner.push(text);
        }
    }
    let mut lines: Vec<String> = Vec::new();
    for (index, block) in inner.iter().enumerate() {
        if index > 0 {
            lines.push(">".to_string());
        }
        for line in block.split('\n') {
            if line.is_empty() {
                lines.push(">".to_string());
            } else {
                lines.push(format!("> {line}"));
            }
        }
    }
    if lines.is_empty() {
        Vec::new()
    } else {
        vec![lines.join("\n")]
    }
}

fn table_rows<'a>(node: &'a Node, rows: &mut Vec<&'a Node>) {
    for child in &node.children {
        let Child::Node(child) = child else {
            continue;
        };
        match child.tag.as_str() {
            "tr" => rows.push(child),
            "thead" | "tbody" | "tfoot" => table_rows(child, rows),
            _ => {}
        }
    }
}

fn cell_text(cell: &Node) -> String {
    let blocks = render_blocks(&cell.children);
    let text = blocks
        .iter()
        .map(|block| block.replace('\n', " "))
        .collect::<Vec<_>>()
        .join(" ");
    clean_inline(&text)
}

fn render_table(node: &Node) -> Vec<String> {
    let mut rows: Vec<&Node> = Vec::new();
    table_rows(node, &mut rows);
    if rows.is_empty() {
        return render_blocks(&node.children);
    }
    let mut lines: Vec<String> = Vec::new();
    for row in rows {
        let cells: Vec<&Node> = row
            .children
            .iter()
            .filter_map(|child| match child {
                Child::Node(node) if node.tag == "td" || node.tag == "th" => Some(node),
                _ => None,
            })
            .collect();
        let line = cells
            .iter()
            .map(|cell| cell_text(cell))
            .collect::<Vec<_>>()
            .join("\t");
        if !line.trim().is_empty() {
            lines.push(line);
        }
    }
    if lines.is_empty() {
        Vec::new()
    } else {
        vec![lines.join("\n")]
    }
}

fn render_block_node(node: &Node) -> Vec<String> {
    if is_heading(&node.tag).is_some() {
        return render_heading(node);
    }
    match node.tag.as_str() {
        "p" => {
            let text = clean_inline(&render_inline(&node.children));
            if text.is_empty() {
                Vec::new()
            } else {
                vec![text]
            }
        }
        "ul" | "ol" => {
            let lines = render_list(node, 0);
            if lines.is_empty() {
                Vec::new()
            } else {
                vec![lines.join("\n")]
            }
        }
        "blockquote" => render_blockquote(node),
        "pre" => render_pre(node),
        "hr" => vec!["---".to_string()],
        "table" => render_table(node),
        _ => render_blocks(&node.children),
    }
}

fn flush_inline(blocks: &mut Vec<String>, inline: &mut String) {
    let text = clean_inline(inline);
    inline.clear();
    if !text.is_empty() {
        blocks.push(text);
    }
}

fn render_blocks(children: &[Child]) -> Vec<String> {
    let mut blocks: Vec<String> = Vec::new();
    let mut inline = String::new();
    for child in children {
        match child {
            Child::Text(text) => inline.push_str(&collapse_text(text)),
            Child::Node(node) if BLOCK_TAGS.contains(&node.tag.as_str()) => {
                flush_inline(&mut blocks, &mut inline);
                blocks.extend(render_block_node(node));
            }
            Child::Node(node) => inline.push_str(&render_inline_node(node)),
        }
    }
    flush_inline(&mut blocks, &mut inline);
    blocks.retain(|block| !block.trim().is_empty());
    blocks
}

/// Trim trailing spaces and collapse blank-line runs outside code fences.
fn tidy(text: &str) -> String {
    let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
    let mut output: Vec<&str> = Vec::new();
    let mut fence_length = 0usize;
    let mut in_fence = false;
    let mut blank_run = 0usize;
    for line in normalized.split('\n') {
        let line = line.trim_end();
        let stripped = line.trim_start();
        if stripped.starts_with("```") {
            let run = stripped
                .chars()
                .take_while(|character| *character == '`')
                .count();
            if fence_length == 0 {
                fence_length = run;
                in_fence = true;
            } else if run >= fence_length {
                fence_length = 0;
                in_fence = false;
            }
        } else {
            in_fence = fence_length > 0;
        }
        if !in_fence && line.trim().is_empty() {
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

/// Convert an HTML fragment to Markdown.
///
/// The result uses plain Markdown only; tables become tab-separated rows
/// because inventing a table dialect would change the text sent to the
/// translator.  Malformed fragments degrade to whatever text could be parsed.
pub fn html_to_markdown(html: &str) -> String {
    if html.trim().is_empty() {
        return String::new();
    }
    let root = build_tree(html);
    let blocks = render_blocks(&root.children);
    tidy(&blocks.join("\n\n"))
}

/// Return whether `value` contains at least one HTML-looking tag.
///
/// `text/html` clipboard flavours are sometimes just a plain string, and a
/// clipboard can also expose a plain fragment with no markup at all.
pub fn looks_like_html(value: &str) -> bool {
    if value.is_empty() {
        return false;
    }
    let bytes = value.as_bytes();
    let mut index = 0;
    while let Some(relative) = value[index..].find('<') {
        let at = index + relative;
        if value[at..].starts_with("<!--") {
            if value[at..].find("-->").is_some() {
                return true;
            }
        } else if value[at..].starts_with("<!") {
            let rest = value[at + 2..].trim_start();
            if rest.len() >= 7 && rest.as_bytes()[..7].eq_ignore_ascii_case(b"doctype") {
                return true;
            }
        } else {
            let mut cursor = at + 1;
            if cursor < bytes.len() && bytes[cursor] == b'/' {
                cursor += 1;
            }
            if cursor < bytes.len() && is_name_start(bytes[cursor]) {
                while cursor < bytes.len() && is_name_char(bytes[cursor]) {
                    cursor += 1;
                }
                while cursor < bytes.len() && bytes[cursor].is_ascii_whitespace() {
                    cursor += 1;
                }
                let mut valid = true;
                while cursor < bytes.len() && bytes[cursor] != b'>' {
                    if bytes[cursor] == b'<' {
                        valid = false;
                        break;
                    }
                    cursor += 1;
                }
                if valid && cursor < bytes.len() && bytes[cursor] == b'>' {
                    return true;
                }
            }
        }
        index = at + 1;
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn headings() {
        assert_eq!(
            html_to_markdown("<h1>Title</h1><h3>Sub</h3>"),
            "# Title\n\n### Sub"
        );
        assert_eq!(html_to_markdown("<h6>Deep</h6>"), "###### Deep");
    }

    #[test]
    fn paragraphs_and_br() {
        assert_eq!(
            html_to_markdown("<p>First line<br>second</p><p>Next</p>"),
            "First line\nsecond\n\nNext"
        );
        assert_eq!(
            html_to_markdown("<div>One</div><div>Two</div>"),
            "One\n\nTwo"
        );
    }

    #[test]
    fn bold_italic_and_inline_code() {
        let html = "<p><strong>Bold</strong> and <em>italic</em> and \
                    <code>x = 1</code> plus <tt>tt</tt></p>";
        assert_eq!(
            html_to_markdown(html),
            "**Bold** and *italic* and `x = 1` plus `tt`"
        );
        assert_eq!(html_to_markdown("<p><b>B</b> <i>I</i></p>"), "**B** *I*");
    }

    #[test]
    fn links_and_javascript_dropped() {
        assert_eq!(
            html_to_markdown(r#"<p><a href="https://example.com">Example</a></p>"#),
            "[Example](https://example.com)"
        );
        assert_eq!(
            html_to_markdown(r#"<p><a href="mailto:x@example.com">Mail</a></p>"#),
            "[Mail](mailto:x@example.com)"
        );
        assert_eq!(
            html_to_markdown(r#"<p><a href="/docs/intro">Docs</a></p>"#),
            "[Docs](/docs/intro)"
        );
        assert_eq!(
            html_to_markdown(r#"<p><a href="javascript:alert(1)">Bad</a></p>"#),
            "Bad"
        );
        assert_eq!(
            html_to_markdown(r#"<p><a href="JaVaScRiPt&#58;alert(1)">Bad</a></p>"#),
            "Bad"
        );
        assert_eq!(
            html_to_markdown(r#"<p><a href="ftp://example.com/x">Ftp</a></p>"#),
            "Ftp"
        );
    }

    #[test]
    fn nested_bullet_list() {
        let html = "<ul><li>One<ul><li>Nested</li></ul></li><li>Two</li></ul>";
        assert_eq!(html_to_markdown(html), "- One\n  - Nested\n- Two");
    }

    #[test]
    fn nested_numbered_list() {
        let html = "<ol><li>First<ol><li>Sub</li></ol></li><li>Second</li></ol>";
        assert_eq!(html_to_markdown(html), "1. First\n  1. Sub\n2. Second");
    }

    #[test]
    fn ordered_list_start_and_value() {
        let html = r#"<ol start="3"><li>Three</li><li value="7">Seven</li><li>Eight</li></ol>"#;
        assert_eq!(html_to_markdown(html), "3. Three\n7. Seven\n8. Eight");
    }

    #[test]
    fn blockquote() {
        assert_eq!(
            html_to_markdown("<blockquote>Quoted</blockquote>"),
            "> Quoted"
        );
        assert_eq!(
            html_to_markdown("<blockquote><p>One</p><p>Two</p></blockquote>"),
            "> One\n>\n> Two"
        );
    }

    #[test]
    fn fenced_pre_preserves_whitespace() {
        let html = "<pre>def f():\n    return 1</pre>";
        assert_eq!(html_to_markdown(html), "```\ndef f():\n    return 1\n```");
        let wrapped = "<pre><code>a &lt; b</code></pre>";
        assert_eq!(html_to_markdown(wrapped), "```\na < b\n```");
    }

    #[test]
    fn pre_with_backticks_uses_a_longer_fence() {
        assert_eq!(
            html_to_markdown("<pre>a ``` b</pre>"),
            "````\na ``` b\n````"
        );
    }

    #[test]
    fn table_falls_back_to_tabs() {
        let html = "<table><tr><th>Name</th><th>Age</th></tr>\
                    <tr><td>Ann</td><td>30</td></tr></table>";
        assert_eq!(html_to_markdown(html), "Name\tAge\nAnn\t30");
    }

    #[test]
    fn table_with_thead_and_tbody() {
        let html = "<table><thead><tr><th>A</th></tr></thead>\
                    <tbody><tr><td>1</td></tr></tbody></table>";
        assert_eq!(html_to_markdown(html), "A\n1");
    }

    #[test]
    fn entities_are_decoded() {
        let html = "<p>Tom &amp; Jerry&nbsp;&mdash; &#8212;</p>";
        assert_eq!(html_to_markdown(html), "Tom & Jerry — —");
        assert_eq!(
            html_to_markdown("<p>&#x41;&#66;&unknown;</p>"),
            "AB&unknown;"
        );
        assert_eq!(html_to_markdown("<p>&copy; &eacute;</p>"), "© é");
    }

    #[test]
    fn script_and_style_are_stripped() {
        let html = "<p>Keep</p><script>var x = '<p>no</p>';</script>\
                    <style>p{}</style><p>This</p>";
        assert_eq!(html_to_markdown(html), "Keep\n\nThis");
    }

    #[test]
    fn comments_and_doctype_are_ignored() {
        assert_eq!(
            html_to_markdown("<!DOCTYPE html><!-- comment --><p>A</p>"),
            "A"
        );
    }

    #[test]
    fn hr_and_blank_line_collapse() {
        assert_eq!(html_to_markdown("<p>A</p><hr><p>B</p>"), "A\n\n---\n\nB");
        assert_eq!(html_to_markdown("<p>A</p>\n\n\n\n<p>B</p>"), "A\n\nB");
    }

    #[test]
    fn images_and_deleted_text() {
        let html = "<p><img src=\"https://example.com/a.png\" alt=\"Pic\"> \
                    <img src=\"data:image/png;base64,AAAA\" alt=\"Skipped\"> \
                    <del>gone</del></p>";
        assert_eq!(
            html_to_markdown(html),
            "![Pic](https://example.com/a.png) ~~gone~~"
        );
        assert_eq!(
            html_to_markdown(r#"<img src="javascript:alert(1)" alt="x">"#),
            ""
        );
    }

    #[test]
    fn realistic_browser_fragment() {
        let html = r#"<article>
  <h2>Release notes</h2>
  <p>Version <strong>2.0</strong> adds <em>dark mode</em> and
     <a href="https://example.com/docs">docs</a>.</p>
  <ul>
    <li>Faster startup</li>
    <li>Better search
      <ul><li>Fuzzy matching</li></ul>
    </li>
  </ul>
  <blockquote>Ship it.</blockquote>
  <pre><code>pip install app</code></pre>
</article>
"#;
        assert_eq!(
            html_to_markdown(html),
            "## Release notes\n\n\
             Version **2.0** adds *dark mode* and [docs](https://example.com/docs).\n\n\
             - Faster startup\n\
             - Better search\n  - Fuzzy matching\n\n\
             > Ship it.\n\n\
             ```\n\
             pip install app\n\
             ```"
        );
    }

    #[test]
    fn looks_like_html_detection() {
        assert!(looks_like_html("<p>Hello</p>"));
        assert!(looks_like_html("</div>"));
        assert!(looks_like_html("<!DOCTYPE html>"));
        assert!(looks_like_html("<br/>"));
        assert!(!looks_like_html("plain text"));
        assert!(!looks_like_html("a < b and c > d"));
        assert!(!looks_like_html(""));
    }

    #[test]
    fn empty_html() {
        assert_eq!(html_to_markdown(""), "");
        assert_eq!(html_to_markdown("   \n\t"), "");
    }

    #[test]
    fn malformed_html_degrades_to_text() {
        assert_eq!(html_to_markdown("<p>unclosed"), "unclosed");
        assert_eq!(html_to_markdown("2 < 3"), "2 < 3");
        assert_eq!(html_to_markdown("<p>a</p></div>b"), "a\n\nb");
    }

    #[test]
    fn entity_helpers() {
        assert_eq!(decode_entities("a &amp; b"), "a & b");
        assert_eq!(decode_entities("&#0;"), "\u{fffd}");
        assert_eq!(decode_entities("&notanentity;"), "&notanentity;");
        assert_eq!(numeric_entity(0x80), '\u{20ac}');
    }
}
