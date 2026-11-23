//! PDF text extraction: a small content-stream interpreter over `lopdf`.
//!
//! The Python port delegates this half to pdfplumber. This port walks the page
//! content streams itself so that it stays pure Rust: it tracks the graphics
//! state (CTM, text state, fill colour), decodes the fonts' `/ToUnicode` maps,
//! and turns glyphs into words, lines and blocks with the same grouping rules as
//! the Python code.

use std::collections::HashMap;
use std::path::Path;
use std::rc::Rc;

use log::warn;
use lopdf::content::Content;
use lopdf::{Dictionary, Document, Object, ObjectId};

use crate::encoding;
use crate::error::{unreadable, DocumentError, DocumentErrorKind};

use super::fonts::base14_width;
use super::{PdfBlock, PdfLayout, TextAlignment};

/// Ceiling for one page's decompressed content streams.
const MAX_PAGE_CONTENT: usize = 64 * 1024 * 1024;
/// Ceiling for a `/ToUnicode` CMap.
const MAX_CMAP: usize = 4 * 1024 * 1024;
/// Maximum nested form XObjects.
const MAX_FORM_DEPTH: usize = 8;
/// Interpreter work budget per page (guards against malicious streams).
const MAX_OPERATIONS: usize = 2_000_000;

// ---------------------------------------------------------------------------
// Public entry point

/// Read the text-block layout of a PDF.
pub(crate) fn read_layout(path: &Path) -> Result<PdfLayout, DocumentError> {
    let data = std::fs::read(path).map_err(|error| unreadable(error.to_string()))?;
    let document = match Document::load_mem(&data) {
        Ok(document) => document,
        Err(error) => {
            if contains_encrypt(&data) {
                return Err(DocumentError::simple(DocumentErrorKind::Encrypted));
            }
            return Err(unreadable(error.to_string()));
        }
    };
    if document.is_encrypted() {
        return Err(DocumentError::simple(DocumentErrorKind::Encrypted));
    }

    let pages = document.get_pages();
    if pages.is_empty() {
        return Err(DocumentError::simple(DocumentErrorKind::NoText));
    }

    let mut page_sizes = Vec::with_capacity(pages.len());
    let mut blocks = Vec::new();
    for (number, page_id) in &pages {
        let (width, height, top) = page_box(&document, *page_id);
        page_sizes.push((width, height));
        let page_index = number.saturating_sub(1) as usize;
        let resources = merged_resources(&document, *page_id);
        let content = document
            .get_page_content_with_limit(*page_id, MAX_PAGE_CONTENT)
            .map_err(|error| unreadable(error.to_string()))?;
        let mut scanner = Scanner::new(&document, top);
        scanner.run(&content, &resources, Matrix::IDENTITY, 0);
        let (words, fills) = scanner.finish();
        let lines = lines_from_words(words);
        let mut page_blocks = blocks_from_lines(lines, page_index, width);
        for block in &mut page_blocks {
            block.background = background_for(block, &fills);
        }
        blocks.extend(page_blocks);
    }

    if blocks.is_empty() {
        return Err(DocumentError::simple(DocumentErrorKind::NoText));
    }
    Ok(PdfLayout {
        page_count: page_sizes.len(),
        page_sizes,
        blocks,
    })
}

fn contains_encrypt(data: &[u8]) -> bool {
    data.windows(b"/Encrypt".len())
        .any(|window| window == b"/Encrypt")
}

/// `(width, height, upper-right y)` of a page in user space.
fn page_box(document: &Document, page_id: ObjectId) -> (f32, f32, f64) {
    let fallback = (595.0, 842.0, 842.0);
    let Ok(page) = document.get_dictionary(page_id) else {
        return fallback;
    };
    let Ok(object) = page.get(b"MediaBox") else {
        return fallback;
    };
    let Ok((_, object)) = document.dereference(object) else {
        return fallback;
    };
    let Ok(array) = object.as_array() else {
        return fallback;
    };
    let values: Vec<f64> = array
        .iter()
        .filter_map(|item| item.as_float().ok().map(f64::from))
        .collect();
    if values.len() != 4 {
        return fallback;
    }
    let (llx, lly, urx, ury) = (values[0], values[1], values[2], values[3]);
    let width = (urx - llx).abs().max(1.0) as f32;
    let height = (ury - lly).abs().max(1.0) as f32;
    (width, height, ury.max(lly))
}

/// Merge every `/Resources` dictionary reachable from the page into a copy.
pub(super) fn merged_resources(document: &Document, page_id: ObjectId) -> Dictionary {
    let mut merged = Dictionary::new();
    let Ok((direct, ids)) = document.get_page_resources(page_id) else {
        return merged;
    };
    if let Some(dictionary) = direct {
        for (key, value) in dictionary.iter() {
            merged.set(key.clone(), value.clone());
        }
    }
    for id in ids {
        if let Ok(dictionary) = document.get_dictionary(id) {
            for (key, value) in dictionary.iter() {
                merged.set(key.clone(), value.clone());
            }
        }
    }
    merged
}

// ---------------------------------------------------------------------------
// Matrix helpers

#[derive(Clone, Copy, Debug)]
struct Matrix {
    a: f64,
    b: f64,
    c: f64,
    d: f64,
    e: f64,
    f: f64,
}

impl Matrix {
    const IDENTITY: Self = Self {
        a: 1.0,
        b: 0.0,
        c: 0.0,
        d: 1.0,
        e: 0.0,
        f: 0.0,
    };

    fn translate(tx: f64, ty: f64) -> Self {
        Self {
            a: 1.0,
            b: 0.0,
            c: 0.0,
            d: 1.0,
            e: tx,
            f: ty,
        }
    }

    /// Row-vector matrix product: `self` applied first, then `other`.
    fn multiply(self, other: Self) -> Self {
        Self {
            a: self.a * other.a + self.b * other.c,
            b: self.a * other.b + self.b * other.d,
            c: self.c * other.a + self.d * other.c,
            d: self.c * other.b + self.d * other.d,
            e: self.e * other.a + self.f * other.c + other.e,
            f: self.e * other.b + self.f * other.d + other.f,
        }
    }

    fn apply(self, x: f64, y: f64) -> (f64, f64) {
        (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )
    }

    fn from_operands(operands: &[Object]) -> Option<Self> {
        if operands.len() < 6 {
            return None;
        }
        let mut values = [0.0f64; 6];
        for (slot, operand) in values.iter_mut().zip(operands.iter()) {
            *slot = f64::from(operand.as_float().ok()?);
        }
        Some(Self {
            a: values[0],
            b: values[1],
            c: values[2],
            d: values[3],
            e: values[4],
            f: values[5],
        })
    }
}

fn round2(value: f64) -> i64 {
    (value * 100.0).round() as i64
}

// ---------------------------------------------------------------------------
// Fonts

#[derive(Clone, Copy)]
enum SimpleEncoding {
    WinAnsi,
    MacRoman,
}

#[derive(Clone, PartialEq, Eq, Hash)]
enum FontKey {
    Reference(ObjectId),
    Name(Vec<u8>),
}

struct PdfFont {
    name: String,
    bold: bool,
    two_byte: bool,
    to_unicode: HashMap<u32, String>,
    widths: HashMap<u32, f64>,
    default_width: f64,
    base14: bool,
    encoding: SimpleEncoding,
    /// Type0 font whose CMap is a UCS-2 programme (`UniGB-UCS2-H`, ...).
    ucs2: bool,
}

impl PdfFont {
    fn unicode(&self, code: u32) -> Option<String> {
        if let Some(text) = self.to_unicode.get(&code) {
            return Some(text.clone());
        }
        if self.two_byte {
            // Adobe CJK CMaps such as `/UniGB-UCS2-H` store UCS-2 code units;
            // when a document omits `/ToUnicode` this is the only way to recover
            // the characters (reportlab's CID fonts are a common case).
            if self.ucs2 {
                return char::from_u32(code).map(|character| character.to_string());
            }
            return None;
        }
        let byte = u8::try_from(code).ok()?;
        let character = match self.encoding {
            SimpleEncoding::WinAnsi => encoding::win_ansi(byte),
            SimpleEncoding::MacRoman => encoding::mac_roman(byte),
        }?;
        Some(character.to_string())
    }

    fn width(&self, code: u32) -> f64 {
        if let Some(width) = self.widths.get(&code) {
            return *width;
        }
        if self.base14 {
            return base14_width(&self.name, code);
        }
        self.default_width
    }
}

fn name_of(dictionary: &Dictionary, key: &[u8]) -> Option<Vec<u8>> {
    dictionary
        .get(key)
        .ok()
        .and_then(|object| object.as_name().ok())
        .map(<[u8]>::to_vec)
}

fn number_of(dictionary: &Dictionary, key: &[u8]) -> Option<f64> {
    dictionary
        .get(key)
        .ok()
        .and_then(|object| object.as_float().ok())
        .map(f64::from)
}

fn load_font(document: &Document, dictionary: &Dictionary) -> PdfFont {
    let subtype = name_of(dictionary, b"Subtype").unwrap_or_default();
    let two_byte = subtype == b"Type0";
    let base = name_of(dictionary, b"BaseFont").unwrap_or_default();
    let name = String::from_utf8_lossy(&base).into_owned();
    let bold = is_bold(&name);
    let to_unicode = read_to_unicode(document, dictionary);
    let (widths, default_width) = if two_byte {
        composite_widths(document, dictionary)
    } else {
        simple_widths(document, dictionary)
    };
    let ucs2 = two_byte
        && to_unicode.is_empty()
        && name_of(dictionary, b"Encoding")
            .map(|encoding| String::from_utf8_lossy(&encoding).to_lowercase())
            .is_some_and(|encoding| encoding.contains("ucs2"));
    PdfFont {
        name: name.clone(),
        bold,
        two_byte,
        to_unicode,
        widths,
        default_width,
        base14: is_base14(&name),
        encoding: simple_encoding(dictionary),
        ucs2,
    }
}

fn is_bold(name: &str) -> bool {
    let lowered = name.to_lowercase();
    ["bold", "black", "heavy", "semibold"]
        .iter()
        .any(|token| lowered.contains(token))
}

fn simple_encoding(dictionary: &Dictionary) -> SimpleEncoding {
    let base = match dictionary.get(b"Encoding") {
        Ok(Object::Name(name)) => Some(name.clone()),
        Ok(Object::Dictionary(encoding)) => name_of(encoding, b"BaseEncoding"),
        _ => None,
    };
    match base {
        Some(name) if name == b"MacRomanEncoding" => SimpleEncoding::MacRoman,
        _ => SimpleEncoding::WinAnsi,
    }
}

fn read_to_unicode(document: &Document, dictionary: &Dictionary) -> HashMap<u32, String> {
    let Ok(object) = dictionary.get(b"ToUnicode") else {
        return HashMap::new();
    };
    let Ok((_, object)) = document.dereference(object) else {
        return HashMap::new();
    };
    let Ok(stream) = object.as_stream() else {
        return HashMap::new();
    };
    let data = stream
        .decompressed_content_with_limit(MAX_CMAP)
        .unwrap_or_else(|_| stream.content.clone());
    parse_cmap(&data)
}

fn deref_dictionary<'a>(
    document: &'a Document,
    dictionary: &'a Dictionary,
    key: &[u8],
) -> Option<&'a Dictionary> {
    let object = dictionary.get(key).ok()?;
    let (_, object) = document.dereference(object).ok()?;
    object.as_dict().ok()
}

fn is_base14(name: &str) -> bool {
    let lowered = name.to_lowercase();
    [
        "helvetica",
        "arial",
        "times",
        "courier",
        "nimbus",
        "symbol",
        "zapf",
        "dingbat",
        "liberationserif",
    ]
    .iter()
    .any(|family| lowered.contains(family))
}

fn simple_widths(document: &Document, dictionary: &Dictionary) -> (HashMap<u32, f64>, f64) {
    let mut widths = HashMap::new();
    let first = dictionary
        .get(b"FirstChar")
        .ok()
        .and_then(|object| object.as_i64().ok())
        .unwrap_or(0)
        .max(0);
    if let Ok(array) = dictionary.get(b"Widths").and_then(Object::as_array) {
        for (index, object) in array.iter().enumerate() {
            if let Ok(width) = object.as_float() {
                widths.insert(first as u32 + index as u32, f64::from(width));
            }
        }
    }
    let missing = deref_dictionary(document, dictionary, b"FontDescriptor")
        .and_then(|descriptor| number_of(descriptor, b"MissingWidth"));
    (widths, missing.unwrap_or(500.0))
}

fn composite_widths(document: &Document, dictionary: &Dictionary) -> (HashMap<u32, f64>, f64) {
    let Some(descendant) = (|| {
        let array = dictionary.get(b"DescendantFonts").ok()?.as_array().ok()?;
        let first = array.first()?;
        let (_, object) = document.dereference(first).ok()?;
        object.as_dict().ok()
    })() else {
        return (HashMap::new(), 1000.0);
    };
    let default_width = number_of(descendant, b"DW").unwrap_or(1000.0);
    let mut widths = HashMap::new();
    let Ok(array) = descendant.get(b"W").and_then(Object::as_array) else {
        return (widths, default_width);
    };
    let mut index = 0usize;
    while index < array.len() {
        let Some(start) = array[index].as_i64().ok() else {
            break;
        };
        let start = start.max(0) as u32;
        match array.get(index + 1) {
            Some(Object::Array(list)) => {
                for (offset, object) in list.iter().enumerate() {
                    if let Ok(width) = object.as_float() {
                        widths.insert(start + offset as u32, f64::from(width));
                    }
                }
                index += 2;
            }
            Some(end_object) => {
                let Ok(end) = end_object.as_i64() else {
                    break;
                };
                let Some(width_object) = array.get(index + 2) else {
                    break;
                };
                let Ok(width) = width_object.as_float() else {
                    break;
                };
                for code in start..=end.max(0) as u32 {
                    widths.insert(code, f64::from(width));
                }
                index += 3;
            }
            None => break,
        }
    }
    (widths, default_width)
}

// ---------------------------------------------------------------------------
// CMap parsing

fn parse_cmap(data: &[u8]) -> HashMap<u32, String> {
    let text = String::from_utf8_lossy(data);
    let tokens: Vec<&str> = text.split_whitespace().collect();
    let mut map = HashMap::new();
    let mut index = 0usize;
    while index < tokens.len() {
        match tokens[index] {
            "beginbfchar" => {
                index += 1;
                while index + 1 < tokens.len() {
                    let Some(code) = parse_hex_token(tokens[index]) else {
                        break;
                    };
                    let Some(destination) = parse_hex_token(tokens[index + 1]) else {
                        break;
                    };
                    if let Some(code) = code_to_u32(&code) {
                        map.entry(code).or_insert_with(|| utf16be(&destination));
                    }
                    index += 2;
                }
            }
            "beginbfrange" => {
                index += 1;
                while index + 2 < tokens.len() {
                    let Some(low) = parse_hex_token(tokens[index]) else {
                        break;
                    };
                    let Some(high) = parse_hex_token(tokens[index + 1]) else {
                        break;
                    };
                    let (Some(low_code), Some(high_code)) = (code_to_u32(&low), code_to_u32(&high))
                    else {
                        break;
                    };
                    if tokens[index + 2] == "[" {
                        index += 3;
                        let mut offset = 0u32;
                        while index < tokens.len() && tokens[index] != "]" {
                            if let Some(destination) = parse_hex_token(tokens[index]) {
                                map.entry(low_code.saturating_add(offset))
                                    .or_insert_with(|| utf16be(&destination));
                            }
                            offset += 1;
                            index += 1;
                        }
                        index = index.saturating_add(1);
                    } else if let Some(destination) = parse_hex_token(tokens[index + 2]) {
                        if let Some(base) = code_to_u32(&destination) {
                            let width = destination.len();
                            for offset in 0..=(high_code.saturating_sub(low_code)) {
                                let mapped = base.saturating_add(offset);
                                let bytes = mapped.to_be_bytes();
                                let slice = if (2..=4).contains(&width) {
                                    &bytes[bytes.len() - width..]
                                } else {
                                    &bytes[bytes.len() - 1..]
                                };
                                map.entry(low_code.saturating_add(offset))
                                    .or_insert_with(|| utf16be(slice));
                            }
                        }
                        index += 3;
                    } else {
                        break;
                    }
                }
            }
            _ => index += 1,
        }
    }
    map
}

fn parse_hex_token(token: &str) -> Option<Vec<u8>> {
    let inner = token.strip_prefix('<')?.strip_suffix('>')?;
    if inner.len() % 2 != 0 {
        return None;
    }
    let mut bytes = Vec::with_capacity(inner.len() / 2);
    let characters: Vec<char> = inner.chars().collect();
    let mut index = 0;
    while index + 1 < characters.len() {
        let high = characters[index].to_digit(16)?;
        let low = characters[index + 1].to_digit(16)?;
        bytes.push((high * 16 + low) as u8);
        index += 2;
    }
    Some(bytes)
}

fn code_to_u32(bytes: &[u8]) -> Option<u32> {
    if bytes.is_empty() || bytes.len() > 4 {
        return None;
    }
    Some(
        bytes
            .iter()
            .fold(0u32, |acc, byte| (acc << 8) | u32::from(*byte)),
    )
}

fn utf16be(bytes: &[u8]) -> String {
    let units: Vec<u16> = bytes
        .chunks_exact(2)
        .map(|pair| u16::from_be_bytes([pair[0], pair[1]]))
        .collect();
    String::from_utf16_lossy(&units)
}

// ---------------------------------------------------------------------------
// Content stream interpreter

#[derive(Clone)]
struct GraphicsState {
    ctm: Matrix,
    fill: [f32; 3],
    font: Option<Rc<PdfFont>>,
    font_size: f64,
    char_space: f64,
    word_space: f64,
    h_scale: f64,
    leading: f64,
    rise: f64,
}

impl Default for GraphicsState {
    fn default() -> Self {
        Self {
            ctm: Matrix::IDENTITY,
            fill: [0.0, 0.0, 0.0],
            font: None,
            font_size: 0.0,
            char_space: 0.0,
            word_space: 0.0,
            h_scale: 1.0,
            leading: 0.0,
            rise: 0.0,
        }
    }
}

struct TextState {
    tm: Matrix,
    tlm: Matrix,
}

impl Default for TextState {
    fn default() -> Self {
        Self {
            tm: Matrix::IDENTITY,
            tlm: Matrix::IDENTITY,
        }
    }
}

struct RawWord {
    text: String,
    x0: f64,
    x1: f64,
    top: f64,
    bottom: f64,
    size: f64,
    bold: bool,
    font_name: String,
    color: [f32; 3],
}

struct FillBox {
    x0: f64,
    top: f64,
    x1: f64,
    bottom: f64,
    color: [f32; 3],
}

#[derive(Clone)]
struct WordBuilder {
    text: String,
    x0: f64,
    x1: f64,
    baseline: f64,
    size: f64,
    bold: bool,
    font_name: String,
    color: [f32; 3],
}

struct Scanner<'a> {
    document: &'a Document,
    /// Upper-right y of the page box (top-left coordinates are derived from it).
    ury: f64,
    words: Vec<RawWord>,
    fills: Vec<FillBox>,
    fonts: HashMap<FontKey, Rc<PdfFont>>,
    operations: usize,
    builder: Option<WordBuilder>,
    path: Option<[f64; 4]>,
}

impl<'a> Scanner<'a> {
    fn new(document: &'a Document, ury: f64) -> Self {
        Self {
            document,
            ury,
            words: Vec::new(),
            fills: Vec::new(),
            fonts: HashMap::new(),
            operations: 0,
            builder: None,
            path: None,
        }
    }

    fn finish(mut self) -> (Vec<RawWord>, Vec<FillBox>) {
        self.flush_word();
        (self.words, self.fills)
    }

    fn run(&mut self, content: &[u8], resources: &Dictionary, initial_ctm: Matrix, depth: usize) {
        if depth > MAX_FORM_DEPTH {
            return;
        }
        let mut state = GraphicsState {
            ctm: initial_ctm,
            ..GraphicsState::default()
        };
        let mut text = TextState::default();
        let mut stack: Vec<GraphicsState> = Vec::new();

        for operation in Content::decode_iter(content) {
            let Ok(operation) = operation else {
                warn!("ofm-docs: stopping at a malformed PDF content stream");
                break;
            };
            self.operations += 1;
            if self.operations > MAX_OPERATIONS {
                warn!("ofm-docs: PDF operation budget exhausted");
                break;
            }
            self.execute(
                &operation.operator,
                &operation.operands,
                resources,
                depth,
                &mut state,
                &mut text,
                &mut stack,
            );
        }
        self.flush_word();
    }

    #[allow(clippy::too_many_arguments)]
    fn execute(
        &mut self,
        operator: &str,
        operands: &[Object],
        resources: &Dictionary,
        depth: usize,
        state: &mut GraphicsState,
        text: &mut TextState,
        stack: &mut Vec<GraphicsState>,
    ) {
        match operator {
            "q" => stack.push(state.clone()),
            "Q" => {
                if let Some(previous) = stack.pop() {
                    *state = previous;
                }
            }
            "cm" => {
                if let Some(matrix) = Matrix::from_operands(operands) {
                    state.ctm = matrix.multiply(state.ctm);
                }
            }
            "BT" => {
                text.tm = Matrix::IDENTITY;
                text.tlm = Matrix::IDENTITY;
            }
            "Tf" => {
                if let Some(Object::Name(name)) = operands.first() {
                    let font = self.font_for(resources, name);
                    state.font = font;
                    state.font_size = operands
                        .get(1)
                        .and_then(|object| object.as_float().ok())
                        .map(f64::from)
                        .unwrap_or(0.0);
                }
            }
            "Td" | "TD" => {
                let tx = number(operands, 0);
                let ty = number(operands, 1);
                if operator == "TD" {
                    state.leading = -ty;
                }
                text.tlm = Matrix::translate(tx, ty).multiply(text.tlm);
                text.tm = text.tlm;
            }
            "Tm" => {
                if let Some(matrix) = Matrix::from_operands(operands) {
                    text.tm = matrix;
                    text.tlm = matrix;
                }
            }
            "T*" => {
                text.tlm = Matrix::translate(0.0, -state.leading).multiply(text.tlm);
                text.tm = text.tlm;
            }
            "TL" => state.leading = number(operands, 0),
            "Tc" => state.char_space = number(operands, 0),
            "Tw" => state.word_space = number(operands, 0),
            "Tz" => state.h_scale = number(operands, 0) / 100.0,
            "Ts" => state.rise = number(operands, 0),
            "Tj" => {
                if let Some(Object::String(bytes, _)) = operands.first() {
                    self.show_text(bytes, state, text);
                }
            }
            "'" => {
                text.tlm = Matrix::translate(0.0, -state.leading).multiply(text.tlm);
                text.tm = text.tlm;
                if let Some(Object::String(bytes, _)) = operands.first() {
                    self.show_text(bytes, state, text);
                }
            }
            "\"" => {
                state.word_space = number(operands, 0);
                state.char_space = number(operands, 1);
                text.tlm = Matrix::translate(0.0, -state.leading).multiply(text.tlm);
                text.tm = text.tlm;
                if let Some(Object::String(bytes, _)) = operands.get(2) {
                    self.show_text(bytes, state, text);
                }
            }
            "TJ" => {
                if let Some(Object::Array(items)) = operands.first() {
                    for item in items {
                        match item {
                            Object::String(bytes, _) => self.show_text(bytes, state, text),
                            other => {
                                if let Ok(adjustment) = other.as_float() {
                                    let shift = -f64::from(adjustment) / 1000.0
                                        * state.font_size
                                        * state.h_scale;
                                    text.tm = Matrix::translate(shift, 0.0).multiply(text.tm);
                                }
                            }
                        }
                    }
                }
            }
            "g" => {
                if let Some(value) = color_from_operands(operands, 1) {
                    state.fill = value;
                }
            }
            "rg" => {
                if let Some(value) = color_from_operands(operands, 3) {
                    state.fill = value;
                }
            }
            "k" => {
                if let Some(value) = color_from_operands(operands, 4) {
                    state.fill = value;
                }
            }
            "sc" | "scn" => {
                if let Some(value) = super::color_from_components(&numbers(operands)) {
                    state.fill = value;
                }
            }
            "re" => {
                let x = number(operands, 0);
                let y = number(operands, 1);
                let width = number(operands, 2);
                let height = number(operands, 3);
                if width != 0.0 && height != 0.0 {
                    let corners = [
                        (x, y),
                        (x + width, y),
                        (x, y + height),
                        (x + width, y + height),
                    ];
                    self.extend_path(&corners, state.ctm);
                }
            }
            "m" | "l" => {
                let points = [(number(operands, 0), number(operands, 1))];
                self.extend_path(&points, state.ctm);
            }
            "c" => {
                let points = [
                    (number(operands, 0), number(operands, 1)),
                    (number(operands, 2), number(operands, 3)),
                    (number(operands, 4), number(operands, 5)),
                ];
                self.extend_path(&points, state.ctm);
            }
            "v" | "y" => {
                let points = [
                    (number(operands, 0), number(operands, 1)),
                    (number(operands, 2), number(operands, 3)),
                ];
                self.extend_path(&points, state.ctm);
            }
            "f" | "F" | "f*" | "B" | "B*" | "b" | "b*" => {
                if let Some(bbox) = self.path.take() {
                    let top = self.ury - bbox[3];
                    let bottom = self.ury - bbox[1];
                    if bbox[2] > bbox[0] && bottom > top {
                        self.fills.push(FillBox {
                            x0: bbox[0],
                            top,
                            x1: bbox[2],
                            bottom,
                            color: state.fill,
                        });
                    }
                }
            }
            "S" | "s" | "n" => self.path = None,
            "Do" => {
                if let Some(Object::Name(name)) = operands.first() {
                    self.run_xobject(name, resources, state, depth);
                }
            }
            _ => {}
        }
    }

    fn font_for(&mut self, resources: &Dictionary, name: &[u8]) -> Option<Rc<PdfFont>> {
        let fonts = resources.get(b"Font").ok()?;
        let (_, fonts) = self.document.dereference(fonts).ok()?;
        let fonts = fonts.as_dict().ok()?;
        let object = fonts.get(name).ok()?;
        let key = match object {
            Object::Reference(id) => FontKey::Reference(*id),
            _ => FontKey::Name(name.to_vec()),
        };
        if let Some(font) = self.fonts.get(&key) {
            return Some(Rc::clone(font));
        }
        let (_, object) = self.document.dereference(object).ok()?;
        let dictionary = object.as_dict().ok()?;
        let font = Rc::new(load_font(self.document, dictionary));
        self.fonts.insert(key, Rc::clone(&font));
        Some(font)
    }

    fn run_xobject(
        &mut self,
        name: &[u8],
        resources: &Dictionary,
        state: &GraphicsState,
        depth: usize,
    ) {
        if depth >= MAX_FORM_DEPTH {
            return;
        }
        let Ok(xobjects) = resources.get(b"XObject") else {
            return;
        };
        let Ok((_, xobjects)) = self.document.dereference(xobjects) else {
            return;
        };
        let Ok(xobjects) = xobjects.as_dict() else {
            return;
        };
        let Ok(object) = xobjects.get(name) else {
            return;
        };
        let Ok((_, object)) = self.document.dereference(object) else {
            return;
        };
        let Ok(stream) = object.as_stream() else {
            return;
        };
        let subtype = name_of(&stream.dict, b"Subtype").unwrap_or_default();
        if subtype != b"Form" {
            return;
        }
        let matrix = stream
            .dict
            .get(b"Matrix")
            .ok()
            .and_then(|object| object.as_array().ok())
            .and_then(|array| Matrix::from_operands(array))
            .unwrap_or(Matrix::IDENTITY);
        let form_resources = match deref_dictionary(self.document, &stream.dict, b"Resources") {
            Some(dictionary) => dictionary.clone(),
            None => resources.clone(),
        };
        let content = stream
            .decompressed_content_with_limit(MAX_PAGE_CONTENT)
            .unwrap_or_else(|_| stream.content.clone());

        let mut form_state = state.clone();
        form_state.ctm = matrix.multiply(state.ctm);
        let mut form_text = TextState::default();
        let mut stack = Vec::new();
        for operation in Content::decode_iter(&content) {
            let Ok(operation) = operation else {
                break;
            };
            self.operations += 1;
            if self.operations > MAX_OPERATIONS {
                return;
            }
            self.execute(
                &operation.operator,
                &operation.operands,
                &form_resources,
                depth + 1,
                &mut form_state,
                &mut form_text,
                &mut stack,
            );
        }
    }

    fn extend_path(&mut self, points: &[(f64, f64)], ctm: Matrix) {
        for (x, y) in points {
            let (device_x, device_y) = ctm.apply(*x, *y);
            match &mut self.path {
                Some(bbox) => {
                    bbox[0] = bbox[0].min(device_x);
                    bbox[1] = bbox[1].min(device_y);
                    bbox[2] = bbox[2].max(device_x);
                    bbox[3] = bbox[3].max(device_y);
                }
                None => self.path = Some([device_x, device_y, device_x, device_y]),
            }
        }
    }

    fn show_text(&mut self, bytes: &[u8], state: &GraphicsState, text: &mut TextState) {
        let Some(font) = state.font.clone() else {
            return;
        };
        let code_length = if font.two_byte { 2 } else { 1 };
        let mut index = 0usize;
        while index + code_length <= bytes.len() {
            let code = if code_length == 2 {
                u32::from(u16::from_be_bytes([bytes[index], bytes[index + 1]]))
            } else {
                u32::from(bytes[index])
            };
            let width = font.width(code);
            let text_scale = Matrix {
                a: state.font_size * state.h_scale,
                b: 0.0,
                c: 0.0,
                d: state.font_size,
                e: 0.0,
                f: state.rise,
            };
            let trm = text_scale.multiply(text.tm).multiply(state.ctm);
            let origin = (trm.e, trm.f);
            let size = (trm.c * trm.c + trm.d * trm.d).sqrt();

            let mut advance = width / 1000.0 * state.font_size + state.char_space;
            if code_length == 1 && code == 32 {
                advance += state.word_space;
            }
            advance *= state.h_scale;
            text.tm = Matrix::translate(advance, 0.0).multiply(text.tm);
            let next = text_scale.multiply(text.tm).multiply(state.ctm);
            let end = (next.e, next.f);

            if let Some(character) = font.unicode(code) {
                self.record_glyph(&character, origin, end, size, &font, state);
            }
            index += code_length;
        }
    }

    fn record_glyph(
        &mut self,
        text: &str,
        origin: (f64, f64),
        end: (f64, f64),
        size: f64,
        font: &PdfFont,
        state: &GraphicsState,
    ) {
        if size <= 0.1 {
            return;
        }
        if text.chars().all(char::is_whitespace) {
            self.flush_word();
            return;
        }
        let x0 = origin.0.min(end.0);
        let x1 = origin.0.max(end.0);
        let baseline = origin.1;
        let class_size = size.max(1.0);
        let mismatch = match &self.builder {
            Some(builder) => {
                (baseline - builder.baseline).abs() > class_size * 0.45
                    || x0 - builder.x1 > class_size * 0.25
                    || x0 < builder.x1 - class_size * 0.5
                    || (builder.size - size).abs() > 1.0
                    || builder.color != state.fill
                    || builder.bold != font.bold
            }
            None => true,
        };
        if mismatch {
            self.flush_word();
            self.builder = Some(WordBuilder {
                text: String::new(),
                x0,
                x1,
                baseline,
                size,
                bold: font.bold,
                font_name: font.name.clone(),
                color: state.fill,
            });
        }
        if let Some(builder) = &mut self.builder {
            builder.text.push_str(text);
            builder.x0 = builder.x0.min(x0);
            builder.x1 = builder.x1.max(x1);
        }
    }

    fn flush_word(&mut self) {
        let Some(builder) = self.builder.take() else {
            return;
        };
        let text = builder.text.trim().to_string();
        if text.is_empty() {
            return;
        }
        let size = builder.size.max(1.0);
        self.words.push(RawWord {
            text,
            x0: builder.x0,
            x1: builder.x1,
            top: self.ury - (builder.baseline + size * 0.8),
            bottom: self.ury - (builder.baseline - size * 0.2),
            size: builder.size,
            bold: builder.bold,
            font_name: builder.font_name,
            color: builder.color,
        });
    }
}

fn number(operands: &[Object], index: usize) -> f64 {
    operands
        .get(index)
        .and_then(|object| object.as_float().ok())
        .map(f64::from)
        .unwrap_or(0.0)
}

fn numbers(operands: &[Object]) -> Vec<f32> {
    operands
        .iter()
        .filter_map(|object| object.as_float().ok())
        .collect()
}

fn color_from_operands(operands: &[Object], expected: usize) -> Option<[f32; 3]> {
    let values = numbers(operands);
    if values.len() < expected {
        return None;
    }
    super::color_from_components(&values[..expected])
}

// ---------------------------------------------------------------------------
// Block grouping (ported from documents.py)

struct Line {
    text: String,
    x0: f64,
    top: f64,
    x1: f64,
    bottom: f64,
    font_size: f64,
    bold: bool,
    font_name: String,
    color: [f32; 3],
}

impl Line {
    fn width(&self) -> f64 {
        self.x1 - self.x0
    }

    fn height(&self) -> f64 {
        self.bottom - self.top
    }
}

fn lines_from_words(mut words: Vec<RawWord>) -> Vec<Line> {
    words.sort_by(|first, second| {
        round2(first.top)
            .cmp(&round2(second.top))
            .then(first.x0.total_cmp(&second.x0))
    });

    struct Group {
        words: Vec<RawWord>,
        top: f64,
    }
    let mut groups: Vec<Group> = Vec::new();
    for word in words {
        let height = (word.bottom - word.top).max(0.1);
        if let Some(group) = groups.last_mut() {
            if (word.top - group.top).abs() <= 1.5f64.max(height * 0.45) {
                group.top = group.top.min(word.top);
                group.words.push(word);
                continue;
            }
        }
        groups.push(Group {
            top: word.top,
            words: vec![word],
        });
    }

    let mut lines = Vec::with_capacity(groups.len());
    for mut group in groups {
        group
            .words
            .sort_by(|first, second| first.x0.total_cmp(&second.x0));
        let Some(first) = group.words.first() else {
            continue;
        };
        let font_size = group
            .words
            .iter()
            .map(|word| word.size)
            .fold(0.0f64, f64::max);
        let text = join_words(&group.words);
        let x0 = group
            .words
            .iter()
            .map(|word| word.x0)
            .fold(f64::INFINITY, f64::min);
        let x1 = group
            .words
            .iter()
            .map(|word| word.x1)
            .fold(f64::NEG_INFINITY, f64::max);
        let top = group
            .words
            .iter()
            .map(|word| word.top)
            .fold(f64::INFINITY, f64::min);
        let bottom = group
            .words
            .iter()
            .map(|word| word.bottom)
            .fold(f64::NEG_INFINITY, f64::max);
        lines.push(Line {
            text,
            x0,
            top,
            x1,
            bottom,
            font_size,
            bold: first.bold,
            font_name: first.font_name.clone(),
            color: first.color,
        });
    }
    lines
}

fn join_words(words: &[RawWord]) -> String {
    let Some(first) = words.first() else {
        return String::new();
    };
    let mut text = first.text.clone();
    for pair in words.windows(2) {
        let (previous, word) = (&pair[0], &pair[1]);
        let height = (word.bottom - word.top).max(1.0);
        let gap = word.x0 - previous.x1;
        let separator = if gap > 0.5f64.max(height * 0.15) {
            " "
        } else {
            ""
        };
        text.push_str(separator);
        text.push_str(&word.text);
    }
    text.trim().to_string()
}

fn same_block(previous: &Line, line: &Line) -> bool {
    if (previous.font_size - line.font_size).abs() >= 1.5 {
        return false;
    }
    let height = previous.height().max(line.height());
    let gap = line.top - previous.bottom;
    if gap > 2.5f64.max(height * 0.45) || gap < -height * 1.2 {
        return false;
    }
    let overlap = previous.x1.min(line.x1) - previous.x0.max(line.x0);
    let width = previous.width().min(line.width());
    if width <= 0.0 {
        return true;
    }
    overlap >= width * 0.35
}

fn blocks_from_lines(mut lines: Vec<Line>, page_index: usize, page_width: f32) -> Vec<PdfBlock> {
    if lines.is_empty() {
        return Vec::new();
    }
    lines.sort_by(|first, second| {
        first
            .top
            .total_cmp(&second.top)
            .then(first.x0.total_cmp(&second.x0))
    });

    let mut groups: Vec<Vec<Line>> = Vec::new();
    for line in lines {
        let mut target: Option<usize> = None;
        for (index, group) in groups.iter().enumerate() {
            let Some(previous) = group.last() else {
                continue;
            };
            if previous.top >= line.top {
                continue;
            }
            if same_block(previous, &line) {
                target = Some(index);
            }
        }
        match target {
            Some(index) => groups[index].push(line),
            None => groups.push(vec![line]),
        }
    }

    groups.sort_by(|first, second| {
        let (a, b) = (&first[0], &second[0]);
        a.top.total_cmp(&b.top).then(a.x0.total_cmp(&b.x0))
    });

    let mut blocks = Vec::with_capacity(groups.len());
    for group in groups {
        let Some(first) = group.first() else {
            continue;
        };
        let text = group
            .iter()
            .map(|line| line.text.as_str())
            .collect::<Vec<&str>>()
            .join(" ");
        let text = text.trim().to_string();
        if text.is_empty() {
            continue;
        }
        let x0 = group
            .iter()
            .map(|line| line.x0)
            .fold(f64::INFINITY, f64::min);
        let x1 = group
            .iter()
            .map(|line| line.x1)
            .fold(f64::NEG_INFINITY, f64::max);
        let top = group
            .iter()
            .map(|line| line.top)
            .fold(f64::INFINITY, f64::min);
        let bottom = group
            .iter()
            .map(|line| line.bottom)
            .fold(f64::NEG_INFINITY, f64::max);
        if x1 - x0 <= 1.0 || bottom - top <= 1.0 {
            continue;
        }

        let page_width = f64::from(page_width).max(1.0);
        let mut alignment = TextAlignment::Left;
        if x1 - x0 < page_width * 0.75 {
            let middle = (x0 + x1) / 2.0;
            if (middle - page_width / 2.0).abs() < page_width * 0.06 {
                alignment = TextAlignment::Center;
            } else if x1 > page_width - page_width * 0.08 {
                alignment = TextAlignment::Right;
            }
        }

        let mut deltas: Vec<f64> = Vec::new();
        for pair in group.windows(2) {
            if pair[1].top > pair[0].top {
                deltas.push(pair[1].top - pair[0].top);
            }
        }
        let pitch = median(&mut deltas).unwrap_or(0.0);

        blocks.push(PdfBlock {
            page_index,
            x0: x0 as f32,
            top: top as f32,
            x1: x1 as f32,
            bottom: bottom as f32,
            text,
            font_size: group
                .iter()
                .map(|line| line.font_size)
                .fold(0.0f64, f64::max) as f32,
            bold: first.bold,
            font_name: first.font_name.clone(),
            alignment,
            line_pitch: pitch as f32,
            text_color: first.color,
            background: [1.0, 1.0, 1.0],
        });
    }
    blocks
}

fn median(values: &mut [f64]) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(|first, second| first.total_cmp(second));
    let middle = values.len() / 2;
    if values.len() % 2 == 1 {
        Some(values[middle])
    } else {
        Some((values[middle - 1] + values[middle]) / 2.0)
    }
}

fn background_for(block: &PdfBlock, fills: &[FillBox]) -> [f32; 3] {
    let mut background = [1.0, 1.0, 1.0];
    let x0 = f64::from(block.x0);
    let x1 = f64::from(block.x1);
    let top = f64::from(block.top);
    let bottom = f64::from(block.bottom);
    let block_area = (x1 - x0).max(1.0) * (bottom - top).max(1.0);
    for fill in fills {
        let overlap_x = x1.min(fill.x1) - x0.max(fill.x0);
        let overlap_y = bottom.min(fill.bottom) - top.max(fill.top);
        if overlap_x <= 0.0 || overlap_y <= 0.0 {
            continue;
        }
        if overlap_x * overlap_y / block_area >= 0.6 {
            background = fill.color;
        }
    }
    background
}
