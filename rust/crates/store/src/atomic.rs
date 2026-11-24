//! Crash-safe file replacement.
//!
//! Both stores rewrite a single JSON document. A half-written file would be
//! read back as corruption, so every save goes through a temporary sibling
//! file that is `fsync`ed and only then renamed over the target. `rename` is
//! atomic on every supported platform, therefore a reader either sees the old
//! document or the new one, never a truncated mixture.

use std::ffi::OsStr;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

/// Monotonic suffix so two writers never pick the same temporary name.
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// Replace `path` with `bytes` atomically.
///
/// The payload is written to `"<name>.<pid>.<sequence>.tmp"` in the target
/// directory, flushed with `fsync`, and then renamed over `path`. Missing
/// parent directories are created. On Unix the file is created with `mode`
/// (default `0600`). When anything fails the temporary file is removed and the
/// previous contents of `path` are left untouched.
pub(crate) fn write_atomically(path: &Path, bytes: &[u8], mode: Option<u32>) -> io::Result<()> {
    let parent = match path.parent() {
        Some(parent) if !parent.as_os_str().is_empty() => parent,
        _ => Path::new("."),
    };
    fs::create_dir_all(parent)?;

    let name = path.file_name().unwrap_or_else(|| OsStr::new("store"));
    let prefix = name.to_string_lossy();
    let (temp_path, mut file) = create_temporary(parent, &prefix, mode)?;

    let written = file
        .write_all(bytes)
        .and_then(|()| file.flush())
        .and_then(|()| file.sync_all());
    drop(file);
    if let Err(error) = written {
        remove_temporary(&temp_path);
        return Err(error);
    }

    // `rename` replaces an existing file atomically on Unix; on Windows the
    // standard library uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`.
    if let Err(error) = fs::rename(&temp_path, path) {
        remove_temporary(&temp_path);
        return Err(error);
    }

    if let Some(mode) = mode {
        set_mode(path, mode);
    }
    sync_directory(parent);
    Ok(())
}

/// Create a fresh temporary file, retrying when a name is already taken.
fn create_temporary(parent: &Path, prefix: &str, mode: Option<u32>) -> io::Result<(PathBuf, File)> {
    #[cfg(not(unix))]
    let _ = mode;

    for _ in 0..32 {
        let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let candidate = parent.join(format!("{prefix}.{}.{sequence}.tmp", std::process::id()));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(mode.unwrap_or(0o600));
        }
        match options.open(&candidate) {
            Ok(file) => return Ok((candidate, file)),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::AlreadyExists,
        "could not create a uniquely named temporary file",
    ))
}

/// Best-effort removal of a temporary file that will not be renamed.
fn remove_temporary(path: &Path) {
    if let Err(error) = fs::remove_file(path) {
        log::debug!(
            "could not remove temporary file {}: {error}",
            path.display()
        );
    }
}

/// Apply a Unix permission mode; a no-op elsewhere or when the mode is ignored.
fn set_mode(path: &Path, mode: u32) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if let Err(error) = fs::set_permissions(path, fs::Permissions::from_mode(mode)) {
            log::debug!("could not set permissions on {}: {error}", path.display());
        }
    }
    #[cfg(not(unix))]
    {
        let _ = (path, mode);
    }
}

/// Make the rename itself durable on POSIX; Windows flushes metadata itself.
fn sync_directory(directory: &Path) {
    #[cfg(unix)]
    {
        match File::open(directory) {
            Ok(handle) => {
                if let Err(error) = handle.sync_all() {
                    log::debug!("could not fsync {}: {error}", directory.display());
                }
            }
            Err(error) => log::debug!("could not open {} for fsync: {error}", directory.display()),
        }
    }
    #[cfg(not(unix))]
    {
        let _ = directory;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::test_support::TempDir;

    #[test]
    fn writes_a_new_file() {
        let dir = TempDir::new("atomic-new");
        let path = dir.join("value.json");
        write_atomically(&path, b"{\"a\":1}\n", None).expect("write");
        assert_eq!(fs::read_to_string(&path).expect("read"), "{\"a\":1}\n");
    }

    #[test]
    fn replaces_an_existing_file_and_creates_parents() {
        let dir = TempDir::new("atomic-replace");
        let path = dir.path().join("deep").join("nested").join("value.json");
        write_atomically(&path, b"first", None).expect("first write");
        write_atomically(&path, b"second", None).expect("second write");
        assert_eq!(fs::read_to_string(&path).expect("read"), "second");
    }

    #[test]
    fn failure_leaves_the_previous_file_and_no_temporary() {
        let dir = TempDir::new("atomic-failure");
        let path = dir.join("value.json");
        write_atomically(&path, b"keep me", None).expect("initial write");

        // Renaming a file over a directory fails on every platform.
        let target = dir.join("target-directory");
        fs::create_dir(&target).expect("directory");
        write_atomically(&target, b"lost", None).expect_err("rename must fail");
        assert!(target.is_dir());
        assert_eq!(fs::read_to_string(&path).expect("read"), "keep me");
        assert_eq!(temporary_files(&dir), Vec::<String>::new());
    }

    #[test]
    fn temporary_files_are_not_left_behind() {
        let dir = TempDir::new("atomic-temp");
        let path = dir.join("value.json");
        write_atomically(&path, b"value", Some(0o600)).expect("write");
        assert_eq!(temporary_files(&dir), Vec::<String>::new());
    }

    #[cfg(unix)]
    #[test]
    fn requested_mode_is_applied() {
        use std::os::unix::fs::PermissionsExt;
        let dir = TempDir::new("atomic-mode");
        let path = dir.join("secrets.json");
        write_atomically(&path, b"value", Some(0o600)).expect("write");
        let mode = fs::metadata(&path).expect("metadata").permissions().mode() & 0o777;
        assert_eq!(mode, 0o600);
    }

    #[test]
    fn concurrent_writers_never_leave_a_partial_file() {
        use std::sync::Arc;

        let dir = TempDir::new("atomic-concurrent");
        let path = Arc::new(dir.join("value.json"));
        let payloads: Vec<String> = (0..8).map(|index| format!("payload-{index}")).collect();
        let mut handles = Vec::new();
        for payload in payloads.clone() {
            let path = Arc::clone(&path);
            handles.push(std::thread::spawn(move || {
                for _ in 0..25 {
                    write_atomically(&path, payload.as_bytes(), None).expect("write");
                }
            }));
        }
        for handle in handles {
            handle.join().expect("writer thread");
        }
        let stored = fs::read_to_string(path.as_ref()).expect("read");
        assert!(payloads.contains(&stored), "unexpected payload: {stored:?}");
        assert_eq!(temporary_files(&dir), Vec::<String>::new());
    }

    /// Names of leftover `*.tmp` files in `dir`, sorted for stable assertions.
    fn temporary_files(dir: &TempDir) -> Vec<String> {
        let mut names: Vec<String> = fs::read_dir(dir.path())
            .expect("read_dir")
            .filter_map(Result::ok)
            .map(|entry| entry.file_name().to_string_lossy().into_owned())
            .filter(|name| name.ends_with(".tmp"))
            .collect();
        names.sort();
        names
    }
}
