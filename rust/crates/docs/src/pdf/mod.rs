//! PDF text-block reading and overlay writing.
//!
//! Reading parses the page content streams with [`lopdf`] and recovers words
//! with their position, font size, colour and boldness. Writing keeps the
//! original pages untouched and appends a small content stream that covers each
//! block with its sampled background colour and draws the translation on top.

use std::path::Path;

use crate::error::{unreadable, DocumentError};

/// Horizontal alignment of a text block, inferred from its position on the page.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Default)]
pub enum TextAlignment {
    /// The block starts at the left margin (default).
    #[default]
    Left,
    /// The block is centred on the page.
    Center,
    /// The block ends at the right margin.
    Right,
}

impl TextAlignment {
    /// Lower-case name, matching the Python representation.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Left => "left",
            Self::Center => "center",
            Self::Right => "right",
        }
    }
}

/// One run of text recovered from a PDF page.
///
/// Coordinates use the top-left origin that pdfplumber uses, so `top` grows
/// downwards; `font_size`, `width` and `height` are in PDF user-space points.
#[derive(Clone, Debug)]
pub struct PdfBlock {
    /// Zero-based page index.
    pub page_index: usize,
    /// Left edge.
    pub x0: f32,
    /// Top edge (distance from the top of the page).
    pub top: f32,
    /// Right edge.
    pub x1: f32,
    /// Bottom edge.
    pub bottom: f32,
    /// Text of the block, lines joined with single spaces.
    pub text: String,
    /// Font size of the largest line in the block.
    pub font_size: f32,
    /// Whether the first line used a bold font.
    pub bold: bool,
    /// Base font name of the first line, as written in the PDF.
    pub font_name: String,
    /// Inferred alignment.
    pub alignment: TextAlignment,
    /// Baseline-to-baseline distance inside the block, `0` for one line.
    pub line_pitch: f32,
    /// Fill colour of the original text.
    pub text_color: [f32; 3],
    /// Sampled background colour behind the block.
    pub background: [f32; 3],
}

impl PdfBlock {
    /// Block width in points.
    pub fn width(&self) -> f32 {
        self.x1 - self.x0
    }

    /// Block height in points.
    pub fn height(&self) -> f32 {
        self.bottom - self.top
    }
}

/// Every text block of a PDF, in page order.
#[derive(Clone, Debug, Default)]
pub struct PdfLayout {
    /// Number of pages in the document.
    pub page_count: usize,
    /// `(width, height)` of every page, indexed by page.
    pub page_sizes: Vec<(f32, f32)>,
    /// Text blocks, ordered by page and vertical position.
    pub blocks: Vec<PdfBlock>,
}

pub(crate) mod fonts;
mod read;
mod write;

/// Read the text-block layout of a PDF.
pub(crate) fn read_layout(path: &Path) -> Result<PdfLayout, DocumentError> {
    read::read_layout(path)
}

/// Draw the translations over the original pages and write the result.
pub(crate) fn write_layout(
    source: &Path,
    layout: &PdfLayout,
    translations: &[String],
    out_path: &Path,
) -> Result<(), DocumentError> {
    write::write_layout(source, layout, translations, out_path)
}

/// Line spacing used to draw a wrapped block.
pub(crate) fn leading(block: &PdfBlock, size: f32) -> f32 {
    if block.line_pitch > 0.0 {
        block.line_pitch.clamp(size * 1.05, size * 2.0)
    } else {
        size * 1.2
    }
}

/// Relative luminance of a normalised RGB colour.
pub(crate) fn luminance(color: [f32; 3]) -> f32 {
    0.2126 * color[0] + 0.7152 * color[1] + 0.0722 * color[2]
}

/// Keep the original text colour when it contrasts with the background.
///
/// Mirrors `DocumentTranslator.draw` in Swift: if the original colour is too
/// close to the background, switch to white on dark surfaces and black on
/// light ones.
pub(crate) fn text_color(background: [f32; 3], original: [f32; 3]) -> [f32; 3] {
    let background_luminance = luminance(background);
    if (luminance(original) - background_luminance).abs() > 0.25 {
        return original;
    }
    if background_luminance < 0.55 {
        [1.0, 1.0, 1.0]
    } else {
        [0.0, 0.0, 0.0]
    }
}

/// Convert PDF colour components (gray, RGB or CMYK, 0..1 or 0..255) to RGB.
pub(crate) fn color_from_components(components: &[f32]) -> Option<[f32; 3]> {
    if components.is_empty() {
        return None;
    }
    let mut values = components.to_vec();
    if values.iter().any(|component| *component > 1.0) {
        for value in &mut values {
            *value /= 255.0;
        }
    }
    for value in &mut values {
        *value = value.clamp(0.0, 1.0);
    }
    match values.len() {
        1 => Some([values[0], values[0], values[0]]),
        3 => Some([values[0], values[1], values[2]]),
        4 => Some([
            (1.0 - values[0]) * (1.0 - values[3]),
            (1.0 - values[1]) * (1.0 - values[3]),
            (1.0 - values[2]) * (1.0 - values[3]),
        ]),
        _ => None,
    }
}

/// Report the error used by the unfinished overlay writer.
#[allow(dead_code)]
pub(crate) fn unavailable(detail: &str) -> DocumentError {
    unreadable(detail)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn block(line_pitch: f32) -> PdfBlock {
        PdfBlock {
            page_index: 0,
            x0: 10.0,
            top: 10.0,
            x1: 110.0,
            bottom: 40.0,
            text: "text".to_string(),
            font_size: 12.0,
            bold: false,
            font_name: "Helvetica".to_string(),
            alignment: TextAlignment::Left,
            line_pitch,
            text_color: [0.0, 0.0, 0.0],
            background: [1.0, 1.0, 1.0],
        }
    }

    #[test]
    fn colour_parsing_handles_gray_rgb_cmyk_and_255_scale() {
        assert_eq!(color_from_components(&[]), None);
        assert_eq!(color_from_components(&[0.5]), Some([0.5, 0.5, 0.5]));
        assert_eq!(
            color_from_components(&[0.2, 0.4, 0.6]),
            Some([0.2, 0.4, 0.6].map(|value| value as f32))
        );
        let cmyk = color_from_components(&[0.0, 0.5, 0.5, 0.0]).expect("cmyk");
        assert!((cmyk[0] - 1.0).abs() < 1e-6);
        assert!((cmyk[1] - 0.5).abs() < 1e-6);
        assert!((cmyk[2] - 0.5).abs() < 1e-6);
        let scaled = color_from_components(&[128.0, 128.0, 128.0]).expect("scaled");
        assert!((scaled[0] - 128.0 / 255.0).abs() < 1e-6);
        assert_eq!(color_from_components(&[1.0, 0.0]), None);
    }

    #[test]
    fn leading_uses_the_source_pitch_when_available() {
        assert!((leading(&block(0.0), 12.0) - 14.4).abs() < 1e-4);
        assert!((leading(&block(16.0), 12.0) - 16.0).abs() < 1e-4);
        // Clamped to [1.05 * size, 2.0 * size].
        assert!((leading(&block(40.0), 12.0) - 24.0).abs() < 1e-4);
    }

    #[test]
    fn text_colour_keeps_contrast_or_flips() {
        assert_eq!(
            text_color([0.2, 0.4, 0.6], [0.0, 0.0, 0.0]),
            [0.0, 0.0, 0.0]
        );
        assert_eq!(
            text_color([0.05, 0.05, 0.05], [0.0, 0.0, 0.0]),
            [1.0, 1.0, 1.0]
        );
        assert_eq!(
            text_color([1.0, 1.0, 1.0], [0.95, 0.95, 0.95]),
            [0.0, 0.0, 0.0]
        );
    }
}
