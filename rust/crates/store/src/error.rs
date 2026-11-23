//! Internal error type shared by the history and secret stores.
//!
//! The public API of this crate is deliberately infallible: a broken history
//! file or an unavailable secret backend must never take the application down.
//! These errors only travel between internal helpers and the `log` macros.

use std::io;

/// A failure while reading, encoding or replacing a store file.
#[derive(Debug, thiserror::Error)]
pub(crate) enum StoreError {
    /// The file could not be read, created, written or renamed.
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),
    /// The in-memory document could not be serialised.
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    /// A base64-encoded secret could not be decoded.
    #[error("base64 error: {0}")]
    Base64(#[from] base64::DecodeError),
    /// The platform credential store reported a failure.
    #[error("backend error: {0}")]
    Backend(String),
    /// The requested mechanism does not exist on this platform.
    #[error("{0} is not available on this platform")]
    Unsupported(&'static str),
}

impl StoreError {
    /// Wrap a message from a platform credential store.
    pub(crate) fn backend(message: impl Into<String>) -> Self {
        Self::Backend(message.into())
    }
}
