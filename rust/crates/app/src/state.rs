//! Application state snapshots and events.
//!
//! The UI never touches the controller's interior: it asks for an [`AppState`]
//! snapshot and subscribes to [`AppEvent`]s. Both serialise to JSON, so the same
//! types feed the Tauri frontend, the CLI and the tests.

use serde::{Deserialize, Serialize};

use ofm_config::AppSettings;
use ofm_platform::startup::StartupStatus;
use ofm_store::HistoryEntry;

/// Backend connection state shown in the status bar.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum BackendStatus {
    /// Nothing checked yet.
    Unknown,
    /// A probe is running.
    Checking,
    /// The server answered and the configured model exists.
    Connected,
    /// The server did not answer, or the model is missing.
    Failed,
    /// A local model is being warmed up.
    Warming,
}

impl BackendStatus {
    /// Stable wire value.
    pub fn value(self) -> &'static str {
        match self {
            Self::Unknown => "unknown",
            Self::Checking => "checking",
            Self::Connected => "connected",
            Self::Failed => "failed",
            Self::Warming => "warming",
        }
    }
}

/// State of the Files tab.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum FileJobState {
    /// Reading and parsing the document.
    Reading,
    /// Translating paragraphs.
    Translating,
    /// Rebuilding the output file (PDF overlay, DOCX repack).
    Writing,
    /// Finished; `output` holds the staged file.
    Done,
    /// Failed; `message` explains why.
    Failed,
    /// Cancelled by the user.
    Cancelled,
}

impl FileJobState {
    /// Stable wire value.
    pub fn value(self) -> &'static str {
        match self {
            Self::Reading => "reading",
            Self::Translating => "translating",
            Self::Writing => "writing",
            Self::Done => "done",
            Self::Failed => "failed",
            Self::Cancelled => "cancelled",
        }
    }

    /// Whether the job still occupies the tab.
    pub fn is_running(self) -> bool {
        matches!(self, Self::Reading | Self::Translating | Self::Writing)
    }
}

/// One document translation in flight or finished.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FileJob {
    /// Absolute source path.
    pub path: String,
    /// File name shown in the card.
    pub name: String,
    /// `txt`, `md`, `pdf`, `docx`.
    pub kind: String,
    /// Size in bytes.
    pub size: u64,
    /// Lifecycle state.
    pub state: String,
    /// Translated units finished.
    pub completed: usize,
    /// Total translatable units.
    pub total: usize,
    /// 0–100, derived from `completed`/`total`.
    pub percent: u32,
    /// Staged output file (valid when `state == "done"`).
    pub output: Option<String>,
    /// File name of the staged output.
    pub result_name: Option<String>,
    /// Localised failure message.
    pub message: Option<String>,
    /// Paragraphs left in the source language.
    pub warnings: usize,
    /// The fallback provider produced this document.
    pub fallback: bool,
    /// Human label of the fallback provider and model.
    pub fallback_label: String,
    /// Save error shown inside the result card.
    pub save_error: Option<String>,
}

impl FileJob {
    /// Start a job for a path that is about to be read.
    pub fn new(path: &std::path::Path, kind: &str, size: u64) -> Self {
        Self {
            path: path.to_string_lossy().into_owned(),
            name: path
                .file_name()
                .map(|name| name.to_string_lossy().into_owned())
                .unwrap_or_default(),
            kind: kind.to_string(),
            size,
            state: FileJobState::Reading.value().to_string(),
            ..Self::default()
        }
    }

    /// Recompute `percent` from the counters.
    pub fn refresh_percent(&mut self) {
        self.percent = if self.total == 0 {
            0
        } else {
            ((self.completed as f64 / self.total as f64) * 100.0).round() as u32
        };
    }
}

/// State of the Write tab.
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WriteState {
    /// A rewrite request is running.
    pub in_progress: bool,
    /// Improved text.
    pub output: String,
    /// Localised failure message.
    pub error: Option<String>,
    /// Language detected for the draft when the user did not pick one.
    pub detected_code: Option<String>,
    /// Round-trip duration.
    pub duration_ms: Option<u64>,
    /// Paragraphs the model left in the original language.
    pub warnings: usize,
}

/// Everything the frontend renders, in one serialisable snapshot.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct AppState {
    /// Active tab: `translate`, `files`, `write`, `history`.
    pub tab: String,
    /// Text being translated.
    pub source_text: String,
    /// Translation result.
    pub translated_text: String,
    /// A translation job is running.
    pub is_translating: bool,
    /// Units finished.
    pub completed: usize,
    /// Units in total.
    pub total: usize,
    /// Lines left in the source language.
    pub warning_count: usize,
    /// Localised error shown in the status bar.
    pub error_message: Option<String>,
    /// Selected source language code (`auto` included).
    pub source_language: String,
    /// Selected target language code.
    pub target_language: String,
    /// Detected source language when `source_language == "auto"`.
    pub detected_language: Option<String>,
    /// `auto`, `literal`, `natural`.
    pub style: String,
    /// `standard`, `formal`, `casual`.
    pub tone: String,
    /// `preview`, `text`, `markdown`.
    pub result_view: String,
    /// Backend status value.
    pub backend_status: String,
    /// Human message for the status bar.
    pub probe_message: String,
    /// Models the server offers.
    pub provider_models: Vec<String>,
    /// A model list request is running.
    pub models_loading: bool,
    /// Localised model-list error.
    pub models_error: Option<String>,
    /// Fallback provider models.
    pub fallback_models: Vec<String>,
    /// A fallback model-list request is running.
    pub fallback_models_loading: bool,
    /// Localised fallback model-list error.
    pub fallback_models_error: Option<String>,
    /// The last translation came from the fallback provider.
    pub using_fallback: bool,
    /// Tokens per second of the last translation.
    pub tokens_per_second: Option<f64>,
    /// Duration of the last translation.
    pub last_duration_ms: Option<u64>,
    /// `source`, `translation` or empty while not speaking.
    pub speaking: String,
    /// Status of the clipboard hotkey (empty when it works).
    pub hotkey_message: String,
    /// Status of the selection hotkey (empty when it works).
    pub selection_hotkey_message: String,
    /// "Open at login" status: `enabled`, `disabled`, `requiresApproval` or
    /// `unsupported`.
    pub login_item_status: String,
    /// Localised failure from the last "Open at login" change.
    pub login_item_error: Option<String>,
    /// Files tab job.
    pub file_job: Option<FileJob>,
    /// Write tab state.
    pub write: WriteState,
    /// History entries, newest first.
    pub history: Vec<HistoryEntry>,
    /// The history file could not be read or written.
    pub history_error: bool,
    /// Current settings.
    pub settings: AppSettings,
    /// Application version.
    pub version: String,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            tab: "translate".to_string(),
            source_text: String::new(),
            translated_text: String::new(),
            is_translating: false,
            completed: 0,
            total: 0,
            warning_count: 0,
            error_message: None,
            source_language: "auto".to_string(),
            target_language: "en".to_string(),
            detected_language: None,
            style: "auto".to_string(),
            tone: "standard".to_string(),
            result_view: "preview".to_string(),
            backend_status: BackendStatus::Unknown.value().to_string(),
            probe_message: String::new(),
            provider_models: Vec::new(),
            models_loading: false,
            models_error: None,
            fallback_models: Vec::new(),
            fallback_models_loading: false,
            fallback_models_error: None,
            using_fallback: false,
            tokens_per_second: None,
            last_duration_ms: None,
            speaking: String::new(),
            hotkey_message: String::new(),
            selection_hotkey_message: String::new(),
            login_item_status: StartupStatus::Disabled.value().to_string(),
            login_item_error: None,
            file_job: None,
            write: WriteState::default(),
            history: Vec::new(),
            history_error: false,
            settings: AppSettings::default(),
            version: env!("CARGO_PKG_VERSION").to_string(),
        }
    }
}

/// A state change the UI must react to.
///
/// Serialised as `{"type": "progress", "completed": 1, "total": 3}`. Payload
/// variants carry their value in a field named `value`, so the frontend can
/// treat unknown events as a hint to fetch a fresh [`AppState`].
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "camelCase")]
pub enum AppEvent {
    /// The whole state changed; refetch it.
    StateChanged,
    /// Translation progress.
    Progress {
        /// Units finished.
        completed: usize,
        /// Units in total.
        total: usize,
    },
    /// A translation job started or stopped.
    Translating {
        /// Whether a job is running.
        value: bool,
    },
    /// The translation text changed.
    TranslatedText {
        /// The new translation.
        value: String,
    },
    /// The source text changed.
    SourceText {
        /// The new source text.
        value: String,
    },
    /// The language pair changed.
    Languages {
        /// Source code.
        source: String,
        /// Target code.
        target: String,
    },
    /// The detected source language changed (empty when unknown).
    Detected {
        /// The detected code, or an empty string.
        value: String,
    },
    /// A user-facing error for the status bar.
    Error {
        /// Localised message.
        value: String,
    },
    /// The translation job failed.
    TranslationFailed {
        /// Localised message.
        value: String,
    },
    /// Backend status changed.
    BackendStatus {
        /// One of `unknown`, `checking`, `connected`, `failed`, `warming`.
        value: String,
    },
    /// Probe message changed.
    ProbeMessage {
        /// Localised message.
        value: String,
    },
    /// The server model list arrived.
    Models {
        /// Model identifiers.
        value: Vec<String>,
    },
    /// A model list request started or stopped.
    ModelsLoading {
        /// Whether a request is running.
        value: bool,
    },
    /// The model list request failed.
    ModelsError {
        /// Localised message.
        value: String,
    },
    /// The fallback model list arrived.
    FallbackModels {
        /// Model identifiers.
        value: Vec<String>,
    },
    /// A fallback model list request started or stopped.
    FallbackModelsLoading {
        /// Whether a request is running.
        value: bool,
    },
    /// The fallback model list request failed.
    FallbackModelsError {
        /// Localised message.
        value: String,
    },
    /// Settings changed.
    Settings {
        /// The new settings.
        value: Box<AppSettings>,
    },
    /// The interface language changed.
    InterfaceLanguage {
        /// The new language code.
        value: String,
    },
    /// The active tab changed.
    Tab {
        /// One of `translate`, `files`, `write`, `history`.
        value: String,
    },
    /// The "Open at login" status changed.
    LoginItem {
        /// One of `enabled`, `disabled`, `requiresApproval`, `unsupported`.
        value: String,
    },
    /// History changed.
    History,
    /// The Files job changed.
    FileJob {
        /// The current job.
        value: Box<FileJob>,
    },
    /// A short confirmation ("Translation copied").
    CopyFeedback {
        /// Localised message.
        value: String,
    },
    /// Tokens/second or duration changed.
    Metrics,
    /// Speech started or stopped (`source`, `translation`, or empty).
    Speaking {
        /// The pane being read aloud.
        value: String,
    },
    /// The style changed.
    Style {
        /// The style value.
        value: String,
    },
    /// The tone changed.
    Tone {
        /// The tone value.
        value: String,
    },
    /// The result view mode changed.
    ResultView {
        /// `preview`, `text` or `markdown`.
        value: String,
    },
    /// The Write tab changed.
    Write {
        /// The current write state.
        value: Box<WriteState>,
    },
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Every variant must survive JSON serialisation.
    ///
    /// This is a regression guard: an internally tagged enum cannot serialise a
    /// newtype variant wrapping a primitive, and the failure is silent at
    /// runtime (the event is simply dropped), so a test is the only way to catch
    /// a payload that regresses to `Variant(String)`.
    #[test]
    fn every_event_serialises() {
        ofm_i18n::set_language(ofm_i18n::AppLanguage::En);
        let events = vec![
            AppEvent::StateChanged,
            AppEvent::Progress {
                completed: 1,
                total: 3,
            },
            AppEvent::Translating { value: true },
            AppEvent::TranslatedText {
                value: "text".to_string(),
            },
            AppEvent::SourceText {
                value: "source".to_string(),
            },
            AppEvent::Languages {
                source: "en".to_string(),
                target: "uk".to_string(),
            },
            AppEvent::Detected {
                value: "en".to_string(),
            },
            AppEvent::Error {
                value: "boom".to_string(),
            },
            AppEvent::TranslationFailed {
                value: "boom".to_string(),
            },
            AppEvent::BackendStatus {
                value: "connected".to_string(),
            },
            AppEvent::ProbeMessage {
                value: "ok".to_string(),
            },
            AppEvent::Models {
                value: vec!["hy-mt2:7b".to_string()],
            },
            AppEvent::ModelsLoading { value: false },
            AppEvent::ModelsError {
                value: "nope".to_string(),
            },
            AppEvent::FallbackModels { value: vec![] },
            AppEvent::FallbackModelsLoading { value: true },
            AppEvent::FallbackModelsError {
                value: "nope".to_string(),
            },
            AppEvent::Settings {
                value: Box::new(AppSettings::default()),
            },
            AppEvent::InterfaceLanguage {
                value: "uk".to_string(),
            },
            AppEvent::Tab {
                value: "files".to_string(),
            },
            AppEvent::History,
            AppEvent::LoginItem {
                value: "enabled".to_string(),
            },
            AppEvent::FileJob {
                value: Box::new(FileJob::default()),
            },
            AppEvent::CopyFeedback {
                value: "copied".to_string(),
            },
            AppEvent::Metrics,
            AppEvent::Speaking {
                value: "source".to_string(),
            },
            AppEvent::Style {
                value: "auto".to_string(),
            },
            AppEvent::Tone {
                value: "formal".to_string(),
            },
            AppEvent::ResultView {
                value: "preview".to_string(),
            },
            AppEvent::Write {
                value: Box::new(WriteState::default()),
            },
        ];

        for event in events {
            let json = serde_json::to_value(&event)
                .unwrap_or_else(|error| panic!("{event:?} does not serialise: {error}"));
            assert!(
                json.get("type").and_then(|value| value.as_str()).is_some(),
                "{event:?} has no `type` tag: {json}"
            );
        }
    }

    /// The snapshot the frontend renders must be JSON with camelCase keys.
    #[test]
    fn state_snapshot_is_camel_case_json() {
        ofm_i18n::set_language(ofm_i18n::AppLanguage::En);
        let json = serde_json::to_value(AppState::default()).expect("serialise");
        for key in [
            "sourceText",
            "translatedText",
            "isTranslating",
            "sourceLanguage",
            "resultView",
            "backendStatus",
            "fileJob",
            "write",
            "history",
            "settings",
        ] {
            assert!(json.get(key).is_some(), "missing {key} in {json}");
        }
        assert!(json["settings"].get("interfaceLanguage").is_some());
    }
}
