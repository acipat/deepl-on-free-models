//! PDF overlay writing: keep every original page, append a drawing stream.
//!
//! The overlay is appended to the page's `/Contents`, so the original content
//! stream (graphics, images, annotations and the text layer) is never touched.
//! Text is drawn with an embedded TrueType font (or base-14 Helvetica for
//! Windows-1252-only translations), covering each block with its sampled
//! background colour first.

use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use log::warn;
use lopdf::{dictionary, Dictionary, Document, Object, ObjectId, Stream};

use crate::error::{unreadable, write_failed, DocumentError, DocumentErrorKind};

use super::fonts::{DrawFont, FontBook, TtfFont};
use super::{leading, text_color, PdfBlock, PdfLayout};

/// Write the translated overlay for `layout` into `out_path`.
pub(crate) fn write_layout(
    source: &Path,
    layout: &PdfLayout,
    translations: &[String],
    out_path: &std::path::Path,
) -> Result<(), DocumentError> {
    let data = std::fs::read(source).map_err(|error| unreadable(error.to_string()))?;
    let mut document = Document::load_mem(&data).map_err(|error| unreadable(error.to_string()))?;
    if document.is_encrypted() {
        return Err(DocumentError::simple(DocumentErrorKind::Encrypted));
    }

    let mut changed: BTreeMap<usize, Vec<(&PdfBlock, String)>> = BTreeMap::new();
    for (index, block) in layout.blocks.iter().enumerate() {
        let Some(translation) = translations.get(index) else {
            continue;
        };
        let text = translation.trim();
        if text.is_empty() || text == block.text {
            continue;
        }
        changed
            .entry(block.page_index)
            .or_default()
            .push((block, text.to_string()));
    }

    if changed.is_empty() {
        return crate::io::write_atomic(out_path, &data);
    }

    let page_ids: Vec<ObjectId> = document.get_pages().values().copied().collect();
    let mut book = FontBook::new();
    let mut embedder = Embedder::new();
    for (page_index, items) in &changed {
        let Some(&page_id) = page_ids.get(*page_index) else {
            continue;
        };
        let page_height = layout
            .page_sizes
            .get(*page_index)
            .map(|(_, height)| *height)
            .unwrap_or(842.0);
        let mut content = String::new();
        for (block, text) in items {
            draw_block(
                &mut content,
                block,
                text,
                page_height,
                &mut book,
                &mut embedder,
            )?;
        }
        if content.is_empty() {
            continue;
        }
        append_content(&mut document, page_id, content.into_bytes())?;
    }

    let fonts = embedder.finish(&mut document)?;
    if !fonts.is_empty() {
        for page_index in changed.keys() {
            if let Some(&page_id) = page_ids.get(*page_index) {
                add_page_fonts(&mut document, page_id, &fonts)?;
            }
        }
    }

    let mut output = Vec::new();
    document
        .save_to(&mut output)
        .map_err(|error| write_failed(error.to_string()))?;
    crate::io::write_atomic(out_path, &output)
}

fn draw_block(
    content: &mut String,
    block: &PdfBlock,
    text: &str,
    page_height: f32,
    book: &mut FontBook,
    embedder: &mut Embedder,
) -> Result<(), DocumentError> {
    let Some(font) = book.choose(text, block.bold) else {
        warn!(
            "ofm-docs: no system font covers a PDF block ({}); leaving it untranslated",
            block.font_name
        );
        return Ok(());
    };
    let resource = embedder.resource_for(&font);
    embedder.note_glyphs(&resource, &font, text);

    let rect_x = f64::from(block.x0);
    let rect_width = f64::from(block.width()).max(1.0);
    let rect_height = f64::from(block.height()).max(1.0);
    let rect_bottom = f64::from(page_height) - f64::from(block.bottom);
    let (size, lines, line_leading) = layout_block(&font, block, text, rect_width, rect_height);

    // Cover the old glyphs; the original text layer stays extractable below.
    content.push_str("q\n");
    content.push_str(&format!(
        "{:.4} {:.4} {:.4} rg\n",
        block.background[0], block.background[1], block.background[2]
    ));
    content.push_str(&format!(
        "{:.4} {:.4} {:.4} {:.4} re\nf\nQ\n",
        rect_x - 2.0,
        rect_bottom - 1.0,
        rect_width + 4.0,
        rect_height + 2.0
    ));

    content.push_str("q\n");
    content.push_str(&format!(
        "{:.4} {:.4} {:.4} {:.4} re\nW n\n",
        rect_x, rect_bottom, rect_width, rect_height
    ));
    content.push_str("BT\n");
    content.push_str(&format!("/{resource} {size:.4} Tf\n"));
    let color = text_color(block.background, block.text_color);
    content.push_str(&format!(
        "{:.4} {:.4} {:.4} rg\n",
        color[0], color[1], color[2]
    ));

    let mut baseline = rect_bottom + rect_height - font.ascent(size);
    for line in &lines {
        if baseline < rect_bottom - size {
            break;
        }
        let width = font.width(line, size);
        let x = match block.alignment {
            super::TextAlignment::Center => rect_x + (rect_width - width) / 2.0,
            super::TextAlignment::Right => rect_x + rect_width - width,
            super::TextAlignment::Left => rect_x,
        };
        let Some(codes) = font.encode(line) else {
            warn!("ofm-docs: could not encode a PDF overlay line; skipping it");
            break;
        };
        content.push_str(&format!("1 0 0 1 {x:.4} {baseline:.4} Tm\n<"));
        if font.two_byte() {
            for code in codes {
                content.push_str(&format!("{code:04x}"));
            }
        } else {
            for code in codes {
                content.push_str(&format!("{:02x}", u8::try_from(code).unwrap_or(b'?')));
            }
        }
        content.push_str("> Tj\n");
        baseline -= f64::from(line_leading);
    }
    content.push_str("ET\nQ\n");
    Ok(())
}

fn layout_block(
    font: &DrawFont<'_>,
    block: &PdfBlock,
    text: &str,
    rect_width: f64,
    rect_height: f64,
) -> (f64, Vec<String>, f32) {
    let mut size = f64::from(block.font_size).clamp(4.5, 200.0);
    let mut lines = vec![text.to_string()];
    let mut spacing = size * 1.2;
    while size >= 4.5 {
        lines = wrap_paragraph(text, font, size, rect_width);
        spacing = f64::from(leading(block, size as f32));
        if lines.len() as f64 * spacing <= rect_height + 1.5 || size <= 4.6 {
            break;
        }
        size -= 0.5;
    }
    (size, lines, spacing as f32)
}

fn wrap_paragraph(text: &str, font: &DrawFont<'_>, size: f64, max_width: f64) -> Vec<String> {
    let mut lines = Vec::new();
    for raw in text.lines() {
        lines.extend(wrap_line(raw, font, size, max_width));
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

fn wrap_line(text: &str, font: &DrawFont<'_>, size: f64, max_width: f64) -> Vec<String> {
    if text.is_empty() {
        return vec![String::new()];
    }
    let width = max_width.max(1.0);
    let mut lines = Vec::new();
    let mut current = String::new();
    for word in text.split_whitespace() {
        let candidate = if current.is_empty() {
            word.to_string()
        } else {
            format!("{current} {word}")
        };
        if font.width(&candidate, size) <= width {
            current = candidate;
            continue;
        }
        if !current.is_empty() {
            lines.push(std::mem::take(&mut current));
        }
        if font.width(word, size) <= width {
            current = word.to_string();
            continue;
        }
        let mut chunks = hard_split(word, font, size, width);
        let last = chunks.pop().unwrap_or_default();
        lines.extend(chunks);
        current = last;
    }
    if !current.is_empty() {
        lines.push(current);
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

fn hard_split(word: &str, font: &DrawFont<'_>, size: f64, max_width: f64) -> Vec<String> {
    let mut chunks = Vec::new();
    let mut current = String::new();
    let mut current_width = 0.0f64;
    for character in word.chars() {
        let character_width = font.width(&character.to_string(), size);
        if !current.is_empty() && current_width + character_width > max_width {
            chunks.push(std::mem::take(&mut current));
            current = character.to_string();
            current_width = character_width;
        } else {
            current.push(character);
            current_width += character_width;
        }
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    if chunks.is_empty() {
        chunks.push(String::new());
    }
    chunks
}

// ---------------------------------------------------------------------------
// Archive-level helpers

fn current_contents(document: &Document, page_id: ObjectId) -> Result<Vec<Object>, DocumentError> {
    let page = document
        .get_dictionary(page_id)
        .map_err(|error| write_failed(error.to_string()))?;
    match page.get(b"Contents") {
        Ok(Object::Reference(id)) => match document.get_object(*id) {
            Ok(Object::Array(array)) => Ok(array.clone()),
            _ => Ok(vec![Object::Reference(*id)]),
        },
        Ok(Object::Array(array)) => Ok(array.clone()),
        _ => Ok(Vec::new()),
    }
}

fn append_content(
    document: &mut Document,
    page_id: ObjectId,
    bytes: Vec<u8>,
) -> Result<(), DocumentError> {
    let direct = document
        .get_dictionary(page_id)
        .ok()
        .and_then(|page| page.get(b"Contents").ok())
        .and_then(|object| object.as_stream().ok())
        .cloned();

    let mut contents = current_contents(document, page_id)?;
    if let Some(stream) = direct {
        let id = document.add_object(Object::Stream(stream));
        contents.push(Object::Reference(id));
    }

    let mut stream = Stream::new(Dictionary::new(), bytes);
    let _ = stream.compress();
    let stream = stream.with_compression(false);
    let id = document.add_object(Object::Stream(stream));
    contents.push(Object::Reference(id));

    document
        .get_dictionary_mut(page_id)
        .map_err(|error| write_failed(error.to_string()))?
        .set("Contents", contents);
    Ok(())
}

fn add_page_fonts(
    document: &mut Document,
    page_id: ObjectId,
    fonts: &[(String, ObjectId)],
) -> Result<(), DocumentError> {
    let mut resources = super::read::merged_resources(document, page_id);
    let mut font_dictionary = match resources.get(b"Font") {
        Ok(Object::Reference(id)) => document.get_dictionary(*id).cloned().unwrap_or_default(),
        Ok(Object::Dictionary(dictionary)) => dictionary.clone(),
        _ => Dictionary::new(),
    };
    for (name, id) in fonts {
        font_dictionary.set(name.as_str(), Object::Reference(*id));
    }
    resources.set("Font", font_dictionary);
    document
        .get_dictionary_mut(page_id)
        .map_err(|error| write_failed(error.to_string()))?
        .set("Resources", resources);
    Ok(())
}

// ---------------------------------------------------------------------------
// Font embedding

#[derive(PartialEq, Eq)]
enum EmbedKey {
    TrueType(PathBuf),
    Helvetica(bool),
}

struct PendingFont {
    key: EmbedKey,
    resource: String,
    path: Option<PathBuf>,
    glyphs: BTreeMap<u16, char>,
}

struct Embedder {
    fonts: Vec<PendingFont>,
}

impl Embedder {
    fn new() -> Self {
        Self { fonts: Vec::new() }
    }

    fn resource_for(&mut self, font: &DrawFont<'_>) -> String {
        let key = match font {
            DrawFont::TrueType(ttf) => EmbedKey::TrueType(ttf.path().to_path_buf()),
            DrawFont::Base14 { bold } => EmbedKey::Helvetica(*bold),
        };
        if let Some(pending) = self.fonts.iter().find(|pending| pending.key == key) {
            return pending.resource.clone();
        }
        let resource = format!("OFMF{}", self.fonts.len());
        let path = match font {
            DrawFont::TrueType(ttf) => Some(ttf.path().to_path_buf()),
            DrawFont::Base14 { .. } => None,
        };
        self.fonts.push(PendingFont {
            key,
            resource: resource.clone(),
            path,
            glyphs: BTreeMap::new(),
        });
        resource
    }

    fn note_glyphs(&mut self, resource: &str, font: &DrawFont<'_>, text: &str) {
        let Some(pending) = self
            .fonts
            .iter_mut()
            .find(|pending| pending.resource == resource)
        else {
            return;
        };
        let Some(ttf) = font.true_type() else {
            return;
        };
        for character in text.chars() {
            if let Some(info) = ttf.glyph_info(character) {
                pending.glyphs.entry(info.gid).or_insert(character);
            }
        }
    }

    fn finish(
        &mut self,
        document: &mut Document,
    ) -> Result<Vec<(String, ObjectId)>, DocumentError> {
        let mut resources = Vec::with_capacity(self.fonts.len());
        for pending in &self.fonts {
            let id = match &pending.key {
                EmbedKey::Helvetica(bold) => embed_base14(document, *bold),
                EmbedKey::TrueType(_) => {
                    let Some(path) = &pending.path else {
                        return Err(write_failed("pdf: embedded font has no path"));
                    };
                    let Some(font) = TtfFont::load(path) else {
                        return Err(write_failed(format!(
                            "pdf: could not load the font {}",
                            path.display()
                        )));
                    };
                    embed_truetype(document, &font, &pending.glyphs)?
                }
            };
            resources.push((pending.resource.clone(), id));
        }
        Ok(resources)
    }
}

fn embed_base14(document: &mut Document, bold: bool) -> ObjectId {
    let base_font = if bold { "Helvetica-Bold" } else { "Helvetica" };
    document.add_object(Object::Dictionary(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type1",
        "BaseFont" => base_font,
        "Encoding" => "WinAnsiEncoding",
    }))
}

fn embed_truetype(
    document: &mut Document,
    font: &TtfFont,
    glyphs: &BTreeMap<u16, char>,
) -> Result<ObjectId, DocumentError> {
    let data = font.data().to_vec();
    let mut file_dictionary = Dictionary::new();
    file_dictionary.set("Length1", data.len() as i64);
    let mut file_stream = Stream::new(file_dictionary, data);
    let _ = file_stream.compress();
    let file_stream = file_stream.with_compression(false);
    let file_id = document.add_object(Object::Stream(file_stream));

    let bbox = font.bbox_1000();
    let base_name = font.base_name();
    let descriptor = document.add_object(Object::Dictionary(dictionary! {
        "Type" => "FontDescriptor",
        "FontName" => base_name.clone(),
        "Flags" => 4i64,
        "FontBBox" => vec![
            Object::Integer(i64::from(bbox[0])),
            Object::Integer(i64::from(bbox[1])),
            Object::Integer(i64::from(bbox[2])),
            Object::Integer(i64::from(bbox[3])),
        ],
        "ItalicAngle" => 0i64,
        "Ascent" => i64::from(font.ascender_1000()),
        "Descent" => i64::from(font.descender_1000()),
        "CapHeight" => i64::from(font.cap_height_1000()),
        "StemV" => 80i64,
        "FontFile2" => file_id,
    }));

    let widths = widths_array(font, glyphs);
    let descendant = document.add_object(Object::Dictionary(dictionary! {
        "Type" => "Font",
        "Subtype" => "CIDFontType2",
        "BaseFont" => base_name.clone(),
        "CIDSystemInfo" => dictionary! {
            "Registry" => Object::string_literal("Adobe"),
            "Ordering" => Object::string_literal("Identity"),
            "Supplement" => 0i64,
        },
        "FontDescriptor" => descriptor,
        "CIDToGIDMap" => "Identity",
        "DW" => 1000i64,
        "W" => Object::Array(widths),
    }));

    let cmap = to_unicode_cmap(glyphs);
    let mut cmap_stream = Stream::new(Dictionary::new(), cmap);
    let _ = cmap_stream.compress();
    let cmap_stream = cmap_stream.with_compression(false);
    let cmap_id = document.add_object(Object::Stream(cmap_stream));

    Ok(document.add_object(Object::Dictionary(dictionary! {
        "Type" => "Font",
        "Subtype" => "Type0",
        "BaseFont" => base_name,
        "Encoding" => "Identity-H",
        "DescendantFonts" => vec![Object::Reference(descendant)],
        "ToUnicode" => cmap_id,
    })))
}

fn widths_array(font: &TtfFont, glyphs: &BTreeMap<u16, char>) -> Vec<Object> {
    let gids: Vec<u16> = glyphs.keys().copied().collect();
    let mut array = Vec::new();
    let mut run_start: Option<u16> = None;
    let mut run: Vec<Object> = Vec::new();
    for gid in gids {
        let advance = glyphs
            .get(&gid)
            .and_then(|character| font.glyph_info(*character))
            .map(|info| info.advance.round().max(0.0) as i64)
            .unwrap_or(1000);
        if let Some(start) = run_start {
            if u32::from(start) + run.len() as u32 == u32::from(gid) {
                run.push(Object::Integer(advance));
                continue;
            }
            array.push(Object::Integer(i64::from(start)));
            array.push(Object::Array(std::mem::take(&mut run)));
        }
        run_start = Some(gid);
        run.push(Object::Integer(advance));
    }
    if let Some(start) = run_start {
        array.push(Object::Integer(i64::from(start)));
        array.push(Object::Array(run));
    }
    array
}

fn to_unicode_cmap(glyphs: &BTreeMap<u16, char>) -> Vec<u8> {
    let mut cmap = String::from(
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n\
         /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n\
         /CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n\
         1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n",
    );
    let entries: Vec<(u16, char)> = glyphs.iter().map(|(gid, ch)| (*gid, *ch)).collect();
    for chunk in entries.chunks(100) {
        cmap.push_str(&format!("{} beginbfchar\n", chunk.len()));
        for (gid, character) in chunk {
            let mut units = [0u16; 2];
            let encoded = character.encode_utf16(&mut units);
            let mut hex = String::new();
            for unit in encoded {
                hex.push_str(&format!("{unit:04X}"));
            }
            cmap.push_str(&format!("<{gid:04X}> <{hex}>\n"));
        }
        cmap.push_str("endbfchar\n");
    }
    cmap.push_str("endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n");
    cmap.into_bytes()
}
