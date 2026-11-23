//! JSON-backed translation history.
//!
//! Ported from `windows/deepl_ofm/services/history.py`. Entries are kept
//! newest-first, capped at [`HistoryStore::LIMIT`], written atomically and
//! loaded tolerantly so a corrupt file never prevents the application from
//! starting. The store is `Send + Sync`: every mutation takes an internal
//! mutex, so it can be shared between threads and used from async code.

use std::collections::hash_map::RandomState;
use std::fs;
use std::hash::{BuildHasher, Hasher};
use std::io;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Map, Value};

use crate::atomic;
use crate::error::StoreError;
use crate::lock;
use crate::paths;

/// Source code used when the entry does not name one.
const DEFAULT_SOURCE_CODE: &str = "auto";
/// Target code used when the entry does not name one.
const DEFAULT_TARGET_CODE: &str = "en";
/// Style used when the entry does not name one.
const DEFAULT_STYLE: &str = "auto";
/// Tone used when the entry does not name one.
const DEFAULT_TONE: &str = "standard";

/// One finished translation, mirroring the Swift `HistoryEntry` model.
///
/// Serde uses the camelCase **wire** format the frontend consumes; the file
/// format is unchanged and still goes through [`HistoryEntry::to_json`] /
/// [`HistoryEntry::from_json`], which speak snake_case.
#[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HistoryEntry {
    /// Stable identifier generated when the entry is created.
    pub id: String,
    /// Creation timestamp, ISO-8601 in UTC (`2026-05-04T07:08:09Z`).
    pub date: String,
    /// Text that was translated.
    pub source_text: String,
    /// Translated text.
    pub translated_text: String,
    /// Source language code (`auto` when it was detected).
    pub source_code: String,
    /// Target language code.
    pub target_code: String,
    /// Translation style value (`auto`, `literal`, `natural`).
    pub style: String,
    /// Translation tone value (`standard`, `formal`, `casual`).
    pub tone: String,
    /// Backend or model label that produced the translation.
    pub engine: String,
    /// Wall-clock duration of the translation in milliseconds.
    pub duration_ms: u64,
}

impl Default for HistoryEntry {
    fn default() -> Self {
        Self {
            id: new_identifier(),
            date: now_iso8601_utc(),
            source_text: String::new(),
            translated_text: String::new(),
            source_code: DEFAULT_SOURCE_CODE.to_owned(),
            target_code: DEFAULT_TARGET_CODE.to_owned(),
            style: DEFAULT_STYLE.to_owned(),
            tone: DEFAULT_TONE.to_owned(),
            engine: String::new(),
            duration_ms: 0,
        }
    }
}

impl HistoryEntry {
    /// Build an entry for a finished translation.
    ///
    /// The identifier and the UTC timestamp are generated; every other field is
    /// stored as given. The Python constructor defaults are `source_code =
    /// "auto"`, `target_code = "en"`, `style = "auto"`, `tone = "standard"`,
    /// `engine = ""` and `duration_ms = 0`.
    #[allow(clippy::too_many_arguments)]
    pub fn create(
        source_text: &str,
        translated_text: &str,
        source_code: &str,
        target_code: &str,
        style: &str,
        tone: &str,
        engine: &str,
        duration_ms: u64,
    ) -> Self {
        Self {
            id: new_identifier(),
            date: now_iso8601_utc(),
            source_text: source_text.to_owned(),
            translated_text: translated_text.to_owned(),
            source_code: source_code.to_owned(),
            target_code: target_code.to_owned(),
            style: style.to_owned(),
            tone: tone.to_owned(),
            engine: engine.to_owned(),
            duration_ms,
        }
    }

    /// Build an entry belonging to `target_code`, with the remaining optional
    /// fields at their Python defaults.
    pub fn simple(source_text: &str, translated_text: &str, target_code: &str) -> Self {
        Self::create(
            source_text,
            translated_text,
            DEFAULT_SOURCE_CODE,
            target_code,
            DEFAULT_STYLE,
            DEFAULT_TONE,
            "",
            0,
        )
    }

    /// Serialise the entry to the documented on-disk object shape.
    pub fn to_json(&self) -> Value {
        json!({
            "id": self.id,
            "date": self.date,
            "source_text": self.source_text,
            "translated_text": self.translated_text,
            "source_code": self.source_code,
            "target_code": self.target_code,
            "style": self.style,
            "tone": self.tone,
            "engine": self.engine,
            "duration_ms": self.duration_ms,
        })
    }

    /// Build an entry from stored JSON.
    ///
    /// Missing, `null`, camelCase (`sourceText`, `durationMs`, …) and
    /// wrongly-typed fields are tolerated: the camelCase aliases come from the
    /// Swift-era files this store must keep reading. An absent identifier or
    /// timestamp is generated, matching `HistoryEntry.from_dict` in the Python
    /// port. Returns `None` when the value is not a JSON object.
    pub fn from_json(value: &Value) -> Option<Self> {
        let object = value.as_object()?;
        Some(Self {
            id: non_empty_text(object, &["id"]).unwrap_or_else(new_identifier),
            date: non_empty_text(object, &["date"]).unwrap_or_else(now_iso8601_utc),
            source_text: text(object, &["source_text", "sourceText"]).unwrap_or_default(),
            translated_text: text(object, &["translated_text", "translatedText"])
                .unwrap_or_default(),
            source_code: non_empty_text(object, &["source_code", "sourceCode"])
                .unwrap_or_else(|| DEFAULT_SOURCE_CODE.to_owned()),
            target_code: non_empty_text(object, &["target_code", "targetCode"])
                .unwrap_or_else(|| DEFAULT_TARGET_CODE.to_owned()),
            style: non_empty_text(object, &["style"]).unwrap_or_else(|| DEFAULT_STYLE.to_owned()),
            tone: non_empty_text(object, &["tone"]).unwrap_or_else(|| DEFAULT_TONE.to_owned()),
            engine: text(object, &["engine"]).unwrap_or_default(),
            duration_ms: duration_ms(object, &["duration_ms", "durationMs"]),
        })
    }
}

/// Thread-safe, disk-backed translation history.
///
/// Writes are atomic; a corrupt file is reported through
/// [`has_storage_error`](Self::has_storage_error) and the store starts empty
/// without touching the file until the next successful save.
pub struct HistoryStore {
    path: PathBuf,
    state: Mutex<State>,
}

/// The mutex-protected part of a [`HistoryStore`].
#[derive(Default)]
struct State {
    /// Newest-first entries.
    entries: Vec<HistoryEntry>,
    /// Whether the last load or save failed.
    has_storage_error: bool,
}

impl Default for HistoryStore {
    fn default() -> Self {
        Self::new()
    }
}

impl HistoryStore {
    /// Maximum number of entries kept on disk, same as the Swift/Python store.
    pub const LIMIT: usize = 400;

    /// Catalogue key the UI shows when the file cannot be read or written.
    ///
    /// The string is an `ofm-i18n` key, not a localised message: this crate
    /// stays independent of the translation layer.
    pub const STORAGE_ERROR_KEY: &'static str = "Could not read or save translation history.";

    /// Open the default location, loading whatever is already stored.
    pub fn new() -> Self {
        Self::with_path(Self::default_path())
    }

    /// Open `path`, loading whatever is already stored.
    pub fn with_path(path: PathBuf) -> Self {
        let store = Self {
            path,
            state: Mutex::new(State::default()),
        };
        store.reload();
        store
    }

    /// `%APPDATA%/DeepL-oFM/history.json` on Windows, and
    /// `DeepL-oFM/history.json` under `$XDG_CONFIG_HOME` (or `~/.config`)
    /// everywhere else.
    pub fn default_path() -> PathBuf {
        paths::default_directory().join("history.json")
    }

    /// Path this store reads and writes.
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Re-read the file from disk, replacing the in-memory entries.
    ///
    /// A missing file simply leaves the store empty. Unreadable or malformed
    /// content is logged, flagged through [`Self::has_storage_error`], and the
    /// store starts empty; the damaged file is left untouched.
    pub fn reload(&self) {
        let mut state = lock(&self.state);
        load_into(&self.path, &mut state);
    }

    /// Newest-first copy of the stored entries.
    pub fn entries(&self) -> Vec<HistoryEntry> {
        lock(&self.state).entries.clone()
    }

    /// Insert an entry at the top.
    ///
    /// Entries with a blank source or translation are skipped, and so is an
    /// entry identical to the current head (same source, translation and target
    /// code) — the same suppression the Swift store performs.
    pub fn add(&self, entry: HistoryEntry) {
        if entry.source_text.trim().is_empty() || entry.translated_text.trim().is_empty() {
            return;
        }

        let mut state = lock(&self.state);
        let duplicated = match state.entries.first() {
            Some(head) => {
                head.source_text == entry.source_text
                    && head.translated_text == entry.translated_text
                    && head.target_code == entry.target_code
            }
            None => false,
        };
        if duplicated {
            return;
        }

        let mut updated = Vec::with_capacity(state.entries.len() + 1);
        updated.push(entry);
        updated.extend(state.entries.iter().cloned());
        updated.truncate(Self::LIMIT);
        commit(&self.path, &mut state, updated);
    }

    /// Remove one entry by identifier; an unknown identifier writes nothing.
    pub fn remove(&self, id: &str) {
        let mut state = lock(&self.state);
        if !state.entries.iter().any(|entry| entry.id == id) {
            return;
        }
        let updated: Vec<HistoryEntry> = state
            .entries
            .iter()
            .filter(|entry| entry.id != id)
            .cloned()
            .collect();
        commit(&self.path, &mut state, updated);
    }

    /// Remove every entry, writing an empty JSON array.
    pub fn clear(&self) {
        let mut state = lock(&self.state);
        commit(&self.path, &mut state, Vec::new());
    }

    /// Case-insensitive search over the source and translated text.
    ///
    /// An empty (or whitespace-only) query returns every entry, newest first.
    pub fn search(&self, query: &str) -> Vec<HistoryEntry> {
        let needle = query.trim().to_lowercase();
        let entries = self.entries();
        if needle.is_empty() {
            return entries;
        }
        entries
            .into_iter()
            .filter(|entry| {
                entry.source_text.to_lowercase().contains(&needle)
                    || entry.translated_text.to_lowercase().contains(&needle)
            })
            .collect()
    }

    /// Whether the last load or save failed.
    pub fn has_storage_error(&self) -> bool {
        lock(&self.state).has_storage_error
    }

    /// UI message key for the current storage state, `None` when healthy.
    pub fn storage_error_key(&self) -> Option<&'static str> {
        self.has_storage_error().then_some(Self::STORAGE_ERROR_KEY)
    }
}

/// Fill `state` from the JSON file at `path`, never panicking on bad content.
fn load_into(path: &Path, state: &mut State) {
    state.entries.clear();
    state.has_storage_error = false;

    let raw = match fs::read_to_string(path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return,
        Err(error) => {
            log::warn!("could not read history file {}: {error}", path.display());
            state.has_storage_error = true;
            return;
        }
    };

    let document: Value = match serde_json::from_str(&raw) {
        Ok(document) => document,
        Err(error) => {
            log::warn!("history file {} is not valid JSON: {error}", path.display());
            state.has_storage_error = true;
            return;
        }
    };

    let items = match document {
        Value::Array(items) => items,
        _ => {
            log::warn!("history file {} does not contain a list", path.display());
            state.has_storage_error = true;
            return;
        }
    };

    for item in &items {
        match HistoryEntry::from_json(item) {
            Some(entry) => state.entries.push(entry),
            None => log::warn!("skipping a malformed history entry in {}", path.display()),
        }
    }
    state.entries.truncate(HistoryStore::LIMIT);
}

/// Persist `updated`; on failure keep the in-memory and on-disk state as it was.
fn commit(path: &Path, state: &mut State, updated: Vec<HistoryEntry>) {
    match write_entries(path, &updated) {
        Ok(()) => {
            state.entries = updated;
            state.has_storage_error = false;
        }
        Err(error) => {
            state.has_storage_error = true;
            log::warn!("could not write history file {}: {error}", path.display());
        }
    }
}

/// Serialise `entries` as a pretty-printed JSON array with a trailing newline.
fn write_entries(path: &Path, entries: &[HistoryEntry]) -> Result<(), StoreError> {
    let values: Vec<Value> = entries.iter().map(HistoryEntry::to_json).collect();
    let mut payload = serde_json::to_string_pretty(&values)?;
    payload.push('\n');
    atomic::write_atomically(path, payload.as_bytes(), None)?;
    Ok(())
}

/// First present, non-null value among `keys`.
fn field<'a>(object: &'a Map<String, Value>, keys: &[&str]) -> Option<&'a Value> {
    keys.iter()
        .find_map(|key| object.get(*key))
        .filter(|value| !value.is_null())
}

/// Text of the first present field, coercing numbers and booleans like Python.
fn text(object: &Map<String, Value>, keys: &[&str]) -> Option<String> {
    match field(object, keys)? {
        Value::String(value) => Some(value.clone()),
        Value::Number(number) => Some(number.to_string()),
        Value::Bool(value) => Some(value.to_string()),
        _ => None,
    }
}

/// Text of the first present field, trimmed, with empty values treated as absent.
fn non_empty_text(object: &Map<String, Value>, keys: &[&str]) -> Option<String> {
    text(object, keys)
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

/// Duration in milliseconds, accepting numbers and numeric strings.
fn duration_ms(object: &Map<String, Value>, keys: &[&str]) -> u64 {
    match field(object, keys) {
        Some(Value::Number(number)) => number.as_u64().unwrap_or_else(|| {
            number
                .as_f64()
                .map(|value| value.max(0.0) as u64)
                .unwrap_or(0)
        }),
        Some(Value::String(value)) => value
            .trim()
            .parse::<i64>()
            .map(|value| value.max(0) as u64)
            .unwrap_or(0),
        _ => 0,
    }
}

/// A UUID-v4-shaped identifier built from OS-seeded hashing and a counter.
///
/// This replaces Python's `uuid.uuid4()` without pulling in a generator crate:
/// `RandomState` is seeded from the operating system, and the counter plus the
/// clock keep identifiers apart inside one process.
fn new_identifier() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);

    let sequence = COUNTER.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or(0);

    let mut high_hasher = RandomState::new().build_hasher();
    high_hasher.write_u128(nanos ^ (u128::from(sequence) << 64));
    let mut low_hasher = RandomState::new().build_hasher();
    low_hasher.write_u128(nanos);
    low_hasher.write_u64(sequence);

    let high = high_hasher.finish();
    let low = low_hasher.finish();
    let mut value = (u128::from(high) << 64) | u128::from(low);
    // Version 4 in the 13th hex digit, RFC 4122 variant in the 17th.
    value = (value & !(0xfu128 << 76)) | (0x4u128 << 76);
    value = (value & !(0xcu128 << 60)) | (0x8u128 << 60);

    let hex = format!("{value:032x}");
    format!(
        "{}-{}-{}-{}-{}",
        &hex[0..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..32]
    )
}

/// Current UTC timestamp as ISO-8601 with second precision and a `Z` suffix.
fn now_iso8601_utc() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_secs())
        .unwrap_or(0);
    format_iso8601_utc(seconds)
}

/// Format seconds since the Unix epoch as `YYYY-MM-DDTHH:MM:SSZ`.
fn format_iso8601_utc(seconds: u64) -> String {
    let days = (seconds / 86_400) as i64;
    let second_of_day = (seconds % 86_400) as u32;
    let (year, month, day) = civil_from_days(days);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        second_of_day / 3_600,
        (second_of_day % 3_600) / 60,
        second_of_day % 60
    )
}

/// Convert days since 1970-01-01 to a proleptic Gregorian `(year, month, day)`.
///
/// Howard Hinnant's `civil_from_days` algorithm (the same one used by
/// `chrono`/`time`), kept here so the crate needs no date-time dependency.
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let shifted = days + 719_468;
    let era = if shifted >= 0 {
        shifted
    } else {
        shifted - 146_096
    } / 146_097;
    let day_of_era = (shifted - era * 146_097) as u64;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let year = year_of_era as i64 + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = (day_of_year - (153 * month_prime + 2) / 5 + 1) as u32;
    let month = if month_prime < 10 {
        month_prime + 3
    } else {
        month_prime - 9
    } as u32;
    (year + i64::from(month <= 2), month, day)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::{env_lock, TempDir};

    /// Entry helper mirroring the Python test helper.
    fn entry(source: &str, translated: &str, target: &str) -> HistoryEntry {
        HistoryEntry::simple(source, translated, target)
    }

    #[test]
    fn add_keeps_newest_first_and_persists() {
        let dir = TempDir::new("history-order");
        let path = dir.join("history.json");
        let store = HistoryStore::with_path(path.clone());
        let first = entry("Hello", "Привіт", "uk");
        let second = entry("Good morning", "Доброго ранку", "uk");

        store.add(first.clone());
        store.add(second.clone());

        let ids =
            |entries: &[HistoryEntry]| entries.iter().map(|e| e.id.clone()).collect::<Vec<_>>();
        assert_eq!(
            ids(&store.entries()),
            vec![second.id.clone(), first.id.clone()]
        );

        let raw = fs::read_to_string(&path).expect("history file");
        let stored: Value = serde_json::from_str(&raw).expect("valid json");
        let stored_ids: Vec<&str> = stored
            .as_array()
            .expect("array")
            .iter()
            .map(|item| item["id"].as_str().unwrap_or_default())
            .collect();
        assert_eq!(stored_ids, vec![second.id.as_str(), first.id.as_str()]);

        let reloaded = HistoryStore::with_path(path);
        assert_eq!(ids(&reloaded.entries()), vec![second.id, first.id]);
        assert_eq!(reloaded.entries()[0].source_text, "Good morning");
    }

    #[test]
    fn add_skips_empty_text() {
        let dir = TempDir::new("history-empty");
        let store = HistoryStore::with_path(dir.join("history.json"));
        store.add(entry("   ", "Привіт", "uk"));
        store.add(entry("Hello", "\n\t", "uk"));
        assert!(store.entries().is_empty());
    }

    #[test]
    fn add_suppresses_identical_head() {
        let dir = TempDir::new("history-duplicate");
        let store = HistoryStore::with_path(dir.join("history.json"));
        store.add(entry("Hello", "Привіт", "uk"));
        store.add(entry("Hello", "Привіт", "uk"));
        assert_eq!(store.entries().len(), 1);

        // A different target language is a different translation.
        store.add(entry("Hello", "Привіт", "de"));
        let targets: Vec<String> = store
            .entries()
            .iter()
            .map(|e| e.target_code.clone())
            .collect();
        assert_eq!(targets, vec!["de".to_owned(), "uk".to_owned()]);
    }

    #[test]
    fn cap_at_400_entries() {
        let dir = TempDir::new("history-cap");
        let store = HistoryStore::with_path(dir.join("history.json"));
        for index in 0..HistoryStore::LIMIT + 5 {
            store.add(entry(
                &format!("Source {index}"),
                &format!("Target {index}"),
                "uk",
            ));
        }

        let entries = store.entries();
        assert_eq!(entries.len(), HistoryStore::LIMIT);
        assert_eq!(entries[0].source_text, "Source 404");
        assert_eq!(entries[HistoryStore::LIMIT - 1].source_text, "Source 5");
    }

    #[test]
    fn remove_and_unknown_id() {
        let dir = TempDir::new("history-remove");
        let store = HistoryStore::with_path(dir.join("history.json"));
        let first = entry("One", "Uno", "uk");
        let second = entry("Two", "Dos", "uk");
        store.add(first.clone());
        store.add(second.clone());

        store.remove(&first.id);
        assert_eq!(store.entries(), vec![second.clone()]);
        store.remove("missing-id");
        assert_eq!(store.entries(), vec![second]);
    }

    #[test]
    fn clear_writes_empty_list() {
        let dir = TempDir::new("history-clear");
        let path = dir.join("history.json");
        let store = HistoryStore::with_path(path.clone());
        store.add(entry("Hello", "Привіт", "uk"));
        store.clear();

        assert!(store.entries().is_empty());
        let raw = fs::read_to_string(&path).expect("history file");
        assert_eq!(
            serde_json::from_str::<Value>(&raw).expect("json"),
            json!([])
        );
        assert!(HistoryStore::with_path(path).entries().is_empty());
    }

    #[test]
    fn search_is_case_insensitive_on_both_sides() {
        let dir = TempDir::new("history-search");
        let store = HistoryStore::with_path(dir.join("history.json"));
        store.add(entry("Hello world", "Привіт, світе", "uk"));
        store.add(entry("Good morning", "Доброго ранку", "uk"));
        store.add(entry("Evening", "HeLLo again", "uk"));

        let sources = |entries: Vec<HistoryEntry>| {
            entries
                .into_iter()
                .map(|e| e.source_text)
                .collect::<Vec<_>>()
        };
        assert_eq!(
            sources(store.search("HELLO")),
            vec!["Evening", "Hello world"]
        );
        assert_eq!(sources(store.search("привіт")), vec!["Hello world"]);
        assert_eq!(store.search("").len(), 3);
        assert_eq!(store.search("   ").len(), 3);
        assert!(store.search("absent").is_empty());
    }

    #[test]
    fn corrupt_file_is_tolerated_and_recovered() {
        let dir = TempDir::new("history-corrupt");
        let path = dir.join("history.json");
        fs::write(&path, "{definitely not json").expect("seed corrupt file");

        let store = HistoryStore::with_path(path.clone());
        assert!(store.entries().is_empty());
        assert!(store.has_storage_error());
        assert_eq!(
            store.storage_error_key(),
            Some(HistoryStore::STORAGE_ERROR_KEY)
        );
        assert!(store.search("anything").is_empty());
        // The corrupt file must survive until the next successful write.
        assert_eq!(
            fs::read_to_string(&path).expect("read"),
            "{definitely not json"
        );

        store.add(entry("Hello", "Привіт", "uk"));
        assert!(!store.has_storage_error());
        assert_eq!(store.storage_error_key(), None);
        assert_eq!(store.entries().len(), 1);
        let stored: Value =
            serde_json::from_str(&fs::read_to_string(&path).expect("read")).expect("json");
        assert_eq!(stored[0]["source_text"], json!("Hello"));
    }

    #[test]
    fn malformed_entries_are_skipped() {
        let dir = TempDir::new("history-malformed");
        let path = dir.join("history.json");
        let document = json!([
            {"id": "a", "source_text": "Hello", "translated_text": "Привіт"},
            42,
            {"date": "2026-01-01T00:00:00+00:00"},
        ]);
        fs::write(&path, document.to_string()).expect("seed file");

        let store = HistoryStore::with_path(path);
        let entries = store.entries();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].id, "a");
        assert!(!store.has_storage_error());
    }

    #[test]
    fn missing_file_is_not_a_storage_error() {
        let dir = TempDir::new("history-missing");
        let store = HistoryStore::with_path(dir.join("history.json"));
        assert!(store.entries().is_empty());
        assert!(!store.has_storage_error());
        assert_eq!(store.storage_error_key(), None);
    }

    #[test]
    fn storage_error_clears_after_the_file_is_repaired() {
        let dir = TempDir::new("history-repair");
        let path = dir.join("history.json");
        fs::write(&path, "not json").expect("seed");
        let store = HistoryStore::with_path(path.clone());
        assert!(store.has_storage_error());

        fs::write(&path, "[]").expect("repair");
        store.reload();
        assert!(!store.has_storage_error());
        assert!(store.entries().is_empty());
    }

    #[test]
    fn file_that_is_not_a_list_is_a_storage_error() {
        let dir = TempDir::new("history-not-a-list");
        let path = dir.join("history.json");
        fs::write(&path, "{\"entries\": []}").expect("seed file");
        let store = HistoryStore::with_path(path);
        assert!(store.entries().is_empty());
        assert!(store.has_storage_error());
    }

    #[cfg(unix)]
    #[test]
    fn write_failure_keeps_previous_file() {
        use std::fs::Permissions;
        use std::os::unix::fs::PermissionsExt;

        let dir = TempDir::new("history-write-failure");
        let path = dir.join("history.json");
        let store = HistoryStore::with_path(path.clone());
        let first = entry("One", "Uno", "uk");
        store.add(first.clone());
        let before = fs::read_to_string(&path).expect("read");

        // Make the directory read-only so the temporary file cannot be created.
        fs::set_permissions(dir.path(), Permissions::from_mode(0o555)).expect("chmod");
        if fs::write(dir.join("probe"), b"").is_ok() {
            // Running as root: directory permissions do not block writes.
            fs::set_permissions(dir.path(), Permissions::from_mode(0o755)).expect("chmod");
            return;
        }
        store.add(entry("Two", "Dos", "uk"));
        assert!(store.has_storage_error());
        assert_eq!(store.entries(), vec![first]);
        assert_eq!(fs::read_to_string(&path).expect("read"), before);
        assert_eq!(temporary_files(&dir), Vec::<String>::new());

        fs::set_permissions(dir.path(), Permissions::from_mode(0o755)).expect("chmod");
        store.add(entry("Kept", "Збережено", "uk"));
        assert!(!store.has_storage_error());
        let sources: Vec<String> = store.entries().into_iter().map(|e| e.source_text).collect();
        assert_eq!(sources, vec!["Kept".to_owned(), "One".to_owned()]);
    }

    #[test]
    fn reload_reads_entries_written_by_another_store() {
        let dir = TempDir::new("history-reload");
        let path = dir.join("history.json");
        let first = HistoryStore::with_path(path.clone());
        first.add(entry("Hello", "Привіт", "uk"));

        let second = HistoryStore::with_path(path);
        assert_eq!(second.entries().len(), 1);
        second.add(entry("Evening", "Вечір", "uk"));

        first.reload();
        let sources: Vec<String> = first.entries().into_iter().map(|e| e.source_text).collect();
        assert_eq!(sources, vec!["Evening".to_owned(), "Hello".to_owned()]);
    }

    #[test]
    fn nested_directory_is_created() {
        let dir = TempDir::new("history-nested");
        let path = dir.path().join("deep").join("nested").join("history.json");
        let store = HistoryStore::with_path(path.clone());
        store.add(entry("Hello", "Привіт", "uk"));
        assert!(path.is_file());
    }

    #[test]
    fn entry_json_round_trip_and_aliases() {
        let original = HistoryEntry::create(
            "Hello",
            "Привіт",
            "en",
            "uk",
            "natural",
            "formal",
            "ollama",
            123,
        );
        let restored = HistoryEntry::from_json(&original.to_json()).expect("entry");
        assert_eq!(restored, original);

        let camel = HistoryEntry::from_json(&json!({
            "sourceText": "Hi",
            "translatedText": "Привіт",
            "sourceCode": "en",
            "targetCode": "uk",
            "durationMs": "42",
        }))
        .expect("entry");
        assert_eq!(camel.source_text, "Hi");
        assert_eq!(camel.target_code, "uk");
        assert_eq!(camel.duration_ms, 42);
        assert!(!camel.id.is_empty());

        assert!(HistoryEntry::from_json(&json!(42)).is_none());
    }

    #[test]
    fn incomplete_entry_gets_defaults() {
        let entry =
            HistoryEntry::from_json(&json!({"date": "2026-01-01T00:00:00Z"})).expect("entry");
        assert_eq!(entry.source_code, "auto");
        assert_eq!(entry.target_code, "en");
        assert_eq!(entry.style, "auto");
        assert_eq!(entry.tone, "standard");
        assert_eq!(entry.duration_ms, 0);
        assert_eq!(entry.date, "2026-01-01T00:00:00Z");
        assert!(!entry.id.is_empty());
    }

    #[test]
    fn identifiers_look_like_uuid_v4_and_are_unique() {
        let mut seen = std::collections::HashSet::new();
        for _ in 0..1_000 {
            let id = new_identifier();
            assert_eq!(id.len(), 36);
            let groups: Vec<&str> = id.split('-').collect();
            assert_eq!(
                groups.iter().map(|g| g.len()).collect::<Vec<_>>(),
                vec![8, 4, 4, 4, 12]
            );
            assert!(id.chars().all(|c| c == '-' || c.is_ascii_hexdigit()));
            assert_eq!(&id[14..15], "4");
            assert!("89ab".contains(&id[19..20]));
            assert!(seen.insert(id));
        }
    }

    #[test]
    fn timestamps_are_iso_8601_utc() {
        assert_eq!(format_iso8601_utc(0), "1970-01-01T00:00:00Z");
        assert_eq!(format_iso8601_utc(951_782_400), "2000-02-29T00:00:00Z");
        assert_eq!(format_iso8601_utc(1_700_000_000), "2023-11-14T22:13:20Z");
        assert_eq!(format_iso8601_utc(1_735_689_600), "2025-01-01T00:00:00Z");
        let now = now_iso8601_utc();
        assert!(now.ends_with('Z'));
        assert_eq!(now.len(), 20);
    }

    #[cfg(windows)]
    #[test]
    fn default_path_follows_appdata() {
        let _guard = env_lock();
        let dir = TempDir::new("history-appdata");
        std::env::set_var("APPDATA", dir.path());
        let expected = dir.path().join("DeepL-oFM").join("history.json");
        assert_eq!(HistoryStore::default_path(), expected);
        std::env::remove_var("APPDATA");
    }

    #[cfg(not(windows))]
    #[test]
    fn default_path_follows_xdg_config_home() {
        let _guard = env_lock();
        let dir = TempDir::new("history-xdg");
        std::env::set_var("XDG_CONFIG_HOME", dir.path());
        let expected = dir.path().join("DeepL-oFM").join("history.json");
        assert_eq!(HistoryStore::default_path(), expected);
        std::env::remove_var("XDG_CONFIG_HOME");
    }

    #[cfg(not(windows))]
    #[test]
    fn default_path_falls_back_to_home() {
        let _guard = env_lock();
        let dir = TempDir::new("history-home");
        std::env::remove_var("XDG_CONFIG_HOME");
        std::env::set_var("HOME", dir.path());
        let expected = dir
            .path()
            .join(".config")
            .join("DeepL-oFM")
            .join("history.json");
        assert_eq!(HistoryStore::default_path(), expected);
    }

    /// Leftover `*.tmp` files in the store directory.
    ///
    /// Only the Unix test can make a directory read-only, so this helper is
    /// dead code elsewhere.
    #[cfg(unix)]
    fn temporary_files(dir: &TempDir) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(dir.path())
            .expect("read_dir")
            .filter_map(Result::ok)
            .map(|item| item.file_name().to_string_lossy().into_owned())
            .filter(|name| name.ends_with(".tmp"))
            .collect();
        names.sort();
        names
    }
}
