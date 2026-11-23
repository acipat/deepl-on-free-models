//! Typed document failures and their localised messages.

use ofm_i18n::{current_language, t_in};

/// Why a document operation failed.
///
/// The variants mirror the string `kind`s of the Python `DocumentError`.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DocumentErrorKind {
    /// The extension is not one of the supported document formats.
    Unsupported,
    /// The file contains no selectable text (blank file, scanned PDF, ...).
    NoText,
    /// The file could not be opened or parsed.
    Unreadable,
    /// The translated document could not be written.
    WriteFailed,
    /// The PDF is encrypted; no password is ever requested.
    Encrypted,
    /// The caller's cancellation flag was set between paragraphs.
    Cancelled,
}

impl DocumentErrorKind {
    /// English catalogue key used for [`DocumentError::message`].
    pub(crate) const fn key(self) -> &'static str {
        match self {
            Self::Unsupported => "This file type is not supported.",
            Self::NoText => {
                "No selectable text found. For a scanned PDF, run text recognition first."
            }
            Self::Unreadable => "The file could not be read.",
            Self::WriteFailed => "The file could not be translated.",
            Self::Encrypted => "The PDF is password-protected and cannot be translated.",
            Self::Cancelled => "Cancelled",
        }
    }
}

/// A document could not be read, translated or written.
#[derive(Debug, thiserror::Error)]
#[error("{kind:?}: {detail}")]
pub struct DocumentError {
    /// Machine-readable failure class.
    pub kind: DocumentErrorKind,
    /// Technical description; never shown to the user as-is.
    pub detail: String,
}

impl DocumentError {
    /// Build an error with a technical detail.
    pub(crate) fn new(kind: DocumentErrorKind, detail: impl Into<String>) -> Self {
        Self {
            kind,
            detail: detail.into(),
        }
    }

    /// Build an error without a detail.
    pub(crate) fn simple(kind: DocumentErrorKind) -> Self {
        Self::new(kind, kind.key())
    }

    /// Localised, user-facing explanation.
    ///
    /// Word processing failures carry a `docx:` detail prefix, which selects the
    /// Word-specific sentence from the catalogue; every other failure uses the
    /// sentence for its kind (exactly like `DocumentError.message()` in Python).
    pub fn message(&self) -> String {
        let key = if self.detail.starts_with("docx:")
            && matches!(
                self.kind,
                DocumentErrorKind::Unreadable | DocumentErrorKind::WriteFailed
            ) {
            "The Word document could not be processed."
        } else {
            self.kind.key()
        };
        t_in(key, current_language()).to_string()
    }
}

/// Build an `Unreadable` error.
pub(crate) fn unreadable(detail: impl Into<String>) -> DocumentError {
    DocumentError::new(DocumentErrorKind::Unreadable, detail)
}

/// Build a `WriteFailed` error.
pub(crate) fn write_failed(detail: impl Into<String>) -> DocumentError {
    DocumentError::new(DocumentErrorKind::WriteFailed, detail)
}

/// Build an error attributed to DOCX processing.
pub(crate) fn docx_error(kind: DocumentErrorKind, detail: impl std::fmt::Display) -> DocumentError {
    DocumentError::new(kind, format!("docx: {detail}"))
}
