//! Default on-disk locations, mirroring the Python port.
//!
//! On Windows everything lives under `%APPDATA%\DeepL-oFM`; elsewhere under
//! `$XDG_CONFIG_HOME/DeepL-oFM` or `~/.config/DeepL-oFM` when the variable is
//! not set (the same rule `AppSettings::default_path` uses).

use std::env;
use std::path::PathBuf;

/// Folder created under the platform configuration root.
pub(crate) const APP_DIRECTORY: &str = "DeepL-oFM";

/// Directory holding `history.json` and the secret files.
pub(crate) fn default_directory() -> PathBuf {
    directory_from(|name| env::var_os(name)).join(APP_DIRECTORY)
}

/// The home directory, or the current directory when the OS has none.
pub(crate) fn home_directory() -> PathBuf {
    match dirs::home_dir() {
        Some(home) if !home.as_os_str().is_empty() => home,
        _ => PathBuf::from("."),
    }
}

/// Resolve the configuration root using `variable`, which is injectable so the
/// rules can be tested without touching the real environment.
fn directory_from(variable: impl Fn(&str) -> Option<std::ffi::OsString>) -> PathBuf {
    #[cfg(windows)]
    {
        if let Some(appdata) = variable("APPDATA").filter(|value| !value.is_empty()) {
            return PathBuf::from(appdata);
        }
        home_directory().join(".config")
    }
    #[cfg(not(windows))]
    {
        if let Some(config) = variable("XDG_CONFIG_HOME").filter(|value| !value.is_empty()) {
            return PathBuf::from(config);
        }
        home_directory().join(".config")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn configuration_root_follows_the_platform_variable() {
        let root = directory_from(|name| match name {
            #[cfg(windows)]
            "APPDATA" => Some(std::ffi::OsString::from("C:\\Roaming")),
            #[cfg(not(windows))]
            "XDG_CONFIG_HOME" => Some(std::ffi::OsString::from("/xdg/config")),
            _ => None,
        });
        #[cfg(windows)]
        assert_eq!(root, PathBuf::from("C:\\Roaming"));
        #[cfg(not(windows))]
        assert_eq!(root, PathBuf::from("/xdg/config"));
    }

    /// The fallback cannot be redirected on Windows: `dirs::home_dir` asks the
    /// OS for the profile folder instead of reading `HOME`, so the environment
    /// trick used here only works on Unix.
    #[cfg(unix)]
    #[test]
    fn configuration_root_falls_back_to_home() {
        let _guard = crate::test_support::env_lock();
        let dir = crate::test_support::TempDir::new("paths-home");
        std::env::set_var("HOME", dir.path());
        assert_eq!(directory_from(|_| None), dir.path().join(".config"));
    }

    #[cfg(unix)]
    #[test]
    fn empty_variables_are_ignored() {
        let _guard = crate::test_support::env_lock();
        let dir = crate::test_support::TempDir::new("paths-empty");
        std::env::set_var("HOME", dir.path());
        let root = directory_from(|_| Some(std::ffi::OsString::new()));
        assert_eq!(root, dir.path().join(".config"));
    }

    /// Windows falls back to the profile folder, which the OS owns.
    #[cfg(windows)]
    #[test]
    fn the_fallback_appends_config_to_the_profile_directory() {
        let root = directory_from(|_| None);
        assert_eq!(root, home_directory().join(".config"));
    }
}
