//! Public-surface tests for `ofm-store`.
//!
//! These exercise the crate the way the application does: the stores are moved
//! between threads (they must be `Send + Sync` so async tasks can hold them),
//! and the on-disk documents keep the schema documented in `lib.rs`.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};

use ofm_store::{HistoryEntry, HistoryStore, SecretStore};

/// Field names of one `history.json` entry, in schema order.
const HISTORY_FIELDS: [&str; 10] = [
    "id",
    "date",
    "source_text",
    "translated_text",
    "source_code",
    "target_code",
    "style",
    "tone",
    "engine",
    "duration_ms",
];

fn temp_dir(label: &str) -> std::path::PathBuf {
    static SEQUENCE: AtomicU64 = AtomicU64::new(0);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|elapsed| elapsed.as_nanos())
        .unwrap_or(0);
    let sequence = SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!(
        "ofm-store-it-{label}-{}-{nanos}-{sequence}",
        std::process::id()
    ));
    std::fs::create_dir_all(&path).expect("create temporary directory");
    path
}

#[test]
fn stores_are_send_and_sync() {
    fn assert_send_sync<T: Send + Sync>() {}
    assert_send_sync::<HistoryStore>();
    assert_send_sync::<SecretStore>();
    assert_send_sync::<HistoryEntry>();
}

#[test]
fn history_store_is_shared_between_threads() {
    let dir = temp_dir("threads");
    let path = dir.join("history.json");
    let store = Arc::new(HistoryStore::with_path(path.clone()));
    let worker = Arc::clone(&store);

    let handles: Vec<thread::JoinHandle<()>> = (0..8)
        .map(|worker_index| {
            let store = Arc::clone(&store);
            thread::spawn(move || {
                for item in 0..10 {
                    let source = format!("Thread {worker_index} item {item}");
                    store.add(HistoryEntry::simple(&source, "переклад", "uk"));
                }
            })
        })
        .collect();
    for handle in handles {
        handle.join().expect("worker thread");
    }
    drop(worker);

    assert_eq!(store.entries().len(), 80);
    let reloaded = HistoryStore::with_path(path);
    assert_eq!(reloaded.entries(), store.entries());

    std::fs::remove_dir_all(dir).expect("remove temporary directory");
}

#[test]
fn history_json_keeps_the_documented_schema() {
    let dir = temp_dir("history-schema");
    let path = dir.join("history.json");
    let store = HistoryStore::with_path(path.clone());
    store.add(HistoryEntry::create(
        "Hello",
        "Привіт",
        "en",
        "uk",
        "natural",
        "formal",
        "ollama",
        830,
    ));

    let raw = std::fs::read_to_string(&path).expect("history file");
    let document: serde_json::Value = serde_json::from_str(&raw).expect("history json");
    let entries = document.as_array().expect("history is an array");
    assert_eq!(entries.len(), 1);
    let object = entries[0].as_object().expect("entry is an object");
    let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
    keys.sort_unstable();
    let mut expected = HISTORY_FIELDS.to_vec();
    expected.sort_unstable();
    assert_eq!(keys, expected);
    assert_eq!(object["source_text"], serde_json::json!("Hello"));
    assert_eq!(object["translated_text"], serde_json::json!("Привіт"));
    assert_eq!(object["duration_ms"], serde_json::json!(830));

    std::fs::remove_dir_all(dir).expect("remove temporary directory");
}

#[test]
fn secrets_file_keeps_the_documented_schema() {
    let dir = temp_dir("secrets-schema");
    let path = dir.join("secrets.json");
    let store = SecretStore::with_path(path.clone());
    store.write("provider:openai", "sk-test");

    let raw = std::fs::read_to_string(&path).expect("secret file");
    let document: serde_json::Value = serde_json::from_str(&raw).expect("secret json");
    let object = document.as_object().expect("secret document is an object");
    let mut keys: Vec<&str> = object.keys().map(String::as_str).collect();
    keys.sort_unstable();
    assert_eq!(keys, vec!["backend", "values", "version"]);
    assert_eq!(object["version"], serde_json::json!(1));
    assert_eq!(object["backend"], serde_json::json!(store.backend_name()));

    std::fs::remove_dir_all(dir).expect("remove temporary directory");
}
