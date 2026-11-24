//! Logging to a file and panic reporting.
//!
//! A release Windows build uses `windows_subsystem = "windows"`, so stderr is
//! not visible and a failing global shortcut would leave no evidence behind.
//! [`install`] writes every log record to `%APPDATA%\DeepL-oFM\deepl-ofm.log`
//! (or the platform equivalent, next to `settings.json`) in addition to stderr,
//! and [`install_panic_hook`] records a panic with its thread and location
//! before the previous hook runs.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};

use log::{LevelFilter, Log, Metadata, Record};

use ofm_config::AppSettings;

/// File name inside the application configuration directory.
const LOG_FILE_NAME: &str = "deepl-ofm.log";

/// Default log file, next to `settings.json` and `history.json`.
pub fn default_log_path() -> PathBuf {
    AppSettings::default_path().with_file_name(LOG_FILE_NAME)
}

/// An append-only log file.
///
/// Writes never panic and a write failure is ignored: logging must never take
/// the application down.
pub struct FileLog {
    path: PathBuf,
    file: Mutex<Option<File>>,
}

impl FileLog {
    /// Open `path` for appending, creating the parent directory if needed.
    pub fn open(path: &Path) -> std::io::Result<Self> {
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            std::fs::create_dir_all(parent)?;
        }
        let file = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self {
            path: path.to_path_buf(),
            file: Mutex::new(Some(file)),
        })
    }

    /// Path of this log file.
    pub fn path(&self) -> &Path {
        &self.path
    }

    fn write(&self, record: &Record<'_>) {
        let line = format!(
            "[{}] {:<5} {}: {}\n",
            utc_timestamp(SystemTime::now()),
            record.level(),
            record.target(),
            record.args()
        );
        if let Ok(mut file) = self.file.lock() {
            if let Some(file) = file.as_mut() {
                let _ = file.write_all(line.as_bytes());
                let _ = file.flush();
            }
        }
    }
}

/// A console logger plus a [`FileLog`] for the log file.
pub struct CombinedLogger<L> {
    console: L,
    file: FileLog,
}

impl<L: Log> Log for CombinedLogger<L> {
    fn enabled(&self, metadata: &Metadata<'_>) -> bool {
        self.console.enabled(metadata)
    }

    fn log(&self, record: &Record<'_>) {
        if !self.console.enabled(record.metadata()) {
            return;
        }
        self.console.log(record);
        self.file.write(record);
    }

    fn flush(&self) {
        self.console.flush();
        if let Ok(mut file) = self.file.file.lock() {
            if let Some(file) = file.as_mut() {
                let _ = file.flush();
            }
        }
    }
}

/// Install `console` plus a file logger at the default path.
///
/// The console logger is built by the shell (`env_logger`), which keeps this
/// crate free of a logging backend.  `max_level` must match the console
/// filter; [`log`] needs it to enable the matching records.  The log file path
/// is returned even when it could not be opened, so the caller can report it
/// and the panic hook can try again.
pub fn install<L: Log + 'static>(console: L, max_level: LevelFilter) -> PathBuf {
    let path = default_log_path();
    let logger: Box<dyn Log> = match FileLog::open(&path) {
        Ok(file) => Box::new(CombinedLogger { console, file }),
        Err(error) => {
            eprintln!("could not open the log file {}: {error}", path.display());
            Box::new(console)
        }
    };
    if log::set_boxed_logger(logger).is_ok() {
        log::set_max_level(max_level);
    }
    path
}

/// Record every panic in `log_path`, then run the previous hook.
///
/// The file is opened for appending on each panic instead of sharing the
/// logger's mutex: a panic that happened while that mutex was held must still
/// be recorded.  The previous hook is kept so a debug build still prints to
/// stderr.
pub fn install_panic_hook(log_path: &Path) {
    let path = log_path.to_path_buf();
    let previous = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        let thread = std::thread::current()
            .name()
            .unwrap_or("unnamed")
            .to_string();
        let location = info
            .location()
            .map(|location| format!("{}:{}", location.file(), location.line()))
            .unwrap_or_else(|| "unknown location".to_string());
        let line = format!(
            "[{}] ERROR panic in thread {thread} at {location}: {}\n",
            utc_timestamp(SystemTime::now()),
            panic_payload(info.payload())
        );
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&path) {
            let _ = file.write_all(line.as_bytes());
            let _ = file.flush();
        }
        previous(info);
    }));
}

/// The message inside a panic payload.
fn panic_payload(payload: &(dyn std::any::Any + Send)) -> String {
    if let Some(message) = payload.downcast_ref::<&str>() {
        (*message).to_string()
    } else if let Some(message) = payload.downcast_ref::<String>() {
        message.clone()
    } else {
        "non-string panic payload".to_string()
    }
}

/// UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` form.
fn utc_timestamp(now: SystemTime) -> String {
    let seconds = now
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    let days = (seconds / 86_400) as i64;
    let remainder = seconds % 86_400;
    let (year, month, day) = civil_from_days(days);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}Z",
        remainder / 3600,
        (remainder % 3600) / 60,
        remainder % 60
    )
}

/// Gregorian date from days since 1970-01-01 (Howard Hinnant's algorithm).
fn civil_from_days(days: i64) -> (i64, u32, u32) {
    let days = days + 719_468;
    let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
    let day_of_era = days - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = if month_prime < 10 {
        month_prime + 3
    } else {
        month_prime - 9
    };
    let year = if month <= 2 { year + 1 } else { year };
    (year, month as u32, day as u32)
}

#[cfg(test)]
mod tests {
    use super::*;
    use log::Level;

    fn unique_log_path(tag: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ofm-logging-{tag}-{}-{}.log",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map(|duration| duration.as_nanos())
                .unwrap_or(0)
        ))
    }

    /// A console sink for the file tests: the record still goes to the file.
    struct SilentConsole;

    impl Log for SilentConsole {
        fn enabled(&self, _metadata: &Metadata<'_>) -> bool {
            true
        }

        fn log(&self, _record: &Record<'_>) {}

        fn flush(&self) {}
    }

    #[test]
    fn default_log_file_sits_next_to_the_settings() {
        assert_eq!(
            default_log_path()
                .file_name()
                .and_then(|name| name.to_str()),
            Some(LOG_FILE_NAME)
        );
    }

    #[test]
    fn the_log_file_receives_the_record() {
        let path = unique_log_path("record");
        let logger = CombinedLogger {
            console: SilentConsole,
            file: FileLog::open(&path).expect("open the log file"),
        };
        logger.log(
            &log::Record::builder()
                .args(format_args!("could not register the clipboard shortcut"))
                .level(Level::Error)
                .target("ofm::hotkeys")
                .build(),
        );
        drop(logger);

        let text = std::fs::read_to_string(&path).expect("read the log file");
        assert!(text.contains("ERROR"), "the level is missing: {text}");
        assert!(
            text.contains("could not register the clipboard shortcut"),
            "the message is missing: {text}"
        );
        assert!(
            text.contains("ofm::hotkeys"),
            "the target is missing: {text}"
        );
        assert!(
            text.trim_end().ends_with("shortcut"),
            "unexpected trailing data: {text}"
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn a_file_log_creates_its_directory() {
        let path = unique_log_path("nested").join("deepl-ofm.log");
        {
            let file = FileLog::open(&path).expect("open the nested log file");
            file.write(
                &log::Record::builder()
                    .args(format_args!("nested"))
                    .level(Level::Info)
                    .target("test")
                    .build(),
            );
            assert_eq!(file.path(), path.as_path());
        }
        assert!(path.exists());
        let _ = std::fs::remove_dir_all(path.parent().expect("parent"));
    }

    #[test]
    fn timestamps_are_utc() {
        assert_eq!(
            utc_timestamp(UNIX_EPOCH),
            "1970-01-01T00:00:00Z".to_string()
        );
        assert_eq!(
            utc_timestamp(UNIX_EPOCH + std::time::Duration::from_secs(1_000_000_000)),
            "2001-09-09T01:46:40Z".to_string()
        );
        assert_eq!(
            utc_timestamp(UNIX_EPOCH + std::time::Duration::from_secs(1_767_225_600)),
            "2026-01-01T00:00:00Z".to_string()
        );
    }

    #[test]
    fn the_panic_payload_is_reported() {
        // `panic!` produces either a `&str` or a `String` payload; anything
        // else must not be lost.
        let borrowed: &'static str = "a &str panic";
        assert_eq!(panic_payload(&borrowed), "a &str panic");
        let owned = "a String panic".to_string();
        assert_eq!(panic_payload(&owned), "a String panic");
        let number = 42_u32;
        assert_eq!(panic_payload(&number), "non-string panic payload");
    }
}
