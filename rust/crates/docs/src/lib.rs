//! Document translation for plain text, Markdown, Word (DOCX) and PDF files.
//!
//! This crate is the Rust port of `windows/deepl_ofm/services/documents.py` and
//! mirrors `Sources/HyMT/Services/DocumentTranslator.swift` on the behaviour the
//! Python version encodes:
//!
//! * **TXT/MD** keep their line structure, blank lines and fenced or indented
//!   code blocks. Only the prose of non-blank lines is handed to the
//!   translation callable: on every line the leading indentation and trailing
//!   spaces are re-attached verbatim, together with the source's own line
//!   separators (so CRLF stays CRLF), and concatenating the units reproduces
//!   the file byte-for-byte. Input may be UTF-8 (with or
//!   without BOM), UTF-16/UTF-32 with a BOM, or legacy cp1251/cp1252; output is
//!   always UTF-8.
//! * **DOCX** changes only the `<w:t>` text nodes of `word/document.xml` inside
//!   a copy of the package. Every other entry keeps its bytes, compression
//!   method, order and timestamps (the `zip` crate normalises the Unix mode
//!   stored in the external attributes), and the spliced XML keeps namespace
//!   prefixes, run
//!   boundaries and unused `mc:Ignorable` declarations. Only the qualified
//!   `w:` elements are WordprocessingML: Office Math (`m:t`), field
//!   instructions (`w:instrText`), deleted revisions (`w:delText`) and
//!   `mc:Fallback` copies are never rewritten. Nested text boxes are translated
//!   per paragraph (the innermost open paragraph owns its text).
//! * **PDF** keeps the original page as the background, extracts text blocks
//!   with coordinates and paints the translation into the same rectangles.
//!   See [`PdfLayout`] for the coordinate model and the crate README for the
//!   documented approximations.
//!
//! The module is free of UI and platform dependencies: it is used from worker
//! threads and must stay importable in a headless test run.
//!
//! # PDF approximations
//!
//! The Python version renders with pdfplumber + reportlab + pypdf. This port is
//! pure Rust ([`lopdf`] + [`ttf-parser`]) and differs in these documented ways:
//!
//! * Text extraction reads the page content streams (including form XObjects).
//!   Simple fonts are decoded through `/ToUnicode` when present and through
//!   WinAnsi/MacRoman otherwise; a font without either extracts as no text.
//! * Only the dominant writing direction is handled: rotated text is placed at
//!   its geometric position but drawn horizontally.
//! * The overlay is drawn in unrotated page space, like `pypdf.merge_page`, so
//!   pages with a non-zero `/Rotate` get correctly placed but misoriented text.
//! * `/Mediabox` is used for page geometry and a non-zero box origin is treated
//!   as `(0, 0)`; `/CropBox` is ignored.
//! * Base-14 text metrics come from the Adobe AFM tables for Helvetica and
//!   Times (regular/bold/italic/bold-italic) and fixed 600 for Courier; Symbol
//!   and ZapfDingbats fall back to a documented default.
//! * Background sampling uses filled path geometry rather than a page raster.
//! * Fonts are embedded whole (no subsetting), so a PDF written with Cyrillic or
//!   CJK text grows by the size of the system font. When no system font covers
//!   the translation, that block is left in the source language and a warning is
//!   logged instead of drawing missing-glyph boxes.
//! * The original text layer is never removed; it stays extractable below the
//!   overlay, exactly like the Python implementation.
//! * Only `word/document.xml` is translated: headers, footers, footnotes and
//!   comments stay in the source language, exactly like the Python version.
//!
//! # Examples
//!
//! ```no_run
//! use std::path::Path;
//! use ofm_docs::DocumentTranslator;
//! use ofm_i18n::LanguageTable;
//!
//! let source = Path::new("report.docx");
//! let document = DocumentTranslator::read(source).expect("supported document");
//! let target = LanguageTable::get("uk").expect("known language");
//! let output = DocumentTranslator::suggested_path(source, target);
//! DocumentTranslator::write(
//!     &document,
//!     &output,
//!     &mut |paragraph| Ok(paragraph.to_uppercase()),
//!     None,
//!     None,
//! )
//! .expect("written");
//! ```

#![deny(missing_docs)]

mod docx;
mod encoding;
mod error;
mod io;
mod kind;
mod pdf;
mod text;

use std::path::{Path, PathBuf};
use std::sync::atomic::AtomicBool;

pub use error::{DocumentError, DocumentErrorKind};
pub use kind::DocumentKind;
pub use pdf::fonts::{cjk_font_available, system_font_available};
pub use pdf::{PdfBlock, PdfLayout, TextAlignment};

use ofm_i18n::Language;

/// Format-specific state that a translated document needs when writing back.
#[derive(Debug)]
pub enum Payload {
    /// No extra state (TXT/MD).
    None,
    /// Raw `word/document.xml` of the source DOCX.
    Docx(Vec<u8>),
    /// Text-block layout of the source PDF.
    Pdf(Box<PdfLayout>),
}

/// A file that was inspected and is ready to be translated.
#[derive(Debug)]
pub struct OpenedDocument {
    /// Source path.
    pub path: PathBuf,
    /// Detected format.
    pub kind: DocumentKind,
    /// Whole decoded source text for TXT/MD.
    pub source_text: Option<String>,
    /// Paragraph texts for DOCX/PDF (empty for TXT/MD).
    pub paragraphs: Vec<String>,
    /// Format-specific state needed by [`DocumentTranslator::write`].
    pub payload: Payload,
}

impl OpenedDocument {
    /// Whole source text (TXT/MD) or the paragraph texts joined by newlines.
    pub fn text(&self) -> String {
        match &self.source_text {
            Some(text) => text.clone(),
            None => self.paragraphs.join("\n"),
        }
    }
}

/// Read documents, hand their paragraphs to a translation callable and write
/// them back.
pub struct DocumentTranslator;

impl DocumentTranslator {
    /// Inspect a document and prepare it for translation.
    ///
    /// # Errors
    ///
    /// [`DocumentErrorKind::Unsupported`] for an unknown extension,
    /// [`DocumentErrorKind::Encrypted`] for a password-protected PDF,
    /// [`DocumentErrorKind::NoText`] when there is nothing to translate, and
    /// [`DocumentErrorKind::Unreadable`] when the file cannot be parsed.
    pub fn read(path: &Path) -> Result<OpenedDocument, DocumentError> {
        let kind = DocumentKind::from_path(path)
            .ok_or_else(|| DocumentError::simple(DocumentErrorKind::Unsupported))?;

        match kind {
            DocumentKind::Text | DocumentKind::Markdown => {
                let text = text::read(path)?;
                if text.trim().is_empty() {
                    return Err(DocumentError::simple(DocumentErrorKind::NoText));
                }
                Ok(OpenedDocument {
                    path: path.to_path_buf(),
                    kind,
                    source_text: Some(text),
                    paragraphs: Vec::new(),
                    payload: Payload::None,
                })
            }
            DocumentKind::Pdf => {
                let layout = pdf::read_layout(path)?;
                let paragraphs = layout
                    .blocks
                    .iter()
                    .map(|block| block.text.clone())
                    .collect();
                Ok(OpenedDocument {
                    path: path.to_path_buf(),
                    kind,
                    source_text: None,
                    paragraphs,
                    payload: Payload::Pdf(Box::new(layout)),
                })
            }
            DocumentKind::Docx => {
                let (xml, paragraphs) = docx::read(path)?;
                if !paragraphs
                    .iter()
                    .any(|paragraph| !paragraph.trim().is_empty())
                {
                    return Err(DocumentError::simple(DocumentErrorKind::NoText));
                }
                Ok(OpenedDocument {
                    path: path.to_path_buf(),
                    kind,
                    source_text: None,
                    paragraphs,
                    payload: Payload::Docx(xml),
                })
            }
        }
    }

    /// Return `report.pdf` -> `report_uk.pdf` without touching the source.
    ///
    /// The target's language code is appended to the stem; the extension is
    /// normalised to the kind's canonical lower-case form (as the Swift app
    /// does when it builds its output file) and the source path is never
    /// returned.
    pub fn suggested_path(path: &Path, target: &Language) -> PathBuf {
        let code = if target.code.is_empty() {
            "translated"
        } else {
            target.code
        };
        let suffix = match DocumentKind::from_path(path) {
            Some(kind) => format!(".{}", kind.value()),
            None => path
                .extension()
                .map(|extension| format!(".{}", extension.to_string_lossy()))
                .unwrap_or_default(),
        };
        let stem = path
            .file_stem()
            .map(|stem| stem.to_string_lossy().into_owned())
            .unwrap_or_else(|| "document".to_string());
        let mut candidate = path.with_file_name(format!("{stem}_{code}{suffix}"));
        if same_path(&candidate, path) {
            for index in 1..1000 {
                let attempt = path.with_file_name(format!("{stem}_{code}_{index}{suffix}"));
                if !same_path(&attempt, path) {
                    candidate = attempt;
                    break;
                }
            }
        }
        candidate
    }

    /// Translate `document` and write the result to `out_path`.
    ///
    /// `translate` is called once per source paragraph and must return one
    /// translated paragraph. `on_progress(completed, total)` is invoked after
    /// every paragraph and counts only paragraphs that were sent to the model.
    /// The cancellation flag is checked before each paragraph and before the
    /// output is written; a set flag returns [`DocumentErrorKind::Cancelled`]
    /// and leaves no output file behind.
    ///
    /// # Errors
    ///
    /// A failed translation callable is reported as
    /// [`DocumentErrorKind::WriteFailed`] with the original message in
    /// [`DocumentError::detail`].
    pub fn write(
        doc: &OpenedDocument,
        out_path: &Path,
        translate: &mut dyn FnMut(&str) -> Result<String, String>,
        on_progress: Option<&dyn Fn(usize, usize)>,
        cancel: Option<&AtomicBool>,
    ) -> Result<PathBuf, DocumentError> {
        io::check_cancel(cancel)?;

        match doc.kind {
            DocumentKind::Text | DocumentKind::Markdown => {
                let text = doc.source_text.clone().unwrap_or_else(|| doc.text());
                let translated = text::translate_text(
                    &text,
                    doc.kind == DocumentKind::Markdown,
                    translate,
                    on_progress,
                    cancel,
                )?;
                io::check_cancel(cancel)?;
                io::write_atomic(out_path, translated.as_bytes())?;
            }
            DocumentKind::Docx => {
                let translations = io::translate_paragraphs_preserving_edges(
                    &doc.paragraphs,
                    translate,
                    on_progress,
                    cancel,
                )?;
                io::check_cancel(cancel)?;
                let payload = match &doc.payload {
                    Payload::Docx(bytes) => Some(bytes.as_slice()),
                    _ => None,
                };
                docx::write(&doc.path, payload, &doc.paragraphs, &translations, out_path)?;
            }
            DocumentKind::Pdf => {
                let Payload::Pdf(layout) = &doc.payload else {
                    return Err(DocumentError::new(
                        DocumentErrorKind::Unreadable,
                        "the document has no PDF layout",
                    ));
                };
                let translations =
                    io::translate_paragraphs(&doc.paragraphs, translate, on_progress, cancel)?;
                io::check_cancel(cancel)?;
                pdf::write_layout(&doc.path, layout, &translations, out_path)?;
            }
        }

        Ok(out_path.to_path_buf())
    }
}

fn same_path(first: &Path, second: &Path) -> bool {
    let first = std::path::absolute(first).unwrap_or_else(|_| first.to_path_buf());
    let second = std::path::absolute(second).unwrap_or_else(|_| second.to_path_buf());
    if cfg!(windows) {
        first.to_string_lossy().to_lowercase() == second.to_string_lossy().to_lowercase()
    } else {
        first == second
    }
}
