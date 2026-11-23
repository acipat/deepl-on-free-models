//! Typed transport failures and their localised, user-facing messages.

use ofm_i18n::{t, tf};

/// Machine-readable failure class.
///
/// The variants mirror the Python `TranslationError.kind` strings one to one,
/// so callers can branch on the transport failure instead of parsing text.
#[derive(Clone, Copy, PartialEq, Eq, Debug, Hash)]
pub enum ErrorKind {
    /// The server could not be reached (DNS, refused connection, timeout).
    Connection,
    /// The configured server URL is not an absolute HTTP(S) URL.
    InvalidUrl,
    /// Any other non-success HTTP status.
    Http,
    /// The provider rejected the credentials (401/403, or a missing API key).
    Unauthorized,
    /// The provider is rate limiting (429).
    RateLimit,
    /// The provider is temporarily unavailable (5xx).
    Server,
    /// No model is selected, or the selected model is unknown.
    Model,
    /// The response ended before its terminal frame.
    Interrupted,
    /// The response could not be understood.
    Unexpected,
    /// The model produced nothing usable for a block.
    Empty,
    /// The caller set the cancel flag.
    Cancelled,
}

/// A provider or transport failure.
///
/// `detail` carries protocol specific context that is used by [`Self::message`]
/// to build the localised sentence shown in the UI: the server address for
/// connection problems, the model id for a missing model, `"api_key"` for a
/// missing key, the `Retry-After` value for a 429, or the reason for a
/// degenerate response.
#[derive(Debug, thiserror::Error)]
#[error("{kind:?}: {detail}")]
pub struct TranslationError {
    /// Failure class.
    pub kind: ErrorKind,
    /// HTTP status when the failure came from a response.
    pub status: Option<u16>,
    /// Protocol specific context, empty when there is none.
    pub detail: String,
}

impl TranslationError {
    /// Create a failure without status or detail.
    pub fn new(kind: ErrorKind) -> Self {
        Self {
            kind,
            status: None,
            detail: String::new(),
        }
    }

    /// Create a failure carrying the HTTP status that caused it.
    pub fn with_status(kind: ErrorKind, status: u16) -> Self {
        Self {
            kind,
            status: Some(status),
            detail: String::new(),
        }
    }

    /// Attach protocol context (server address, model id, …).
    pub fn with_detail(mut self, detail: impl Into<String>) -> Self {
        self.detail = detail.into();
        self
    }

    /// Localised, user-facing text.
    ///
    /// English keys are the Swift originals; other languages come from the
    /// `ofm-i18n` catalogue. An unknown key falls back to English.
    pub fn message(&self) -> String {
        match self.kind {
            ErrorKind::InvalidUrl => tf("Invalid server URL: %@", &[&self.detail]),
            ErrorKind::Model => {
                if self.detail.is_empty() {
                    t("Choose a model in Settings.").to_string()
                } else {
                    tf("Model “%@” not found on the server.", &[&self.detail])
                }
            }
            ErrorKind::Connection => tf(
                "Could not connect to %@. Check that the server is running.",
                &[&self.detail],
            ),
            ErrorKind::Unauthorized => {
                if self.detail == "api_key" {
                    t("Add your API key in Settings.").to_string()
                } else {
                    t("The provider rejected the request. \
                       Check the API key and model in Settings.")
                    .to_string()
                }
            }
            ErrorKind::RateLimit => {
                t("Too many requests. Wait a moment and try again.").to_string()
            }
            ErrorKind::Server => {
                t("The provider is temporarily unavailable. Try again.").to_string()
            }
            ErrorKind::Empty => {
                t("The model returned an empty translation. Try again.").to_string()
            }
            ErrorKind::Interrupted => {
                t("The server interrupted the response. Try again.").to_string()
            }
            ErrorKind::Unexpected => {
                t("The model could not translate this text. Try again or choose another model.")
                    .to_string()
            }
            ErrorKind::Cancelled => t("Translation cancelled.").to_string(),
            ErrorKind::Http => match self.status {
                None => t("The provider rejected the request. \
                           Check the API key and model in Settings.")
                .to_string(),
                Some(400 | 401 | 403 | 422) => t("The provider rejected the request. \
                     Check the API key and model in Settings.")
                .to_string(),
                Some(status) if (500..=599).contains(&status) => {
                    t("The provider is temporarily unavailable. Try again.").to_string()
                }
                Some(status) => tf("Server returned error %@.", &[&status]),
            },
        }
    }
}

/// Map an HTTP status to the documented [`ErrorKind`].
///
/// 401/403 become [`ErrorKind::Unauthorized`], 429 [`ErrorKind::RateLimit`],
/// 5xx [`ErrorKind::Server`] and everything else [`ErrorKind::Http`].
pub(crate) fn http_error(status: u16, detail: &str) -> TranslationError {
    let kind = match status {
        401 | 403 => ErrorKind::Unauthorized,
        429 => ErrorKind::RateLimit,
        500..=599 => ErrorKind::Server,
        _ => ErrorKind::Http,
    };
    TranslationError::with_status(kind, status).with_detail(detail)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ofm_i18n::{set_language, AppLanguage};

    fn english() -> std::sync::MutexGuard<'static, ()> {
        // The interface language is process global; keep the assertions stable
        // even if another test switches it.
        static LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());
        let guard = LOCK.lock().unwrap_or_else(|error| error.into_inner());
        set_language(AppLanguage::En);
        guard
    }

    #[test]
    fn statuses_map_to_the_documented_kinds() {
        assert_eq!(http_error(401, "").kind, ErrorKind::Unauthorized);
        assert_eq!(http_error(403, "").kind, ErrorKind::Unauthorized);
        assert_eq!(http_error(429, "").kind, ErrorKind::RateLimit);
        assert_eq!(http_error(500, "").kind, ErrorKind::Server);
        assert_eq!(http_error(503, "").kind, ErrorKind::Server);
        assert_eq!(http_error(400, "").kind, ErrorKind::Http);
        assert_eq!(http_error(404, "").kind, ErrorKind::Http);
        assert_eq!(http_error(429, "").status, Some(429));
    }

    #[test]
    fn display_contains_the_kind_and_detail() {
        let error = TranslationError::with_status(ErrorKind::Server, 503).with_detail("busy");
        assert_eq!(error.to_string(), "Server: busy");
    }

    #[test]
    fn messages_are_localised_english_sentences() {
        let _guard = english();
        assert_eq!(
            TranslationError::new(ErrorKind::Model).message(),
            "Choose a model in Settings."
        );
        assert_eq!(
            TranslationError::new(ErrorKind::Model)
                .with_detail("hy-mt2")
                .message(),
            "Model “hy-mt2” not found on the server."
        );
        assert_eq!(
            TranslationError::new(ErrorKind::Unauthorized)
                .with_detail("api_key")
                .message(),
            "Add your API key in Settings."
        );
        assert_eq!(
            TranslationError::with_status(ErrorKind::RateLimit, 429).message(),
            "Too many requests. Wait a moment and try again."
        );
        assert_eq!(
            TranslationError::with_status(ErrorKind::Http, 418).message(),
            "Server returned error 418."
        );
        assert_eq!(
            TranslationError::new(ErrorKind::InvalidUrl)
                .with_detail("not a url")
                .message(),
            "Invalid server URL: not a url"
        );
        assert_eq!(
            TranslationError::new(ErrorKind::Cancelled).message(),
            "Translation cancelled."
        );
    }

    #[test]
    fn http_message_uses_the_status_family() {
        let _guard = english();
        let rejected = TranslationError::with_status(ErrorKind::Http, 422).message();
        assert!(rejected.contains("rejected the request"), "{rejected}");
        let unavailable = TranslationError::with_status(ErrorKind::Http, 503).message();
        assert!(
            unavailable.contains("temporarily unavailable"),
            "{unavailable}"
        );
        let generic = TranslationError::new(ErrorKind::Http).message();
        assert!(generic.contains("rejected the request"), "{generic}");
    }
}
