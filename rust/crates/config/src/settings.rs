//! JSON backed application settings.
//!
//! Ported from `windows/deepl_ofm/core/settings.py` (itself a port of
//! `Sources/HyMT/Models/AppSettings.swift`): the Swift `UserDefaults` keys become
//! one atomic JSON document, API keys stay out of that document, per-provider
//! `base_url`/`model` memory and the "never lose the last entry point" rule are
//! preserved.
//!
//! Two deliberate differences from the Python class:
//!
//! * There is no secret store here — `ofm-store` depends on this crate, not the
//!   other way round. [`AppSettings::api_key`] is a session value: loading a file
//!   never reads a key from disk (a stray `api_key` in the file is ignored) and
//!   [`AppSettings::save`] never writes one. The app layer copies keys from
//!   `ofm_store::SecretStore` using [`Provider::key_account`].
//! * Persistence is explicit. The Python setters saved on every change; here the
//!   fields are public, and the caller persists with [`AppSettings::save`] or
//!   [`AppSettings::save_to`].
//!
//! [`AppSettings::show_in_dock`] and [`AppSettings::remembered`] are additive
//! bookkeeping fields: the dock flag is what makes the Python entry-point rule
//! observable without a Qt/macOS shell, and the map keeps `base_url.<provider>`
//! / `model.<provider>` memory across provider switches in one session.

use std::collections::BTreeMap;
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use ofm_i18n::AppLanguage;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::catalog::{CatalogEntry, ModelCatalog};
use crate::keycombo::KeyCombo;
use crate::providers::{BackendConfig, BackendKind, Provider};

/// Model installed by the default settings.
const DEFAULT_MODEL: &str = "hy-mt2:7b";
/// Allowed values of [`AppSettings::result_view`].
const RESULT_VIEWS: &[&str] = &["preview", "text", "markdown"];
/// Allowed values of [`AppSettings::last_style`].
const STYLES: &[&str] = &["auto", "literal", "natural"];
/// Allowed values of [`AppSettings::last_tone`].
const TONES: &[&str] = &["standard", "formal", "casual"];
/// Keys that carry per-provider memory (`base_url.ollama`, `model.groq`, …).
const MEMORY_PREFIXES: &[&str] = &["base_url", "model", "fallback_base_url", "fallback_model"];
/// Directory created under the configuration root.
const APP_DIR: &str = "DeepL-oFM";
/// File name inside the application directory.
const FILE_NAME: &str = "settings.json";

/// JSON backed settings, independent of Qt and safe to use without a UI.
///
/// Serde serialises the **frontend wire format**: camelCase field names, the
/// provider as its stored value and the hot keys in the same shape as
/// [`KeyCombo::to_json`]. The on-disk file keeps the snake_case document built by
/// [`AppSettings::to_json`] / [`AppSettings::from_json`], so the two formats can
/// evolve independently.
#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", default)]
pub struct AppSettings {
    /// Selected provider.
    pub provider: Provider,
    /// Server address of the selected provider.
    pub base_url: String,
    /// Model identifier sent to the provider.
    pub model: String,
    /// Session-only API key (never persisted; see the module docs).
    pub api_key: String,
    /// Whether a second provider may be used when the first one fails.
    pub fallback_enabled: bool,
    /// Provider used as a fallback.
    pub fallback_provider: Provider,
    /// Server address of the fallback provider.
    pub fallback_base_url: String,
    /// Model identifier of the fallback provider.
    pub fallback_model: String,
    /// Session-only API key of the fallback provider.
    pub fallback_api_key: String,
    /// Sampling temperature.
    pub temperature: f32,
    /// Nucleus sampling probability.
    pub top_p: f32,
    /// Top-K sampling cut-off.
    pub top_k: u32,
    /// Repetition penalty passed to Ollama.
    pub repetition_penalty: f32,
    /// Context window size in tokens.
    pub context_window: u32,
    /// Translate while typing.
    pub auto_translate: bool,
    /// Delay between the last keystroke and an automatic translation.
    pub debounce: f64,
    /// Global shortcut that translates the clipboard.
    pub hot_key: KeyCombo,
    /// Global shortcut that translates the selected text.
    pub selection_hot_key: KeyCombo,
    /// Whether the tray icon is shown.
    pub show_in_menu_bar: bool,
    /// Whether the main window is shown in the taskbar. Kept so the Python
    /// "never lose the last entry point" rule stays meaningful.
    pub show_in_dock: bool,
    /// Identifier of the chosen text-to-speech voice.
    pub speech_voice_id: String,
    /// Whether translations are stored in the history.
    pub keep_history: bool,
    /// Whether a local model is loaded during start-up.
    pub warm_up_on_launch: bool,
    /// Interface language (`System` follows the OS).
    pub interface_language: AppLanguage,
    /// Result presentation mode: `preview`, `text` or `markdown`.
    pub result_view: String,
    /// Last used translation style (`auto`, `literal`, `natural`).
    pub last_style: String,
    /// Last used tone (`standard`, `formal`, `casual`).
    pub last_tone: String,
    /// Last target language code.
    pub last_target_code: String,
    /// Last source language code (`auto` by default).
    pub last_source_code: String,
    /// Per-provider `base_url`/`model` memory from the settings document.
    ///
    /// Keys look like `base_url.ollamaCloud`. Public only so that struct update
    /// syntax keeps working for the app crate; treat it as internal.
    #[doc(hidden)]
    pub remembered: BTreeMap<String, String>,
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            provider: Provider::Ollama,
            base_url: Provider::Ollama.base_url().to_string(),
            model: DEFAULT_MODEL.to_string(),
            api_key: String::new(),
            fallback_enabled: false,
            fallback_provider: Provider::Ollama,
            fallback_base_url: Provider::Ollama.base_url().to_string(),
            fallback_model: String::new(),
            fallback_api_key: String::new(),
            temperature: 0.7,
            top_p: 0.6,
            top_k: 20,
            repetition_penalty: 1.05,
            context_window: 8192,
            auto_translate: true,
            debounce: 0.45,
            hot_key: KeyCombo::standard(),
            selection_hot_key: KeyCombo::selection(),
            show_in_menu_bar: true,
            show_in_dock: true,
            speech_voice_id: String::new(),
            keep_history: true,
            warm_up_on_launch: false,
            interface_language: AppLanguage::System,
            result_view: "preview".to_string(),
            last_style: "auto".to_string(),
            last_tone: "standard".to_string(),
            last_target_code: "en".to_string(),
            last_source_code: "auto".to_string(),
            remembered: BTreeMap::new(),
        }
    }
}

impl AppSettings {
    /// Load the settings file from the platform default location.
    pub fn load() -> Self {
        Self::load_from(&Self::default_path())
    }

    /// Load a settings file, tolerating a missing or malformed document.
    ///
    /// Unknown keys are ignored, bad values fall back to their defaults, and a
    /// stray `api_key` in the file is ignored because keys live in `ofm-store`.
    pub fn load_from(path: &Path) -> Self {
        let raw = match fs::read_to_string(path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Self::default(),
            Err(error) => {
                log::warn!("cannot read settings {}: {error}", path.display());
                return Self::default();
            }
        };
        match serde_json::from_str::<Value>(&raw) {
            Ok(document) => Self::from_json(&document),
            Err(error) => {
                log::warn!("settings {} is not valid JSON: {error}", path.display());
                Self::default()
            }
        }
    }

    /// Write the settings to the platform default location.
    pub fn save(&self) {
        self.save_to(&Self::default_path());
    }

    /// Write the settings document atomically; failures are logged, never raised.
    pub fn save_to(&self, path: &Path) {
        let document = self.to_json();
        let text = match serde_json::to_string_pretty(&document) {
            Ok(text) => text,
            Err(error) => {
                log::warn!("cannot prepare settings for {}: {error}", path.display());
                return;
            }
        };
        let mut payload = text;
        payload.push('\n');
        if let Err(error) = write_atomic(path, &payload) {
            log::warn!("cannot save settings to {}: {error}", path.display());
        }
    }

    /// `%APPDATA%\DeepL-oFM\settings.json`, or the POSIX equivalent.
    ///
    /// On Windows `%APPDATA%` wins; elsewhere `$XDG_CONFIG_HOME` is used, then
    /// `~/.config`. Without a home directory the relative `.config` is used.
    pub fn default_path() -> PathBuf {
        let appdata = std::env::var_os("APPDATA").map(PathBuf::from);
        let xdg = std::env::var_os("XDG_CONFIG_HOME").map(PathBuf::from);
        let home = dirs::home_dir();
        settings_path_for(appdata.as_deref(), xdg.as_deref(), home.as_deref())
    }

    /// The current backend configuration for a translation request.
    pub fn snapshot(&self) -> BackendConfig {
        BackendConfig {
            kind: self.provider.kind(),
            base_url: self.normalized_base_url(),
            model: self.model.trim().to_string(),
            api_key: self.api_key.trim().to_string(),
            temperature: self.temperature,
            top_p: self.top_p,
            top_k: self.top_k,
            repetition_penalty: self.repetition_penalty,
            context_window: self.context_window,
            requires_api_key: self.provider.requires_key(),
        }
    }

    /// Fallback configuration, or `None` when it is disabled or incomplete.
    pub fn fallback_config(&self) -> Option<BackendConfig> {
        if !self.fallback_enabled {
            return None;
        }
        let model = self.fallback_model.trim();
        if model.is_empty() {
            return None;
        }
        let config = self.fallback_config_with_model(model);
        if config.uses_same_endpoint(&self.snapshot()) {
            // Falling back to the same endpoint cannot help anyone.
            return None;
        }
        Some(config)
    }

    /// Fallback endpoint used for the "load models" probe, even when disabled.
    pub fn fallback_probe_config(&self) -> BackendConfig {
        let model = self.fallback_model.trim();
        self.fallback_config_with_model(model)
    }

    /// Switch provider, restoring its remembered model/base URL.
    ///
    /// The previous provider's base URL and model are remembered in
    /// [`Self::remembered`] and written out as `base_url.<provider>` /
    /// `model.<provider>` on the next save. The API key is cleared: the app layer
    /// reloads it from `ofm-store` for the new provider.
    pub fn apply_provider(&mut self, provider: Provider, model: Option<&str>) {
        if provider == self.provider {
            if let Some(model) = model.filter(|model| !model.is_empty()) {
                self.model = model.to_string();
            }
            return;
        }
        let previous = self.provider;
        let previous_base = self.base_url.clone();
        let previous_model = self.model.clone();
        self.remember(previous, &previous_base, &previous_model);

        self.provider = provider;
        self.base_url = self
            .remembered
            .get(&format!("base_url.{}", provider.value()))
            .cloned()
            .unwrap_or_else(|| provider.base_url().to_string());
        self.model = self
            .remembered
            .get(&format!("model.{}", provider.value()))
            .cloned()
            .unwrap_or_default();
        self.api_key.clear();
        if let Some(model) = model.filter(|model| !model.is_empty()) {
            self.model = model.to_string();
        }
    }

    /// Switch the fallback provider, restoring its remembered model/base URL.
    pub fn apply_fallback_provider(&mut self, provider: Provider, model: Option<&str>) {
        if provider == self.fallback_provider {
            if let Some(model) = model.filter(|model| !model.is_empty()) {
                self.fallback_model = model.to_string();
            }
            return;
        }
        let previous = self.fallback_provider;
        let previous_base = self.fallback_base_url.clone();
        let previous_model = self.fallback_model.clone();
        self.remember_fallback(previous, &previous_base, &previous_model);

        self.fallback_provider = provider;
        self.fallback_base_url = self
            .remembered
            .get(&format!("fallback_base_url.{}", provider.value()))
            .cloned()
            .unwrap_or_else(|| provider.base_url().to_string());
        self.fallback_model = self
            .remembered
            .get(&format!("fallback_model.{}", provider.value()))
            .cloned()
            .unwrap_or_default();
        self.fallback_api_key.clear();
        if let Some(model) = model.filter(|model| !model.is_empty()) {
            self.fallback_model = model.to_string();
        }
    }

    /// Apply a catalogue entry: provider plus its model id.
    pub fn apply_catalog_entry(&mut self, entry: &CatalogEntry) {
        self.apply_provider(entry.provider, Some(entry.model_id));
    }

    /// Ollama command that installs the currently selected model.
    pub fn install_command(&self) -> Option<&'static str> {
        ModelCatalog::install_command(&self.model)
    }

    /// Forget the API key of the selected provider (session value only).
    pub fn clear_key(&mut self) {
        self.api_key.clear();
    }

    /// Base URL without trailing slashes, never empty.
    pub fn normalized_base_url(&self) -> String {
        normalize_base(&self.base_url, self.provider.base_url())
    }

    /// Fallback base URL without trailing slashes, never empty.
    pub fn normalized_fallback_base_url(&self) -> String {
        normalize_base(&self.fallback_base_url, self.fallback_provider.base_url())
    }

    /// Force the "never lose the last entry point" rule.
    ///
    /// Disabling the tray icon while the window is also hidden from the taskbar
    /// would leave the app unreachable, so the dock entry point comes back.
    pub fn apply_entry_point_rule(&mut self) {
        if !self.show_in_menu_bar && !self.show_in_dock {
            self.show_in_dock = true;
        }
    }

    /// Show or hide the tray icon, keeping at least one entry point reachable.
    pub fn set_show_in_menu_bar(&mut self, enabled: bool) {
        self.show_in_menu_bar = enabled;
        self.apply_entry_point_rule();
    }

    /// Show or hide the taskbar entry, keeping at least one entry point reachable.
    pub fn set_show_in_dock(&mut self, enabled: bool) {
        self.show_in_dock = enabled;
        if !enabled && !self.show_in_menu_bar {
            self.show_in_menu_bar = true;
        }
    }

    /// Set the result view, falling back to `preview` for unknown modes.
    pub fn set_result_view(&mut self, mode: &str) {
        self.result_view = choice(mode, RESULT_VIEWS, "preview");
    }

    /// Set the interface language, falling back to `System` for unknown codes.
    pub fn set_interface_language(&mut self, language: &str) {
        self.interface_language = coerce_language(language);
    }

    /// The persisted settings document (API keys excluded).
    pub fn to_json(&self) -> Value {
        let mut object = Map::new();
        object.insert(
            "provider".to_string(),
            Value::String(self.provider.value().to_string()),
        );
        object.insert("base_url".to_string(), Value::String(self.base_url.clone()));
        object.insert("model".to_string(), Value::String(self.model.clone()));
        object.insert(
            "fallback_enabled".to_string(),
            Value::Bool(self.fallback_enabled),
        );
        object.insert(
            "fallback_provider".to_string(),
            Value::String(self.fallback_provider.value().to_string()),
        );
        object.insert(
            "fallback_base_url".to_string(),
            Value::String(self.fallback_base_url.clone()),
        );
        object.insert(
            "fallback_model".to_string(),
            Value::String(self.fallback_model.clone()),
        );
        object.insert("temperature".to_string(), number_f32(self.temperature));
        object.insert("top_p".to_string(), number_f32(self.top_p));
        object.insert("top_k".to_string(), Value::from(self.top_k));
        object.insert(
            "repetition_penalty".to_string(),
            number_f32(self.repetition_penalty),
        );
        object.insert(
            "context_window".to_string(),
            Value::from(self.context_window),
        );
        object.insert(
            "auto_translate".to_string(),
            Value::Bool(self.auto_translate),
        );
        object.insert("debounce".to_string(), number_f64(self.debounce));
        object.insert("hot_key".to_string(), self.hot_key.to_json());
        object.insert(
            "selection_hot_key".to_string(),
            self.selection_hot_key.to_json(),
        );
        object.insert(
            "show_in_menu_bar".to_string(),
            Value::Bool(self.show_in_menu_bar),
        );
        object.insert("show_in_dock".to_string(), Value::Bool(self.show_in_dock));
        object.insert(
            "speech_voice_id".to_string(),
            Value::String(self.speech_voice_id.clone()),
        );
        object.insert("keep_history".to_string(), Value::Bool(self.keep_history));
        object.insert(
            "warm_up_on_launch".to_string(),
            Value::Bool(self.warm_up_on_launch),
        );
        object.insert(
            "interface_language".to_string(),
            Value::String(self.interface_language.code().to_string()),
        );
        object.insert(
            "result_view".to_string(),
            Value::String(self.result_view.clone()),
        );
        object.insert(
            "last_style".to_string(),
            Value::String(self.last_style.clone()),
        );
        object.insert(
            "last_tone".to_string(),
            Value::String(self.last_tone.clone()),
        );
        object.insert(
            "last_target_code".to_string(),
            Value::String(self.last_target_code.clone()),
        );
        object.insert(
            "last_source_code".to_string(),
            Value::String(self.last_source_code.clone()),
        );
        for (key, value) in &self.remembered {
            object.insert(key.clone(), Value::String(value.clone()));
        }
        Value::Object(object)
    }

    /// Tolerant parser for a settings document.
    ///
    /// Mirrors the Python `_apply_document`: unknown keys ignored, bad values
    /// replaced by defaults, camelCase aliases accepted, `api_key` ignored.
    pub fn from_json(document: &Value) -> Self {
        let mut settings = Self::default();
        let Some(object) = document.as_object() else {
            return settings;
        };

        let mut flat: BTreeMap<String, Value> = BTreeMap::new();
        for (raw_key, raw_value) in object {
            let key = raw_key.trim();
            if key.is_empty() {
                continue;
            }
            if let Some((raw_prefix, suffix)) = key.split_once('.') {
                let prefix = memory_alias(raw_prefix);
                let suffix = suffix.trim();
                if MEMORY_PREFIXES.contains(&prefix) && !suffix.is_empty() {
                    if let Value::String(text) = raw_value {
                        settings
                            .remembered
                            .insert(format!("{prefix}.{suffix}"), text.clone());
                    }
                }
                continue;
            }
            flat.insert(canonical_key(key).to_string(), raw_value.clone());
        }

        let legacy_kind = flat
            .get("backend")
            .and_then(Value::as_str)
            .and_then(BackendKind::from_stored)
            .unwrap_or(BackendKind::Ollama);
        let mut stored_base = string_value(flat.get("base_url"), "").trim().to_string();
        let stored_provider = flat
            .get("provider")
            .and_then(Value::as_str)
            .and_then(Provider::from_value);
        let provider = match stored_provider {
            Some(provider) => {
                if stored_base.is_empty() {
                    stored_base = provider.base_url().to_string();
                }
                provider
            }
            None => {
                if stored_base.is_empty() {
                    stored_base = legacy_kind.default_base_url().to_string();
                }
                Provider::infer(legacy_kind, &stored_base)
            }
        };
        settings.provider = provider;
        settings.base_url = stored_base;
        settings.model = string_value(flat.get("model"), DEFAULT_MODEL);

        let fallback_provider = flat
            .get("fallback_provider")
            .and_then(Value::as_str)
            .and_then(Provider::from_value)
            .unwrap_or(Provider::Ollama);
        settings.fallback_provider = fallback_provider;
        settings.fallback_enabled = bool_value(flat.get("fallback_enabled"), false);
        settings.fallback_base_url =
            string_value(flat.get("fallback_base_url"), fallback_provider.base_url());
        settings.fallback_model = string_value(flat.get("fallback_model"), "");

        settings.temperature = float_value(flat.get("temperature"), 0.7) as f32;
        settings.top_p = float_value(flat.get("top_p"), 0.6) as f32;
        settings.top_k = u32_value(flat.get("top_k"), 20);
        settings.repetition_penalty = float_value(flat.get("repetition_penalty"), 1.05) as f32;
        settings.context_window = u32_value(flat.get("context_window"), 8192);
        settings.auto_translate = bool_value(flat.get("auto_translate"), true);
        settings.debounce = float_value(flat.get("debounce"), 0.45);
        settings.hot_key = combo_value(flat.get("hot_key"), &KeyCombo::standard());
        settings.selection_hot_key =
            combo_value(flat.get("selection_hot_key"), &KeyCombo::selection());
        settings.show_in_menu_bar = bool_value(flat.get("show_in_menu_bar"), true);
        settings.show_in_dock = bool_value(flat.get("show_in_dock"), true);
        settings.speech_voice_id = string_value(flat.get("speech_voice_id"), "");
        settings.keep_history = bool_value(flat.get("keep_history"), true);
        settings.warm_up_on_launch = bool_value(flat.get("warm_up_on_launch"), false);
        if let Some(language) = flat.get("interface_language") {
            settings.interface_language = language_value(language);
        }
        settings.result_view = choice_value(flat.get("result_view"), RESULT_VIEWS, "preview");
        settings.last_style = exact_choice(flat.get("last_style"), STYLES, "auto");
        settings.last_tone = exact_choice(flat.get("last_tone"), TONES, "standard");
        settings.last_target_code = code_value(flat.get("last_target_code"), "en");
        settings.last_source_code = code_value(flat.get("last_source_code"), "auto");

        // API keys never come from disk; the app layer reads them from ofm-store.
        settings.api_key.clear();
        settings.fallback_api_key.clear();
        settings.apply_entry_point_rule();
        settings
    }

    /// Remember the primary endpoint of a provider being switched away from.
    fn remember(&mut self, provider: Provider, base_url: &str, model: &str) {
        self.remembered.insert(
            format!("base_url.{}", provider.value()),
            base_url.to_string(),
        );
        self.remembered
            .insert(format!("model.{}", provider.value()), model.to_string());
    }

    /// Remember the fallback endpoint of a provider being switched away from.
    fn remember_fallback(&mut self, provider: Provider, base_url: &str, model: &str) {
        self.remembered.insert(
            format!("fallback_base_url.{}", provider.value()),
            base_url.to_string(),
        );
        self.remembered.insert(
            format!("fallback_model.{}", provider.value()),
            model.to_string(),
        );
    }

    /// Build a [`BackendConfig`] from the fallback fields and a trimmed model.
    fn fallback_config_with_model(&self, model: &str) -> BackendConfig {
        BackendConfig {
            kind: self.fallback_provider.kind(),
            base_url: self.normalized_fallback_base_url(),
            model: model.to_string(),
            api_key: self.fallback_api_key.trim().to_string(),
            temperature: self.temperature,
            top_p: self.top_p,
            top_k: self.top_k,
            repetition_penalty: self.repetition_penalty,
            context_window: self.context_window,
            requires_api_key: self.fallback_provider.requires_key(),
        }
    }
}

/// Compute the settings path from the platform environment values.
fn settings_path_for(appdata: Option<&Path>, xdg: Option<&Path>, home: Option<&Path>) -> PathBuf {
    let configured = || {
        xdg.filter(|path| path.is_absolute())
            .map(Path::to_path_buf)
            .or_else(|| home.map(|home| home.join(".config")))
    };
    let root = if cfg!(windows) {
        appdata
            .filter(|path| !path.as_os_str().is_empty())
            .map(Path::to_path_buf)
            .or_else(configured)
    } else {
        configured()
    };
    root.unwrap_or_else(|| PathBuf::from(".config"))
        .join(APP_DIR)
        .join(FILE_NAME)
}

/// Strip trailing slashes from a base URL, falling back to the provider default.
fn normalize_base(value: &str, fallback: &str) -> String {
    let mut text = value.trim().to_string();
    while text.ends_with('/') {
        text.pop();
    }
    if text.is_empty() {
        fallback.to_string()
    } else {
        text
    }
}

/// Serialise an `f32` with the shortest representation that round-trips.
fn number_f32(value: f32) -> Value {
    if !value.is_finite() {
        return Value::Null;
    }
    match value.to_string().parse::<f64>() {
        Ok(parsed) => number_f64(parsed),
        Err(_) => Value::Null,
    }
}

/// Serialise an `f64`, emitting JSON `null` for non-finite values.
fn number_f64(value: f64) -> Value {
    serde_json::Number::from_f64(value).map_or(Value::Null, Value::Number)
}

/// Write `text` to `path` through a temporary file in the same directory.
fn write_atomic(path: &Path, text: &str) -> io::Result<()> {
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    let mut last_error: Option<io::Error> = None;
    for attempt in 0..8 {
        let temporary = parent.join(format!(".{FILE_NAME}.{}.{attempt}.tmp", std::process::id()));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
        {
            Ok(mut file) => {
                let written = file
                    .write_all(text.as_bytes())
                    .and_then(|()| file.sync_all());
                drop(file);
                if let Err(error) = written {
                    let _ = fs::remove_file(&temporary);
                    return Err(error);
                }
                if let Err(error) = fs::rename(&temporary, path) {
                    let _ = fs::remove_file(&temporary);
                    return Err(error);
                }
                return Ok(());
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                last_error = Some(error);
            }
            Err(error) => return Err(error),
        }
    }
    Err(last_error.unwrap_or_else(|| io::Error::other("cannot create a temporary settings file")))
}

/// Canonical snake_case name for a camelCase settings alias.
fn canonical_key(key: &str) -> &str {
    match key {
        "baseURL" | "baseUrl" => "base_url",
        "fallbackEnabled" => "fallback_enabled",
        "fallbackProvider" => "fallback_provider",
        "fallbackBaseURL" | "fallbackBaseUrl" => "fallback_base_url",
        "fallbackModel" => "fallback_model",
        "topP" => "top_p",
        "topK" => "top_k",
        "repetitionPenalty" => "repetition_penalty",
        "contextWindow" => "context_window",
        "autoTranslate" => "auto_translate",
        "hotKey" => "hot_key",
        "selectionHotKey" => "selection_hot_key",
        "showInMenuBar" => "show_in_menu_bar",
        "showInDock" => "show_in_dock",
        "speechVoiceID" | "speechVoiceId" => "speech_voice_id",
        "keepHistory" => "keep_history",
        "warmUpOnLaunch" => "warm_up_on_launch",
        "interfaceLanguage" => "interface_language",
        "resultView" => "result_view",
        "lastStyle" => "last_style",
        "lastTone" => "last_tone",
        "lastTargetCode" => "last_target_code",
        "lastSourceCode" => "last_source_code",
        "lastTarget" => "last_target_code",
        "lastSource" => "last_source_code",
        _ => key,
    }
}

/// Canonical prefix for a per-provider memory key.
fn memory_alias(prefix: &str) -> &str {
    match prefix {
        "baseURL" | "baseUrl" => "base_url",
        "fallbackBaseURL" | "fallbackBaseUrl" => "fallback_base_url",
        "fallbackModel" => "fallback_model",
        _ => prefix,
    }
}

/// A JSON string, or `default` for anything else.
fn string_value(value: Option<&Value>, default: &str) -> String {
    match value {
        Some(Value::String(text)) => text.clone(),
        _ => default.to_string(),
    }
}

/// A trimmed, non-empty JSON string, or `default`.
fn code_value(value: Option<&Value>, default: &str) -> String {
    match value {
        Some(Value::String(text)) if !text.trim().is_empty() => text.trim().to_string(),
        _ => default.to_string(),
    }
}

/// A JSON boolean (or integer `0`/`1`), or `default` for anything else.
fn bool_value(value: Option<&Value>, default: bool) -> bool {
    match value {
        Some(Value::Bool(flag)) => *flag,
        Some(Value::Number(number)) => match number.as_i64() {
            Some(0) => false,
            Some(1) => true,
            _ => default,
        },
        _ => default,
    }
}

/// A JSON number, or `default` for booleans and non-numbers.
fn float_value(value: Option<&Value>, default: f64) -> f64 {
    match value {
        Some(Value::Number(number)) => number.as_f64().unwrap_or(default),
        _ => default,
    }
}

/// A non-negative integral JSON number that fits in `u32`, or `default`.
fn u32_value(value: Option<&Value>, default: u32) -> u32 {
    match value {
        Some(Value::Number(number)) => {
            if let Some(integer) = number.as_u64() {
                return u32::try_from(integer).unwrap_or(default);
            }
            match number.as_f64() {
                Some(real)
                    if real.is_finite()
                        && real.fract() == 0.0
                        && (0.0..=f64::from(u32::MAX)).contains(&real) =>
                {
                    real as u32
                }
                _ => default,
            }
        }
        _ => default,
    }
}

/// A validated hot key, or a clone of `default` when the value is unusable.
fn combo_value(value: Option<&Value>, default: &KeyCombo) -> KeyCombo {
    match value {
        Some(value @ Value::Object(_)) => {
            let combo = KeyCombo::from_json(value);
            if combo.is_valid() {
                combo
            } else {
                default.clone()
            }
        }
        _ => default.clone(),
    }
}

/// One of `choices` after trimming and lower-casing, or `default`.
fn choice_value(value: Option<&Value>, choices: &[&str], default: &str) -> String {
    match value {
        Some(Value::String(text)) => choice(text, choices, default),
        _ => default.to_string(),
    }
}

/// One of `choices` after trimming and lower-casing, or `default`.
fn choice(text: &str, choices: &[&str], default: &str) -> String {
    let lowered = text.trim().to_lowercase();
    if choices.contains(&lowered.as_str()) {
        lowered
    } else {
        default.to_string()
    }
}

/// One of `choices` after trimming (case-sensitive, like the Python enum), or
/// `default`.
fn exact_choice(value: Option<&Value>, choices: &[&str], default: &str) -> String {
    match value {
        Some(Value::String(text)) if choices.contains(&text.trim()) => text.trim().to_string(),
        _ => default.to_string(),
    }
}

/// Tolerant `AppLanguage` lookup: `"uk_UA"` and `"uk-UA"` both mean `Uk`.
fn language_value(value: &Value) -> AppLanguage {
    match value {
        Value::String(text) => coerce_language(text),
        _ => AppLanguage::System,
    }
}

/// Tolerant `AppLanguage` lookup; unknown codes fall back to `System`.
fn coerce_language(text: &str) -> AppLanguage {
    let code = text.trim().to_lowercase().replace('-', "_");
    if code.is_empty() || code == "system" {
        return AppLanguage::System;
    }
    let primary = code.split('_').next().unwrap_or("");
    if primary == "ua" {
        return AppLanguage::Uk;
    }
    AppLanguage::from_code(primary).unwrap_or(AppLanguage::System)
}

#[cfg(test)]
mod tests {
    // The ported Python cases assign properties one by one; keep that shape.
    #![allow(clippy::field_reassign_with_default)]

    use super::*;
    use serde_json::json;
    use std::sync::atomic::{AtomicU64, Ordering};

    /// Self-cleaning temporary directory (no dev-dependency needed).
    struct TempDir {
        path: PathBuf,
    }

    impl TempDir {
        fn new() -> Self {
            static COUNTER: AtomicU64 = AtomicU64::new(0);
            let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
            let path = std::env::temp_dir()
                .join(format!("ofm-config-test-{}-{unique}", std::process::id()));
            fs::create_dir_all(&path).expect("create temp dir");
            Self { path }
        }

        fn settings_path(&self) -> PathBuf {
            self.path.join(APP_DIR).join(FILE_NAME)
        }
    }

    impl Drop for TempDir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn write_json(path: &Path, payload: &Value) {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).expect("create parent");
        }
        fs::write(path, serde_json::to_string(payload).expect("serialise")).expect("write file");
    }

    fn read_json(path: &Path) -> Value {
        let raw = fs::read_to_string(path).expect("read settings");
        serde_json::from_str(&raw).expect("parse settings")
    }

    #[test]
    fn defaults_match_the_swift_initialiser() {
        let settings = AppSettings::default();
        assert_eq!(settings.provider, Provider::Ollama);
        assert_eq!(settings.base_url, "http://127.0.0.1:11434");
        assert_eq!(settings.model, "hy-mt2:7b");
        assert_eq!(settings.api_key, "");
        assert_eq!(settings.provider.kind(), BackendKind::Ollama);

        assert!(!settings.fallback_enabled);
        assert_eq!(settings.fallback_provider, Provider::Ollama);
        assert_eq!(settings.fallback_base_url, "http://127.0.0.1:11434");
        assert_eq!(settings.fallback_model, "");
        assert_eq!(settings.fallback_api_key, "");

        assert_eq!(settings.temperature, 0.7);
        assert_eq!(settings.top_p, 0.6);
        assert_eq!(settings.top_k, 20);
        assert_eq!(settings.repetition_penalty, 1.05);
        assert_eq!(settings.context_window, 8192);

        assert!(settings.auto_translate);
        assert_eq!(settings.debounce, 0.45);
        assert_eq!(settings.hot_key, KeyCombo::standard());
        assert_eq!(settings.selection_hot_key, KeyCombo::selection());

        assert!(settings.show_in_menu_bar);
        assert!(settings.show_in_dock);
        assert_eq!(settings.speech_voice_id, "");
        assert!(settings.keep_history);
        assert!(!settings.warm_up_on_launch);
        assert_eq!(settings.interface_language, AppLanguage::System);
        assert_eq!(settings.result_view, "preview");

        assert_eq!(settings.last_style, "auto");
        assert_eq!(settings.last_tone, "standard");
        assert_eq!(settings.last_target_code, "en");
        assert_eq!(settings.last_source_code, "auto");
    }

    #[test]
    fn missing_file_loads_defaults() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        assert!(!path.exists());
        assert_eq!(AppSettings::load_from(&path), AppSettings::default());
        assert_eq!(AppSettings::load_from(&path).model, "hy-mt2:7b");
    }

    #[test]
    fn corrupt_file_is_tolerated() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        fs::create_dir_all(path.parent().expect("parent")).expect("mkdir");
        fs::write(&path, "{ this is not json").expect("write");

        let mut settings = AppSettings::load_from(&path);
        assert_eq!(settings.model, "hy-mt2:7b");
        assert_eq!(settings.temperature, 0.7);

        // A save repairs the file.
        settings.temperature = 0.3;
        settings.save_to(&path);
        assert_eq!(
            read_json(&path)["temperature"].as_f64(),
            Some(0.3),
            "the repaired file must contain the new temperature"
        );
    }

    #[test]
    fn json_array_is_tolerated() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(&path, &json!([1, 2, 3]));
        assert_eq!(AppSettings::load_from(&path).provider, Provider::Ollama);
        assert_eq!(
            AppSettings::from_json(&json!("nope")),
            AppSettings::default()
        );
    }

    #[test]
    fn bad_values_fall_back_to_defaults() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({
                "provider": "nonsense",
                "base_url": "http://127.0.0.1:11434",
                "model": 42,
                "temperature": "hot",
                "top_p": null,
                "top_k": "many",
                "repetition_penalty": [1.0],
                "context_window": 1.5,
                "debounce": null,
                "hot_key": "Ctrl+Alt+T",
                "selection_hot_key": {"key": ""},
                "result_view": "bogus",
                "last_style": "nope",
                "last_tone": 3,
                "interface_language": 7,
                "keep_history": "yes",
                "last_target_code": "",
            }),
        );
        let settings = AppSettings::load_from(&path);

        assert_eq!(settings.provider, Provider::Ollama);
        assert_eq!(settings.model, "hy-mt2:7b");
        assert_eq!(settings.temperature, 0.7);
        assert_eq!(settings.top_p, 0.6);
        assert_eq!(settings.top_k, 20);
        assert_eq!(settings.repetition_penalty, 1.05);
        assert_eq!(settings.context_window, 8192);
        assert_eq!(settings.debounce, 0.45);
        assert_eq!(settings.hot_key, KeyCombo::standard());
        assert_eq!(settings.selection_hot_key, KeyCombo::selection());
        assert_eq!(settings.result_view, "preview");
        assert_eq!(settings.last_style, "auto");
        assert_eq!(settings.last_tone, "standard");
        assert_eq!(settings.interface_language, AppLanguage::System);
        assert!(settings.keep_history);
        assert_eq!(settings.last_target_code, "en");
    }

    #[test]
    fn unknown_keys_are_ignored() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({"model": "hy-mt2:1.8b", "future_key": {"a": 1}}),
        );

        let mut settings = AppSettings::load_from(&path);
        assert_eq!(settings.model, "hy-mt2:1.8b");
        settings.top_k = 10;
        settings.save_to(&path);
        let data = read_json(&path);
        assert!(data.get("future_key").is_none());
        assert_eq!(data["model"], "hy-mt2:1.8b");
    }

    #[test]
    fn camel_case_aliases_are_accepted() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({
                "baseURL": "http://127.0.0.1:1234/v1",
                "topP": 0.5,
                "hotKey": {"key": "k", "command": true},
                "lastTarget": "de",
                "interfaceLanguage": "uk",
            }),
        );
        let settings = AppSettings::load_from(&path);
        assert_eq!(settings.base_url, "http://127.0.0.1:1234/v1");
        assert_eq!(settings.top_p, 0.5);
        assert_eq!(
            settings.hot_key,
            KeyCombo {
                key: "k".to_string(),
                ctrl: true,
                ..KeyCombo::default()
            }
        );
        assert_eq!(settings.last_target_code, "de");
        assert_eq!(settings.interface_language, AppLanguage::Uk);
    }

    #[test]
    fn legacy_backend_key_is_understood() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({"backend": "openAI", "base_url": "https://openrouter.ai/api/v1"}),
        );
        let settings = AppSettings::load_from(&path);
        assert_eq!(settings.provider, Provider::OpenRouter);
        assert_eq!(settings.provider.kind(), BackendKind::OpenAI);
        assert_eq!(settings.base_url, "https://openrouter.ai/api/v1");
    }

    #[test]
    fn stored_provider_without_base_url_uses_its_default() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({"provider": "groq", "model": "openai/gpt-oss-120b"}),
        );
        let settings = AppSettings::load_from(&path);
        assert_eq!(settings.provider, Provider::Groq);
        assert_eq!(settings.base_url, Provider::Groq.base_url());
        assert_eq!(
            settings.snapshot().base_url,
            "https://api.groq.com/openai/v1"
        );
    }

    #[test]
    fn non_string_provider_memory_is_ignored() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({
                "provider": "ollama",
                "base_url": "http://127.0.0.1:11434",
                "model.x": null,
            }),
        );
        let mut settings = AppSettings::load_from(&path);
        settings.apply_provider(Provider::Groq, None);
        assert_eq!(settings.base_url, Provider::Groq.base_url());
    }

    #[test]
    fn save_and_reload_round_trip() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();

        settings.apply_provider(Provider::Groq, None);
        settings.model = "openai/gpt-oss-120b".to_string();
        settings.api_key = "gsk-test-key".to_string();
        settings.temperature = 0.2;
        settings.top_p = 0.9;
        settings.top_k = 5;
        settings.repetition_penalty = 1.2;
        settings.context_window = 4096;
        settings.auto_translate = false;
        settings.debounce = 0.8;
        settings.hot_key = KeyCombo {
            key: "k".to_string(),
            ctrl: true,
            shift: true,
            ..KeyCombo::default()
        };
        settings.selection_hot_key = KeyCombo {
            key: "j".to_string(),
            alt: true,
            ..KeyCombo::default()
        };
        settings.interface_language = AppLanguage::De;
        settings.result_view = "markdown".to_string();
        settings.last_style = "literal".to_string();
        settings.last_tone = "formal".to_string();
        settings.last_target_code = "uk".to_string();
        settings.last_source_code = "de".to_string();
        settings.keep_history = false;
        settings.warm_up_on_launch = true;
        settings.speech_voice_id = "voice-1".to_string();
        settings.set_show_in_menu_bar(false);
        settings.save_to(&path);

        let raw = fs::read_to_string(&path).expect("read settings");
        assert!(!raw.contains("gsk-test-key"));
        let data = read_json(&path);
        assert!(data.get("api_key").is_none());
        assert_eq!(data["base_url.ollama"], "http://127.0.0.1:11434");
        assert_eq!(data["model.ollama"], "hy-mt2:7b");
        assert!(!data["show_in_menu_bar"].as_bool().unwrap_or(true));
        assert!(data["show_in_dock"].as_bool().unwrap_or(false));

        let reloaded = AppSettings::load_from(&path);
        assert_eq!(reloaded.provider, Provider::Groq);
        assert_eq!(reloaded.model, "openai/gpt-oss-120b");
        assert_eq!(reloaded.api_key, "", "keys are never read from the file");
        assert_eq!(reloaded.temperature, 0.2);
        assert_eq!(reloaded.top_p, 0.9);
        assert_eq!(reloaded.top_k, 5);
        assert_eq!(reloaded.repetition_penalty, 1.2);
        assert_eq!(reloaded.context_window, 4096);
        assert!(!reloaded.auto_translate);
        assert_eq!(reloaded.debounce, 0.8);
        assert_eq!(reloaded.hot_key, settings.hot_key);
        assert_eq!(reloaded.selection_hot_key, settings.selection_hot_key);
        assert_eq!(reloaded.interface_language, AppLanguage::De);
        assert_eq!(reloaded.result_view, "markdown");
        assert_eq!(reloaded.last_style, "literal");
        assert_eq!(reloaded.last_tone, "formal");
        assert_eq!(reloaded.last_target_code, "uk");
        assert_eq!(reloaded.last_source_code, "de");
        assert!(!reloaded.keep_history);
        assert!(reloaded.warm_up_on_launch);
        assert_eq!(reloaded.speech_voice_id, "voice-1");
        assert!(!reloaded.show_in_menu_bar);
        assert!(reloaded.show_in_dock);
    }

    #[test]
    fn per_provider_memory() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.base_url = "http://127.0.0.1:9999".to_string();
        settings.model = "custom-model".to_string();

        settings.apply_provider(Provider::Groq, None);
        assert_eq!(settings.provider, Provider::Groq);
        assert_eq!(settings.base_url, Provider::Groq.base_url());
        assert_eq!(settings.model, "");
        assert_eq!(settings.api_key, "");

        settings.apply_provider(Provider::Ollama, None);
        assert_eq!(settings.provider, Provider::Ollama);
        assert_eq!(settings.base_url, "http://127.0.0.1:9999");
        assert_eq!(settings.model, "custom-model");

        settings.save_to(&path);
        let data = read_json(&path);
        assert_eq!(data["base_url.groq"], Provider::Groq.base_url());
        assert_eq!(data["model.groq"], "");
        assert_eq!(data["base_url.ollama"], "http://127.0.0.1:9999");

        // Memory survives a restart.
        let mut restarted = AppSettings::load_from(&path);
        assert_eq!(restarted.base_url, "http://127.0.0.1:9999");
        restarted.apply_provider(Provider::Groq, None);
        restarted.apply_provider(Provider::Ollama, None);
        assert_eq!(restarted.base_url, "http://127.0.0.1:9999");
        assert_eq!(restarted.model, "custom-model");
    }

    #[test]
    fn apply_provider_with_model() {
        let mut settings = AppSettings::default();
        settings.apply_provider(Provider::OpenRouter, Some("tencent/hy-mt2-7b"));
        assert_eq!(settings.provider, Provider::OpenRouter);
        assert_eq!(settings.base_url, Provider::OpenRouter.base_url());
        assert_eq!(settings.model, "tencent/hy-mt2-7b");
        assert_eq!(settings.provider.kind(), BackendKind::OpenAI);
    }

    #[test]
    fn apply_provider_on_the_same_provider_updates_only_the_model() {
        let mut settings = AppSettings::default();
        settings.base_url = "http://127.0.0.1:9999".to_string();
        settings.apply_provider(Provider::Ollama, Some("qwen3:8b"));
        assert_eq!(settings.model, "qwen3:8b");
        assert_eq!(settings.base_url, "http://127.0.0.1:9999");
        settings.apply_provider(Provider::Ollama, None);
        assert_eq!(settings.model, "qwen3:8b");
    }

    #[test]
    fn api_key_never_reaches_the_json_file() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.api_key = "super-secret".to_string();
        settings.save_to(&path);
        let raw = fs::read_to_string(&path).expect("read settings");
        assert!(!raw.contains("super-secret"));
        assert_eq!(settings.api_key, "super-secret");
        assert!(read_json(&path).get("api_key").is_none());
    }

    #[test]
    fn clear_key_only_clears_the_session_value() {
        let mut settings = AppSettings::default();
        settings.api_key = "secret".to_string();
        settings.clear_key();
        assert_eq!(settings.api_key, "");
    }

    #[test]
    fn snapshot() {
        let mut settings = AppSettings::default();
        settings.base_url = "http://127.0.0.1:11434///".to_string();
        settings.model = "  hy-mt2:7b  ".to_string();
        settings.temperature = 0.4;
        settings.top_p = 0.5;
        settings.top_k = 12;
        settings.repetition_penalty = 1.1;
        settings.context_window = 2048;
        let config = settings.snapshot();

        assert_eq!(config.kind, BackendKind::Ollama);
        assert_eq!(config.base_url, "http://127.0.0.1:11434");
        assert_eq!(config.model, "hy-mt2:7b");
        assert_eq!(config.api_key, "");
        assert_eq!(config.temperature, 0.4);
        assert_eq!(config.top_p, 0.5);
        assert_eq!(config.top_k, 12);
        assert_eq!(config.repetition_penalty, 1.1);
        assert_eq!(config.context_window, 2048);
        assert!(!config.requires_api_key);

        settings.apply_provider(Provider::Groq, Some("openai/gpt-oss-120b"));
        let groq = settings.snapshot();
        assert_eq!(groq.kind, BackendKind::OpenAI);
        assert!(groq.requires_api_key);
        assert_eq!(groq.base_url, "https://api.groq.com/openai/v1");
    }

    #[test]
    fn fallback_config_requires_enabled_and_model() {
        let mut settings = AppSettings::default();
        assert!(settings.fallback_config().is_none());

        settings.fallback_model = "qwen3:8b".to_string();
        assert!(settings.fallback_config().is_none());

        settings.fallback_enabled = true;
        let config = settings.fallback_config().expect("fallback config");
        assert_eq!(config.kind, BackendKind::Ollama);
        assert_eq!(config.base_url, "http://127.0.0.1:11434");
        assert_eq!(config.model, "qwen3:8b");
        assert_eq!(config.api_key, "");
        assert_eq!(config.temperature, settings.temperature);
        assert!(!config.requires_api_key);

        settings.apply_fallback_provider(Provider::OpenRouter, None);
        settings.fallback_model = " tencent/hy-mt2-7b ".to_string();
        let config = settings.fallback_config().expect("fallback config");
        assert_eq!(config.kind, BackendKind::OpenAI);
        assert_eq!(config.base_url, "https://openrouter.ai/api/v1");
        assert_eq!(config.model, "tencent/hy-mt2-7b");
        assert!(config.requires_api_key);
    }

    #[test]
    fn fallback_equal_to_primary_is_none() {
        let mut settings = AppSettings::default();
        settings.fallback_enabled = true;
        settings.fallback_model = "hy-mt2:7b".to_string();
        settings.fallback_base_url = settings.base_url.clone();
        assert!(settings.fallback_config().is_none());

        // Same provider and base URL but another model is a real fallback:
        // `uses_same_endpoint` compares the model too (Swift parity).
        settings.fallback_model = "qwen3:8b".to_string();
        assert!(settings.fallback_config().is_some());

        // A different endpoint is a real fallback.
        settings.apply_fallback_provider(Provider::Groq, None);
        settings.fallback_model = "openai/gpt-oss-20b".to_string();
        assert!(settings.fallback_config().is_some());
    }

    #[test]
    fn fallback_probe_config_ignores_the_enabled_flag() {
        let mut settings = AppSettings::default();
        let probe = settings.fallback_probe_config();
        assert_eq!(probe.kind, BackendKind::Ollama);
        assert_eq!(probe.base_url, "http://127.0.0.1:11434");
        assert_eq!(probe.model, "");

        settings.fallback_enabled = false;
        settings.fallback_model = "aya-expanse:8b".to_string();
        assert_eq!(settings.fallback_probe_config().model, "aya-expanse:8b");
    }

    #[test]
    fn fallback_api_key_is_session_only() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.fallback_enabled = true;
        settings.apply_fallback_provider(Provider::Groq, None);
        settings.fallback_model = "openai/gpt-oss-20b".to_string();
        settings.fallback_api_key = "groq-fallback".to_string();
        settings.save_to(&path);

        let raw = fs::read_to_string(&path).expect("read settings");
        assert!(!raw.contains("groq-fallback"));
        let reloaded = AppSettings::load_from(&path);
        assert_eq!(reloaded.fallback_api_key, "");
        assert_eq!(
            reloaded.fallback_config().expect("fallback config").model,
            "openai/gpt-oss-20b"
        );
    }

    #[test]
    fn entry_point_rule() {
        let mut settings = AppSettings::default();
        settings.set_show_in_menu_bar(false);
        assert!(!settings.show_in_menu_bar);
        assert!(settings.show_in_dock);

        settings.set_show_in_dock(false);
        assert!(!settings.show_in_dock);
        assert!(settings.show_in_menu_bar);

        settings.set_show_in_menu_bar(false);
        assert!(!settings.show_in_menu_bar);
        assert!(settings.show_in_dock);
    }

    #[test]
    fn entry_point_rule_applies_to_loaded_files() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(
            &path,
            &json!({"show_in_menu_bar": false, "show_in_dock": false}),
        );
        let settings = AppSettings::load_from(&path);
        assert!(!settings.show_in_menu_bar);
        assert!(settings.show_in_dock);
    }

    #[test]
    fn result_view_validation() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        write_json(&path, &json!({"result_view": "bogus"}));
        assert_eq!(AppSettings::load_from(&path).result_view, "preview");

        let mut settings = AppSettings::default();
        settings.set_result_view("bogus");
        assert_eq!(settings.result_view, "preview");
        settings.set_result_view("markdown");
        assert_eq!(settings.result_view, "markdown");
        settings.set_result_view("text");
        assert_eq!(settings.result_view, "text");
    }

    #[test]
    fn interface_language_round_trip() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.set_interface_language("uk_UA");
        assert_eq!(settings.interface_language, AppLanguage::Uk);
        settings.set_interface_language("en-US");
        assert_eq!(settings.interface_language, AppLanguage::En);
        settings.set_interface_language("klingon");
        assert_eq!(settings.interface_language, AppLanguage::System);

        settings.interface_language = AppLanguage::Uk;
        settings.save_to(&path);
        assert_eq!(
            AppSettings::load_from(&path).interface_language,
            AppLanguage::Uk
        );
    }

    #[test]
    fn apply_catalog_entry() {
        let mut settings = AppSettings::default();
        let entry = ModelCatalog::entry("tencent/hy-mt2-7b").expect("catalogue entry");
        settings.apply_catalog_entry(entry);
        assert_eq!(settings.provider, Provider::OpenRouter);
        assert_eq!(settings.model, "tencent/hy-mt2-7b");
        assert_eq!(settings.base_url, "https://openrouter.ai/api/v1");
    }

    #[test]
    fn install_command() {
        let mut settings = AppSettings::default();
        assert_eq!(
            settings.install_command(),
            Some(
                "ollama pull maternion/hy-mt2:7b && \
                 ollama cp maternion/hy-mt2:7b hy-mt2:7b"
            )
        );
        settings.model = "some-unknown-model".to_string();
        assert_eq!(settings.install_command(), None);
    }

    #[test]
    fn default_path_uses_the_platform_configuration_root() {
        let path = settings_path_for(
            Some(Path::new("/roaming")),
            Some(Path::new("/xdg")),
            Some(Path::new("/home/user")),
        );
        if cfg!(windows) {
            assert_eq!(path, PathBuf::from("/roaming/DeepL-oFM/settings.json"));
        } else {
            assert_eq!(path, PathBuf::from("/xdg/DeepL-oFM/settings.json"));
        }

        let without_xdg = settings_path_for(None, None, Some(Path::new("/home/user")));
        assert_eq!(
            without_xdg,
            PathBuf::from("/home/user/.config/DeepL-oFM/settings.json")
        );

        let fallback = settings_path_for(None, None, None);
        assert_eq!(fallback, PathBuf::from(".config/DeepL-oFM/settings.json"));

        assert_eq!(
            AppSettings::default_path().file_name(),
            Some(std::ffi::OsStr::new("settings.json"))
        );
    }

    #[test]
    fn atomic_write_leaves_no_temporary_files() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.model = "hy-mt2:1.8b".to_string();
        settings.top_k = 7;
        settings.save_to(&path);
        assert!(path.exists());
        let names: Vec<String> = fs::read_dir(path.parent().expect("parent"))
            .expect("read dir")
            .map(|entry| {
                entry
                    .expect("dir entry")
                    .file_name()
                    .to_string_lossy()
                    .to_string()
            })
            .collect();
        assert_eq!(names, vec!["settings.json".to_string()]);
    }

    #[test]
    fn settings_survive_repeated_saves() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        for index in 0..20 {
            settings.top_k = index;
            settings.save_to(&path);
        }
        assert_eq!(AppSettings::load_from(&path).top_k, 19);
    }

    #[test]
    fn non_finite_numbers_serialise_as_null_and_reload_as_defaults() {
        let temp = TempDir::new();
        let path = temp.settings_path();
        let mut settings = AppSettings::default();
        settings.temperature = f32::NAN;
        settings.save_to(&path);
        assert!(read_json(&path)["temperature"].is_null());
        assert_eq!(AppSettings::load_from(&path).temperature, 0.7);
    }

    #[test]
    fn to_json_round_trips_through_from_json() {
        let mut settings = AppSettings::default();
        settings.apply_provider(Provider::Cerebras, Some("gpt-oss-120b"));
        settings.debounce = 0.75;
        settings.set_show_in_menu_bar(false);
        let parsed = AppSettings::from_json(&settings.to_json());
        assert_eq!(parsed, settings);
    }

    #[test]
    fn serde_wire_format_is_camel_case() {
        let mut settings = AppSettings::default();
        settings.apply_provider(Provider::Groq, Some("openai/gpt-oss-120b"));
        settings.interface_language = AppLanguage::Uk;
        settings.set_show_in_menu_bar(false);

        let wire = serde_json::to_value(&settings).expect("serialise settings");
        for key in [
            "provider",
            "baseUrl",
            "model",
            "apiKey",
            "fallbackEnabled",
            "fallbackProvider",
            "fallbackBaseUrl",
            "fallbackModel",
            "fallbackApiKey",
            "temperature",
            "topP",
            "topK",
            "repetitionPenalty",
            "contextWindow",
            "autoTranslate",
            "debounce",
            "hotKey",
            "selectionHotKey",
            "showInMenuBar",
            "showInDock",
            "speechVoiceId",
            "keepHistory",
            "warmUpOnLaunch",
            "interfaceLanguage",
            "resultView",
            "lastStyle",
            "lastTone",
            "lastTargetCode",
            "lastSourceCode",
            "remembered",
        ] {
            assert!(wire.get(key).is_some(), "missing wire key {key}");
        }
        for key in [
            "base_url",
            "api_key",
            "top_p",
            "top_k",
            "hot_key",
            "interface_language",
            "result_view",
            "show_in_menu_bar",
        ] {
            assert!(wire.get(key).is_none(), "unexpected snake_case key {key}");
        }
        assert_eq!(wire["provider"], "groq");
        assert_eq!(wire["interfaceLanguage"], "uk");
        assert_eq!(wire["hotKey"], KeyCombo::standard().to_json());
        assert_eq!(wire["showInMenuBar"], false);
        assert_eq!(wire["showInDock"], true);

        let parsed: AppSettings = serde_json::from_value(wire).expect("parse settings");
        assert_eq!(parsed, settings);
    }

    #[test]
    fn serde_accepts_a_minimal_ui_payload() {
        let parsed: AppSettings = serde_json::from_value(json!({
            "provider": "openRouter",
            "baseUrl": "https://openrouter.ai/api/v1",
            "model": "tencent/hy-mt2-7b",
            "apiKey": "sk-or-test",
            "topP": 0.9,
            "hotKey": {"key": "k", "ctrl": true},
            "interfaceLanguage": "de",
            "resultView": "text",
        }))
        .expect("parse ui payload");

        assert_eq!(parsed.provider, Provider::OpenRouter);
        assert_eq!(parsed.base_url, "https://openrouter.ai/api/v1");
        assert_eq!(parsed.model, "tencent/hy-mt2-7b");
        assert_eq!(parsed.api_key, "sk-or-test");
        assert_eq!(parsed.top_p, 0.9);
        assert_eq!(
            parsed.hot_key,
            KeyCombo {
                key: "k".to_string(),
                ctrl: true,
                ..KeyCombo::default()
            }
        );
        assert_eq!(parsed.interface_language, AppLanguage::De);
        assert_eq!(parsed.result_view, "text");
        // Fields absent from the payload keep their defaults.
        assert_eq!(parsed.top_k, 20);
        assert!(parsed.show_in_menu_bar);
        assert_eq!(parsed.selection_hot_key, KeyCombo::selection());
    }

    #[test]
    fn from_json_accepts_the_wire_camel_case_aliases() {
        let parsed = AppSettings::from_json(&json!({
            "baseUrl": "https://api.groq.com/openai/v1",
            "fallbackBaseUrl": "http://127.0.0.1:8080/v1",
            "speechVoiceId": "voice-2",
        }));
        assert_eq!(parsed.base_url, "https://api.groq.com/openai/v1");
        assert_eq!(parsed.fallback_base_url, "http://127.0.0.1:8080/v1");
        assert_eq!(parsed.speech_voice_id, "voice-2");
    }

    #[test]
    fn api_key_from_json_is_ignored() {
        let settings = AppSettings::from_json(&json!({"api_key": "leaked", "model": "qwen3:8b"}));
        assert_eq!(settings.api_key, "");
        assert_eq!(settings.model, "qwen3:8b");
    }
}
