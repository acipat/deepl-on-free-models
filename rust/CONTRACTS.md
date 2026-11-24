# DeepL-oFM — Rust workspace contracts

Binding API contract for the parallel port. **Signatures below are the source of
truth**; the compiler is the integrator. If a signature is genuinely impossible,
keep it and report the deviation instead of changing it silently.

## 0. Ground rules

- Rust **1.82+**, edition **2021**. Toolchain here is 1.96.
- **Always invoke cargo through `rust/cargo.sh`** (it sets the workspace-local
  `CARGO_HOME`; `~/.cargo` is read-only in this sandbox):
  ```bash
  cd rust && ./cargo.sh build && ./cargo.sh test
  ```
- Never edit files outside your own crate. `Cargo.toml` of your crate may gain
  dependencies; nothing else.
- **Everything except `ofm-desktop` must build and test on Linux without system
  libraries.** The desktop shell needs Tauri + WebView and is excluded from
  `default-members`; it is written to compile on Windows/macOS.
- No `unsafe` unless it is platform code with a `// SAFETY:` comment.
- No `unwrap()`/`expect()` on user data; `unwrap()` in tests is fine.
- Public items get doc comments. Errors are typed (`thiserror`), never `String`.
- Tests: `#[cfg(test)] mod tests` inside the module, plus `tests/` for
  integration. `cargo clippy -- -D warnings` must stay clean-ish (allow
  `too_many_arguments` where the port needs it).
- Logging via the `log` crate; never `println!` in library code.

### Reference implementation to port from

The behavioural spec is **the Python port that already works**, not the Swift
original (Swift is only authoritative for user-facing strings):

| Port from | To |
|---|---|
| `windows/deepl_ofm/core/languages.py` + `windows/deepl_ofm/i18n/` | `ofm-i18n` |
| `windows/deepl_ofm/core/prompts.py`, `chunker.py`, `tokens.py`, `sanitizer.py` | `ofm-text` |
| `windows/deepl_ofm/core/providers.py`, `catalog.py`, `settings.py`, `keycombo.py` | `ofm-config` |
| `windows/deepl_ofm/services/translation.py`, `probe.py` | `ofm-net` |
| `windows/deepl_ofm/services/documents.py` | `ofm-docs` |
| `windows/deepl_ofm/services/history.py`, `secrets.py` | `ofm-store` |
| `windows/deepl_ofm/services/{hotkeys,speech}.py`, `support/{selection,pasteboard}.py` | `ofm-platform` |
| `windows/deepl_ofm/controller.py` | `ofm-app` |

The matching Python tests (`windows/tests/test_*.py`) are the acceptance
criteria: port the cases, keep the same expectations. Prompt strings must be
**byte-identical** to the Swift originals in `Sources/HyMT/Models/Prompt.swift`.

## 1. Workspace layout and ownership

```
rust/
  Cargo.toml            workspace (default-members excludes desktop)
  cargo.sh              cargo wrapper
  crates/
    i18n/     ofm-i18n        languages, detection, interface catalogue
    text/     ofm-text        prompts, chunker, token protection, sanitizer
    config/   ofm-config      providers, catalogue, KeyCombo, settings
    net/      ofm-net         streaming translators, probe
    docs/     ofm-docs        txt/md/docx/pdf
    store/    ofm-store       history, secrets
    platform/ ofm-platform    clipboard→markdown, selection, hotkeys, speech
    app/      ofm-app         controller + events (no UI toolkit types)
    cli/      ofm-cli         headless binary
    desktop/  ofm-desktop     Tauri v2 shell (Windows/macOS build)
  ui/                     static HTML/CSS/JS frontend (no npm)
```

Dependency graph (already wired in the manifests — do not change direction):

```
i18n ← text, config, docs, store, platform
config ← net, platform, app
text   ← net, app
net, docs, store, platform ← app ← cli, desktop
```

## 2. `ofm-i18n`

```rust
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum AppLanguage { System, En, Uk, Ru, De, Fr, Es, Pl, Pt, It }

impl AppLanguage {
    pub fn resolved(self) -> AppLanguage;              // System → OS language, else self
    pub fn code(self) -> &'static str;                 // "system", "en", …
    pub fn locale_identifier(self) -> &'static str;    // "en_US", "uk_UA", …
    pub fn picker_title(self) -> String;               // "System" localised, "Українська", …
    pub fn from_code(code: &str) -> Option<AppLanguage>;
    pub fn system() -> AppLanguage;
}

pub fn set_language(language: AppLanguage);            // thread-safe (AtomicU8)
pub fn current_language() -> AppLanguage;              // never System
pub fn available_languages() -> &'static [AppLanguage];
pub fn t(key: &str) -> &str;                           // current language, key when missing
pub fn t_in(key: &str, language: AppLanguage) -> &str;
pub fn tf(key: &str, args: &[&dyn std::fmt::Display]) -> String; // %@/%d/%s placeholders
```

```rust
#[derive(Clone, Copy, Debug)]
pub struct Language {
    pub code: &'static str,
    pub english_name: &'static str,
    pub local_name: &'static str,
    pub bcp47: Option<&'static str>,
}

impl Language {
    pub fn display_name(&self, ui: AppLanguage) -> String;  // "Auto-detect" for auto
    pub fn is_auto(&self) -> bool;
}

pub struct LanguageTable;

impl LanguageTable {
    pub const AUTO: Language;
    pub fn all() -> &'static [Language];                    // exactly 38, Swift order
    pub fn get(code: &str) -> Option<&'static Language>;
    pub fn detect(text: &str, preferred: AppLanguage) -> Option<&'static Language>;
}
```

- 38 languages, 9 interface languages; `detect` mirrors the Python version
  (script ranges first, then uk/ru word scoring, then a Latin stop-word scorer).
- The catalogue is generated from `Sources/HyMT/Support/Localization.swift`
  (302 keys × 8 languages) **plus** the Windows-only table in
  `windows/deepl_ofm/i18n/extra.py` (≈60 keys). Generate a `.rs` file with a
  script under `rust/scripts/`, commit the generated output, and make the script
  reproducible (`python3 rust/scripts/gen_i18n.py`).
- Storage: `static` maps resolved once (`std::sync::OnceLock`), zero deps beyond
  `serde` for the settings enum.

## 3. `ofm-text`

```rust
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TranslationStyle { Auto, Literal, Natural }
impl TranslationStyle {
    pub fn title(self) -> &'static str; pub fn detail(self) -> &'static str;
    pub fn value(self) -> &'static str; pub fn from_value(s: &str) -> Option<Self>;
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum TranslationTone { Standard, Formal, Casual }
// same four accessors

pub struct PromptBuilder;   // all associated functions, no state
impl PromptBuilder {
    pub fn instruction(style: TranslationStyle, tone: TranslationTone,
                       target_language: &str, preserve_markdown: bool) -> String;
    pub fn prompt(text: &str, style: TranslationStyle, tone: TranslationTone,
                  target_language: &str, preserve_markdown: bool) -> String;
    pub fn heading_instruction(/* same args */) -> String;
    pub fn heading_prompt(/* same args + text first */) -> String;
    pub fn plain_instruction(target_language: &str) -> String;
    pub fn plain_prompt(text: &str, target_language: &str) -> String;
    pub fn preview(style: TranslationStyle, tone: TranslationTone,
                   target_language: &str, sample: &str) -> String;
}
```

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct TextChunk {
    pub prefix: String,          // "## ", "- ", "1. ", "> ", "- [ ] "
    pub text: String,            // text without the prefix
    pub is_heading: bool,
    pub is_code: bool,           // fenced block, passes through untranslated
    pub separator_before: String,// "\n" or "\n\n"
    pub index: usize,
}

pub struct TextChunker;
impl TextChunker {
    pub const LINE_LIMIT: usize;                 // 3200, same as Python
    pub fn normalize(text: &str) -> String;      // CRLF/CR → LF
    pub fn split(text: &str) -> Vec<TextChunk>;
    pub fn compose(chunks: &[TextChunk], translated: &[String]) -> Result<String, ChunkError>;
    pub fn split_sentences(text: &str) -> Vec<String>;
}
```

```rust
pub struct TokenRestorer;
impl TokenRestorer {
    pub fn restore(source: &str, translated: &str) -> Option<String>;
    pub fn preserve_trailing_punctuation(source: &str, translated: &str) -> String;
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DegenerateReason { Empty, Repetition, Script, RoleTokens, Echo, Length }

pub struct OutputSanitizer;
impl OutputSanitizer {
    pub fn strip_wrappers(text: &str) -> String;
    pub fn strip_preamble(text: &str, source: &str) -> String;
    pub fn has_role_tokens(text: &str) -> bool;
    pub fn script_ok(text: &str, target: &ofm_i18n::Language) -> bool;
    pub fn is_degenerate(source: &str, translated: &str, target: &ofm_i18n::Language)
        -> Option<DegenerateReason>;   // None == acceptable
}
```

**Token regex warning:** the original pattern uses lookbehind/lookahead, which
`regex` cannot express. Use **`fancy-regex`** (already a dependency) for
`TokenRestorer`; keep `regex` for the simpler sanitizer patterns. Verify the
patterns against the Python test cases including U+2010…U+2212 hyphens.

## 4. `ofm-config`

```rust
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum BackendKind { Ollama, OpenAI }

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Provider {
    Ollama, OllamaCloud, LmStudio, Omlx, LlamaCpp,
    OpenRouter, Groq, Cerebras, Custom,
}

impl Provider {
    pub fn title(self) -> &'static str;
    pub fn base_url(self) -> &'static str;
    pub fn kind(self) -> BackendKind;
    pub fn is_local(self) -> bool;
    pub fn requires_key(self) -> bool;
    pub fn key_url(self) -> Option<&'static str>;
    pub fn key_account(self) -> String;                 // "provider:ollama"
    pub fn detail_key(self) -> &'static str;            // English key for t()
    pub fn detail(self) -> String;                      // t_in(detail_key, current)
    pub fn value(self) -> &'static str;                 // "ollamaCloud", …
    pub fn from_value(s: &str) -> Option<Self>;
    pub fn all() -> &'static [Provider];
    pub fn infer(kind: BackendKind, base_url: &str) -> Provider;
}

#[derive(Clone, Debug, PartialEq)]
pub struct BackendConfig {
    pub kind: BackendKind,
    pub base_url: String,
    pub model: String,
    pub api_key: String,
    pub temperature: f32,
    pub top_p: f32,
    pub top_k: u32,
    pub repetition_penalty: f32,
    pub context_window: u32,
    pub requires_api_key: bool,
}

impl BackendConfig {
    pub fn compatible_base(&self) -> String;             // trailing "/" stripped
    pub fn uses_same_endpoint(&self, other: &Self) -> bool;
}
```

```rust
pub struct CatalogEntry {
    pub name: &'static str,
    pub model_id: &'static str,
    pub provider: Provider,
    pub size: &'static str,
    pub languages: &'static str,
    pub note: &'static str,
    pub install_command: &'static str,
    pub badges: &'static [&'static str],
    pub is_free: bool,
}

pub struct ModelCatalog;
impl ModelCatalog {
    pub fn entries() -> &'static [CatalogEntry];         // 28, Swift order
    pub fn entry(model_id: &str) -> Option<&'static CatalogEntry>;
    pub fn install_command(model_id: &str) -> Option<&'static str>;
    pub fn for_provider(provider: Provider) -> Vec<&'static CatalogEntry>;
}
```

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct KeyCombo {
    pub key: String,      // "t", "f5", "space"
    pub ctrl: bool,
    pub alt: bool,
    pub shift: bool,
    pub meta: bool,
}

impl KeyCombo {
    pub fn display(&self) -> String;                 // "Ctrl+Alt+T"
    pub fn is_valid(&self) -> bool;                  // needs ctrl or alt
    pub fn standard() -> Self;                       // Ctrl+Alt+T
    pub fn selection() -> Self;                      // Ctrl+Alt+C
    pub fn to_json(&self) -> serde_json::Value;
    pub fn from_json(value: &serde_json::Value) -> Self;
}
```

```rust
#[derive(Clone, Debug)]
pub struct AppSettings {
    pub provider: Provider,
    pub base_url: String,
    pub model: String,
    pub api_key: String,
    pub fallback_enabled: bool,
    pub fallback_provider: Provider,
    pub fallback_base_url: String,
    pub fallback_model: String,
    pub fallback_api_key: String,
    pub temperature: f32,
    pub top_p: f32,
    pub top_k: u32,
    pub repetition_penalty: f32,
    pub context_window: u32,
    pub auto_translate: bool,
    pub debounce: f64,
    pub hot_key: KeyCombo,
    pub selection_hot_key: KeyCombo,
    pub show_in_menu_bar: bool,
    pub speech_voice_id: String,
    pub keep_history: bool,
    pub warm_up_on_launch: bool,
    pub interface_language: AppLanguage,
    pub result_view: String,          // "preview" | "text" | "markdown"
    pub last_style: String,           // "auto" | "literal" | "natural"
    pub last_tone: String,            // "standard" | "formal" | "casual"
    pub last_target_code: String,
    pub last_source_code: String,
}

impl Default for AppSettings { /* documented defaults, see Python */ }

impl AppSettings {
    pub fn load() -> Self;                       // tolerant of missing/corrupt file
    pub fn load_from(path: &Path) -> Self;
    pub fn save(&self);                          // atomic, never panics
    pub fn save_to(&self, path: &Path);
    pub fn snapshot(&self) -> BackendConfig;
    pub fn fallback_config(&self) -> Option<BackendConfig>;   // None when equal endpoint
    pub fn fallback_probe_config(&self) -> BackendConfig;
    pub fn apply_provider(&mut self, provider: Provider, model: Option<&str>);
    pub fn apply_catalog_entry(&mut self, entry: &CatalogEntry);
    pub fn install_command(&self) -> Option<&'static str>;
    pub fn default_path() -> PathBuf;            // %APPDATA%/DeepL-oFM or ~/.config
    pub fn to_json(&self) -> serde_json::Value;
    pub fn from_json(value: &serde_json::Value) -> Self;
}
```

Style/tone are `String` here on purpose: `ofm-config` must not depend on
`ofm-text`. The app layer converts with `TranslationStyle::from_value`.

## 5. `ofm-net`

```rust
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum ErrorKind {
    Connection, InvalidUrl, Http, Unauthorized, RateLimit, Server,
    Model, Interrupted, Unexpected, Empty, Cancelled,
}

#[derive(Debug, thiserror::Error)]
#[error("{kind:?}: {detail}")]
pub struct TranslationError { pub kind: ErrorKind, pub status: Option<u16>, pub detail: String }

impl TranslationError {
    pub fn new(kind: ErrorKind) -> Self;
    pub fn with_status(kind: ErrorKind, status: u16) -> Self;
    pub fn message(&self) -> String;        // localised via ofm_i18n::tf
}

#[derive(Clone, Debug, Default)]
pub struct TranslationOutput {
    pub text: String,
    pub warnings: usize,
    pub tokens_per_second: Option<f64>,
    pub duration_ms: Option<u64>,
    pub used_fallback: bool,
}

pub type ProgressFn = Arc<dyn Fn(usize, usize) + Send + Sync>;
pub type PartialFn = Arc<dyn Fn(&str) + Send + Sync>;
pub type CancelFlag = Arc<std::sync::atomic::AtomicBool>;

pub struct TranslateRequest<'a> {
    pub text: &'a str,
    pub source: &'a ofm_i18n::Language,
    /// True when the user *chose* the source language rather than the detector
    /// guessing it; only then does the prompt assert "The source language is …".
    pub source_explicit: bool,
    pub target: &'a ofm_i18n::Language,
    pub style: TranslationStyle,
    pub tone: TranslationTone,
    pub config: &'a BackendConfig,
    pub fallback: Option<&'a BackendConfig>,
    pub cancel: Option<CancelFlag>,
    pub on_progress: Option<ProgressFn>,
    pub on_partial: Option<PartialFn>,
}

pub struct Translator { /* reqwest::Client, timeout */ }

impl Translator {
    pub fn new() -> Self;
    pub async fn translate(&self, request: TranslateRequest<'_>) -> Result<TranslationOutput, TranslationError>;
    pub async fn rewrite(&self, text: &str, target: &ofm_i18n::Language,
                         config: &BackendConfig, fallback: Option<&BackendConfig>,
                         cancel: Option<CancelFlag>) -> Result<TranslationOutput, TranslationError>;
    pub async fn list_models(&self, config: &BackendConfig) -> Result<Vec<String>, TranslationError>;
    pub async fn warm_up(&self, config: &BackendConfig) -> bool;
}

pub fn model_listed(name: &str, models: &[String]) -> bool;
```

Wire protocol: exactly the Python implementation — Ollama `POST /api/chat`
(NDJSON, `options` with the ten generation parameters), OpenAI-compatible
`POST /chat/completions` (SSE `data:` frames, `/v1` inserted only when the base
has no path), `Authorization: Bearer` when the key is non-empty, the retry ladder
(lower temperature → plain prompt → per-sentence), the byte budget with marker
truncation (`hy_end`, `<｜`, …), and fallback on non-cancellation errors.

**Cancellation:** `CancelFlag` is polled between chunks and paragraphs; on cancel
close the response and return `ErrorKind::Cancelled`.

## 6. `ofm-docs`

```rust
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DocumentKind { Text, Markdown, Pdf, Docx }

impl DocumentKind {
    pub fn from_path(path: &Path) -> Option<Self>;   // .txt .text .md .markdown .mdown .pdf .docx
    pub fn value(self) -> &'static str;
    pub fn pattern(self) -> &'static str;            // "*.pdf"
    pub fn label(self) -> &'static str;              // "PDF"
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DocumentErrorKind { Unsupported, NoText, Unreadable, WriteFailed, Encrypted, Cancelled }

#[derive(Debug, thiserror::Error)]
#[error("{kind:?}: {detail}")]
pub struct DocumentError { pub kind: DocumentErrorKind, pub detail: String }
impl DocumentError { pub fn message(&self) -> String; }

pub enum Payload { None, Docx(Vec<u8>), Pdf(Box<PdfLayout>) }

pub struct OpenedDocument {
    pub path: PathBuf,
    pub kind: DocumentKind,
    pub source_text: Option<String>,
    pub paragraphs: Vec<String>,
    pub payload: Payload,
}

pub struct DocumentTranslator;
impl DocumentTranslator {
    pub fn read(path: &Path) -> Result<OpenedDocument, DocumentError>;
    pub fn suggested_path(path: &Path, target: &ofm_i18n::Language) -> PathBuf; // report.pdf → report_uk.pdf
    pub fn write(
        doc: &OpenedDocument,
        out_path: &Path,
        translate: &mut dyn FnMut(&str) -> Result<String, String>,
        on_progress: Option<&dyn Fn(usize, usize)>,
        cancel: Option<&std::sync::atomic::AtomicBool>,
    ) -> Result<PathBuf, DocumentError>;
}
```

- TXT/MD: paragraph units, blank lines preserved, fenced code untouched,
  UTF-8/UTF-16/cp1251/cp1252 detection with the plausibility scorer.
- DOCX: `zip` + `quick-xml`; rewrite only `word/document.xml`, keep every other
  entry byte-for-byte.
- PDF: keep the original pages, draw the translation over each block. **Choose
  pure-Rust crates** so this builds in CI (leading candidates: `lopdf` +
  `printpdf`; text with coordinates is the hard part — report what you chose and
  what is approximate). Keep the original text layer.

## 7. `ofm-store`

```rust
#[derive(Clone, Debug, PartialEq)]
pub struct HistoryEntry {
    pub id: String,             // uuid-ish, generated on create
    pub date: String,           // ISO-8601 UTC
    pub source_text: String,
    pub translated_text: String,
    pub source_code: String,
    pub target_code: String,
    pub style: String,
    pub tone: String,
    pub engine: String,
    pub duration_ms: u64,
}

impl HistoryEntry { pub fn create(...) -> Self; pub fn to_json(&self) -> Value; pub fn from_json(&Value) -> Option<Self>; }

pub struct HistoryStore { /* path, Mutex<Vec<HistoryEntry>> */ }
impl HistoryStore {
    pub const LIMIT: usize = 400;
    pub fn new() -> Self;
    pub fn with_path(path: PathBuf) -> Self;
    pub fn entries(&self) -> Vec<HistoryEntry>;      // newest first, copy
    pub fn add(&self, entry: HistoryEntry);
    pub fn remove(&self, id: &str);
    pub fn clear(&self);
    pub fn search(&self, query: &str) -> Vec<HistoryEntry>;
    pub fn has_storage_error(&self) -> bool;
    pub fn default_path() -> PathBuf;
}

pub struct SecretStore;
impl SecretStore {
    pub fn new() -> Self;
    pub fn with_path(path: PathBuf) -> Self;         // file backend, for tests
    pub fn read(&self, account: &str) -> String;
    pub fn write(&self, account: &str, value: &str);
    pub fn delete(&self, account: &str);
    pub fn backend_name(&self) -> &'static str;      // "keyring" | "dpapi" | "plain"
}
```

`keyring` 3.x covers Credential Manager and Keychain. Read/write/delete must
never panic: degrade to an empty key and log.

## 8. `ofm-platform`

```rust
pub mod pasteboard {
    pub fn html_to_markdown(html: &str) -> String;
    pub fn rtf_to_markdown(rtf: &str) -> String;
    pub fn clipboard_markdown() -> Option<String>;   // rich → md, else plain text
    pub fn clipboard_text() -> Option<String>;
    pub fn set_clipboard_text(text: &str, html: Option<&str>, rtf: Option<&str>);
}

pub mod selection {
    pub fn is_supported() -> bool;
    pub fn capture(timeout: std::time::Duration) -> Option<String>;
}

pub mod hotkeys {
    pub struct HotkeyError { pub message_key: &'static str }
    pub struct HotkeyManager { /* … */ }
    impl HotkeyManager {
        pub fn new() -> Self;
        pub fn is_supported() -> bool;
        pub fn register(&mut self, action: &str, combo: &KeyCombo) -> Result<(), HotkeyError>;
        pub fn unregister_all(&mut self);
        pub fn poll(&mut self) -> Vec<String>;       // actions pressed since the last call
    }
}

pub mod speech {
    pub struct Speaker;
    impl Speaker {
        pub fn new() -> Self;
        pub fn is_available(&self) -> bool;
        pub fn voices(&self) -> Vec<(String, String)>;   // (id, label)
        pub fn speak(&self, text: &str, voice_id: &str, language_code: &str) -> bool;
        pub fn stop(&self);
        pub fn is_speaking(&self) -> bool;
    }
}
```

Everything must **compile on Linux**; unsupported features return `false`/`None`
and log. Clipboard: `arboard` (html support included). Hotkeys: `global-hotkey`.
Selection capture: Windows = send `Ctrl+C` and watch the clipboard sequence
number (as in `support/selection.py`); macOS = `Cmd+C` via `osascript` or CGEvent;
Linux = unsupported.

## 9. `ofm-app`

```rust
pub struct AppState {           // plain snapshot handed to the UI as JSON
    pub tab: String,
    pub source_text: String,
    pub translated_text: String,
    pub is_translating: bool,
    pub completed: usize,
    pub total: usize,
    pub warning_count: usize,
    pub error_message: Option<String>,
    pub source_language: String,
    pub target_language: String,
    pub detected_language: Option<String>,
    pub style: String,
    pub tone: String,
    pub result_view: String,
    pub backend_status: String,      // unknown | checking | connected | failed | warming
    pub probe_message: String,
    pub provider_models: Vec<String>,
    pub models_loading: bool,
    pub models_error: Option<String>,
    pub fallback_models: Vec<String>,
    pub fallback_models_loading: bool,
    pub fallback_models_error: Option<String>,
    pub using_fallback: bool,
    pub tokens_per_second: Option<f64>,
    pub last_duration_ms: Option<u64>,
    pub speaking: String,
    pub hotkey_message: String,
    pub selection_hotkey_message: String,
    pub file_job: Option<FileJob>,
    pub write: WriteState,
    pub history: Vec<HistoryEntry>,
    pub history_error: bool,
    /// Login-item state: `enabled`, `disabled`, `requiresApproval`, `unsupported`.
    pub login_item_status: String,
    /// Why the login item could not be changed, localised.
    pub login_item_error: Option<String>,
    pub settings: AppSettings,
    pub version: String,
}

pub struct FileJob {
    pub path: String, pub name: String, pub kind: String, pub size: u64,
    pub state: String,   // reading | translating | writing | done | failed | cancelled
    pub completed: usize, pub total: usize, pub percent: u32,
    pub output: Option<String>, pub result_name: Option<String>,
    pub message: Option<String>, pub warnings: usize,
    pub fallback: bool, pub fallback_label: String, pub save_error: Option<String>,
    /// Where the user last saved the result; the staged file remains the source
    /// of truth, so a second save always copies the staged output.
    pub saved_path: Option<String>,
}

/// `AppEvent` is serialised with `#[serde(tag = "type", rename_all = "camelCase")]`
/// so the frontend receives `{"type": "progress", "completed": 2, "total": 5}`.
/// Payload variants carry their value in a single field named after the variant
/// (`{"type": "translatedText", "translatedText": "…"}` is *not* the shape — use
/// a newtype field `value`, e.g. `{"type": "translatedText", "value": "…"}`).
/// The frontend is expected to treat every event as a hint and may always call
/// `get_state` to resynchronise; this keeps the contract tolerant to additions.
pub enum AppEvent {   // every variant is mirrored to the frontend as JSON
    StateChanged,                     // coarse: re-send the whole state
    Progress { completed: usize, total: usize },
    Translating(bool),
    TranslatedText(String),
    SourceText(String),
    Languages { source: String, target: String },
    Detected(String),
    Error(String),
    TranslationFailed(String),
    BackendStatus(String),
    ProbeMessage(String),
    Models(Vec<String>),
    ModelsLoading(bool),
    ModelsError(String),
    FallbackModels(Vec<String>),
    FallbackModelsLoading(bool),
    FallbackModelsError(String),
    Settings(AppSettings),
    InterfaceLanguage(String),
    Tab(String),
    History,
    FileJob(FileJob),
    CopyFeedback(String),
    Metrics,
    Speaking(String),
    Style(String),
    Tone(String),
    ResultView(String),
    /// Streamed text that is not final yet.
    TranslationPartial(String),
}

pub struct AppController { /* … */ }

impl AppController {
    pub fn new() -> Self;
    pub fn state(&self) -> AppState;
    pub fn subscribe(&self) -> tokio::sync::broadcast::Receiver<AppEvent>;

    // translate tab
    pub fn set_source_text(&self, text: &str);
    pub fn set_source_language(&self, code: &str);
    pub fn set_target_language(&self, code: &str);
    pub fn swap_languages(&self);
    pub fn set_style(&self, style: &str);
    pub fn set_tone(&self, tone: &str);
    pub fn set_result_view(&self, mode: &str);
    pub fn clear_source(&self);
    pub fn translate(&self, force: bool);          // spawns the async job
    pub fn cancel(&self);
    pub fn translate_clipboard(&self);
    pub fn translate_selection(&self);
    pub fn copy_translation(&self);
    pub fn copy_source(&self);
    pub fn speak(&self, target: &str);
    pub fn stop_speaking(&self);

    // backend
    pub fn check_connection(&self);
    pub fn connect_and_load_models(&self);
    pub fn load_fallback_models(&self);
    pub fn apply_catalog_entry(&self, entry: &CatalogEntry);

    // settings / language
    pub fn set_interface_language(&self, language: AppLanguage);
    pub fn save_settings(&self, settings: AppSettings);
    pub fn save_settings_json(&self, value: &serde_json::Value);  // tolerant: bad fields keep their old value
    pub fn set_tab(&self, tab: &str);   // "translate" | "files" | "write" | "history"

    // files
    pub fn start_file_translation(&self, path: &Path);
    pub fn cancel_file_translation(&self);
    pub fn save_translated_file(&self, destination: &Path);
    pub fn clear_file_job(&self);

    // write
    pub fn write_text(&self, text: &str, target_code: &str);
    pub fn cancel_write(&self);

    // history
    pub fn history_search(&self, query: &str) -> Vec<HistoryEntry>;
    pub fn history_delete(&self, id: &str);
    pub fn history_clear(&self);
    pub fn load_history_entry(&self, id: &str);
}
```

Rules carried over from the reviewed Python controller (they were real bugs —
do not repeat them):

1. Every async job carries a **generation counter**; late results are dropped.
2. Cancel the previous job **before** replacing its cancel flag.
3. The worker never mutates shared state directly — it sends `AppEvent`s.
4. The translation cache key includes text, source, target, style, tone, model.
5. `clear_source` resets text, translation, metrics, detection, warnings, error.
6. A failed request marks the backend `failed`; a missing model after Connect is
   a failure, not "connected".
7. Warm-up only runs for local providers.

## 10. `ofm-desktop` (Tauri v2) — not built in this sandbox

- `tauri.conf.json` with `"frontendDist": "../ui"` (static files, **no npm**),
  `"devUrl"` omitted, one window 1180×800, min 960×620.
- `src/main.rs` + `src/commands.rs`: thin wrappers that call `AppController` and
  return `serde_json::Value`. Every command name used by `ui/app.js` must exist.
- Events: emit `app://event` with the serialised `AppEvent`; the frontend
  subscribes with `window.__TAURI__.event.listen`.
- Plugins: `tauri-plugin-dialog` (file open/save), `tauri-plugin-single-instance`,
  `tauri-plugin-opener`. Tray + global shortcuts are handled by `ofm-platform`.
- When `ofm-desktop` cannot build (no WebView libraries), that is expected; keep
  the code honest and report it.

## 11. Frontend (`rust/ui/`) — static, no bundler

Files: `index.html`, `styles.css`, `app.js`, `mock.js`.
- `app.js` talks to Rust with `window.__TAURI__.core.invoke(name, args)` and falls
  back to `mock.js` when `window.__TAURI__` is undefined, so the UI can be opened
  directly in a browser (and screenshotted with `chromium --headless`).
- Commands and their argument names are fixed by `ui/app.js` ⇄ `ofm-desktop`.
- Design: reuse the existing palette (accent `#2F6BFF`, canvas `#F6F7F9`,
  cards `#FFFFFF`, borders `#E3E6EB`, text `#14161A`, muted `#6B7280`; dark
  canvas `#15171C`, cards `#1D2027`, borders `#2A2E37`, text `#F2F4F8`).
  10 px radius, Segoe UI Variable / SF Pro, 14 px body. No CSS framework.
- Tabs: Translate / Files / Write / History + a Settings dialog.

## 12. Definition of done per crate

1. `./cargo.sh build` and `./cargo.sh test` pass from `rust/`.
2. `./cargo.sh clippy -p <crate> --all-targets` has no `deny`-level issues.
3. Public API matches this document.
4. Ported tests from the Python suite pass; new edge cases added where the port
   introduced risk.
5. No `TODO` left in public paths; approximations documented in the crate docs.
