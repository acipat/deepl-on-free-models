//! Application controller: the state machine the UI drives.
//!
//! Ported from `windows/deepl_ofm/controller.py`, including the fixes that came
//! out of its code review:
//!
//! * every job carries a **generation counter**, and a late result from an older
//!   generation is dropped instead of overwriting newer state;
//! * the previous job is cancelled **before** its cancel flag is replaced;
//! * workers never mutate shared state directly — they send [`AppEvent`]s and the
//!   controller applies them on its own thread of control;
//! * the translation cache key includes the style, the tone and the model;
//! * `clear_source` resets text, translation, metrics, detection and warnings;
//! * a failed request marks the backend `failed`; a missing model after Connect
//!   is a failure, not "connected";
//! * warm-up only runs for local providers (a cloud request at launch costs
//!   money).

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};

use log::{debug, info, warn};
use serde_json::{json, Value};
use tokio::runtime::Runtime;

use ofm_config::{AppSettings, CatalogEntry, ModelCatalog, Provider};
use ofm_docs::{DocumentKind, DocumentTranslator};
use ofm_i18n::{t, t_in, AppLanguage, Language, LanguageTable};
use ofm_net::{CancelFlag, Translator};
use ofm_platform::speech::Speaker;
use ofm_store::{HistoryEntry, HistoryStore, SecretStore};
use ofm_text::{PromptBuilder, TranslationStyle, TranslationTone};

use crate::state::{AppEvent, AppState, BackendStatus, FileJob, FileJobState, WriteState};

/// Upper bound for the translated-text cache: one entry is enough.
type CacheKey = (String, String, String, String, String, String);

/// Everything the controller owns. Cloned as an `Arc` into every job.
struct Inner {
    runtime: Runtime,
    settings: RwLock<AppSettings>,
    state: RwLock<AppState>,
    history: HistoryStore,
    secrets: SecretStore,
    translator: Arc<Translator>,
    events: tokio::sync::broadcast::Sender<AppEvent>,
    speaker: Mutex<Speaker>,

    // translate tab
    cancel: Mutex<Option<CancelFlag>>,
    generation: AtomicU64,
    debounce: AtomicU64,
    cache: Mutex<Option<CacheKey>>,

    // files tab
    file_cancel: Mutex<Option<CancelFlag>>,
    file_generation: AtomicU64,
    file_staging: Mutex<Option<PathBuf>>,

    // write tab
    write_cancel: Mutex<Option<CancelFlag>>,
    write_generation: AtomicU64,

    /// Where settings are persisted; `None` means the platform default.
    settings_path: Option<PathBuf>,
}

/// The single entry point every frontend uses.
#[derive(Clone)]
pub struct AppController {
    inner: Arc<Inner>,
}

impl AppController {
    /// Create the controller: loads settings and history, starts the async
    /// runtime and prepares the translator.
    pub fn new() -> Self {
        Self::build(None)
    }

    /// Controller whose settings, history and secrets live in `directory`.
    ///
    /// Tests use this so they never read or write the real user profile (which
    /// is read-only in a sandbox, making key storage silently fail).
    pub fn with_directory(directory: &Path) -> Self {
        Self::build(Some(directory.to_path_buf()))
    }

    fn build(directory: Option<PathBuf>) -> Self {
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .thread_name("ofm-worker")
            .build()
            .expect("could not start the DeepL-oFM worker runtime");

        let settings_path = directory
            .as_ref()
            .map(|dir| dir.join("settings.json"))
            .unwrap_or_else(AppSettings::default_path);
        let mut settings = match &directory {
            Some(_) => AppSettings::load_from(&settings_path),
            None => AppSettings::load(),
        };
        ofm_i18n::set_language(settings.interface_language);

        let history = match &directory {
            Some(dir) => HistoryStore::with_path(dir.join("history.json")),
            None => HistoryStore::new(),
        };
        let secrets = match &directory {
            Some(dir) => SecretStore::with_path(dir.join("secrets.json")),
            None => SecretStore::new(),
        };

        // API keys live in the OS secret store, never in settings.json.
        settings.api_key = secrets.read(&settings.provider.key_account());
        settings.fallback_api_key = secrets.read(&settings.fallback_provider.key_account());

        let initial = AppState {
            source_language: settings.last_source_code.clone(),
            target_language: settings.last_target_code.clone(),
            style: settings.last_style.clone(),
            tone: settings.last_tone.clone(),
            result_view: settings.result_view.clone(),
            history: history.entries(),
            history_error: history.has_storage_error(),
            settings: settings.clone(),
            ..AppState::default()
        };

        // API keys live in the secret store, never in settings.json.
        settings.api_key = secrets.read(&settings.provider.key_account());
        settings.fallback_api_key = secrets.read(&settings.fallback_provider.key_account());

        let (events, _) = tokio::sync::broadcast::channel(256);

        Self {
            inner: Arc::new(Inner {
                runtime,
                settings: RwLock::new(settings),
                state: RwLock::new(initial),
                history,
                secrets,
                translator: Arc::new(Translator::new()),
                events,
                speaker: Mutex::new(Speaker::new()),
                cancel: Mutex::new(None),
                generation: AtomicU64::new(0),
                debounce: AtomicU64::new(0),
                cache: Mutex::new(None),
                file_cancel: Mutex::new(None),
                file_generation: AtomicU64::new(0),
                file_staging: Mutex::new(None),
                write_cancel: Mutex::new(None),
                write_generation: AtomicU64::new(0),
                settings_path: directory.map(|dir| dir.join("settings.json")),
            }),
        }
    }

    // ------------------------------------------------------------- plumbing

    fn state_guard(&self) -> std::sync::RwLockReadGuard<'_, AppState> {
        self.inner
            .state
            .read()
            .unwrap_or_else(|poison| poison.into_inner())
    }

    fn settings(&self) -> std::sync::RwLockReadGuard<'_, AppSettings> {
        self.inner
            .settings
            .read()
            .unwrap_or_else(|poison| poison.into_inner())
    }

    /// Mutate the settings, persist them and mirror the copy the UI renders.
    ///
    /// `AppState::settings` is a snapshot, so every write must update both or the
    /// dialog would show stale values after a chip click.
    fn update_settings(&self, mutate: impl FnOnce(&mut AppSettings)) {
        let snapshot = {
            let mut guard = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|poison| poison.into_inner());
            mutate(&mut guard);
            match &self.inner.settings_path {
                Some(path) => guard.save_to(path),
                None => guard.save(),
            }
            guard.clone()
        };
        let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
        state.settings = snapshot;
    }

    fn emit(&self, event: AppEvent) {
        let _ = self.inner.events.send(event);
    }

    /// Subscribe to state changes. The frontend calls this once.
    pub fn subscribe(&self) -> tokio::sync::broadcast::Receiver<AppEvent> {
        self.inner.events.subscribe()
    }

    /// Full state snapshot for the UI.
    pub fn state_snapshot(&self) -> AppState {
        self.state_guard().clone()
    }

    /// Short alias used by the desktop shell and the CLI.
    pub fn state(&self) -> AppState {
        self.state_snapshot()
    }

    fn set_backend_status(&self, status: BackendStatus, message: impl Into<String>) {
        let message = message.into();
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.backend_status = status.value().to_string();
            state.probe_message = message.clone();
        }
        self.emit(AppEvent::BackendStatus {
            value: status.value().to_string(),
        });
        self.emit(AppEvent::ProbeMessage { value: message });
    }

    fn report_error(&self, message: impl Into<String>) {
        let message = message.into();
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.error_message = Some(message.clone());
        }
        self.emit(AppEvent::Error { value: message });
    }

    // --------------------------------------------------------------- tabs

    /// Switch the active tab.
    pub fn set_tab(&self, tab: &str) {
        if !matches!(tab, "translate" | "files" | "write" | "history") {
            return;
        }
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.tab == tab {
                return;
            }
            state.tab = tab.to_string();
        }
        self.emit(AppEvent::Tab {
            value: tab.to_string(),
        });
    }

    // -------------------------------------------------------- source text

    /// Replace the source text. Cancels a running job and schedules a new one
    /// when automatic translation is enabled.
    pub fn set_source_text(&self, text: &str) {
        let changed = {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.source_text == text {
                return;
            }
            state.source_text = text.to_string();
            if text.trim().is_empty() {
                state.translated_text.clear();
                state.warning_count = 0;
                state.completed = 0;
                state.total = 0;
            }
            true
        };
        if !changed {
            return;
        }

        self.emit(AppEvent::SourceText {
            value: text.to_string(),
        });
        if text.trim().is_empty() {
            self.emit(AppEvent::TranslatedText {
                value: String::new(),
            });
            self.emit(AppEvent::Progress {
                completed: 0,
                total: 0,
            });
        }

        // A result for the previous text must never land in the pane.
        // Read the flags into locals first: `cancel` and `detect_language_now`
        // take the same lock, so holding a guard across the call would deadlock.
        let (translating, auto_source) = {
            let state = self.state_guard();
            (state.is_translating, state.source_language == "auto")
        };
        if translating {
            self.cancel();
        }
        if auto_source {
            self.detect_language_now();
        }
        self.schedule_translation();
    }

    /// Text currently in the source pane.
    pub fn source_text(&self) -> String {
        self.state_guard().source_text.clone()
    }

    /// Current translation.
    pub fn translated_text(&self) -> String {
        self.state_guard().translated_text.clone()
    }

    // ----------------------------------------------------------- languages

    /// Select the source language (`auto` allowed).
    pub fn set_source_language(&self, code: &str) {
        let Some(language) = LanguageTable::get(code) else {
            return;
        };
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.source_language == language.code {
                return;
            }
            state.source_language = language.code.to_string();
            if !language.is_auto() {
                state.detected_language = None;
            }
        }
        let code = language.code.to_string();
        self.update_settings(|settings| settings.last_source_code = code);
        self.emit_languages();
        if language.is_auto() {
            self.detect_language_now();
        }
        self.retranslate_if_possible();
    }

    /// Select the target language.
    pub fn set_target_language(&self, code: &str) {
        let Some(language) = LanguageTable::get(code) else {
            return;
        };
        if language.is_auto() {
            return;
        }
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.target_language == language.code {
                return;
            }
            state.target_language = language.code.to_string();
        }
        let code = language.code.to_string();
        self.update_settings(|settings| settings.last_target_code = code);
        self.emit_languages();
        self.retranslate_if_possible();
    }

    /// Swap the two languages and the two panes, then translate again.
    pub fn swap_languages(&self) {
        let (source, target, source_text, translated) = {
            let state = self.state_guard();
            (
                state.source_language.clone(),
                state.target_language.clone(),
                state.source_text.clone(),
                state.translated_text.clone(),
            )
        };

        let resolved_source = if source == "auto" {
            self.state_guard()
                .detected_language
                .clone()
                .unwrap_or_else(|| "en".to_string())
        } else {
            source
        };
        if resolved_source == target {
            return;
        }

        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.source_language = target.clone();
            state.target_language = resolved_source.clone();
            state.detected_language = None;
            if !translated.trim().is_empty() {
                state.source_text = translated;
                state.translated_text = source_text;
            }
        }
        let (new_source, new_target) = (target.clone(), resolved_source.clone());
        self.update_settings(|settings| {
            settings.last_source_code = new_source;
            settings.last_target_code = new_target;
        });

        let (text, translation) = {
            let state = self.state_guard();
            (state.source_text.clone(), state.translated_text.clone())
        };
        self.emit(AppEvent::SourceText { value: text });
        self.emit(AppEvent::TranslatedText { value: translation });
        self.emit(AppEvent::Detected {
            value: String::new(),
        });
        self.emit_languages();
        self.translate(true);
    }

    fn emit_languages(&self) {
        let state = self.state_guard();
        self.emit(AppEvent::Languages {
            source: state.source_language.clone(),
            target: state.target_language.clone(),
        });
    }

    fn detect_language_now(&self) {
        let text = self.state_guard().source_text.clone();
        let ui = self.settings().interface_language;
        if text.trim().is_empty() {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.detected_language = None;
            drop(state);
            self.emit(AppEvent::Detected {
                value: String::new(),
            });
            return;
        }
        let detected = LanguageTable::detect(&text, ui).map(|language| language.code.to_string());
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.detected_language = detected.clone();
        }
        self.emit(AppEvent::Detected {
            value: detected.unwrap_or_default(),
        });
    }

    /// Language actually used as the source: the selection, or the detection.
    fn resolved_source(&self) -> &'static Language {
        let state = self.state_guard();
        if state.source_language != "auto" {
            if let Some(language) = LanguageTable::get(&state.source_language) {
                return language;
            }
        }
        if let Some(code) = &state.detected_language {
            if let Some(language) = LanguageTable::get(code) {
                return language;
            }
        }
        &LanguageTable::AUTO
    }

    fn target_language(&self) -> &'static Language {
        let state = self.state_guard();
        LanguageTable::get(&state.target_language).unwrap_or(&LanguageTable::AUTO)
    }

    // ------------------------------------------------------- style / tone

    /// Select the translation style.
    pub fn set_style(&self, style: &str) {
        let Some(value) = TranslationStyle::from_value(style) else {
            return;
        };
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.style == value.value() {
                return;
            }
            state.style = value.value().to_string();
        }
        let label = value.value().to_string();
        self.update_settings(|settings| settings.last_style = label);
        self.emit(AppEvent::Style {
            value: value.value().to_string(),
        });
        self.retranslate_if_possible();
    }

    /// Select the translation tone.
    pub fn set_tone(&self, tone: &str) {
        let Some(value) = TranslationTone::from_value(tone) else {
            return;
        };
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.tone == value.value() {
                return;
            }
            state.tone = value.value().to_string();
        }
        let label = value.value().to_string();
        self.update_settings(|settings| settings.last_tone = label);
        self.emit(AppEvent::Tone {
            value: value.value().to_string(),
        });
        self.retranslate_if_possible();
    }

    fn style(&self) -> TranslationStyle {
        TranslationStyle::from_value(&self.state_guard().style).unwrap_or(TranslationStyle::Auto)
    }

    fn tone(&self) -> TranslationTone {
        TranslationTone::from_value(&self.state_guard().tone).unwrap_or(TranslationTone::Standard)
    }

    /// Select the result view mode: `preview`, `text` or `markdown`.
    pub fn set_result_view(&self, mode: &str) {
        if !matches!(mode, "preview" | "text" | "markdown") {
            return;
        }
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if state.result_view == mode {
                return;
            }
            state.result_view = mode.to_string();
        }
        let chosen = mode.to_string();
        self.update_settings(|settings| settings.set_result_view(&chosen));
        self.emit(AppEvent::ResultView {
            value: mode.to_string(),
        });
    }

    // ------------------------------------------------------------ clearing

    /// Clear the source, the translation and every metric.
    pub fn clear_source(&self) {
        self.cancel();
        self.inner.debounce.fetch_add(1, Ordering::SeqCst);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.source_text.clear();
            state.translated_text.clear();
            state.error_message = None;
            state.warning_count = 0;
            state.completed = 0;
            state.total = 0;
            state.detected_language = None;
            state.tokens_per_second = None;
            state.last_duration_ms = None;
            state.using_fallback = false;
        }
        *self.inner.cache.lock().unwrap_or_else(|p| p.into_inner()) = None;

        self.emit(AppEvent::SourceText {
            value: String::new(),
        });
        self.emit(AppEvent::TranslatedText {
            value: String::new(),
        });
        self.emit(AppEvent::Progress {
            completed: 0,
            total: 0,
        });
        self.emit(AppEvent::Detected {
            value: String::new(),
        });
        self.emit(AppEvent::Metrics);
    }

    // ---------------------------------------------------------- scheduling

    fn schedule_translation(&self) {
        // The two locks are never held at the same time: taking them in
        // different orders on different threads deadlocks under `std::RwLock`.
        let text = self.state_guard().source_text.clone();
        let (auto, delay) = {
            let settings = self.settings();
            (settings.auto_translate, settings.debounce)
        };
        if !auto || text.trim().is_empty() {
            return;
        }

        let token = self.inner.debounce.fetch_add(1, Ordering::SeqCst) + 1;
        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            tokio::time::sleep(Duration::from_secs_f64(delay.max(0.05))).await;
            if inner.debounce.load(Ordering::SeqCst) != token {
                return; // a newer keystroke superseded this schedule
            }
            translate_now(&inner, false);
        });
    }

    fn retranslate_if_possible(&self) {
        let has_text = !self.state_guard().source_text.trim().is_empty();
        let auto = self.settings().auto_translate;
        if !has_text {
            return;
        }
        // Supersede the running job first: otherwise `translate_now`'s
        // `translating && !force` guard drops the new request and the style or
        // tone change is silently ignored.
        self.cancel();
        if auto {
            self.schedule_translation();
        } else {
            self.translate(true);
        }
    }

    // -------------------------------------------------------- translation

    /// Start a translation. `force` supersedes a running job.
    pub fn translate(&self, force: bool) {
        translate_now(&self.inner, force);
    }

    /// Cancel the running translation.
    pub fn cancel(&self) {
        if let Some(flag) = self
            .inner
            .cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        self.inner.generation.fetch_add(1, Ordering::SeqCst);
        self.inner.debounce.fetch_add(1, Ordering::SeqCst);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if !state.is_translating {
                return;
            }
            state.is_translating = false;
            state.completed = 0;
            state.total = 0;
        }
        self.emit(AppEvent::Translating { value: false });
        self.emit(AppEvent::Progress {
            completed: 0,
            total: 0,
        });
    }

    // ---------------------------------------------------------- clipboard

    /// Copy the translation in the flavour of the active view.
    pub fn copy_translation(&self) {
        let (markdown, mode) = {
            let state = self.state_guard();
            (state.translated_text.clone(), state.result_view.clone())
        };
        if markdown.trim().is_empty() {
            return;
        }
        let (plain, html) = render_flavours(&markdown, &mode);
        ofm_platform::pasteboard::set_clipboard_text(&plain, html.as_deref(), None);
        self.emit(AppEvent::CopyFeedback {
            value: t("Translation copied").to_string(),
        });
    }

    /// Copy the source text as it is.
    pub fn copy_source(&self) {
        let text = self.state_guard().source_text.clone();
        if text.trim().is_empty() {
            return;
        }
        ofm_platform::pasteboard::set_clipboard_text(&text, None, None);
        self.emit(AppEvent::CopyFeedback {
            value: t("Source text copied").to_string(),
        });
    }

    /// Translate whatever the clipboard holds (rich text becomes Markdown).
    pub fn translate_clipboard(&self) {
        let text = ofm_platform::pasteboard::clipboard_markdown()
            .or_else(ofm_platform::pasteboard::clipboard_text)
            .unwrap_or_default();
        if text.trim().is_empty() {
            self.report_error(t("The clipboard is empty."));
            return;
        }
        self.set_tab("translate");
        self.set_source_text(&text);
        self.translate(true);
    }

    /// Capture the selection of the foreground app and translate it.
    pub fn translate_selection(&self) {
        if !ofm_platform::selection::is_supported() {
            self.report_error(t("Selected text is only captured on Windows."));
            return;
        }
        let captured = ofm_platform::selection::capture(Duration::from_millis(900));
        self.set_tab("translate");
        match captured {
            Some(text) if !text.trim().is_empty() => {
                self.set_source_text(&text);
                self.translate(true);
            }
            _ => self.report_error(t(
                "Could not copy the selected text. If the other app runs as administrator, this shortcut cannot reach it.",
            )),
        }
    }

    // -------------------------------------------------------------- speech

    /// Read the source or the translation aloud.
    pub fn speak(&self, target: &str) {
        // Resolve the source language *before* taking the snapshot guard:
        // `resolved_source` takes the same lock, and a recursive read on
        // `std::sync::RwLock` can deadlock.
        let source_code = self.resolved_source().code.to_string();
        let (text, code) = {
            let state = self.state_guard();
            if target == "source" {
                (state.source_text.clone(), source_code)
            } else {
                (state.translated_text.clone(), state.target_language.clone())
            }
        };
        if text.trim().is_empty() {
            return;
        }
        let voice = self.settings().speech_voice_id.clone();
        let started = self
            .inner
            .speaker
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .speak(&text, &voice, &code);
        if started {
            {
                let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
                state.speaking = target.to_string();
            }
            self.emit(AppEvent::Speaking {
                value: target.to_string(),
            });
            self.watch_speech();
        }
    }

    /// Clear the "speaking" flag when the engine finishes by itself.
    ///
    /// The speech backends report no completion event, so the flag is polled;
    /// without this the speaker button stays lit forever.
    fn watch_speech(&self) {
        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            for _ in 0..120 {
                tokio::time::sleep(Duration::from_millis(250)).await;
                let speaking = inner
                    .speaker
                    .lock()
                    .unwrap_or_else(|p| p.into_inner())
                    .is_speaking();
                if speaking {
                    continue;
                }
                let was = {
                    let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
                    std::mem::take(&mut state.speaking)
                };
                if !was.is_empty() {
                    send(
                        &inner,
                        AppEvent::Speaking {
                            value: String::new(),
                        },
                    );
                }
                return;
            }
        });
    }

    /// Stop reading aloud.
    pub fn stop_speaking(&self) {
        self.inner
            .speaker
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .stop();
        let was = {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            std::mem::take(&mut state.speaking)
        };
        if !was.is_empty() {
            self.emit(AppEvent::Speaking {
                value: String::new(),
            });
        }
    }

    // ------------------------------------------------------------- backend

    /// Probe the configured server.
    pub fn check_connection(&self) {
        self.set_backend_status(BackendStatus::Checking, t("Connecting…"));
        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            let config = inner
                .settings
                .read()
                .unwrap_or_else(|p| p.into_inner())
                .snapshot();
            match inner.translator.list_models(&config).await {
                Ok(models) => {
                    let configured = config.model.trim().to_string();
                    if !configured.is_empty() && !ofm_net::model_listed(&configured, &models) {
                        let message = missing_model_message(&configured, &models);
                        set_status(&inner, BackendStatus::Failed, message.clone());
                        send(&inner, AppEvent::Error { value: message });
                        return;
                    }
                    set_status(&inner, BackendStatus::Connected, t("Connected"));
                    if !models.is_empty() {
                        send(&inner, AppEvent::Models { value: models });
                    }
                }
                Err(error) => {
                    set_status(&inner, BackendStatus::Failed, error.message());
                }
            }
        });
    }

    /// Load the model list of the configured server and verify the selection.
    pub fn connect_and_load_models(&self) {
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.models_loading = true;
            state.models_error = None;
        }
        self.emit(AppEvent::ModelsLoading { value: true });

        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            let config = inner
                .settings
                .read()
                .unwrap_or_else(|p| p.into_inner())
                .snapshot();
            let result = inner.translator.list_models(&config).await;

            let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.models_loading = false;
            drop(state);
            send(&inner, AppEvent::ModelsLoading { value: false });

            match result {
                Ok(models) => {
                    let configured = config.model.trim().to_string();
                    {
                        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
                        state.provider_models = models.clone();
                    }
                    send(
                        &inner,
                        AppEvent::Models {
                            value: models.clone(),
                        },
                    );

                    if models.is_empty() {
                        let message = t("The server returned no models.").to_string();
                        set_state_error(&inner, Some(message.clone()));
                        set_status(&inner, BackendStatus::Failed, message);
                        return;
                    }
                    if !configured.is_empty() && !ofm_net::model_listed(&configured, &models) {
                        let message = missing_model_message(&configured, &models);
                        set_state_error(&inner, Some(message.clone()));
                        set_status(
                            &inner,
                            BackendStatus::Failed,
                            format!("Model “{configured}” not found"),
                        );
                        send(&inner, AppEvent::Error { value: message });
                        return;
                    }
                    set_state_error(&inner, None);
                    set_status(&inner, BackendStatus::Connected, t("Connected"));
                }
                Err(error) => {
                    let message = error.message();
                    set_state_error(&inner, Some(message.clone()));
                    set_status(&inner, BackendStatus::Failed, message.clone());
                    send(&inner, AppEvent::ModelsError { value: message });
                }
            }
        });
    }

    /// Load the model list of the fallback provider.
    pub fn load_fallback_models(&self) {
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.fallback_models_loading = true;
            state.fallback_models_error = None;
        }
        self.emit(AppEvent::FallbackModelsLoading { value: true });

        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            let config = inner
                .settings
                .read()
                .unwrap_or_else(|p| p.into_inner())
                .fallback_probe_config();
            let result = inner.translator.list_models(&config).await;

            {
                let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
                state.fallback_models_loading = false;
            }
            send(&inner, AppEvent::FallbackModelsLoading { value: false });

            match result {
                Ok(models) => {
                    {
                        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
                        state.fallback_models = models.clone();
                        state.fallback_models_error = None;
                    }
                    send(&inner, AppEvent::FallbackModels { value: models });
                }
                Err(error) => {
                    let message = error.message();
                    {
                        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
                        state.fallback_models_error = Some(message.clone());
                    }
                    send(&inner, AppEvent::FallbackModelsError { value: message });
                }
            }
        });
    }

    /// Apply a catalogue entry: provider, base URL and model.
    pub fn apply_catalog_entry(&self, entry: &CatalogEntry) {
        {
            let mut settings = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|p| p.into_inner());
            settings.apply_catalog_entry(entry);
            settings.save();
            let snapshot = settings.clone();
            drop(settings);
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.settings = snapshot.clone();
            drop(state);
            self.emit(AppEvent::Settings {
                value: Box::new(snapshot),
            });
        }
        self.connect_and_load_models();
    }

    /// Select a model by id, from the catalogue or discovered on the server.
    pub fn apply_model(&self, model_id: &str) {
        let model_id = model_id.trim();
        if model_id.is_empty() {
            return;
        }
        if let Some(entry) = ModelCatalog::entry(model_id) {
            self.apply_catalog_entry(entry);
            return;
        }
        let snapshot = {
            let mut settings = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|poison| poison.into_inner());
            // Remember the model per provider so switching providers does not
            // lose it (the catalogue path does this through `apply_provider`).
            let key = format!("model.{}", settings.provider.value());
            settings.remembered.insert(key, model_id.to_string());
            settings.model = model_id.to_string();
            match &self.inner.settings_path {
                Some(path) => settings.save_to(path),
                None => settings.save(),
            }
            settings.clone()
        };
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.settings = snapshot.clone();
        }
        self.emit(AppEvent::Settings {
            value: Box::new(snapshot),
        });
        self.check_connection();
    }

    /// Record whether a global shortcut registered, for the Hot keys tab.
    ///
    /// `which` is `"clipboard"` or `"selection"`; `None` clears the message,
    /// which means the shortcut works.
    pub fn set_hotkey_message(&self, which: &str, message: Option<String>) {
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            let slot = if which == "selection" {
                &mut state.selection_hotkey_message
            } else {
                &mut state.hotkey_message
            };
            let next = message.unwrap_or_default();
            if *slot == next {
                return;
            }
            *slot = next;
        }
        self.emit(AppEvent::StateChanged);
    }

    /// Whether the app should live in the tray / menu bar.
    pub fn show_in_menu_bar(&self) -> bool {
        self.settings().show_in_menu_bar
    }

    /// Paths and storage backends, for the About section.
    pub fn diagnostics_json(&self) -> Value {
        let settings_path = self
            .inner
            .settings_path
            .clone()
            .unwrap_or_else(AppSettings::default_path);
        let history_path = HistoryStore::default_path();
        json!({
            "settingsPath": settings_path.to_string_lossy(),
            "historyPath": history_path.to_string_lossy(),
            "secretBackend": self.inner.secrets.backend_name(),
            "version": env!("CARGO_PKG_VERSION"),
            "interfaceLanguage": ofm_i18n::current_language().code(),
            "providerCount": Provider::all().len(),
            "catalogCount": ModelCatalog::entries().len(),
        })
    }

    // ------------------------------------------------------------ settings

    /// Replace the settings, persist them and apply the interface language.
    ///
    /// Three things happen beyond writing the file, and each one was a real bug
    /// in the Python port before it was fixed there:
    /// * API keys go to the secret store, never to `settings.json`;
    /// * switching the provider restores that provider's remembered base URL and
    ///   model instead of carrying the previous provider's values across;
    /// * the key field shows the key of the provider now selected.
    pub fn save_settings(&self, mut settings: AppSettings) {
        let current = self.settings().clone();
        let provider_changed = settings.provider != current.provider;
        let fallback_changed = settings.fallback_provider != current.fallback_provider;

        if provider_changed {
            // `apply_provider` remembers the outgoing pair and restores the
            // incoming provider's own pair from memory.
            let mut memory = current.clone();
            memory.apply_provider(settings.provider, None);
            // The memory map lives in the settings that get written back.
            settings.remembered = memory.remembered.clone();
            // Restore each field the UI did not touch, independently: a dialog
            // usually echoes the new provider's base URL but leaves the model.
            if settings.model == current.model {
                settings.model = memory.model;
            }
            if settings.base_url == current.base_url {
                settings.base_url = memory.base_url;
            }
            if settings.api_key.trim().is_empty() || settings.api_key == current.api_key {
                settings.api_key = self.inner.secrets.read(&settings.provider.key_account());
            }
        }

        if fallback_changed {
            let mut memory = current.clone();
            memory.apply_fallback_provider(settings.fallback_provider, None);
            settings.remembered = memory.remembered.clone();
            if settings.fallback_model == current.fallback_model {
                settings.fallback_model = memory.fallback_model;
            }
            if settings.fallback_base_url == current.fallback_base_url {
                settings.fallback_base_url = memory.fallback_base_url;
            }
            if settings.fallback_api_key.trim().is_empty()
                || settings.fallback_api_key == current.fallback_api_key
            {
                settings.fallback_api_key = self
                    .inner
                    .secrets
                    .read(&settings.fallback_provider.key_account());
            }
        }

        // Keep the outgoing key when the provider changed, then store the new one.
        if provider_changed && !current.api_key.trim().is_empty() {
            self.store_key(current.provider, &current.api_key);
        }
        self.store_key(settings.provider, &settings.api_key);
        if fallback_changed && !current.fallback_api_key.trim().is_empty() {
            self.store_key(current.fallback_provider, &current.fallback_api_key);
        }
        self.store_key(settings.fallback_provider, &settings.fallback_api_key);

        let language = settings.interface_language;
        match &self.inner.settings_path {
            Some(path) => settings.save_to(path),
            None => settings.save(),
        }
        ofm_i18n::set_language(language);
        {
            let mut guard = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|p| p.into_inner());
            *guard = settings.clone();
        }
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.settings = settings.clone();
            state.result_view = settings.result_view.clone();
            state.style = settings.last_style.clone();
            state.tone = settings.last_tone.clone();
            state.source_language = settings.last_source_code.clone();
            state.target_language = settings.last_target_code.clone();
        }
        self.emit(AppEvent::Settings {
            value: Box::new(settings),
        });
        self.emit(AppEvent::InterfaceLanguage {
            value: language.code().to_string(),
        });
        self.check_connection();
    }

    /// Apply a partial settings object coming from the frontend.
    ///
    /// The incoming object is merged over the current settings on the **wire**
    /// representation (camelCase), so fields the dialog does not own — the
    /// per-provider memory, the stored keys — survive a partial save. Unknown or
    /// invalid values keep their previous value: a stale UI cannot corrupt the
    /// configuration.
    pub fn save_settings_json(&self, value: &Value) {
        let current = self.settings().clone();
        let mut merged = serde_json::to_value(&current).unwrap_or_else(|_| json!({}));
        if let (Some(target), Some(incoming)) = (merged.as_object_mut(), value.as_object()) {
            for (key, incoming_value) in incoming {
                target.insert(key.clone(), incoming_value.clone());
            }
        }
        let updated = match serde_json::from_value::<AppSettings>(merged) {
            Ok(settings) => settings,
            Err(error) => {
                warn!("ignoring a malformed settings payload: {error}");
                return;
            }
        };
        self.save_settings(updated);
    }

    /// Switch the interface language.
    pub fn set_interface_language(&self, language: AppLanguage) {
        {
            let mut settings = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|p| p.into_inner());
            if settings.interface_language == language {
                return;
            }
            settings.interface_language = language;
            settings.save();
        }
        ofm_i18n::set_language(language);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.settings.interface_language = language;
        }
        self.emit(AppEvent::InterfaceLanguage {
            value: language.code().to_string(),
        });
    }

    // --------------------------------------------------------------- files

    /// Start translating a document.
    ///
    /// `target_code` is the Files tab's own choice; when it is `None` the
    /// Translate tab's target is used. The Files tab keeps its selection local
    /// so choosing German there does not silently change the other tab.
    pub fn start_file_translation(&self, path: &Path, target_code: Option<&str>) {
        let Some(kind) = DocumentKind::from_path(path) else {
            self.report_error(t("This file type is not supported."));
            return;
        };
        let config = self.settings().snapshot();
        if config.model.trim().is_empty() {
            self.report_error(t("Choose a model in Settings."));
            return;
        }

        // A new document replaces the current one.
        if let Some(flag) = self
            .inner
            .file_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        self.discard_staging();

        let generation = self.inner.file_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let cancel: CancelFlag = Arc::new(AtomicBool::new(false));
        *self
            .inner
            .file_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner()) = Some(Arc::clone(&cancel));

        let size = std::fs::metadata(path).map(|meta| meta.len()).unwrap_or(0);
        let job = FileJob::new(path, kind.value(), size);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.file_job = Some(job.clone());
        }
        self.emit(AppEvent::FileJob {
            value: Box::new(job),
        });

        let inner = Arc::clone(&self.inner);
        let target = target_code
            .and_then(LanguageTable::get)
            .copied()
            .unwrap_or_else(|| *self.target_language());
        let source = *self.resolved_source();
        let style = self.style();
        let tone = self.tone();
        let path = path.to_path_buf();
        let fallback = self.settings().fallback_config();

        // Reading, translating and rewriting a document is synchronous and can
        // take seconds: run it on the blocking pool so the async workers stay free.
        self.inner.runtime.spawn_blocking(move || {
            let staging = std::env::temp_dir().join(format!(
                "deepl-ofm-{}-{}",
                std::process::id(),
                generation
            ));
            if let Err(error) = std::fs::create_dir_all(&staging) {
                file_failed(
                    &inner,
                    generation,
                    format!("could not create a temporary folder: {error}"),
                );
                return;
            }

            let read = DocumentTranslator::read(&path);
            let document = match read {
                Ok(document) => document,
                Err(error) => {
                    let _ = std::fs::remove_dir_all(&staging);
                    file_failed(&inner, generation, error.message());
                    return;
                }
            };

            file_update(&inner, generation, |job| {
                job.state = FileJobState::Translating.value().to_string();
            });

            let out_path = staging.join(
                DocumentTranslator::suggested_path(&path, &target)
                    .file_name()
                    .map(|name| name.to_owned())
                    .unwrap_or_else(|| std::ffi::OsString::from("translated.txt")),
            );

            let handle = tokio::runtime::Handle::current();
            let translator = Arc::clone(&inner.translator);
            let config = config.clone();
            let cancel_for_closure = Arc::clone(&cancel);
            let counters = Arc::new(Mutex::new((0usize, false)));

            let mut translate = |paragraph: &str| -> Result<String, String> {
                if cancel_for_closure.load(Ordering::SeqCst) {
                    return Err("cancelled".to_string());
                }
                let request = ofm_net::TranslateRequest {
                    text: paragraph,
                    source: &source,
                    target: &target,
                    style,
                    tone,
                    config: &config,
                    fallback: fallback.as_ref(),
                    cancel: Some(Arc::clone(&cancel_for_closure)),
                    on_progress: None,
                    on_partial: None,
                };
                let outcome = handle.block_on(translator.translate(request));
                match outcome {
                    Ok(output) => {
                        let mut counters = counters.lock().unwrap_or_else(|p| p.into_inner());
                        counters.0 += output.warnings;
                        counters.1 |= output.used_fallback;
                        Ok(output.text)
                    }
                    Err(error) => Err(error.message()),
                }
            };

            let progress_inner = Arc::clone(&inner);
            let on_progress = move |completed: usize, total: usize| {
                file_progress(&progress_inner, generation, completed, total);
            };

            let result = DocumentTranslator::write(
                &document,
                &out_path,
                &mut translate,
                Some(&on_progress),
                Some(cancel.as_ref()),
            );

            match result {
                Ok(written) => {
                    let (warnings, used_fallback) =
                        *counters.lock().unwrap_or_else(|p| p.into_inner());
                    let label = if used_fallback {
                        fallback_label(&inner)
                    } else {
                        String::new()
                    };
                    // Only the current job may own the staging folder, or a
                    // superseded job leaks it and a stale path could be saved.
                    if inner.file_generation.load(Ordering::SeqCst) == generation {
                        *inner.file_staging.lock().unwrap_or_else(|p| p.into_inner()) =
                            Some(staging.clone());
                        file_done(&inner, generation, &written, warnings, used_fallback, label);
                    } else {
                        let _ = std::fs::remove_dir_all(&staging);
                    }
                }
                Err(error) => {
                    let _ = std::fs::remove_dir_all(&staging);
                    if error.kind == ofm_docs::DocumentErrorKind::Cancelled
                        || cancel.load(Ordering::SeqCst)
                    {
                        file_cancelled(&inner, generation);
                    } else {
                        file_failed(&inner, generation, error.message());
                    }
                }
            }
        });
    }

    /// Stop the document translation.
    pub fn cancel_file_translation(&self) {
        if let Some(flag) = self
            .inner
            .file_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        self.inner.file_generation.fetch_add(1, Ordering::SeqCst);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if let Some(job) = state.file_job.as_mut() {
                if job.state == FileJobState::Cancelled.value() {
                    return;
                }
                job.state = FileJobState::Cancelled.value().to_string();
            }
        }
        let job = self.state_guard().file_job.clone();
        if let Some(job) = job {
            self.emit(AppEvent::FileJob {
                value: Box::new(job),
            });
        }
    }

    /// Copy the staged result to the destination the user picked.
    pub fn save_translated_file(&self, destination: &Path) {
        let Some(staged) = self
            .inner
            .file_staging
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .clone()
        else {
            self.report_error(t("The file could not be translated."));
            return;
        };
        let Some(job) = self.state_guard().file_job.clone() else {
            return;
        };
        let Some(output) = job.output.as_ref().map(PathBuf::from) else {
            return;
        };
        let _ = staged; // the staged folder is removed by `clear_file_job`

        // Copy next to the target and rename, so a failure never truncates an
        // existing file the user chose.
        let temporary = destination.with_extension(format!(
            "{}.part",
            destination
                .extension()
                .map(|value| value.to_string_lossy().into_owned())
                .unwrap_or_default()
        ));
        let copy = std::fs::copy(&output, &temporary)
            .and_then(|_| std::fs::rename(&temporary, destination));
        match copy {
            Ok(_) => {
                self.update_file_job(|job| {
                    job.output = Some(destination.to_string_lossy().into_owned());
                    job.result_name = destination
                        .file_name()
                        .map(|name| name.to_string_lossy().into_owned());
                    job.save_error = None;
                });
                self.emit(AppEvent::CopyFeedback {
                    value: t("Saved").to_string(),
                });
            }
            Err(error) => {
                let _ = std::fs::remove_file(&temporary);
                let message = format!("{error}");
                self.update_file_job(|job| job.save_error = Some(message.clone()));
                self.report_error(message);
            }
        }
    }

    /// Forget the current document and delete its staged output.
    pub fn clear_file_job(&self) {
        if let Some(flag) = self
            .inner
            .file_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        self.inner.file_generation.fetch_add(1, Ordering::SeqCst);
        self.discard_staging();
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.file_job = None;
        }
        self.emit(AppEvent::FileJob {
            value: Box::default(),
        });
    }

    fn discard_staging(&self) {
        if let Some(folder) = self
            .inner
            .file_staging
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            let _ = std::fs::remove_dir_all(folder);
        }
    }

    fn update_file_job(&self, mutate: impl FnOnce(&mut FileJob)) {
        let job = {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            let Some(job) = state.file_job.as_mut() else {
                return;
            };
            mutate(job);
            job.refresh_percent();
            job.clone()
        };
        self.emit(AppEvent::FileJob {
            value: Box::new(job),
        });
    }

    // --------------------------------------------------------------- write

    /// Improve a draft. Without an explicit language the text is improved in the
    /// language it is written in, like the macOS app.
    pub fn write_text(&self, text: &str, target_code: &str) {
        if text.trim().is_empty() {
            return;
        }
        // Supersede the previous rewrite rather than dropping this request: a
        // user pressing Improve again expects the new draft to be handled.
        if self.state_guard().write.in_progress {
            self.cancel_write();
        }
        let config = self.settings().snapshot();
        if config.model.trim().is_empty() {
            self.report_error(t("Choose a model in Settings."));
            return;
        }

        let target = if target_code.is_empty() || target_code == "auto" {
            let ui = self.settings().interface_language;
            LanguageTable::detect(text, ui)
                .copied()
                .unwrap_or(*self.target_language())
        } else {
            *LanguageTable::get(target_code).unwrap_or(self.target_language())
        };

        if let Some(flag) = self
            .inner
            .write_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        let generation = self.inner.write_generation.fetch_add(1, Ordering::SeqCst) + 1;
        let cancel: CancelFlag = Arc::new(AtomicBool::new(false));
        *self
            .inner
            .write_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner()) = Some(Arc::clone(&cancel));

        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.write = WriteState {
                in_progress: true,
                output: String::new(),
                error: None,
                detected_code: if target_code == "auto" {
                    Some(target.code.to_string())
                } else {
                    None
                },
                duration_ms: None,
                warnings: 0,
            };
        }
        self.emit_write();

        let inner = Arc::clone(&self.inner);
        let text = text.to_string();
        let fallback = self.settings().fallback_config();
        self.inner.runtime.spawn(async move {
            let started = Instant::now();
            // Stream the text into the pane while the model types, so a long
            // draft does not look frozen. One event per change is enough.
            let partial_inner = Arc::clone(&inner);
            let partial: ofm_net::PartialFn = Arc::new(move |chunk: &str| {
                let snapshot = {
                    let mut state = partial_inner
                        .state
                        .write()
                        .unwrap_or_else(|p| p.into_inner());
                    // A cancelled or superseded rewrite must not repaint the pane.
                    if partial_inner.write_generation.load(Ordering::SeqCst) != generation
                        || state.write.output == chunk
                    {
                        return;
                    }
                    state.write.output = chunk.to_string();
                    state.write.clone()
                };
                send(
                    &partial_inner,
                    AppEvent::Write {
                        value: Box::new(snapshot),
                    },
                );
            });
            let request = inner.translator.rewrite_with(
                &text,
                &target,
                &config,
                fallback.as_ref(),
                Some(Arc::clone(&cancel)),
                None,
                Some(partial),
            );
            let outcome = request.await;
            if inner.write_generation.load(Ordering::SeqCst) != generation {
                return;
            }
            let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
            match outcome {
                Ok(output) => {
                    state.write = WriteState {
                        in_progress: false,
                        output: output.text,
                        error: if output.warnings == 0 {
                            None
                        } else {
                            Some(ofm_i18n::tf(
                                "Some paragraphs are still in the original language (%d).",
                                &[&output.warnings],
                            ))
                        },
                        detected_code: state.write.detected_code.clone(),
                        duration_ms: Some(
                            output
                                .duration_ms
                                .unwrap_or_else(|| started.elapsed().as_millis() as u64),
                        ),
                        warnings: output.warnings,
                    };
                }
                Err(error) if error.kind == ofm_net::ErrorKind::Cancelled => {
                    state.write.in_progress = false;
                    state.write.error = None;
                }
                Err(error) => {
                    state.write.in_progress = false;
                    state.write.error = Some(error.message());
                }
            }
            let snapshot = state.write.clone();
            drop(state);
            send(
                &inner,
                AppEvent::Write {
                    value: Box::new(snapshot),
                },
            );
        });
    }

    /// Stop the running rewrite.
    pub fn cancel_write(&self) {
        if let Some(flag) = self
            .inner
            .write_cancel
            .lock()
            .unwrap_or_else(|p| p.into_inner())
            .take()
        {
            flag.store(true, Ordering::SeqCst);
        }
        self.inner.write_generation.fetch_add(1, Ordering::SeqCst);
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            if !state.write.in_progress {
                return;
            }
            state.write.in_progress = false;
        }
        self.emit_write();
    }

    /// Drop a stale rewrite result (the draft changed under it).
    pub fn reset_write(&self) {
        self.cancel_write();
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.write = WriteState::default();
        }
        self.emit_write();
    }

    fn emit_write(&self) {
        let write = self.state_guard().write.clone();
        self.emit(AppEvent::Write {
            value: Box::new(write),
        });
    }

    // ------------------------------------------------------------- history

    /// Search the history (case-insensitive over both texts).
    pub fn history_search(&self, query: &str) -> Vec<HistoryEntry> {
        if query.trim().is_empty() {
            self.inner.history.entries()
        } else {
            self.inner.history.search(query)
        }
    }

    /// Delete one entry.
    pub fn history_delete(&self, id: &str) {
        self.inner.history.remove(id);
        self.refresh_history();
    }

    /// Delete everything.
    pub fn history_clear(&self) {
        self.inner.history.clear();
        self.refresh_history();
    }

    /// Restore an entry into the Translate tab.
    pub fn load_history_entry(&self, id: &str) {
        // The in-flight translation would land on top of the restored entry.
        self.cancel();
        self.inner.debounce.fetch_add(1, Ordering::SeqCst);
        let Some(entry) = self
            .inner
            .history
            .entries()
            .into_iter()
            .find(|entry| entry.id == id)
        else {
            return;
        };

        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.source_text = entry.source_text.clone();
            state.translated_text = entry.translated_text.clone();
            state.source_language = entry.source_code.clone();
            state.target_language = entry.target_code.clone();
            state.style = entry.style.clone();
            state.tone = entry.tone.clone();
            state.last_duration_ms = Some(entry.duration_ms);
            state.tokens_per_second = None;
            state.error_message = None;
            state.warning_count = 0;
            state.tab = "translate".to_string();
            state.detected_language = if entry.source_code == "auto" {
                let ui = self.settings().interface_language;
                LanguageTable::detect(&entry.source_text, ui)
                    .map(|language| language.code.to_string())
            } else {
                None
            };
        }
        let (source_code, target_code) = (entry.source_code.clone(), entry.target_code.clone());
        let (style_value, tone_value) = (entry.style.clone(), entry.tone.clone());
        self.update_settings(|settings| {
            settings.last_source_code = source_code;
            settings.last_target_code = target_code;
            settings.last_style = style_value;
            settings.last_tone = tone_value;
        });
        *self.inner.cache.lock().unwrap_or_else(|p| p.into_inner()) = None;

        let state = self.state_guard().clone();
        self.emit(AppEvent::SourceText {
            value: state.source_text,
        });
        self.emit(AppEvent::TranslatedText {
            value: state.translated_text,
        });
        self.emit(AppEvent::Languages {
            source: state.source_language,
            target: state.target_language,
        });
        self.emit(AppEvent::Style { value: state.style });
        self.emit(AppEvent::Tone { value: state.tone });
        self.emit(AppEvent::Detected {
            value: state.detected_language.unwrap_or_default(),
        });
        self.emit(AppEvent::Metrics);
        self.emit(AppEvent::Tab {
            value: "translate".to_string(),
        });
    }

    fn refresh_history(&self) {
        let (entries, error) = {
            let entries = self.inner.history.entries();
            let error = self.inner.history.has_storage_error();
            (entries, error)
        };
        {
            let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.history = entries;
            state.history_error = error;
        }
        self.emit(AppEvent::History);
    }

    /// API key of the configured provider, read from the secret store.
    pub fn provider_api_key(&self) -> String {
        let provider = self.settings().provider;
        self.inner.secrets.read(&provider.key_account())
    }

    /// Store (or clear) the key of `provider` in the OS secret store.
    fn store_key(&self, provider: Provider, key: &str) {
        if key.trim().is_empty() {
            self.inner.secrets.delete(&provider.key_account());
        } else {
            self.inner.secrets.write(&provider.key_account(), key);
        }
    }

    /// Store the API key of the configured provider.
    pub fn set_provider_api_key(&self, key: &str) {
        let provider = self.settings().provider;
        self.store_key(provider, key);
        let snapshot = {
            let mut settings = self
                .inner
                .settings
                .write()
                .unwrap_or_else(|p| p.into_inner());
            settings.api_key = key.to_string();
            settings.clone()
        };
        let mut state = self.inner.state.write().unwrap_or_else(|p| p.into_inner());
        state.settings = snapshot;
    }

    /// Warm the model up at launch, but only for a local provider.
    pub fn warm_up(&self) {
        let (enabled, config, provider) = {
            let settings = self.settings();
            (
                settings.warm_up_on_launch,
                settings.snapshot(),
                settings.provider,
            )
        };
        if !enabled || !provider.is_local() || config.model.trim().is_empty() {
            return;
        }
        self.set_backend_status(BackendStatus::Warming, t("Loading the translator…"));
        let inner = Arc::clone(&self.inner);
        self.inner.runtime.spawn(async move {
            let ok = inner.translator.warm_up(&config).await;
            if ok {
                set_status(&inner, BackendStatus::Connected, t("Connected"));
            }
        });
    }

    /// The backend configuration the translator should use right now.
    pub fn backend_config(&self) -> ofm_config::BackendConfig {
        self.settings().snapshot()
    }

    /// Models the configured server offers.
    pub async fn fetch_models(&self) -> Result<Vec<String>, ofm_net::TranslationError> {
        let config = self.backend_config();
        self.inner.translator.list_models(&config).await
    }

    /// Voices the system speech engine offers as `(id, label)` pairs.
    pub fn voices(&self) -> Vec<(String, String)> {
        self.inner
            .speaker
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
            .voices()
    }

    /// The prompt that would be sent for this style, tone and target.
    pub fn prompt_preview_for(&self, style: &str, tone: &str, target_code: &str) -> String {
        let target = LanguageTable::get(target_code).unwrap_or(&LanguageTable::AUTO);
        PromptBuilder::preview(
            TranslationStyle::from_value(style).unwrap_or(TranslationStyle::Auto),
            TranslationTone::from_value(tone).unwrap_or(TranslationTone::Standard),
            target.english_name,
            "Hello, world!",
        )
    }

    /// Every interface string for the active language, as a JSON object.
    ///
    /// The frontend renders English keys, so it can translate itself by looking
    /// each label up in this map and falling back to the key.
    pub fn translations_json(&self) -> Value {
        let language = ofm_i18n::current_language();
        let mut map = serde_json::Map::with_capacity(384);
        for (key, value) in ofm_i18n::catalogue(language) {
            map.insert(key.to_string(), Value::String(value.to_string()));
        }
        Value::Object(map)
    }

    /// Settings as JSON for the frontend (camelCase wire format).
    pub fn settings_json(&self) -> Value {
        serde_json::to_value(self.settings().clone()).unwrap_or_else(|_| json!({}))
    }

    /// Catalogue as JSON for the frontend.
    #[allow(dead_code)]
    pub fn catalog_json() -> Value {
        Value::Array(
            ModelCatalog::entries()
                .iter()
                .map(|entry| {
                    json!({
                        "name": entry.name,
                        "modelId": entry.model_id,
                        "provider": entry.provider.title(),
                        "providerValue": entry.provider.value(),
                        "size": entry.size,
                        "languages": entry.languages,
                        "note": entry.note,
                        "installCommand": entry.install_command,
                        "badges": entry.badges,
                        "isFree": entry.is_free,
                    })
                })
                .collect(),
        )
    }

    /// Prompt preview for the settings dialog.
    pub fn prompt_preview(&self) -> String {
        let target = self.target_language();
        PromptBuilder::preview(
            self.style(),
            self.tone(),
            target.english_name,
            "Hello, world!",
        )
    }
}

impl Default for AppController {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------- helpers

/// Shared state for the free functions below (they run inside jobs).
fn send(inner: &Arc<Inner>, event: AppEvent) {
    let _ = inner.events.send(event);
}

fn set_status(inner: &Arc<Inner>, status: BackendStatus, message: impl Into<String>) {
    let message = message.into();
    {
        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
        state.backend_status = status.value().to_string();
        state.probe_message = message.clone();
    }
    send(
        inner,
        AppEvent::BackendStatus {
            value: status.value().to_string(),
        },
    );
    send(inner, AppEvent::ProbeMessage { value: message });
}

fn set_state_error(inner: &Arc<Inner>, message: Option<String>) {
    {
        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
        state.models_error = message.clone();
    }
    send(
        inner,
        AppEvent::ModelsError {
            value: message.unwrap_or_default(),
        },
    );
}

fn missing_model_message(model: &str, models: &[String]) -> String {
    let available = models
        .iter()
        .take(6)
        .cloned()
        .collect::<Vec<_>>()
        .join(", ");
    format!("Server responds, but model “{model}” is missing. Available: {available}.")
}

fn fallback_label(inner: &Arc<Inner>) -> String {
    let settings = inner.settings.read().unwrap_or_else(|p| p.into_inner());
    match settings.fallback_config() {
        Some(config) => format!("{} · {}", settings.fallback_provider.title(), config.model),
        None => String::new(),
    }
}

fn file_update(inner: &Arc<Inner>, generation: u64, mutate: impl FnOnce(&mut FileJob)) {
    if inner.file_generation.load(Ordering::SeqCst) != generation {
        return;
    }
    let job = {
        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
        let Some(job) = state.file_job.as_mut() else {
            return;
        };
        mutate(job);
        job.refresh_percent();
        job.clone()
    };
    send(
        inner,
        AppEvent::FileJob {
            value: Box::new(job),
        },
    );
}

fn file_progress(inner: &Arc<Inner>, generation: u64, completed: usize, total: usize) {
    file_update(inner, generation, |job| {
        job.completed = completed;
        job.total = total;
        if total > 0 && completed >= total {
            job.state = FileJobState::Writing.value().to_string();
        }
    });
}

fn file_done(
    inner: &Arc<Inner>,
    generation: u64,
    output: &Path,
    warnings: usize,
    used_fallback: bool,
    fallback_label: String,
) {
    file_update(inner, generation, |job| {
        job.state = FileJobState::Done.value().to_string();
        job.completed = job.total;
        job.percent = 100;
        job.output = Some(output.to_string_lossy().into_owned());
        job.result_name = output
            .file_name()
            .map(|name| name.to_string_lossy().into_owned());
        job.warnings = warnings;
        job.fallback = used_fallback;
        job.fallback_label = fallback_label;
    });
}

fn file_failed(inner: &Arc<Inner>, generation: u64, message: String) {
    file_update(inner, generation, |job| {
        job.state = FileJobState::Failed.value().to_string();
        job.message = Some(message);
    });
}

fn file_cancelled(inner: &Arc<Inner>, generation: u64) {
    file_update(inner, generation, |job| {
        job.state = FileJobState::Cancelled.value().to_string();
        job.completed = 0;
        job.total = 0;
        job.percent = 0;
    });
}

/// Start a translation for `inner`. Shared by the command and the debounce timer.
fn translate_now(inner: &Arc<Inner>, force: bool) {
    // Take the two locks in sequence, never nested: another path takes them in
    // the opposite order and `std::sync::RwLock` would deadlock.
    let (text, source_code, target_code, style_value, tone_value) = {
        let state = inner.state.read().unwrap_or_else(|p| p.into_inner());
        (
            state.source_text.clone(),
            state.source_language.clone(),
            state.target_language.clone(),
            state.style.clone(),
            state.tone.clone(),
        )
    };
    let (config, fallback) = {
        let settings = inner.settings.read().unwrap_or_else(|p| p.into_inner());
        (settings.snapshot(), settings.fallback_config())
    };

    if text.trim().is_empty() {
        return;
    }
    if config.model.trim().is_empty() {
        let message = t("Choose a model in Settings.").to_string();
        {
            let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
            state.error_message = Some(message.clone());
        }
        send(inner, AppEvent::Error { value: message });
        return;
    }

    let translating = {
        let state = inner.state.read().unwrap_or_else(|p| p.into_inner());
        state.is_translating
    };
    if translating && !force {
        return;
    }

    // Cancel the previous job before its flag is replaced.
    if let Some(flag) = inner
        .cancel
        .lock()
        .unwrap_or_else(|p| p.into_inner())
        .take()
    {
        flag.store(true, Ordering::SeqCst);
    }
    let generation = inner.generation.fetch_add(1, Ordering::SeqCst) + 1;
    let cancel: CancelFlag = Arc::new(AtomicBool::new(false));
    *inner.cancel.lock().unwrap_or_else(|p| p.into_inner()) = Some(Arc::clone(&cancel));

    // The cache key must include everything that changes the result.
    let key: CacheKey = (
        text.clone(),
        source_code.clone(),
        target_code.clone(),
        style_value.clone(),
        tone_value.clone(),
        config.model.clone(),
    );
    // A cache hit only means "the pane already shows this exact result". If the
    // text was cleared and retyped the pane is empty, so the request must run.
    let cached = !force
        && {
            let cache = inner.cache.lock().unwrap_or_else(|p| p.into_inner());
            cache.as_ref() == Some(&key)
        }
        && {
            let state = inner.state.read().unwrap_or_else(|p| p.into_inner());
            !state.translated_text.trim().is_empty()
        };
    if cached {
        return;
    }

    {
        let mut state = inner.state.write().unwrap_or_else(|p| p.into_inner());
        state.is_translating = true;
        state.error_message = None;
        state.warning_count = 0;
        state.completed = 0;
        state.total = 0;
        state.tokens_per_second = None;
        state.last_duration_ms = None;
        state.using_fallback = false;
    }
    send(inner, AppEvent::Translating { value: true });
    send(
        inner,
        AppEvent::Progress {
            completed: 0,
            total: 0,
        },
    );

    let source = if source_code == "auto" {
        let state = inner.state.read().unwrap_or_else(|p| p.into_inner());
        state
            .detected_language
            .as_deref()
            .and_then(LanguageTable::get)
            .copied()
            .unwrap_or(LanguageTable::AUTO)
    } else {
        LanguageTable::get(&source_code)
            .copied()
            .unwrap_or(LanguageTable::AUTO)
    };
    let target = LanguageTable::get(&target_code)
        .copied()
        .unwrap_or(LanguageTable::AUTO);
    let style = TranslationStyle::from_value(&style_value).unwrap_or(TranslationStyle::Auto);
    let tone = TranslationTone::from_value(&tone_value).unwrap_or(TranslationTone::Standard);

    let worker = Arc::clone(inner);
    inner.runtime.spawn(async move {
        let started = Instant::now();
        let progress_worker = Arc::clone(&worker);
        let progress: ofm_net::ProgressFn = Arc::new(move |completed: usize, total: usize| {
            // A superseded job must not move the counters of the new one.
            {
                let mut state = progress_worker
                    .state
                    .write()
                    .unwrap_or_else(|p| p.into_inner());
                if progress_worker.generation.load(Ordering::SeqCst) != generation {
                    return;
                }
                state.completed = completed;
                state.total = total;
            }
            send(&progress_worker, AppEvent::Progress { completed, total });
        });

        let request = ofm_net::TranslateRequest {
            text: &text,
            source: &source,
            target: &target,
            style,
            tone,
            config: &config,
            fallback: fallback.as_ref(),
            cancel: Some(Arc::clone(&cancel)),
            on_progress: Some(progress),
            on_partial: None,
        };

        let outcome = worker.translator.translate(request).await;

        // A newer job superseded this one: drop the result silently.
        if worker.generation.load(Ordering::SeqCst) != generation {
            return;
        }

        match outcome {
            Ok(output) => {
                let duration = output
                    .duration_ms
                    .unwrap_or_else(|| started.elapsed().as_millis() as u64);
                {
                    let mut state = worker.state.write().unwrap_or_else(|p| p.into_inner());
                    state.translated_text = output.text.clone();
                    state.is_translating = false;
                    state.warning_count = output.warnings;
                    state.tokens_per_second = output.tokens_per_second;
                    state.last_duration_ms = Some(duration);
                    state.using_fallback = output.used_fallback;
                    if state.total == 0 {
                        state.completed = 0;
                    } else {
                        state.completed = state.total;
                    }
                }
                *worker.cache.lock().unwrap_or_else(|p| p.into_inner()) = Some(key);

                send(&worker, AppEvent::Translating { value: false });
                send(
                    &worker,
                    AppEvent::TranslatedText {
                        value: output.text.clone(),
                    },
                );
                send(&worker, AppEvent::Metrics);

                if output.warnings > 0 {
                    let message = ofm_i18n::tf(
                        "Some paragraphs are still in the original language (%d).",
                        &[&output.warnings],
                    );
                    {
                        let mut state = worker.state.write().unwrap_or_else(|p| p.into_inner());
                        state.error_message = Some(message.clone());
                    }
                    send(&worker, AppEvent::Error { value: message });
                }

                let keep_history = worker
                    .settings
                    .read()
                    .unwrap_or_else(|p| p.into_inner())
                    .keep_history;
                if keep_history && !output.text.trim().is_empty() {
                    let settings = worker.settings.read().unwrap_or_else(|p| p.into_inner());
                    let engine = if settings.model.trim().is_empty() {
                        settings.provider.title().to_string()
                    } else {
                        format!("{} · {}", settings.provider.title(), settings.model)
                    };
                    drop(settings);
                    let entry = HistoryEntry::create(
                        &text,
                        &output.text,
                        &source_code,
                        &target_code,
                        &style_value,
                        &tone_value,
                        &engine,
                        duration,
                    );
                    worker.history.add(entry);
                    let entries = worker.history.entries();
                    let error = worker.history.has_storage_error();
                    {
                        let mut state = worker.state.write().unwrap_or_else(|p| p.into_inner());
                        state.history = entries;
                        state.history_error = error;
                    }
                    send(&worker, AppEvent::History);
                }
            }
            Err(error) => {
                let cancelled = error.kind == ofm_net::ErrorKind::Cancelled;
                {
                    let mut state = worker.state.write().unwrap_or_else(|p| p.into_inner());
                    state.is_translating = false;
                    state.completed = 0;
                    state.total = 0;
                    if !cancelled {
                        state.error_message = Some(error.message());
                    }
                }
                send(&worker, AppEvent::Translating { value: false });
                if cancelled {
                    send(
                        &worker,
                        AppEvent::Progress {
                            completed: 0,
                            total: 0,
                        },
                    );
                } else {
                    let message = error.message();
                    send(
                        &worker,
                        AppEvent::Error {
                            value: message.clone(),
                        },
                    );
                    send(
                        &worker,
                        AppEvent::TranslationFailed {
                            value: message.clone(),
                        },
                    );
                    if matches!(
                        error.kind,
                        ofm_net::ErrorKind::Connection
                            | ofm_net::ErrorKind::Server
                            | ofm_net::ErrorKind::RateLimit
                            | ofm_net::ErrorKind::Unauthorized
                            | ofm_net::ErrorKind::InvalidUrl
                    ) {
                        set_status(&worker, BackendStatus::Failed, message);
                    }
                }
            }
        }
    });
}

/// Plain text and (when the view is rich) HTML for the clipboard.
fn render_flavours(markdown: &str, mode: &str) -> (String, Option<String>) {
    match mode {
        "markdown" => (markdown.to_string(), None),
        "text" => (ofm_platform::markdown::to_plain(markdown), None),
        _ => (
            ofm_platform::markdown::to_plain(markdown),
            Some(ofm_platform::markdown::to_html(markdown)),
        ),
    }
}

/// Log a one-line summary; used by the desktop shell at startup.
pub fn describe(controller: &AppController) -> String {
    let settings = controller.settings();
    let summary = format!(
        "{} · {} · {}",
        settings.provider.title(),
        if settings.model.trim().is_empty() {
            "(no model)"
        } else {
            settings.model.as_str()
        },
        settings.interface_language.code()
    );
    debug!("controller ready: {summary}");
    summary
}

/// Convenience for the CLI and tests: a controller that never touches the network.
pub fn offline_controller(settings: AppSettings) -> AppController {
    let controller = AppController::new();
    controller.save_settings(settings);
    info!("offline controller ready");
    warn_if_cloud(&controller);
    controller
}

fn warn_if_cloud(controller: &AppController) {
    let settings = controller.settings();
    if !settings.provider.is_local() && settings.api_key.trim().is_empty() {
        info!(
            "cloud provider {} has no API key",
            settings.provider.title()
        );
    }
}

/// Catalogue of installable models as JSON.
pub fn catalog_json() -> Value {
    AppController::catalog_json()
}

/// Provider list with the metadata the settings dialog needs.
pub fn providers_json() -> Value {
    Value::Array(
        Provider::all()
            .iter()
            .map(|provider| {
                json!({
                    "value": provider.value(),
                    "title": provider.title(),
                    "baseUrl": provider.base_url(),
                    "kind": match provider.kind() {
                        ofm_config::BackendKind::Ollama => "ollama",
                        ofm_config::BackendKind::OpenAI => "openAI",
                    },
                    "isLocal": provider.is_local(),
                    "requiresKey": provider.requires_key(),
                    "keyUrl": provider.key_url(),
                    "detail": provider.detail(),
                })
            })
            .collect(),
    )
}

/// Interface languages for the settings dialog.
pub fn languages_json() -> Value {
    Value::Array(
        ofm_i18n::available_languages()
            .iter()
            .map(|language| {
                json!({
                    "code": language.code(),
                    "title": language.picker_title(),
                })
            })
            .collect(),
    )
}

/// The 38 translation languages for the pickers.
pub fn translation_languages_json() -> Value {
    let ui = ofm_i18n::current_language();
    Value::Array(
        LanguageTable::all()
            .iter()
            .map(|language| {
                json!({
                    "code": language.code,
                    "name": language.display_name(ui),
                    "englishName": language.english_name,
                    "isAuto": language.is_auto(),
                })
            })
            .collect(),
    )
}

/// Localised text for a catalogue key (used by the shell for menus).
pub fn localized(key: &str) -> String {
    t_in(key, ofm_i18n::current_language()).to_string()
}

/// Convenience wrapper used by the CLI to render a status line.
pub fn status_line(controller: &AppController) -> String {
    let state = controller.state();
    format!(
        "{} · {} · {}",
        state.backend_status, state.source_language, state.target_language
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_settings() -> AppSettings {
        let path =
            std::env::temp_dir().join(format!("ofm-app-test-{}-settings.json", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let settings = AppSettings {
            model: "hy-mt2:7b".to_string(),
            auto_translate: false,
            ..AppSettings::default()
        };
        settings.save_to(&path);
        settings
    }

    #[test]
    fn empty_text_is_not_translated() {
        let controller = AppController::new();
        controller.set_source_text("   ");
        controller.translate(true);
        let state = controller.state();
        assert!(!state.is_translating);
        assert!(state.translated_text.is_empty());
    }

    #[test]
    fn missing_model_reports_an_error() {
        let controller = AppController::new();
        controller.save_settings({
            let mut settings = temp_settings();
            settings.model.clear();
            settings
        });
        controller.set_source_text("Hello");
        controller.translate(true);
        let state = controller.state();
        assert!(!state.is_translating);
        assert!(state.error_message.is_some());
    }

    #[test]
    fn clear_resets_everything() {
        let controller = AppController::new();
        controller.set_source_text("Hello");
        controller.clear_source();
        let state = controller.state();
        assert!(state.source_text.is_empty());
        assert!(state.translated_text.is_empty());
        assert!(state.detected_language.is_none());
        assert!(state.tokens_per_second.is_none());
        assert!(!state.using_fallback);
    }

    #[test]
    fn style_and_tone_persist_to_settings() {
        let controller = AppController::new();
        controller.set_style("natural");
        controller.set_tone("formal");
        let state = controller.state();
        assert_eq!(state.style, "natural");
        assert_eq!(state.tone, "formal");
        assert_eq!(state.settings.last_style, "natural");
        assert_eq!(state.settings.last_tone, "formal");
    }

    #[test]
    fn tab_switch_is_validated() {
        let controller = AppController::new();
        controller.set_tab("files");
        assert_eq!(controller.state().tab, "files");
        controller.set_tab("nonsense");
        assert_eq!(controller.state().tab, "files");
    }

    #[test]
    fn catalogue_and_provider_json_are_available() {
        assert_eq!(
            AppController::catalog_json()
                .as_array()
                .map(|items| items.len()),
            Some(28)
        );
        assert_eq!(
            providers_json().as_array().map(|items| items.len()),
            Some(9)
        );
        assert_eq!(
            translation_languages_json()
                .as_array()
                .map(|items| items.len()),
            Some(38)
        );
    }
}

#[cfg(test)]
mod translation_tests {
    use super::*;

    // `AppController::new()` applies the language stored in the user's settings,
    // so every test that manipulates the global language must do it *after*
    // construction and restore English afterwards.
    fn controller() -> AppController {
        let controller = AppController::new();
        ofm_i18n::set_language(AppLanguage::En);
        controller
    }

    #[test]
    fn the_catalogue_covers_every_interface_language() {
        let controller = controller();
        let english = controller.translations_json();
        let keys = english.as_object().map(|map| map.len()).unwrap_or(0);
        assert!(keys > 350, "expected the full catalogue, found {keys}");

        for language in ofm_i18n::available_languages() {
            ofm_i18n::set_language(*language);
            let table = controller.translations_json();
            let object = table.as_object().expect("an object");
            assert_eq!(object.len(), keys, "{language:?} table size differs");
        }
        ofm_i18n::set_language(AppLanguage::En);
    }

    #[test]
    fn english_translates_to_itself() {
        let controller = controller();
        assert_eq!(controller.translations_json()["Settings"], "Settings");
        ofm_i18n::set_language(AppLanguage::Uk);
        assert_eq!(controller.translations_json()["Settings"], "Налаштування");
        ofm_i18n::set_language(AppLanguage::En);
    }
}

#[cfg(test)]
mod settings_tests {
    use super::*;

    /// A controller whose settings, history and secrets live in a temp folder,
    /// so tests never read or write the real user profile.
    struct Fixture {
        directory: PathBuf,
        controller: AppController,
    }

    impl Fixture {
        fn new(tag: &str) -> Self {
            let directory = std::env::temp_dir().join(format!(
                "ofm-app-{tag}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|value| value.as_nanos())
                    .unwrap_or(0)
            ));
            std::fs::create_dir_all(&directory).expect("create the temp directory");
            let controller = AppController::with_directory(&directory);
            ofm_i18n::set_language(AppLanguage::En);
            Self {
                directory,
                controller,
            }
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.directory);
        }
    }

    #[test]
    fn api_keys_round_trip_through_the_secret_store() {
        let fixture = Fixture::new("keys");
        let controller = &fixture.controller;

        let mut settings = controller.settings().clone();
        settings.provider = Provider::Groq;
        settings.base_url = Provider::Groq.base_url().to_string();
        settings.model = "llama-3.3-70b-versatile".to_string();
        settings.api_key = "  sk-secret-value  ".to_string();
        controller.save_settings(settings);

        let stored = controller.inner.secrets.read(&Provider::Groq.key_account());
        assert_eq!(stored.trim(), "sk-secret-value");
        assert_eq!(controller.settings().api_key.trim(), "sk-secret-value");

        // A reload reads the key back from the store, not from settings.json.
        let reloaded = AppController::with_directory(&fixture.directory);
        assert_eq!(reloaded.settings().api_key.trim(), "sk-secret-value");

        let disk = std::fs::read_to_string(fixture.directory.join("settings.json"))
            .expect("settings file");
        assert!(
            !disk.contains("sk-secret-value"),
            "the key must never be written to settings.json"
        );

        // Clearing the field removes the secret.
        let mut cleared = controller.settings().clone();
        cleared.api_key = String::new();
        controller.save_settings(cleared);
        assert!(controller
            .inner
            .secrets
            .read(&Provider::Groq.key_account())
            .trim()
            .is_empty());
    }

    #[test]
    fn switching_provider_restores_the_remembered_model() {
        let fixture = Fixture::new("providers");
        let controller = &fixture.controller;

        let mut ollama = controller.settings().clone();
        ollama.provider = Provider::Ollama;
        ollama.base_url = Provider::Ollama.base_url().to_string();
        ollama.model = "hy-mt2:7b".to_string();
        controller.save_settings(ollama);

        let mut groq = controller.settings().clone();
        groq.provider = Provider::Groq;
        groq.base_url = Provider::Groq.base_url().to_string();
        groq.model = "llama-3.3-70b-versatile".to_string();
        controller.save_settings(groq);
        assert_eq!(controller.settings().model, "llama-3.3-70b-versatile");

        // Going back must restore Ollama's own model, not keep Groq's.
        let mut back = controller.settings().clone();
        back.provider = Provider::Ollama;
        back.base_url = Provider::Ollama.base_url().to_string();
        back.model = "llama-3.3-70b-versatile".to_string();
        controller.save_settings(back);
        assert_eq!(
            controller.settings().model,
            "hy-mt2:7b",
            "the previous provider's model must not leak into Ollama"
        );
    }

    #[test]
    fn partial_settings_json_keeps_unrelated_fields() {
        let fixture = Fixture::new("partial");
        let controller = &fixture.controller;
        let before = controller.settings().clone();

        controller.save_settings_json(&json!({ "temperature": 1.15 }));

        let after = controller.settings().clone();
        assert!((after.temperature - 1.15).abs() < 1e-3);
        assert_eq!(after.model, before.model);
        assert_eq!(after.provider, before.provider);
        assert_eq!(after.interface_language, before.interface_language);
    }
}

#[cfg(test)]
mod concurrency_tests {
    use super::*;

    struct Fixture {
        directory: PathBuf,
        controller: AppController,
    }

    impl Fixture {
        fn new(tag: &str) -> Self {
            let directory = std::env::temp_dir().join(format!(
                "ofm-concurrency-{tag}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|value| value.as_nanos())
                    .unwrap_or(0)
            ));
            std::fs::create_dir_all(&directory).expect("create the temp directory");
            let controller = AppController::with_directory(&directory);
            ofm_i18n::set_language(AppLanguage::En);
            Self {
                directory,
                controller,
            }
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.directory);
        }
    }

    /// Run `body` on a worker thread and fail instead of hanging forever.
    ///
    /// Every method reaches for the `state` and `settings` locks, so a lock-order
    /// regression shows up here as a timeout rather than as a wedged app.
    fn within<T: Send + 'static>(seconds: u64, body: impl FnOnce() -> T + Send + 'static) -> T {
        let (sender, receiver) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let value = body();
            let _ = sender.send(value);
        });
        receiver
            .recv_timeout(Duration::from_secs(seconds))
            .expect("the controller deadlocked")
    }

    #[test]
    fn speak_does_not_re_enter_the_state_lock() {
        let fixture = Fixture::new("speak");
        fixture.controller.set_source_text("Hello");
        let controller = fixture.controller.clone();
        // `speak` reads the state to pick the text and the language; taking the
        // same read lock twice used to deadlock here.
        within(5, move || controller.speak("source"));
        within(5, move || {
            let controller = fixture.controller.clone();
            controller.speak("translation");
        });
    }

    #[test]
    fn concurrent_commands_do_not_deadlock() {
        let fixture = Fixture::new("parallel");
        let controller = fixture.controller.clone();
        let workers: Vec<_> = (0..4)
            .map(|index| {
                let controller = controller.clone();
                std::thread::spawn(move || {
                    for step in 0..40 {
                        controller.set_source_text(&format!("text {index}-{step}"));
                        controller.set_style(if step % 2 == 0 { "natural" } else { "auto" });
                        controller.set_tone(if step % 3 == 0 { "formal" } else { "standard" });
                        controller.set_source_language(if step % 2 == 0 { "auto" } else { "en" });
                        controller.set_target_language(if step % 2 == 0 { "uk" } else { "de" });
                        let _ = controller.state();
                        controller.clear_source();
                    }
                })
            })
            .collect();

        for worker in workers {
            let (sender, receiver) = std::sync::mpsc::channel();
            std::thread::spawn(move || {
                let _ = worker.join();
                let _ = sender.send(());
            });
            receiver
                .recv_timeout(Duration::from_secs(20))
                .expect("concurrent commands deadlocked");
        }
    }

    #[test]
    fn style_changes_reach_the_injected_settings_file() {
        let fixture = Fixture::new("settings-path");
        fixture.controller.set_style("natural");
        fixture.controller.set_tone("formal");
        let disk = std::fs::read_to_string(fixture.directory.join("settings.json"))
            .expect("settings file");
        assert!(disk.contains("natural"), "style not persisted: {disk}");
        assert!(disk.contains("formal"), "tone not persisted: {disk}");
    }

    #[test]
    fn an_empty_pane_is_not_served_from_the_cache() {
        let fixture = Fixture::new("cache");
        let controller = &fixture.controller;
        let mut settings = controller.settings().clone();
        settings.model = "hy-mt2:7b".to_string();
        settings.auto_translate = false;
        // Port 1 is closed, so the job fails immediately; the point is that it
        // *starts* instead of being swallowed by the cache.
        settings.base_url = "http://127.0.0.1:1".to_string();
        controller.save_settings(settings);

        controller.set_source_text("Hello");
        controller.translate(true);
        let first = controller.state_guard();
        let started = first.is_translating;
        drop(first);
        assert!(started, "the first request must start");

        controller.cancel();
        controller.clear_source();
        controller.set_source_text("Hello");
        controller.translate(false);
        let second = controller.state_guard();
        assert!(
            second.is_translating,
            "a cleared pane must not be served from the cache"
        );
    }
}
