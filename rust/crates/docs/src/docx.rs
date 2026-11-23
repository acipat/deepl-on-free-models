//! WordprocessingML (`.docx`) support.
//!
//! Only `word/document.xml` is rewritten; every other archive entry is copied
//! through raw, keeping its bytes, compression method and metadata. The XML is
//! spliced at the `<w:t>` text nodes so namespace prefixes, unused
//! `mc:Ignorable` declarations, comments, run boundaries and all formatting
//! survive byte-for-byte.

use std::collections::HashMap;
use std::io::{Cursor, Read, Write};
use std::path::Path;

use quick_xml::events::{BytesRef, BytesStart, Event};
use quick_xml::reader::Reader;
use zip::read::ZipArchive;
use zip::write::{SimpleFileOptions, ZipWriter};

use crate::error::{docx_error, write_failed, DocumentError, DocumentErrorKind};

const DOCUMENT_XML: &str = "word/document.xml";
/// Same ceiling as the Swift `unzipEntry` guard, in bytes of uncompressed XML.
const MAX_XML: u64 = 32 * 1024 * 1024;

/// Read a DOCX package: the raw `document.xml` plus its paragraph texts.
pub(crate) fn read(path: &Path) -> Result<(Vec<u8>, Vec<String>), DocumentError> {
    let xml = read_document_xml(path)?;
    let scan = scan(&xml).map_err(|detail| docx_error(DocumentErrorKind::Unreadable, detail))?;
    Ok((xml, scan.paragraphs))
}

/// Rewrite the document XML with the translations and rebuild the package.
pub(crate) fn write(
    source: &Path,
    payload: Option<&[u8]>,
    paragraphs: &[String],
    translations: &[String],
    out_path: &Path,
) -> Result<(), DocumentError> {
    let xml = match payload {
        Some(bytes) => bytes.to_vec(),
        None => read_document_xml(source)?,
    };
    let updated = rewrite(&xml, paragraphs, translations)?;
    let package = rebuild(source, &updated)?;
    crate::io::write_atomic(out_path, &package)
}

fn read_document_xml(path: &Path) -> Result<Vec<u8>, DocumentError> {
    let file = std::fs::File::open(path)
        .map_err(|error| docx_error(DocumentErrorKind::Unreadable, error))?;
    let mut archive =
        ZipArchive::new(file).map_err(|error| docx_error(DocumentErrorKind::Unreadable, error))?;
    let mut entry = archive
        .by_name(DOCUMENT_XML)
        .map_err(|error| docx_error(DocumentErrorKind::Unreadable, error))?;
    if entry.size() > MAX_XML {
        return Err(docx_error(
            DocumentErrorKind::Unreadable,
            "word/document.xml is too large",
        ));
    }
    let mut data = Vec::with_capacity(entry.size() as usize);
    entry
        .by_ref()
        .take(MAX_XML + 1)
        .read_to_end(&mut data)
        .map_err(|error| docx_error(DocumentErrorKind::Unreadable, error))?;
    if data.len() as u64 > MAX_XML {
        return Err(docx_error(
            DocumentErrorKind::Unreadable,
            "word/document.xml is too large",
        ));
    }
    Ok(data)
}

/// A `<w:t>` text node with the byte spans needed to splice it.
struct TextNode {
    element_start: usize,
    content_start: usize,
    content_end: usize,
    element_end: usize,
    self_closing: bool,
    paragraph: Option<usize>,
    preserve: bool,
    name: Vec<u8>,
    text: String,
}

struct Scan {
    paragraphs: Vec<String>,
    nodes: Vec<TextNode>,
}

/// Elements whose contents are never translated: Office Math, field
/// instructions, deleted revisions and the compatibility fallback (which
/// duplicates the `mc:Choice` content).
const SKIPPED_ELEMENTS: &[&[u8]] = &[
    b"m:oMath",
    b"m:oMathPara",
    b"w:instrText",
    b"w:delText",
    b"mc:Fallback",
];

fn is_skipped(name: &[u8]) -> bool {
    SKIPPED_ELEMENTS.contains(&name)
}

fn has_preserve(element: &BytesStart<'_>) -> bool {
    element
        .attributes()
        .flatten()
        .any(|attribute| attribute.key.as_ref() == b"xml:space")
}

fn resolve_reference(reference: &BytesRef<'_>) -> Result<String, String> {
    if let Some(character) = reference
        .resolve_char_ref()
        .map_err(|error| error.to_string())?
    {
        return Ok(character.to_string());
    }
    let name = reference.decode().map_err(|error| error.to_string())?;
    let text = match name.as_ref() {
        "amp" => "&",
        "lt" => "<",
        "gt" => ">",
        "quot" => "\"",
        "apos" => "'",
        _ => "",
    };
    Ok(text.to_string())
}

fn push_space(paragraphs: &mut [String], stack: &[usize]) {
    // Only the innermost open paragraph owns the text; a nested text box has
    // its own paragraph and must not duplicate its content into the outer one.
    if let Some(&index) = stack.last() {
        if let Some(paragraph) = paragraphs.get_mut(index) {
            paragraph.push(' ');
        }
    }
}

fn push_text(paragraphs: &mut [String], stack: &[usize], text: &str) {
    if let Some(&index) = stack.last() {
        if let Some(paragraph) = paragraphs.get_mut(index) {
            paragraph.push_str(text);
        }
    }
}

fn scan(xml: &[u8]) -> Result<Scan, String> {
    let mut reader = Reader::from_reader(xml);
    let mut buffer = Vec::new();
    let mut paragraphs: Vec<String> = Vec::new();
    let mut stack: Vec<usize> = Vec::new();
    // Qualified names of the open elements; a skipped subtree only needs its
    // depth, not its inner structure.
    let mut elements: Vec<Vec<u8>> = Vec::new();
    let mut skip_from: Option<usize> = None;
    let mut nodes: Vec<TextNode> = Vec::new();
    // Index into `nodes` of the `<w:t>` element whose text is being collected.
    let mut open_text: Option<usize> = None;

    loop {
        let start = reader.buffer_position() as usize;
        let event = reader
            .read_event_into(&mut buffer)
            .map_err(|error| error.to_string())?;
        let end = reader.buffer_position() as usize;

        match event {
            Event::Start(ref element) => {
                // Only the qualified `w:` names are WordprocessingML; `m:t`
                // (Office Math) and friends are different elements entirely.
                let name = element.name().as_ref().to_vec();
                if skip_from.is_none() && is_skipped(&name) {
                    skip_from = Some(elements.len());
                }
                let skipping = skip_from.is_some();
                elements.push(name.clone());
                if !skipping {
                    match name.as_slice() {
                        b"w:p" => {
                            paragraphs.push(String::new());
                            stack.push(paragraphs.len() - 1);
                        }
                        b"w:t" => {
                            if open_text.is_some() {
                                return Err("nested w:t elements".to_string());
                            }
                            nodes.push(TextNode {
                                element_start: start,
                                content_start: end,
                                content_end: end,
                                element_end: end,
                                self_closing: false,
                                paragraph: stack.last().copied(),
                                preserve: has_preserve(element),
                                name,
                                text: String::new(),
                            });
                            open_text = Some(nodes.len() - 1);
                        }
                        b"w:tab" | b"w:br" | b"w:cr" => push_space(&mut paragraphs, &stack),
                        _ => {}
                    }
                }
            }
            Event::Empty(ref element) => {
                if skip_from.is_none() {
                    let qualified = element.name();
                    let name = qualified.as_ref();
                    match name {
                        b"w:p" => {
                            paragraphs.push(String::new());
                        }
                        b"w:t" => {
                            nodes.push(TextNode {
                                element_start: start,
                                content_start: end,
                                content_end: end,
                                element_end: end,
                                self_closing: true,
                                paragraph: stack.last().copied(),
                                preserve: has_preserve(element),
                                name: name.to_vec(),
                                text: String::new(),
                            });
                        }
                        b"w:tab" | b"w:br" | b"w:cr" => push_space(&mut paragraphs, &stack),
                        _ => {}
                    }
                }
            }
            Event::End(ref element) => {
                elements.pop();
                if let Some(depth) = skip_from {
                    if elements.len() <= depth {
                        skip_from = None;
                    }
                } else {
                    match element.name().as_ref() {
                        b"w:p" => {
                            stack.pop();
                        }
                        b"w:t" => {
                            if let Some(index) = open_text.take() {
                                if let Some(node) = nodes.get_mut(index) {
                                    node.content_end = start;
                                    node.element_end = end;
                                }
                            }
                        }
                        _ => {}
                    }
                }
            }
            Event::Text(ref text) => {
                if skip_from.is_none() {
                    if let Some(index) = open_text {
                        let decoded = text.xml10_content().map_err(|error| error.to_string())?;
                        collect_text(&mut nodes, &mut paragraphs, &stack, index, &decoded);
                    }
                }
            }
            Event::CData(ref data) => {
                if skip_from.is_none() {
                    if let Some(index) = open_text {
                        let decoded = data.decode().map_err(|error| error.to_string())?;
                        collect_text(&mut nodes, &mut paragraphs, &stack, index, &decoded);
                    }
                }
            }
            Event::GeneralRef(ref reference) => {
                if skip_from.is_none() {
                    if let Some(index) = open_text {
                        let decoded = resolve_reference(reference)?;
                        collect_text(&mut nodes, &mut paragraphs, &stack, index, &decoded);
                    }
                }
            }
            Event::Eof => break,
            _ => {}
        }
        buffer.clear();
    }

    if open_text.is_some() {
        return Err("unterminated w:t element".to_string());
    }
    Ok(Scan { paragraphs, nodes })
}

fn collect_text(
    nodes: &mut [TextNode],
    paragraphs: &mut [String],
    stack: &[usize],
    index: usize,
    text: &str,
) {
    if let Some(node) = nodes.get_mut(index) {
        node.text.push_str(text);
    }
    push_text(paragraphs, stack, text);
}

fn escape_into(out: &mut Vec<u8>, text: &str) {
    for character in text.chars() {
        match character {
            '&' => out.extend_from_slice(b"&amp;"),
            '<' => out.extend_from_slice(b"&lt;"),
            '>' => out.extend_from_slice(b"&gt;"),
            '\r' => out.extend_from_slice(b"&#13;"),
            other => {
                let mut buffer = [0u8; 4];
                out.extend_from_slice(other.encode_utf8(&mut buffer).as_bytes());
            }
        }
    }
}

fn needs_preserve(text: &str) -> bool {
    text.chars().next().is_some_and(char::is_whitespace)
        || text.chars().last().is_some_and(char::is_whitespace)
}

fn rewrite(
    xml: &[u8],
    paragraphs: &[String],
    translations: &[String],
) -> Result<Vec<u8>, DocumentError> {
    let scan = scan(xml).map_err(|detail| docx_error(DocumentErrorKind::WriteFailed, detail))?;

    let mut by_paragraph: HashMap<usize, Vec<usize>> = HashMap::new();
    for (index, node) in scan.nodes.iter().enumerate() {
        if let Some(paragraph) = node.paragraph {
            by_paragraph.entry(paragraph).or_default().push(index);
        }
    }

    let mut replacements: Vec<Option<String>> = vec![None; scan.nodes.len()];
    for (index, translation) in translations.iter().enumerate() {
        let Some(source) = paragraphs.get(index) else {
            continue;
        };
        if translation == source {
            continue;
        }
        let Some(node_indices) = by_paragraph.get(&index) else {
            continue;
        };
        let weights: Vec<usize> = node_indices
            .iter()
            .map(|&node_index| scan.nodes[node_index].text.chars().count())
            .collect();
        let total: usize = weights.iter().sum();
        let characters: Vec<char> = translation.chars().collect();
        let length = characters.len();
        let mut position = 0usize;
        let mut consumed = 0usize;
        for (slot, &node_index) in node_indices.iter().enumerate() {
            consumed += weights[slot];
            let end = (length * consumed).checked_div(total).unwrap_or(length);
            let end = end.min(length);
            let fragment: String = characters[position.min(length)..end].iter().collect();
            replacements[node_index] = Some(fragment);
            position = end;
        }
    }

    let mut out = Vec::with_capacity(xml.len() + 128);
    let mut cursor = 0usize;
    for (index, node) in scan.nodes.iter().enumerate() {
        let Some(text) = replacements[index].as_deref() else {
            continue;
        };
        if text == node.text
            || node.element_start < cursor
            || node.element_end > xml.len()
            || node.element_end < node.element_start
        {
            continue;
        }
        out.extend_from_slice(&xml[cursor..node.element_start]);
        let preserve = needs_preserve(text);
        if node.self_closing {
            out.push(b'<');
            out.extend_from_slice(&node.name);
            if preserve {
                out.extend_from_slice(b" xml:space=\"preserve\"");
            }
            out.push(b'>');
            escape_into(&mut out, text);
            out.extend_from_slice(b"</");
            out.extend_from_slice(&node.name);
            out.push(b'>');
        } else {
            let tag = &xml[node.element_start..node.content_start];
            if preserve && !node.preserve {
                let mut owned = tag.to_vec();
                if let Some(close) = owned.iter().rposition(|byte| *byte == b'>') {
                    owned.splice(close..close, b" xml:space=\"preserve\"".iter().copied());
                }
                out.extend_from_slice(&owned);
            } else {
                out.extend_from_slice(tag);
            }
            escape_into(&mut out, text);
            out.extend_from_slice(&xml[node.content_end.min(xml.len())..node.element_end]);
        }
        cursor = node.element_end;
    }
    out.extend_from_slice(&xml[cursor.min(xml.len())..]);
    Ok(out)
}

fn rebuild(source: &Path, document_xml: &[u8]) -> Result<Vec<u8>, DocumentError> {
    let file =
        std::fs::File::open(source).map_err(|error| write_failed(format!("docx: {error}")))?;
    let mut archive =
        ZipArchive::new(file).map_err(|error| write_failed(format!("docx: {error}")))?;
    let comment = archive.comment().to_vec();
    let count = archive.len();
    let mut cursor = Cursor::new(Vec::new());
    {
        let mut writer = ZipWriter::new(&mut cursor);
        for index in 0..count {
            let entry = archive
                .by_index_raw(index)
                .map_err(|error| write_failed(format!("docx: {error}")))?;
            if entry.name() == DOCUMENT_XML {
                let mut options =
                    SimpleFileOptions::default().compression_method(entry.compression());
                if let Some(modified) = entry.last_modified() {
                    options = options.last_modified_time(modified);
                }
                if let Some(mode) = entry.unix_mode() {
                    options = options.unix_permissions(mode);
                }
                writer
                    .start_file(DOCUMENT_XML, options)
                    .map_err(|error| write_failed(format!("docx: {error}")))?;
                writer
                    .write_all(document_xml)
                    .map_err(|error| write_failed(format!("docx: {error}")))?;
            } else {
                writer
                    .raw_copy_file(entry)
                    .map_err(|error| write_failed(format!("docx: {error}")))?;
            }
        }
        if !comment.is_empty() {
            writer.set_comment(String::from_utf8_lossy(&comment).into_owned());
        }
        writer
            .finish()
            .map_err(|error| write_failed(format!("docx: {error}")))?;
    }
    Ok(cursor.into_inner())
}
