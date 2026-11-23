//! File kinds the document engine can open, translate and write back.

use std::path::Path;

/// A document format supported by [`crate::DocumentTranslator`].
///
/// Mirrors `DocumentKind` in `windows/deepl_ofm/services/documents.py`.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum DocumentKind {
    /// Plain text (`.txt`, `.text`).
    Text,
    /// Markdown (`.md`, `.markdown`, `.mdown`).
    Markdown,
    /// Portable Document Format (`.pdf`).
    Pdf,
    /// WordprocessingML package (`.docx`).
    Docx,
}

impl DocumentKind {
    /// Detect the kind from a file path, ignoring case.
    ///
    /// Returns `None` for unknown or missing extensions.
    pub fn from_path(path: &Path) -> Option<Self> {
        let extension = path.extension()?.to_str()?.to_ascii_lowercase();
        match extension.as_str() {
            "txt" | "text" => Some(Self::Text),
            "md" | "markdown" | "mdown" => Some(Self::Markdown),
            "pdf" => Some(Self::Pdf),
            "docx" => Some(Self::Docx),
            _ => None,
        }
    }

    /// Canonical lower-case extension, without the dot (as in the Python port).
    pub const fn value(self) -> &'static str {
        match self {
            Self::Text => "txt",
            Self::Markdown => "md",
            Self::Pdf => "pdf",
            Self::Docx => "docx",
        }
    }

    /// File-dialog glob for this kind (`*.txt`, `*.pdf`, ...).
    pub const fn pattern(self) -> &'static str {
        match self {
            Self::Text => "*.txt",
            Self::Markdown => "*.md",
            Self::Pdf => "*.pdf",
            Self::Docx => "*.docx",
        }
    }

    /// Short label shown in the file card, matching the Python UI.
    pub const fn label(self) -> &'static str {
        match self {
            Self::Text => "TXT",
            Self::Markdown => "Markdown",
            Self::Pdf => "PDF",
            Self::Docx => "DOCX",
        }
    }
}
