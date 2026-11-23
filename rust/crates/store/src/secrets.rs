//! API-key storage.
//!
//! Ported from `windows/deepl_ofm/services/secrets.py`. On Windows and macOS a
//! usable `keyring` backend (Credential Manager / Keychain) is preferred; when
//! it is missing — or when the crate is built without a platform backend, which
//! makes `keyring` hand out its in-memory mock — the store falls back to a file:
//! DPAPI-encrypted `secrets.dat` on Windows, an owner-only `secrets.json`
//! elsewhere. Read, write and delete never panic: failures are logged and the
//! caller simply sees an empty key.

use std::collections::BTreeMap;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use base64::Engine as _;
use serde_json::{json, Value};

use crate::atomic;
use crate::dpapi;
use crate::error::StoreError;
use crate::paths;

/// Service name used for the platform credential entries, shared with Python.
const SERVICE: &str = "ua.admin.hymt";

/// Account name used only to probe whether `keyring` has a real backend.
const PROBE_ACCOUNT: &str = "ofm-store-backend-probe";

/// Unix mode applied to the secret files (`rw-------`).
const FILE_MODE: u32 = 0o600;

/// Storage the [`SecretStore`] writes to.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Backend {
    /// Platform credential store through `keyring`.
    Keyring,
    /// DPAPI-encrypted file, Windows only.
    Dpapi,
    /// Plain JSON file with owner-only permissions.
    Plain,
}

impl Backend {
    /// Name reported by [`SecretStore::backend_name`].
    fn name(self) -> &'static str {
        match self {
            Self::Keyring => "keyring",
            Self::Dpapi => "dpapi",
            Self::Plain => "plain",
        }
    }

    /// File name used by the file backends.
    fn file_name(self) -> &'static str {
        match self {
            Self::Dpapi => "secrets.dat",
            Self::Keyring | Self::Plain => "secrets.json",
        }
    }
}

/// One secret per account, mirroring `Keychain`'s read/write/delete API.
pub struct SecretStore {
    path: PathBuf,
    backend: Backend,
    lock: Mutex<()>,
}

impl Default for SecretStore {
    fn default() -> Self {
        Self::new()
    }
}

impl SecretStore {
    /// Open the platform store, falling back to a file when none is usable.
    pub fn new() -> Self {
        let backend = if keyring_is_usable() {
            Backend::Keyring
        } else {
            file_backend()
        };
        Self {
            path: paths::default_directory().join(backend.file_name()),
            backend,
            lock: Mutex::new(()),
        }
    }

    /// Force the file backend, so tests stay hermetic and callers can relocate
    /// the vault. On Windows that still means DPAPI when it is available.
    pub fn with_path(path: PathBuf) -> Self {
        Self {
            path,
            backend: file_backend(),
            lock: Mutex::new(()),
        }
    }

    /// Path used by the file backends (informational for the keyring backend).
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// `"keyring"`, `"dpapi"` or `"plain"`.
    pub fn backend_name(&self) -> &'static str {
        self.backend.name()
    }

    /// Read one account's secret; an unknown account yields an empty string.
    pub fn read(&self, account: &str) -> String {
        let account = account.trim();
        if account.is_empty() {
            return String::new();
        }

        let _guard = crate::lock(&self.lock);
        let outcome = match self.backend {
            Backend::Keyring => keyring_read(account),
            Backend::Dpapi | Backend::Plain => {
                Ok(self.read_values().remove(account).unwrap_or_default())
            }
        };
        match outcome {
            Ok(value) => value,
            Err(error) => {
                log::warn!("could not read secret {account:?}: {error}");
                String::new()
            }
        }
    }

    /// Store one account's secret; a blank value deletes the account.
    pub fn write(&self, account: &str, value: &str) {
        let account = account.trim();
        if account.is_empty() {
            return;
        }
        let secret = value.trim();
        if secret.is_empty() {
            self.delete(account);
            return;
        }

        let _guard = crate::lock(&self.lock);
        let outcome = match self.backend {
            Backend::Keyring => keyring_write(account, secret),
            Backend::Dpapi | Backend::Plain => self.write_values_entry(account, secret),
        };
        if let Err(error) = outcome {
            log::warn!("could not store secret {account:?}: {error}");
        }
    }

    /// Delete one account's secret; deleting a missing account is silent.
    pub fn delete(&self, account: &str) {
        let account = account.trim();
        if account.is_empty() {
            return;
        }

        let _guard = crate::lock(&self.lock);
        let outcome = match self.backend {
            Backend::Keyring => keyring_delete(account),
            Backend::Dpapi | Backend::Plain => {
                let mut values = self.read_values();
                if values.remove(account).is_none() {
                    return;
                }
                self.write_values(&values)
            }
        };
        if let Err(error) = outcome {
            log::warn!("could not delete secret {account:?}: {error}");
        }
    }

    /// Add or replace one account in the file, preserving all others.
    fn write_values_entry(&self, account: &str, secret: &str) -> Result<(), StoreError> {
        let mut values = self.read_values();
        values.insert(account.to_owned(), secret.to_owned());
        self.write_values(&values)
    }

    /// Read every account from the file, degrading to an empty map on damage.
    fn read_values(&self) -> BTreeMap<String, String> {
        let raw = match fs::read_to_string(&self.path) {
            Ok(raw) => raw,
            Err(error) if error.kind() == io::ErrorKind::NotFound => return BTreeMap::new(),
            Err(error) => {
                log::warn!(
                    "could not read secret file {}: {error}",
                    self.path.display()
                );
                return BTreeMap::new();
            }
        };

        let document: Value = match serde_json::from_str(&raw) {
            Ok(document) => document,
            Err(error) => {
                log::warn!(
                    "secret file {} is not valid JSON: {error}",
                    self.path.display()
                );
                return BTreeMap::new();
            }
        };

        let object = match document.as_object() {
            Some(object) => object,
            None => {
                log::warn!(
                    "secret file {} does not contain an object",
                    self.path.display()
                );
                return BTreeMap::new();
            }
        };

        // Accept both the documented wrapper and a bare account map.
        let stored = match object.get("values") {
            Some(Value::Object(stored)) => stored,
            Some(_) => {
                log::warn!("secret file {} has no values object", self.path.display());
                return BTreeMap::new();
            }
            None => object,
        };

        let mut values = BTreeMap::new();
        for (account, value) in stored {
            let Value::String(value) = value else {
                continue;
            };
            match self.backend {
                Backend::Dpapi => match decrypt(value) {
                    Some(plain) => {
                        values.insert(account.clone(), plain);
                    }
                    None => log::warn!("could not decrypt secret {account:?}"),
                },
                Backend::Keyring | Backend::Plain => {
                    values.insert(account.clone(), value.clone());
                }
            }
        }
        values
    }

    /// Replace the file with `values`, atomically and owner-only.
    fn write_values(&self, values: &BTreeMap<String, String>) -> Result<(), StoreError> {
        let mut stored = serde_json::Map::with_capacity(values.len());
        for (account, value) in values {
            let encoded = match self.backend {
                Backend::Dpapi => {
                    let sealed = dpapi::protect(value.as_bytes())?;
                    base64::engine::general_purpose::STANDARD.encode(sealed)
                }
                Backend::Keyring | Backend::Plain => value.clone(),
            };
            stored.insert(account.clone(), Value::String(encoded));
        }

        let document = json!({
            "version": 1,
            "backend": self.backend.name(),
            "values": Value::Object(stored),
        });
        let mut payload = serde_json::to_string_pretty(&document)?;
        payload.push('\n');
        atomic::write_atomically(&self.path, payload.as_bytes(), Some(FILE_MODE))?;
        Ok(())
    }
}

/// The file backend for this platform: DPAPI when available, else plain.
fn file_backend() -> Backend {
    if dpapi::is_available() {
        Backend::Dpapi
    } else {
        Backend::Plain
    }
}

/// Whether `keyring` has a real, persistent backend.
///
/// `keyring` 3.x silently selects its in-memory mock when the crate is built
/// without a platform backend, and that mock would pretend to store keys while
/// forgetting them on exit. The probe therefore rejects anything that is not
/// persistent and anything whose credential is the mock, then asks for one
/// entry without touching the store.
fn keyring_is_usable() -> bool {
    static USABLE: OnceLock<bool> = OnceLock::new();
    *USABLE.get_or_init(|| {
        use keyring::credential::CredentialPersistence;

        let builder = keyring::default::default_credential_builder();
        if !matches!(builder.persistence(), CredentialPersistence::UntilDelete) {
            log::debug!("the keyring backend does not persist secrets; using a file");
            return false;
        }

        let entry = match keyring::Entry::new(SERVICE, PROBE_ACCOUNT) {
            Ok(entry) => entry,
            Err(error) => {
                log::debug!("the keyring backend is unusable ({error}); using a file");
                return false;
            }
        };
        if entry.get_credential().is::<keyring::mock::MockCredential>() {
            log::debug!("keyring provided the mock backend; using a file");
            return false;
        }
        true
    })
}

/// Read an account from the platform credential store.
fn keyring_read(account: &str) -> Result<String, StoreError> {
    let entry = keyring::Entry::new(SERVICE, account).map_err(keyring_error)?;
    match entry.get_password() {
        Ok(value) => Ok(value),
        Err(keyring::Error::NoEntry) => Ok(String::new()),
        Err(error) => Err(keyring_error(error)),
    }
}

/// Write an account to the platform credential store.
fn keyring_write(account: &str, secret: &str) -> Result<(), StoreError> {
    let entry = keyring::Entry::new(SERVICE, account).map_err(keyring_error)?;
    entry.set_password(secret).map_err(keyring_error)
}

/// Delete an account from the platform credential store, tolerating a miss.
fn keyring_delete(account: &str) -> Result<(), StoreError> {
    let entry = keyring::Entry::new(SERVICE, account).map_err(keyring_error)?;
    match entry.delete_credential() {
        Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(keyring_error(error)),
    }
}

/// Convert a `keyring` failure into the crate's typed error.
fn keyring_error(error: keyring::Error) -> StoreError {
    StoreError::backend(error.to_string())
}

/// Decrypt one base64-encoded DPAPI value.
fn decrypt(encoded: &str) -> Option<String> {
    let sealed = base64::engine::general_purpose::STANDARD
        .decode(encoded.as_bytes())
        .ok()?;
    let plain = dpapi::unprotect(&sealed).ok()?;
    String::from_utf8(plain).ok()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::TempDir;

    /// Store bound to a file inside `dir`, the way the Python tests do it.
    fn store_in(dir: &TempDir) -> SecretStore {
        SecretStore::with_path(dir.join("secrets.json"))
    }

    #[test]
    fn backend_name_with_explicit_path() {
        let store = SecretStore::with_path(PathBuf::from("/nonexistent/DeepL-oFM/secrets.json"));
        assert!(["keyring", "dpapi", "plain"].contains(&store.backend_name()));
        #[cfg(windows)]
        assert!(["dpapi", "plain"].contains(&store.backend_name()));
        #[cfg(not(windows))]
        assert_eq!(store.backend_name(), "plain");
    }

    #[test]
    fn default_backend_name() {
        let store = SecretStore::new();
        assert!(["keyring", "dpapi", "plain"].contains(&store.backend_name()));
        #[cfg(not(windows))]
        assert_eq!(store.backend_name(), "plain");
    }

    #[test]
    fn default_path_uses_the_platform_file_name() {
        let store = SecretStore::new();
        let name = store
            .path()
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or_default();
        assert!(["secrets.json", "secrets.dat"].contains(&name));
    }

    #[test]
    fn round_trip_with_non_ascii() {
        let dir = TempDir::new("secrets-round-trip");
        let store = store_in(&dir);
        assert_eq!(store.read("provider:openai"), "");

        store.write("provider:openai", "sk-ключ-🔑-ü");
        assert_eq!(store.read("provider:openai"), "sk-ключ-🔑-ü");

        let other = store_in(&dir);
        assert_eq!(other.read("provider:openai"), "sk-ключ-🔑-ü");
    }

    #[test]
    fn write_trims_whitespace() {
        let dir = TempDir::new("secrets-trim");
        let store = store_in(&dir);
        store.write("provider:groq", "  gsk-123\n");
        assert_eq!(store.read("provider:groq"), "gsk-123");
    }

    #[test]
    fn account_names_are_trimmed() {
        let dir = TempDir::new("secrets-trim-account");
        let store = store_in(&dir);
        store.write("  provider:openai  ", "sk-1");
        assert_eq!(store.read("provider:openai"), "sk-1");
        assert_eq!(store.read("  provider:openai  "), "sk-1");
        store.delete("provider:openai");
        assert_eq!(store.read("provider:openai"), "");
    }

    #[test]
    fn multiple_accounts_and_delete() {
        let dir = TempDir::new("secrets-multiple");
        let store = store_in(&dir);
        store.write("provider:openai", "one");
        store.write("provider:groq", "two");
        assert_eq!(store.read("provider:openai"), "one");
        assert_eq!(store.read("provider:groq"), "two");

        store.delete("provider:openai");
        assert_eq!(store.read("provider:openai"), "");
        assert_eq!(store.read("provider:groq"), "two");
    }

    #[test]
    fn empty_value_deletes_account() {
        let dir = TempDir::new("secrets-empty");
        let store = store_in(&dir);
        store.write("provider:openai", "sk-1");
        store.write("provider:openai", "   ");
        assert_eq!(store.read("provider:openai"), "");
    }

    #[test]
    fn delete_missing_account_is_silent() {
        let dir = TempDir::new("secrets-delete-missing");
        let store = store_in(&dir);
        store.delete("never-written");
        store.delete("");
        store.write("", "value");
        assert_eq!(store.read(""), "");
        assert_eq!(store.read("never-written"), "");
    }

    #[test]
    fn missing_account_and_missing_file() {
        let dir = TempDir::new("secrets-missing");
        let store = store_in(&dir);
        assert_eq!(store.read("provider:openai"), "");
        assert!(!dir.join("secrets.json").exists());
    }

    #[cfg(unix)]
    #[test]
    fn file_permissions_are_owner_only() {
        use std::os::unix::fs::PermissionsExt;

        let dir = TempDir::new("secrets-permissions");
        let store = store_in(&dir);
        if store.backend_name() != "plain" {
            return;
        }
        store.write("account", "value");
        let mode = fs::metadata(dir.join("secrets.json"))
            .expect("metadata")
            .permissions()
            .mode();
        assert_eq!(mode & 0o777, 0o600);
    }

    #[test]
    fn file_document_shape() {
        let dir = TempDir::new("secrets-shape");
        let store = store_in(&dir);
        store.write("account", "value");

        let raw = fs::read_to_string(dir.join("secrets.json")).expect("read");
        let document: Value = serde_json::from_str(&raw).expect("json");
        assert_eq!(document["version"], json!(1));
        assert_eq!(document["backend"], json!(store.backend_name()));
        let values = document["values"].as_object().expect("values object");
        assert_eq!(values.len(), 1);
        assert!(values.contains_key("account"));
        if store.backend_name() == "plain" {
            assert_eq!(values["account"], json!("value"));
        } else {
            assert_ne!(values["account"], json!("value"));
        }
    }

    #[test]
    fn corrupt_file_degrades_and_recovers() {
        let dir = TempDir::new("secrets-corrupt");
        let path = dir.join("secrets.json");
        fs::write(&path, "{not json").expect("seed");
        let store = store_in(&dir);

        assert_eq!(store.read("account"), "");
        store.write("account", "value");
        assert_eq!(store.read("account"), "value");

        let raw = fs::read_to_string(&path).expect("read");
        let document: Value = serde_json::from_str(&raw).expect("json");
        let values = document["values"].as_object().expect("values");
        assert_eq!(values.len(), 1);
        assert!(values.contains_key("account"));
    }

    #[test]
    fn directory_as_path_never_panics() {
        let dir = TempDir::new("secrets-directory");
        let store = SecretStore::with_path(dir.path().to_path_buf());
        assert_eq!(store.read("account"), "");
        store.write("account", "value");
        store.delete("account");
        assert_eq!(store.read("account"), "");
    }

    #[test]
    fn nested_directory_is_created() {
        let dir = TempDir::new("secrets-nested");
        let path = dir
            .path()
            .join("nested")
            .join("deeper")
            .join("secrets.json");
        let store = SecretStore::with_path(path.clone());
        store.write("account", "value");
        assert_eq!(store.read("account"), "value");
        assert!(path.is_file());
    }

    #[test]
    fn read_never_raises_on_bad_types() {
        let dir = TempDir::new("secrets-bad-types");
        let path = dir.join("secrets.json");
        fs::write(
            &path,
            json!({"values": {"ok": "yes", "bad": 12}}).to_string(),
        )
        .expect("seed");
        let store = store_in(&dir);
        if store.backend_name() == "plain" {
            assert_eq!(store.read("ok"), "yes");
        } else {
            assert_eq!(store.read("ok"), "");
        }
        assert_eq!(store.read("bad"), "");
    }

    #[test]
    fn flat_document_without_wrapper_is_accepted() {
        let dir = TempDir::new("secrets-flat");
        let path = dir.join("secrets.json");
        fs::write(&path, json!({"account": "value"}).to_string()).expect("seed");
        let store = store_in(&dir);
        if store.backend_name() == "plain" {
            assert_eq!(store.read("account"), "value");
        }
    }

    #[test]
    fn unusable_values_section_degrades() {
        let dir = TempDir::new("secrets-unusable");
        let path = dir.join("secrets.json");
        fs::write(&path, json!({"values": ["not", "a", "map"]}).to_string()).expect("seed");
        let store = store_in(&dir);
        assert_eq!(store.read("account"), "");

        fs::write(&path, "[]").expect("seed list");
        assert_eq!(store.read("account"), "");
    }

    #[test]
    fn unicode_account_names_are_preserved() {
        let dir = TempDir::new("secrets-unicode-account");
        let store = store_in(&dir);
        store.write("постачальник:ключ", "значення");
        assert_eq!(store.read("постачальник:ключ"), "значення");
        assert_eq!(
            SecretStore::with_path(dir.join("secrets.json")).read("постачальник:ключ"),
            "значення"
        );
    }

    #[test]
    fn concurrent_writes_keep_every_account() {
        use std::sync::Arc;

        let dir = TempDir::new("secrets-concurrent");
        let store = Arc::new(SecretStore::with_path(dir.join("secrets.json")));
        let mut handles = Vec::new();
        for index in 0..8 {
            let store = Arc::clone(&store);
            handles.push(std::thread::spawn(move || {
                for round in 0..10 {
                    let account = format!("provider:{index}:{round}");
                    store.write(&account, &format!("value-{index}-{round}"));
                }
            }));
        }
        for handle in handles {
            handle.join().expect("writer thread");
        }

        let raw = fs::read_to_string(dir.join("secrets.json")).expect("read");
        let document: Value = serde_json::from_str(&raw).expect("valid json");
        assert_eq!(document["values"].as_object().expect("values").len(), 80);
        for index in 0..8 {
            assert_eq!(
                store.read(&format!("provider:{index}:9")),
                format!("value-{index}-9")
            );
        }
    }
}
