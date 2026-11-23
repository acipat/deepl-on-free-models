//! Helpers shared by the crate's unit tests.
//!
//! Only compiled for `cfg(test)`: a self-deleting temporary directory and a
//! lock that serialises the tests which mutate process-wide environment
//! variables.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, MutexGuard};
use std::time::{SystemTime, UNIX_EPOCH};

/// Monotonic suffix so two tests never share a directory.
static DIRECTORY_SEQUENCE: AtomicU64 = AtomicU64::new(0);

/// Serialise tests that read or write process-wide environment variables.
pub(crate) fn env_lock() -> MutexGuard<'static, ()> {
    static LOCK: Mutex<()> = Mutex::new(());
    LOCK.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
}

/// A temporary directory that removes itself when dropped.
pub(crate) struct TempDir {
    path: PathBuf,
}

impl TempDir {
    /// Create a uniquely named directory under the system temporary folder.
    pub(crate) fn new(label: &str) -> Self {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|elapsed| elapsed.as_nanos())
            .unwrap_or(0);
        let sequence = DIRECTORY_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "ofm-store-{label}-{}-{nanos}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir_all(&path).expect("create temporary directory");
        Self { path }
    }

    /// Directory path.
    pub(crate) fn path(&self) -> &Path {
        &self.path
    }

    /// Join `name` onto the directory path.
    pub(crate) fn join(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.path);
    }
}
