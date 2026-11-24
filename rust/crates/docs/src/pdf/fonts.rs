//! System font discovery and TrueType metrics for PDF overlays.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

use ttf_parser::{Face, GlyphId};

use crate::encoding;

/// Whether a system TrueType font covering Cyrillic and other non-WinAnsi
/// scripts is available for PDF overlays.
pub fn system_font_available() -> bool {
    system_font_path(false).is_some()
}

/// Whether a system TrueType font covering CJK text is available for overlays.
pub fn cjk_font_available() -> bool {
    cjk_font_path().is_some()
}

/// Locate a regular or bold Unicode TrueType font.
pub(crate) fn system_font_path(bold: bool) -> Option<PathBuf> {
    let names: &[&str] = if bold {
        &[
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "FreeSansBold.ttf",
            "segoeuib.ttf",
            "arialbd.ttf",
            "Arial Bold.ttf",
        ]
    } else {
        &[
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "FreeSans.ttf",
            "segoeui.ttf",
            "arial.ttf",
            "Arial.ttf",
        ]
    };
    find_in_system_dirs(names)
}

/// Locate a system font covering CJK codepoints.
pub(crate) fn cjk_font_path() -> Option<PathBuf> {
    find_in_system_dirs(&[
        "DroidSansFallbackFull.ttf",
        "DroidSansFallback.ttf",
        "fonts-japanese-gothic.ttf",
        "wqy-zenhei.ttc",
        "wqy-microhei.ttc",
        "NotoSansCJK-Regular.ttc",
        "NotoSansCJKsc-Regular.otf",
        "msyh.ttc",
        "simsun.ttc",
        "Arial Unicode.ttf",
    ])
}

fn find_in_system_dirs(names: &[&str]) -> Option<PathBuf> {
    for directory in font_directories() {
        for name in names {
            let candidate = directory.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

fn font_directories() -> Vec<PathBuf> {
    let mut directories = Vec::new();
    if let Ok(windows) = std::env::var("WINDIR") {
        directories.push(PathBuf::from(windows).join("Fonts"));
    }
    directories.push(PathBuf::from("C:/Windows/Fonts"));
    for path in [
        "/usr/share/fonts/truetype/dejavu",
        "/usr/share/fonts/truetype/liberation",
        "/usr/share/fonts/truetype/liberation2",
        "/usr/share/fonts/truetype/freefont",
        "/usr/share/fonts/truetype/noto",
        "/usr/share/fonts/truetype/wqy",
        "/usr/share/fonts/truetype/droid",
        "/usr/share/fonts/truetype",
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "/System/Library/Fonts/Supplemental",
        "/System/Library/Fonts",
        "/Library/Fonts",
    ] {
        directories.push(PathBuf::from(path));
    }
    directories
}

/// Advance widths in 1/1000 em for the standard-14 text faces, indexed by
/// WinAnsi code 32..255 (`0` means the face has no glyph for that byte).
///
/// Taken from the Adobe AFM metrics through reportlab, i.e. the same data the
/// Python reference measures with. Courier is fixed-pitch (600) and Symbol /
/// ZapfDingbats are symbol faces, so they share a documented default.
const HELVETICA_WIDTHS: [u16; 224] = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667,
    611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500,
    222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
    761, 556, 0, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 222, 222,
    333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556,
    260, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 556, 537, 278, 333,
    333, 365, 556, 834, 834, 834, 611, 667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667,
    278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667,
    611, 556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278, 556, 556,
    556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,
];

const HELVETICA_BOLD_WIDTHS: [u16; 224] = [
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556,
    556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667,
    611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667,
    667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556,
    278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
    761, 556, 0, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0, 0, 278, 278,
    500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500, 667, 278, 333, 556, 556, 556, 556,
    280, 556, 333, 737, 370, 556, 584, 333, 737, 333, 400, 584, 333, 333, 333, 611, 556, 278, 333,
    333, 365, 556, 834, 834, 834, 611, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667,
    278, 278, 278, 278, 722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667,
    611, 556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278, 611, 611,
    611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,
];

const TIMES_ROMAN_WIDTHS: [u16; 224] = [
    250, 333, 408, 500, 500, 833, 778, 180, 333, 333, 500, 564, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 278, 278, 564, 564, 564, 444, 921, 722, 667, 667, 722, 611,
    556, 722, 722, 333, 389, 722, 611, 889, 722, 722, 556, 722, 667, 556, 611, 722, 722, 944, 722,
    722, 611, 333, 278, 333, 469, 500, 333, 444, 500, 444, 500, 444, 333, 500, 500, 278, 278, 500,
    278, 778, 500, 500, 500, 500, 333, 389, 278, 500, 500, 722, 500, 500, 444, 480, 200, 480, 541,
    761, 500, 0, 333, 500, 444, 1000, 500, 500, 333, 1000, 556, 333, 889, 0, 611, 0, 0, 333, 333,
    444, 444, 350, 500, 1000, 333, 980, 389, 333, 722, 0, 444, 722, 250, 333, 500, 500, 500, 500,
    200, 500, 333, 760, 276, 500, 564, 333, 760, 333, 400, 564, 300, 300, 333, 500, 453, 250, 333,
    300, 310, 500, 750, 750, 750, 444, 722, 722, 722, 722, 722, 722, 889, 667, 611, 611, 611, 611,
    333, 333, 333, 333, 722, 722, 722, 722, 722, 722, 722, 564, 722, 722, 722, 722, 722, 722, 556,
    500, 444, 444, 444, 444, 444, 444, 667, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 500,
    500, 500, 500, 500, 500, 564, 500, 500, 500, 500, 500, 500, 500, 500,
];

const TIMES_BOLD_WIDTHS: [u16; 224] = [
    250, 333, 555, 500, 500, 1000, 833, 278, 333, 333, 500, 570, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 333, 333, 570, 570, 570, 500, 930, 722, 667, 722, 722, 667,
    611, 778, 778, 389, 500, 778, 667, 944, 722, 778, 611, 778, 722, 556, 667, 722, 722, 1000, 722,
    722, 667, 333, 278, 333, 581, 500, 333, 500, 556, 444, 556, 444, 333, 500, 556, 278, 333, 556,
    278, 833, 556, 500, 556, 556, 444, 389, 333, 556, 500, 722, 500, 500, 444, 394, 220, 394, 520,
    761, 500, 0, 333, 500, 500, 1000, 500, 500, 333, 1000, 556, 333, 1000, 0, 667, 0, 0, 333, 333,
    500, 500, 350, 500, 1000, 333, 1000, 389, 333, 722, 0, 444, 722, 250, 333, 500, 500, 500, 500,
    220, 500, 333, 747, 300, 500, 570, 333, 747, 333, 400, 570, 300, 300, 333, 556, 540, 250, 333,
    300, 330, 500, 750, 750, 750, 500, 722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667,
    389, 389, 389, 389, 722, 722, 778, 778, 778, 778, 778, 570, 778, 722, 722, 722, 722, 722, 611,
    556, 500, 500, 500, 500, 500, 500, 722, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 556,
    500, 500, 500, 500, 500, 570, 500, 556, 556, 556, 556, 500, 556, 500,
];

const TIMES_ITALIC_WIDTHS: [u16; 224] = [
    250, 333, 420, 500, 500, 833, 778, 214, 333, 333, 500, 675, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 333, 333, 675, 675, 675, 500, 920, 611, 611, 667, 722, 611,
    611, 722, 722, 333, 444, 667, 556, 833, 667, 722, 611, 722, 611, 500, 556, 722, 611, 833, 611,
    556, 556, 389, 278, 389, 422, 500, 333, 500, 500, 444, 500, 444, 278, 500, 500, 278, 278, 444,
    278, 722, 500, 500, 500, 500, 389, 389, 278, 500, 444, 667, 444, 444, 389, 400, 275, 400, 541,
    761, 500, 0, 333, 500, 556, 889, 500, 500, 333, 1000, 500, 333, 944, 0, 556, 0, 0, 333, 333,
    556, 556, 350, 500, 889, 333, 980, 389, 333, 667, 0, 389, 556, 250, 389, 500, 500, 500, 500,
    275, 500, 333, 760, 276, 500, 675, 333, 760, 333, 400, 675, 300, 300, 333, 500, 523, 250, 333,
    300, 310, 500, 750, 750, 750, 500, 611, 611, 611, 611, 611, 611, 889, 667, 611, 611, 611, 611,
    333, 333, 333, 333, 722, 667, 722, 722, 722, 722, 722, 675, 722, 722, 722, 722, 722, 556, 611,
    500, 500, 500, 500, 500, 500, 500, 667, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 500,
    500, 500, 500, 500, 500, 675, 500, 500, 500, 500, 500, 444, 500, 444,
];

const TIMES_BOLD_ITALIC_WIDTHS: [u16; 224] = [
    250, 389, 555, 500, 500, 833, 778, 278, 333, 333, 500, 570, 250, 333, 250, 278, 500, 500, 500,
    500, 500, 500, 500, 500, 500, 500, 333, 333, 570, 570, 570, 500, 832, 667, 667, 667, 722, 667,
    667, 722, 778, 389, 500, 667, 611, 889, 722, 722, 611, 722, 667, 556, 611, 722, 667, 889, 667,
    611, 611, 333, 278, 333, 570, 500, 333, 500, 500, 444, 500, 444, 333, 500, 556, 278, 278, 500,
    278, 778, 556, 500, 500, 500, 389, 389, 278, 556, 444, 667, 500, 444, 389, 348, 220, 348, 570,
    761, 500, 0, 333, 500, 500, 1000, 500, 500, 333, 1000, 556, 333, 944, 0, 611, 0, 0, 333, 333,
    500, 500, 350, 500, 1000, 333, 1000, 389, 333, 722, 0, 389, 611, 250, 389, 500, 500, 500, 500,
    220, 500, 333, 747, 266, 500, 606, 333, 747, 333, 400, 570, 300, 300, 333, 576, 500, 250, 333,
    300, 300, 500, 750, 750, 750, 500, 667, 667, 667, 667, 667, 667, 944, 667, 667, 667, 667, 667,
    389, 389, 389, 389, 722, 722, 722, 722, 722, 722, 722, 570, 722, 722, 722, 722, 722, 611, 611,
    500, 500, 500, 500, 500, 500, 500, 722, 444, 444, 444, 444, 444, 278, 278, 278, 278, 500, 556,
    500, 500, 500, 500, 500, 570, 500, 556, 556, 556, 556, 444, 500, 444,
];

/// Metric family of a base-14 font name.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Family {
    Helvetica,
    Times,
    Courier,
    Symbol,
}

fn family_of(lowered: &str) -> Family {
    if lowered.contains("courier") {
        Family::Courier
    } else if lowered.contains("symbol") || lowered.contains("zapf") || lowered.contains("dingbat")
    {
        Family::Symbol
    } else if lowered.contains("times")
        || lowered.contains("nimbusroman")
        || lowered.contains("liberationserif")
    {
        Family::Times
    } else {
        Family::Helvetica
    }
}

/// Advance width in 1/1000 text units for a base-14 font and a WinAnsi code.
pub(crate) fn base14_width(name: &str, code: u32) -> f64 {
    let lowered = name.to_lowercase();
    let family = family_of(&lowered);
    if family == Family::Courier {
        return 600.0;
    }
    let bold = lowered.contains("bold");
    let italic = lowered.contains("italic") || lowered.contains("oblique");
    let (table, default) = match family {
        Family::Courier => (None, 600.0),
        Family::Symbol => (None, 600.0),
        Family::Times => (
            Some(match (bold, italic) {
                (false, false) => &TIMES_ROMAN_WIDTHS,
                (true, false) => &TIMES_BOLD_WIDTHS,
                (false, true) => &TIMES_ITALIC_WIDTHS,
                (true, true) => &TIMES_BOLD_ITALIC_WIDTHS,
            }),
            500.0,
        ),
        Family::Helvetica => (
            Some(if bold {
                &HELVETICA_BOLD_WIDTHS
            } else {
                &HELVETICA_WIDTHS
            }),
            556.0,
        ),
    };
    if let Some(table) = table {
        if let Some(slot) = code
            .checked_sub(32)
            .and_then(|index| table.get(index as usize))
        {
            if *slot > 0 {
                return f64::from(*slot);
            }
        }
    }
    default
}

/// A glyph resolved in a TrueType font.
#[derive(Clone, Copy, Debug)]
pub(crate) struct GlyphInfo {
    /// Glyph index, used as the CID in `Identity-H` encoding.
    pub gid: u16,
    /// Horizontal advance in 1/1000 text units.
    pub advance: f32,
}

/// A parsed system TrueType font plus a per-character metric cache.
pub(crate) struct TtfFont {
    path: PathBuf,
    data: Vec<u8>,
    units_per_em: f32,
    ascender: f32,
    descender: f32,
    bbox: [i32; 4],
    cache: RefCell<HashMap<char, Option<GlyphInfo>>>,
}

impl TtfFont {
    pub(crate) fn load(path: &Path) -> Option<Self> {
        let data = std::fs::read(path).ok()?;
        let face = Face::parse(&data, 0).ok()?;
        let units_per_em = f32::from(face.units_per_em().max(1));
        let scale = 1000.0 / units_per_em;
        let bbox = face.global_bounding_box();
        Some(Self {
            path: path.to_path_buf(),
            units_per_em,
            ascender: f32::from(face.ascender()) * scale,
            descender: f32::from(face.descender()) * scale,
            bbox: [
                (f32::from(bbox.x_min) * scale).round() as i32,
                (f32::from(bbox.y_min) * scale).round() as i32,
                (f32::from(bbox.x_max) * scale).round() as i32,
                (f32::from(bbox.y_max) * scale).round() as i32,
            ],
            data,
            cache: RefCell::new(HashMap::new()),
        })
    }

    pub(crate) fn path(&self) -> &Path {
        &self.path
    }

    pub(crate) fn data(&self) -> &[u8] {
        &self.data
    }

    /// A PDF-safe PostScript name for the embedded font.
    pub(crate) fn base_name(&self) -> String {
        let stem = self
            .path
            .file_stem()
            .map(|stem| stem.to_string_lossy().into_owned())
            .unwrap_or_else(|| "Unicode".to_string());
        let sanitized: String = stem
            .chars()
            .filter(|character| character.is_ascii_alphanumeric())
            .collect();
        format!(
            "OFM{}",
            if sanitized.is_empty() {
                "Unicode"
            } else {
                &sanitized
            }
        )
    }

    pub(crate) fn bbox_1000(&self) -> [i32; 4] {
        self.bbox
    }

    pub(crate) fn ascender_1000(&self) -> i32 {
        self.ascender.round() as i32
    }

    pub(crate) fn descender_1000(&self) -> i32 {
        self.descender.round() as i32
    }

    pub(crate) fn cap_height_1000(&self) -> i32 {
        // ttf-parser 0.25 does not expose OS/2 cap height; 70 % of the em is a
        // documented approximation for the descriptor only.
        (self.units_per_em * 0.7).round() as i32
    }

    pub(crate) fn glyph_info(&self, character: char) -> Option<GlyphInfo> {
        if let Some(cached) = self.cache.borrow().get(&character).copied() {
            return cached;
        }
        let info = Face::parse(&self.data, 0).ok().and_then(|face| {
            let gid: GlyphId = face.glyph_index(character)?;
            let advance = face
                .glyph_hor_advance(gid)
                .map(|advance| f32::from(advance) * 1000.0 / self.units_per_em)
                .unwrap_or(0.0);
            Some(GlyphInfo {
                gid: gid.0,
                advance,
            })
        });
        self.cache.borrow_mut().insert(character, info);
        info
    }

    pub(crate) fn covers(&self, text: &str) -> bool {
        text.chars()
            .all(|character| character.is_whitespace() || self.glyph_info(character).is_some())
    }
}

/// A font usable for drawing one block of translated text.
pub(crate) enum DrawFont<'a> {
    /// An embedded TrueType font.
    TrueType(&'a TtfFont),
    /// A base-14 Helvetica face, limited to Windows-1252 text.
    Base14 {
        /// Whether the bold face is used.
        bold: bool,
    },
}

impl DrawFont<'_> {
    /// Width of `text` at `size` points.
    pub(crate) fn width(&self, text: &str, size: f64) -> f64 {
        match self {
            Self::TrueType(font) => {
                text.chars()
                    .map(|character| {
                        font.glyph_info(character)
                            .map(|info| f64::from(info.advance))
                            .unwrap_or(0.0)
                    })
                    .sum::<f64>()
                    * size
                    / 1000.0
            }
            Self::Base14 { bold } => {
                let name = if *bold { "Helvetica-Bold" } else { "Helvetica" };
                text.chars()
                    .map(|character| base14_char_width(name, character))
                    .sum::<f64>()
                    * size
                    / 1000.0
            }
        }
    }

    /// Distance from the baseline to the top of the text box at `size`.
    pub(crate) fn ascent(&self, size: f64) -> f64 {
        match self {
            Self::TrueType(font) => f64::from(font.ascender) * size / 1000.0,
            Self::Base14 { .. } => 0.718 * size,
        }
    }

    /// Encode `text` for a `Tj` operator, or `None` when a glyph is missing.
    pub(crate) fn encode(&self, text: &str) -> Option<Vec<u16>> {
        match self {
            Self::TrueType(font) => text
                .chars()
                .map(|character| font.glyph_info(character).map(|info| info.gid))
                .collect(),
            Self::Base14 { .. } => encoding::encode_win_ansi(text)
                .map(|bytes| bytes.into_iter().map(u16::from).collect()),
        }
    }

    /// Whether codes are two-byte CIDs (TrueType) rather than WinAnsi bytes.
    pub(crate) fn two_byte(&self) -> bool {
        matches!(self, Self::TrueType(_))
    }

    /// The underlying TrueType font, when the face is embedded.
    pub(crate) fn true_type(&self) -> Option<&TtfFont> {
        match self {
            Self::TrueType(font) => Some(font),
            Self::Base14 { .. } => None,
        }
    }
}

fn base14_char_width(name: &str, character: char) -> f64 {
    let mut buffer = [0u8; 4];
    let slice = character.encode_utf8(&mut buffer);
    match encoding::encode_win_ansi(slice) {
        Some(bytes) => bytes
            .first()
            .map(|byte| base14_width(name, u32::from(*byte)))
            .unwrap_or(556.0),
        None => 556.0,
    }
}

/// Lazily loaded fonts, one per role.
pub(crate) struct FontBook {
    regular: Option<TtfFont>,
    bold: Option<TtfFont>,
    cjk: Option<TtfFont>,
    regular_searched: bool,
    bold_searched: bool,
    cjk_searched: bool,
}

impl FontBook {
    pub(crate) fn new() -> Self {
        Self {
            regular: None,
            bold: None,
            cjk: None,
            regular_searched: false,
            bold_searched: false,
            cjk_searched: false,
        }
    }

    /// Choose a drawing font for `text`.
    ///
    /// Returns `None` when the text needs a Unicode or CJK face and no system
    /// font covers every character; the caller keeps the original text then
    /// instead of drawing missing-glyph boxes.
    pub(crate) fn choose(&mut self, text: &str, bold: bool) -> Option<DrawFont<'_>> {
        if has_cjk(text) {
            if !self.cjk_searched {
                self.cjk = cjk_font_path().and_then(|path| TtfFont::load(&path));
                self.cjk_searched = true;
            }
            let font = self.cjk.as_ref()?;
            return if font.covers(text) {
                Some(DrawFont::TrueType(font))
            } else {
                None
            };
        }
        if encoding::encode_win_ansi(text).is_some() {
            return Some(DrawFont::Base14 { bold });
        }
        let slot = if bold {
            &mut self.bold
        } else {
            &mut self.regular
        };
        let searched = if bold {
            &mut self.bold_searched
        } else {
            &mut self.regular_searched
        };
        if !*searched {
            *slot = system_font_path(bold).and_then(|path| TtfFont::load(&path));
            *searched = true;
        }
        let font = slot.as_ref()?;
        if font.covers(text) {
            Some(DrawFont::TrueType(font))
        } else {
            None
        }
    }
}

/// Whether the text contains Hangul, kana or Han characters.
pub(crate) fn has_cjk(text: &str) -> bool {
    text.chars().any(|character| {
        matches!(
            character as u32,
            0x1100..=0x11ff
                | 0x3040..=0x30ff
                | 0x3130..=0x318f
                | 0x31f0..=0x31ff
                | 0x3400..=0x4dbf
                | 0x4e00..=0x9fff
                | 0xac00..=0xd7af
                | 0xf900..=0xfaff
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn string_width(name: &str, text: &str, size: f64) -> f64 {
        text.chars()
            .map(|character| base14_char_width(name, character))
            .sum::<f64>()
            * size
            / 1000.0
    }

    #[test]
    fn times_roman_uses_afm_widths() {
        // AFM: H=722, e=444, l=278, l=278, o=500 -> 26.664 pt at 12 pt.
        let hello = string_width("Times-Roman", "Hello", 12.0);
        assert!((hello - 26.664).abs() < 0.01, "{hello}");
        // The Python reference measures this line as 161.93 pt at 11 pt.
        let line = string_width("Times-Roman", "A line in Times Roman on page one.", 11.0);
        assert!((line - 161.931).abs() < 0.05, "{line}");
        // Helvetica metrics must not leak into Times.
        let helvetica = string_width("Helvetica", "A line in Times Roman on page one.", 11.0);
        assert!((helvetica - line).abs() > 10.0);
    }

    #[test]
    fn families_have_their_own_default_widths() {
        assert_eq!(base14_width("Times-Roman", 0), 500.0);
        assert_eq!(base14_width("Times-BoldItalic", 0), 500.0);
        assert_eq!(base14_width("Helvetica", 0), 556.0);
        assert_eq!(base14_width("Helvetica-Bold", 0), 556.0);
        assert_eq!(base14_width("Courier", 65), 600.0);
        assert_eq!(base14_width("Courier-BoldOblique", 0), 600.0);
        assert_eq!(base14_width("Symbol", 65), 600.0);
        assert_eq!(base14_width("ZapfDingbats", 65), 600.0);
    }

    #[test]
    fn every_standard_face_has_a_positive_width_for_every_winansi_code() {
        for name in [
            "Helvetica",
            "Helvetica-Bold",
            "Helvetica-Oblique",
            "Helvetica-BoldOblique",
            "Times-Roman",
            "Times-Bold",
            "Times-Italic",
            "Times-BoldItalic",
            "Courier",
            "Courier-Bold",
            "I Helvetica",
        ] {
            let name = if name == "I Helvetica" {
                "Helvetica"
            } else {
                name
            };
            for code in 32..=255u32 {
                assert!(
                    base14_width(name, code) > 0.0,
                    "{name} has no width for code {code}"
                );
            }
        }
    }

    #[test]
    fn italic_and_oblique_variants_are_selected() {
        assert_eq!(
            base14_width("Times-Italic", u32::from(b'A')),
            base14_width("Times-Italic", u32::from(b'A'))
        );
        assert_ne!(
            base14_width("Times-Italic", u32::from(b'A')),
            base14_width("Times-Roman", u32::from(b'A'))
        );
        assert_eq!(
            base14_width("Helvetica-Oblique", u32::from(b'A')),
            base14_width("Helvetica", u32::from(b'A'))
        );
    }
}
