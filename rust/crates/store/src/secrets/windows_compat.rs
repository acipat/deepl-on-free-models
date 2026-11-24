//! Windows Credential Manager targets used by python-keyring and earlier Rust builds.

use super::{atomic, decrypt, keyring_error, Backend, SecretStore, StoreError, FILE_MODE, SERVICE};
use keyring::{Entry, Error as KeyringError};
use serde_json::{Map, Value};
use std::{fs, io, ptr};
use windows::core::HSTRING;
use windows::Win32::Foundation::ERROR_NOT_FOUND;
use windows::Win32::Security::Credentials::{CredFree, CredReadW, CREDENTIALW, CRED_TYPE_GENERIC};

fn optional<T>(result: keyring::Result<T>) -> Result<Option<T>, StoreError> {
    match result {
        Ok(value) => Ok(Some(value)),
        Err(KeyringError::NoEntry) => Ok(None),
        Err(error) => Err(keyring_error(error)),
    }
}

fn compound_entry(account: &str) -> Result<Entry, StoreError> {
    Entry::new_with_target(&format!("{account}@{SERVICE}"), SERVICE, account).map_err(keyring_error)
}

/// Python also uses a shared target named after the service. Read its owner
/// and blob from the same Win32 snapshot so a different provider's key can
/// never be returned between two lookups.
fn shared_entry<T>(
    account: &str,
    inspect: impl FnOnce(&CREDENTIALW) -> Result<T, StoreError>,
) -> Result<Option<T>, StoreError> {
    let mut raw = ptr::null_mut();
    // SAFETY: CredReadW initialises raw on success; it remains live until CredFree.
    if let Err(error) =
        unsafe { CredReadW(&HSTRING::from(SERVICE), CRED_TYPE_GENERIC, None, &mut raw) }
    {
        return if error.code() == ERROR_NOT_FOUND.to_hresult() {
            Ok(None)
        } else {
            Err(StoreError::backend(error.to_string()))
        };
    }
    // SAFETY: Win32 owns this record and its NUL-terminated (optional) user name.
    let record = unsafe { &*raw };
    let matches = !record.UserName.is_null()
        && account
            .encode_utf16()
            .eq(unsafe { record.UserName.as_wide() }.iter().copied());
    let result = if matches {
        inspect(record).map(Some)
    } else {
        Ok(None)
    };
    // SAFETY: this is the buffer returned by our successful CredReadW call.
    unsafe { CredFree(raw.cast()) };
    result
}

fn password(record: &CREDENTIALW) -> Result<String, StoreError> {
    let size = record.CredentialBlobSize as usize;
    if size == 0 {
        return Ok(String::new());
    }
    if record.CredentialBlob.is_null() || size % 2 != 0 {
        return Err(StoreError::backend("invalid Windows credential blob"));
    }
    // SAFETY: the live Win32 record owns CredentialBlobSize bytes.
    let bytes = unsafe { std::slice::from_raw_parts(record.CredentialBlob, size) };
    let units = bytes
        .chunks_exact(2)
        .map(|p| u16::from_le_bytes([p[0], p[1]]));
    char::decode_utf16(units)
        .collect::<Result<String, _>>()
        .map_err(|_| StoreError::backend("invalid UTF-16 in Windows credential"))
}

pub(super) fn read(store: &SecretStore, account: &str) -> Result<String, StoreError> {
    if let Some(value) = shared_entry(account, password)? {
        return Ok(value);
    }
    if let Some(value) = optional(compound_entry(account)?.get_password())? {
        return Ok(value);
    }
    let old = Entry::new(SERVICE, account).map_err(keyring_error)?;
    if let Some(value) = optional(old.get_password())? {
        return Ok(value);
    }
    let Some(mut doc) = dpapi_document(store)? else {
        return Ok(String::new());
    };
    match dpapi_accounts(&mut doc)?
        .get(account)
        .and_then(Value::as_str)
    {
        Some(blob) => {
            decrypt(blob).ok_or_else(|| StoreError::backend("could not decrypt saved key"))
        }
        None => Ok(String::new()),
    }
}

pub(super) fn write(store: &SecretStore, account: &str, value: &str) -> Result<(), StoreError> {
    let entry = if shared_entry(account, |_| Ok(()))?.is_some() {
        Entry::new_with_target(SERVICE, SERVICE, account).map_err(keyring_error)?
    } else {
        compound_entry(account)?
    };
    entry.set_password(value).map_err(keyring_error)?;
    remove_old_key(store, account)
}

pub(super) fn delete(store: &SecretStore, account: &str) -> Result<(), StoreError> {
    remove_old_key(store, account)?;
    optional(compound_entry(account)?.delete_credential())?;
    if shared_entry(account, |_| Ok(()))?.is_some() {
        let entry = Entry::new_with_target(SERVICE, SERVICE, account).map_err(keyring_error)?;
        optional(entry.delete_credential())?;
    }
    Ok(())
}

fn dpapi_document(store: &SecretStore) -> Result<Option<Value>, StoreError> {
    let path = store.path.with_file_name(Backend::Dpapi.file_name());
    match fs::read(path) {
        Ok(bytes) => Ok(Some(serde_json::from_slice(&bytes)?)),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}

fn dpapi_accounts(doc: &mut Value) -> Result<&mut Map<String, Value>, StoreError> {
    let accounts = if doc.get("values").is_some() {
        &mut doc["values"]
    } else {
        doc
    };
    accounts
        .as_object_mut()
        .ok_or_else(|| StoreError::backend("invalid DPAPI account map"))
}

/// Retire just this account's old representations after a successful write,
/// or before deleting its live key. Other encrypted records stay opaque.
fn remove_old_key(store: &SecretStore, account: &str) -> Result<(), StoreError> {
    let old = Entry::new(SERVICE, account).map_err(keyring_error)?;
    optional(old.delete_credential())?;
    if let Some(mut doc) = dpapi_document(store)? {
        if dpapi_accounts(&mut doc)?.remove(account).is_some() {
            let path = store.path.with_file_name(Backend::Dpapi.file_name());
            atomic::write_atomically(&path, &serde_json::to_vec_pretty(&doc)?, Some(FILE_MODE))?;
        }
    }
    Ok(())
}
