//! "Open at login": start DeepL-oFM when the user signs in.
//!
//! Ported from the macOS app's `SMAppService.mainApp` controls.  Each platform
//! has its own native mechanism:
//!
//! * **Windows** — a value under
//!   `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`;
//! * **macOS** — a LaunchAgent plist in `~/Library/LaunchAgents`, loaded with
//!   `launchctl bootstrap` and unloaded with `launchctl bootout`;
//! * **Linux and other Unix** — an XDG autostart desktop entry.
//!
//! The module compiles everywhere: platforms without an implementation report
//! [`StartupStatus::Unsupported`] instead of failing.  [`StartupLocation`] takes
//! the directory that stands in for the user's home, so tests never touch the
//! real profile; [`status`] only reads and never creates anything.

use std::fmt;
use std::path::PathBuf;

/// Current state of the "Open at login" registration.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum StartupStatus {
    /// The app is registered and will start at login.
    Enabled,
    /// The app is not registered.
    Disabled,
    /// The registration exists but the user must approve it in System Settings.
    ///
    /// macOS reports this through `SMAppService`; the LaunchAgent backend has no
    /// approval step and never returns it, but the value is part of the
    /// cross-platform contract the frontend renders.
    RequiresApproval,
    /// This platform cannot manage login items.
    Unsupported,
}

impl StartupStatus {
    /// Stable wire value used by the app state and the frontend.
    pub fn value(self) -> &'static str {
        match self {
            Self::Enabled => "enabled",
            Self::Disabled => "disabled",
            Self::RequiresApproval => "requiresApproval",
            Self::Unsupported => "unsupported",
        }
    }
}

/// Failure returned by [`set_enabled`].
///
/// The app localises [`message`](Self::message) into the same
/// "Could not change Open at login. %@" string as the macOS original.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct StartupError {
    /// Platform-neutral reason for the failure.
    pub message: String,
}

impl StartupError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

impl fmt::Display for StartupError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.message)
    }
}

impl std::error::Error for StartupError {}

/// Where the "Open at login" registration lives.
///
/// [`new`](Self::new) uses the real user profile. [`with_root`](Self::with_root)
/// points the file-based backends at another directory so tests are hermetic.
#[derive(Clone, Debug)]
pub struct StartupLocation {
    /// Directory treated as the user's home directory by the file-based
    /// backends. Empty when the platform did not report one.
    #[cfg_attr(windows, allow(dead_code))]
    root: PathBuf,
}

impl StartupLocation {
    /// The real user profile.
    pub fn new() -> Self {
        Self {
            root: home_directory(),
        }
    }

    /// A location rooted at `root` instead of the user's home directory.
    ///
    /// The Windows backend always writes the current user's registry, so `root`
    /// only affects the macOS and Linux/Unix backends.
    pub fn with_root(root: impl Into<PathBuf>) -> Self {
        Self { root: root.into() }
    }

    /// Current state, without creating or changing anything.
    pub fn status(&self) -> StartupStatus {
        #[cfg(windows)]
        {
            windows::status()
        }
        #[cfg(target_os = "macos")]
        {
            macos::status(&self.root)
        }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            linux::status(&self.root)
        }
        #[cfg(not(any(windows, unix)))]
        {
            StartupStatus::Unsupported
        }
    }

    /// Register or unregister the current executable for login startup.
    pub fn set_enabled(&self, enabled: bool) -> Result<StartupStatus, StartupError> {
        #[cfg(windows)]
        {
            windows::set_enabled(enabled)
        }
        #[cfg(target_os = "macos")]
        {
            macos::set_enabled(&self.root, enabled)
        }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            linux::set_enabled(&self.root, enabled)
        }
        #[cfg(not(any(windows, unix)))]
        {
            let _ = enabled;
            Ok(StartupStatus::Unsupported)
        }
    }

    /// Open the system page where login items are approved.
    ///
    /// Returns `false` when the platform has no such page.
    pub fn open_settings(&self) -> bool {
        #[cfg(windows)]
        {
            windows::open_settings()
        }
        #[cfg(target_os = "macos")]
        {
            macos::open_settings()
        }
        #[cfg(all(unix, not(target_os = "macos")))]
        {
            linux::open_settings()
        }
        #[cfg(not(any(windows, unix)))]
        {
            false
        }
    }
}

impl Default for StartupLocation {
    fn default() -> Self {
        Self::new()
    }
}

/// Current state of the real user's login-item registration.
pub fn status() -> StartupStatus {
    StartupLocation::new().status()
}

/// Register or unregister the current executable for login startup.
pub fn set_enabled(enabled: bool) -> Result<StartupStatus, StartupError> {
    StartupLocation::new().set_enabled(enabled)
}

/// Open the system page where login items are approved.
pub fn open_settings() -> bool {
    StartupLocation::new().open_settings()
}

/// The user's home directory, or an empty path when it cannot be resolved.
fn home_directory() -> PathBuf {
    std::env::var_os("HOME")
        .filter(|value| !value.is_empty())
        .map(PathBuf::from)
        .unwrap_or_default()
}

// ------------------------------------------------------------------ Windows

#[cfg(windows)]
mod windows {
    use windows::core::PCWSTR;
    use windows::Win32::Foundation::{ERROR_FILE_NOT_FOUND, ERROR_SUCCESS, WIN32_ERROR};
    use windows::Win32::System::Registry::{
        RegCloseKey, RegCreateKeyExW, RegDeleteValueW, RegOpenKeyExW, RegQueryValueExW,
        RegSetValueExW, HKEY, HKEY_CURRENT_USER, KEY_QUERY_VALUE, KEY_SET_VALUE,
        REG_OPTION_NON_VOLATILE, REG_SZ, REG_VALUE_TYPE,
    };

    use super::{StartupError, StartupStatus};

    /// Per-user registry key Windows runs at login.
    const RUN_KEY: &str = r"Software\Microsoft\Windows\CurrentVersion\Run";
    /// Value name the shell reads; kept stable so upgrades replace themselves.
    const VALUE_NAME: &str = "DeepL-oFM";

    pub(super) fn status() -> StartupStatus {
        let subkey = wide(RUN_KEY);
        let mut key = HKEY::default();
        // SAFETY: `subkey` is a NUL-terminated wide string that outlives the
        // call, `key` is valid writable memory, and a successfully opened
        // handle is closed exactly once below.
        let opened = unsafe {
            RegOpenKeyExW(
                HKEY_CURRENT_USER,
                PCWSTR(subkey.as_ptr()),
                None,
                KEY_QUERY_VALUE,
                &mut key,
            )
        };
        if opened != ERROR_SUCCESS {
            return StartupStatus::Disabled;
        }

        let name = wide(VALUE_NAME);
        let mut kind = REG_VALUE_TYPE(0);
        let mut size = 0u32;
        // SAFETY: `key` is open, `name` is a NUL-terminated wide string, and
        // both out-parameters point at initialised local storage.
        let queried = unsafe {
            RegQueryValueExW(
                key,
                PCWSTR(name.as_ptr()),
                None,
                Some(&mut kind),
                None,
                Some(&mut size),
            )
        };
        // SAFETY: the handle was opened above and is closed exactly once here.
        let _ = unsafe { RegCloseKey(key) };

        if queried == ERROR_SUCCESS {
            StartupStatus::Enabled
        } else {
            if queried != ERROR_FILE_NOT_FOUND {
                log::debug!(
                    "could not read HKCU\\{RUN_KEY}\\{VALUE_NAME}: {}",
                    describe(queried)
                );
            }
            StartupStatus::Disabled
        }
    }

    pub(super) fn set_enabled(enabled: bool) -> Result<StartupStatus, StartupError> {
        if enabled {
            enable()
        } else {
            disable()
        }
    }

    fn enable() -> Result<StartupStatus, StartupError> {
        let executable = std::env::current_exe().map_err(|error| {
            StartupError::new(format!("could not locate the application: {error}"))
        })?;
        let command = format!("\"{}\"", executable.display());

        let subkey = wide(RUN_KEY);
        let mut key = HKEY::default();
        // SAFETY: `subkey` is a NUL-terminated wide string that outlives the
        // call, `key` is valid writable memory, and the returned handle is
        // closed on every path that opens it.
        let created = unsafe {
            RegCreateKeyExW(
                HKEY_CURRENT_USER,
                PCWSTR(subkey.as_ptr()),
                None,
                PCWSTR::null(),
                REG_OPTION_NON_VOLATILE,
                KEY_SET_VALUE,
                None,
                &mut key,
                None,
            )
        };
        if created != ERROR_SUCCESS {
            return Err(StartupError::new(describe(created)));
        }

        let name = wide(VALUE_NAME);
        let data: Vec<u8> = command
            .encode_utf16()
            .chain(std::iter::once(0))
            .flat_map(u16::to_le_bytes)
            .collect();
        // SAFETY: `key` is open, `name` is a NUL-terminated wide string, and
        // `data` is the UTF-16LE value including its terminating NUL.
        let written =
            unsafe { RegSetValueExW(key, PCWSTR(name.as_ptr()), None, REG_SZ, Some(&data)) };
        // SAFETY: the handle was opened above and is closed exactly once here.
        let _ = unsafe { RegCloseKey(key) };

        if written == ERROR_SUCCESS {
            Ok(StartupStatus::Enabled)
        } else {
            Err(StartupError::new(describe(written)))
        }
    }

    fn disable() -> Result<StartupStatus, StartupError> {
        let subkey = wide(RUN_KEY);
        let mut key = HKEY::default();
        // SAFETY: `subkey` is a NUL-terminated wide string that outlives the
        // call, `key` is valid writable memory, and a successfully opened
        // handle is closed exactly once below.
        let opened = unsafe {
            RegOpenKeyExW(
                HKEY_CURRENT_USER,
                PCWSTR(subkey.as_ptr()),
                None,
                KEY_SET_VALUE,
                &mut key,
            )
        };
        if opened == ERROR_FILE_NOT_FOUND {
            return Ok(StartupStatus::Disabled);
        }
        if opened != ERROR_SUCCESS {
            return Err(StartupError::new(describe(opened)));
        }

        let name = wide(VALUE_NAME);
        // SAFETY: `key` is open and `name` is a NUL-terminated wide string.
        let deleted = unsafe { RegDeleteValueW(key, PCWSTR(name.as_ptr())) };
        // SAFETY: the handle was opened above and is closed exactly once here.
        let _ = unsafe { RegCloseKey(key) };

        match deleted {
            ERROR_SUCCESS | ERROR_FILE_NOT_FOUND => Ok(StartupStatus::Disabled),
            code => Err(StartupError::new(describe(code))),
        }
    }

    pub(super) fn open_settings() -> bool {
        use std::os::windows::process::CommandExt;

        /// Do not flash a console window for the helper process.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;

        std::process::Command::new("cmd")
            .args(["/C", "start", "", "ms-settings:startupapps"])
            .creation_flags(CREATE_NO_WINDOW)
            .spawn()
            .is_ok()
    }

    /// NUL-terminated UTF-16 for the wide Win32 entry points.
    fn wide(value: &str) -> Vec<u16> {
        value.encode_utf16().chain(std::iter::once(0)).collect()
    }

    fn describe(code: WIN32_ERROR) -> String {
        std::io::Error::from_raw_os_error(code.0 as i32).to_string()
    }
}

// -------------------------------------------------------------------- macOS

#[cfg(target_os = "macos")]
mod macos {
    use std::fs;
    use std::io;
    use std::path::{Path, PathBuf};
    use std::process::{Command, Output};

    use super::{StartupError, StartupStatus};

    /// Reverse-DNS label shared with the app bundle identifier.
    const LABEL: &str = "ua.admin.hymt";
    /// File name inside `~/Library/LaunchAgents`.
    const PLIST_NAME: &str = "ua.admin.hymt.plist";
    const LAUNCHCTL: &str = "launchctl";
    /// System Settings pane macOS 13+ uses for login items.
    const LOGIN_ITEMS_PANE: &str =
        "x-apple.systempreferences:com.apple.LoginItems-Settings.extension";

    pub(super) fn status(root: &Path) -> StartupStatus {
        if root.as_os_str().is_empty() || !launchctl_available() {
            return StartupStatus::Unsupported;
        }
        if !plist_path(root).is_file() {
            return StartupStatus::Disabled;
        }
        if is_loaded() {
            StartupStatus::Enabled
        } else {
            StartupStatus::Disabled
        }
    }

    pub(super) fn set_enabled(root: &Path, enabled: bool) -> Result<StartupStatus, StartupError> {
        if root.as_os_str().is_empty() || !launchctl_available() {
            return Ok(StartupStatus::Unsupported);
        }
        if enabled {
            enable(root)
        } else {
            disable(root)
        }
    }

    fn enable(root: &Path) -> Result<StartupStatus, StartupError> {
        let executable = std::env::current_exe().map_err(|error| {
            StartupError::new(format!("could not locate the application: {error}"))
        })?;
        let path = plist_path(root);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|error| {
                StartupError::new(format!("could not create {}: {error}", parent.display()))
            })?;
        }
        fs::write(&path, launch_agent_plist(&executable)).map_err(|error| {
            StartupError::new(format!("could not write {}: {error}", path.display()))
        })?;

        // Replace a stale registration first: `bootstrap` fails when the label
        // is already loaded, and `bootout` fails when it is not.
        let target = format!("gui/{}/{LABEL}", user_id());
        let _ = launchctl(&["bootout", target.as_str()]);
        let domain = format!("gui/{}", user_id());
        let plist = path.to_string_lossy().into_owned();
        let output = launchctl(&["bootstrap", domain.as_str(), plist.as_str()]);
        match output {
            Some(output) if output.status.success() => Ok(StartupStatus::Enabled),
            // `launchctl` disappeared between the availability probe and now.
            None => Ok(StartupStatus::Unsupported),
            Some(output) => Err(StartupError::new(command_error(&output))),
        }
    }

    fn disable(root: &Path) -> Result<StartupStatus, StartupError> {
        let target = format!("gui/{}/{LABEL}", user_id());
        let _ = launchctl(&["bootout", target.as_str()]);
        let path = plist_path(root);
        match fs::remove_file(&path) {
            Ok(()) => Ok(StartupStatus::Disabled),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(StartupStatus::Disabled),
            Err(error) => Err(StartupError::new(format!(
                "could not remove {}: {error}",
                path.display()
            ))),
        }
    }

    pub(super) fn open_settings() -> bool {
        Command::new("open")
            .arg(LOGIN_ITEMS_PANE)
            .status()
            .is_ok_and(|status| status.success())
    }

    fn plist_path(root: &Path) -> PathBuf {
        root.join("Library").join("LaunchAgents").join(PLIST_NAME)
    }

    fn is_loaded() -> bool {
        let target = format!("gui/{}/{LABEL}", user_id());
        launchctl(&["print", target.as_str()]).is_some_and(|output| output.status.success())
    }

    fn launchctl_available() -> bool {
        Command::new(LAUNCHCTL).arg("list").output().is_ok()
    }

    fn launchctl(arguments: &[&str]) -> Option<Output> {
        Command::new(LAUNCHCTL).args(arguments).output().ok()
    }

    fn command_error(output: &Output) -> String {
        let stderr = String::from_utf8_lossy(&output.stderr);
        let message = stderr.trim();
        if message.is_empty() {
            format!("launchctl exited with {}", output.status)
        } else {
            message.to_string()
        }
    }

    fn user_id() -> u32 {
        // SAFETY: `getuid` takes no arguments, has no preconditions and cannot
        // fail; it returns the real user id of the calling process.
        unsafe { libc::getuid() }
    }

    fn launch_agent_plist(executable: &Path) -> String {
        let program = xml_escape(&executable.to_string_lossy());
        format!(
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n\
             <!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \
             \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n\
             <plist version=\"1.0\">\n\
             <dict>\n\
             \t<key>Label</key>\n\
             \t<string>{LABEL}</string>\n\
             \t<key>ProgramArguments</key>\n\
             \t<array>\n\
             \t\t<string>{program}</string>\n\
             \t</array>\n\
             \t<key>RunAtLoad</key>\n\
             \t<true/>\n\
             </dict>\n\
             </plist>\n"
        )
    }

    fn xml_escape(value: &str) -> String {
        let mut escaped = String::with_capacity(value.len());
        for character in value.chars() {
            match character {
                '&' => escaped.push_str("&amp;"),
                '<' => escaped.push_str("&lt;"),
                '>' => escaped.push_str("&gt;"),
                '"' => escaped.push_str("&quot;"),
                '\'' => escaped.push_str("&apos;"),
                other => escaped.push(other),
            }
        }
        escaped
    }
}

// -------------------------------------------------------------- Linux/Unix

#[cfg(all(unix, not(target_os = "macos")))]
mod linux {
    use std::fs;
    use std::io;
    use std::path::{Path, PathBuf};

    use super::{StartupError, StartupStatus};

    /// XDG autostart entry name.
    const DESKTOP_FILE: &str = "deepl-ofm.desktop";

    pub(super) fn status(root: &Path) -> StartupStatus {
        if root.as_os_str().is_empty() {
            return StartupStatus::Unsupported;
        }
        if desktop_path(root).is_file() {
            StartupStatus::Enabled
        } else {
            StartupStatus::Disabled
        }
    }

    pub(super) fn set_enabled(root: &Path, enabled: bool) -> Result<StartupStatus, StartupError> {
        if root.as_os_str().is_empty() {
            return Ok(StartupStatus::Unsupported);
        }
        let path = desktop_path(root);
        if enabled {
            let executable = std::env::current_exe().map_err(|error| {
                StartupError::new(format!("could not locate the application: {error}"))
            })?;
            if let Some(parent) = path.parent() {
                fs::create_dir_all(parent).map_err(|error| {
                    StartupError::new(format!("could not create {}: {error}", parent.display()))
                })?;
            }
            fs::write(&path, desktop_entry(&executable)).map_err(|error| {
                StartupError::new(format!("could not write {}: {error}", path.display()))
            })?;
            Ok(StartupStatus::Enabled)
        } else {
            match fs::remove_file(&path) {
                Ok(()) => Ok(StartupStatus::Disabled),
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    Ok(StartupStatus::Disabled)
                }
                Err(error) => Err(StartupError::new(format!(
                    "could not remove {}: {error}",
                    path.display()
                ))),
            }
        }
    }

    /// XDG autostart has no standard settings page to open.
    pub(super) fn open_settings() -> bool {
        false
    }

    fn desktop_path(root: &Path) -> PathBuf {
        root.join(".config").join("autostart").join(DESKTOP_FILE)
    }

    fn desktop_entry(executable: &Path) -> String {
        format!(
            "[Desktop Entry]\n\
             Type=Application\n\
             Name=DeepL-oFM\n\
             Comment=Open DeepL-oFM at login\n\
             Exec={}\n\
             Terminal=false\n\
             X-GNOME-Autostart-enabled=true\n",
            quote_exec(executable)
        )
    }

    /// Quote a path for the `Exec` key: XDG rules, not shell rules.
    fn quote_exec(executable: &Path) -> String {
        let mut quoted = String::with_capacity(executable.as_os_str().len() + 2);
        quoted.push('"');
        for character in executable.to_string_lossy().chars() {
            match character {
                '"' | '\\' | '$' | '`' => {
                    quoted.push('\\');
                    quoted.push(character);
                }
                '%' => quoted.push_str("%%"),
                other => quoted.push(other),
            }
        }
        quoted.push('"');
        quoted
    }

    #[cfg(test)]
    mod tests {
        use std::fs;
        use std::os::unix::fs::PermissionsExt;
        use std::path::{Path, PathBuf};

        use crate::startup::{StartupLocation, StartupStatus};

        use super::{desktop_entry, DESKTOP_FILE};

        /// A throwaway home directory, so tests never touch the real profile.
        struct TempRoot {
            path: PathBuf,
        }

        impl TempRoot {
            fn new(tag: &str) -> Self {
                let path = std::env::temp_dir().join(format!(
                    "ofm-startup-{tag}-{}-{}",
                    std::process::id(),
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|value| value.as_nanos())
                        .unwrap_or(0)
                ));
                fs::create_dir_all(&path).expect("create the temp root");
                Self { path }
            }

            fn location(&self) -> StartupLocation {
                StartupLocation::with_root(self.path.clone())
            }

            fn entry(&self) -> PathBuf {
                self.path
                    .join(".config")
                    .join("autostart")
                    .join(DESKTOP_FILE)
            }
        }

        impl Drop for TempRoot {
            fn drop(&mut self) {
                let _ = fs::remove_dir_all(&self.path);
            }
        }

        #[test]
        fn disabled_by_default() {
            let root = TempRoot::new("default");
            assert_eq!(root.location().status(), StartupStatus::Disabled);
            assert!(!root.entry().exists());
        }

        #[test]
        fn enabling_writes_the_autostart_entry() {
            let root = TempRoot::new("enable");
            let location = root.location();
            assert_eq!(location.set_enabled(true), Ok(StartupStatus::Enabled));
            assert_eq!(location.status(), StartupStatus::Enabled);

            let content = fs::read_to_string(root.entry()).expect("read the desktop entry");
            assert!(content.contains("[Desktop Entry]"));
            assert!(content.contains("Type=Application"));
            assert!(content.contains("Name=DeepL-oFM"));
            assert!(content.contains("X-GNOME-Autostart-enabled=true"));

            let executable = std::env::current_exe().expect("current executable");
            let quoted = format!("\"{}\"", executable.display());
            assert!(
                content.contains(&format!("Exec={quoted}")),
                "Exec missing from:\n{content}"
            );
        }

        #[test]
        fn disabling_removes_the_autostart_entry() {
            let root = TempRoot::new("disable");
            let location = root.location();
            assert_eq!(location.set_enabled(true), Ok(StartupStatus::Enabled));
            assert!(root.entry().is_file());

            assert_eq!(location.set_enabled(false), Ok(StartupStatus::Disabled));
            assert_eq!(location.status(), StartupStatus::Disabled);
            assert!(!root.entry().exists());
        }

        #[test]
        fn repeated_changes_are_idempotent() {
            let root = TempRoot::new("idempotent");
            let location = root.location();

            assert_eq!(location.set_enabled(true), Ok(StartupStatus::Enabled));
            assert_eq!(location.set_enabled(true), Ok(StartupStatus::Enabled));
            assert_eq!(location.status(), StartupStatus::Enabled);
            assert!(root.entry().is_file());

            assert_eq!(location.set_enabled(false), Ok(StartupStatus::Disabled));
            assert_eq!(location.set_enabled(false), Ok(StartupStatus::Disabled));
            assert_eq!(location.status(), StartupStatus::Disabled);
        }

        #[test]
        fn status_never_creates_anything() {
            let root = TempRoot::new("read-status");
            let missing = root.path.join("missing-home");
            let location = StartupLocation::with_root(missing.clone());

            assert_eq!(location.status(), StartupStatus::Disabled);
            assert!(!missing.exists(), "status() created the home directory");
        }

        #[test]
        fn a_read_only_directory_surfaces_an_error() {
            let root = TempRoot::new("read-only");
            fs::set_permissions(&root.path, fs::Permissions::from_mode(0o555))
                .expect("make the root read-only");

            // Root can write through mode bits, so check before trusting the
            // permission: in that case block the parent with a regular file.
            let probe = root.path.join("probe");
            let writable = fs::write(&probe, b"probe").is_ok();
            let _ = fs::remove_file(&probe);
            if writable {
                fs::set_permissions(&root.path, fs::Permissions::from_mode(0o755))
                    .expect("restore the root");
                fs::write(root.path.join(".config"), b"not a directory")
                    .expect("block the autostart parent");
            }

            let location = root.location();
            let result = location.set_enabled(true);
            assert!(result.is_err(), "expected an error, got {result:?}");
            assert_eq!(location.status(), StartupStatus::Disabled);

            let _ = fs::set_permissions(&root.path, fs::Permissions::from_mode(0o755));
        }

        #[test]
        fn a_blocked_parent_surfaces_an_error() {
            let root = TempRoot::new("blocked");
            fs::write(root.path.join(".config"), b"not a directory")
                .expect("block the autostart parent");

            let result = root.location().set_enabled(true);
            let error = result.expect_err("a blocked parent must fail");
            assert!(!error.message.is_empty(), "the error message is empty");
        }

        #[test]
        fn the_exec_path_is_quoted_and_escaped() {
            let entry = desktop_entry(Path::new("/opt/DeepL oFM/$app/deepl-ofm"));
            assert!(
                entry.contains(r#"Exec="/opt/DeepL oFM/\$app/deepl-ofm""#),
                "unexpected Exec line:\n{entry}"
            );
        }
    }
}
