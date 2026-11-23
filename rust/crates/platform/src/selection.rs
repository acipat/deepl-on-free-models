//! Capture the text selected in the foreground application.
//!
//! The trick is the same as the Swift original: synthesise the platform's copy
//! shortcut, wait for the clipboard to change and read it.  Windows uses
//! `SendInput` plus the clipboard sequence number (no Qt and no Accessibility
//! grant); macOS asks `System Events` to send `⌘C` and reads the pasteboard.
//! Other platforms report the feature as unsupported.

use std::time::Duration;

/// Whether selected-text capture works on this platform.
pub const fn is_supported() -> bool {
    cfg!(any(windows, target_os = "macos"))
}

/// Return the text selected in the foreground window, or `None`.
///
/// Blocks for at most the modifier-release grace period plus `timeout`.  On
/// unsupported platforms it logs once and returns `None` without blocking.
pub fn capture(timeout: Duration) -> Option<String> {
    #[cfg(windows)]
    {
        windows_impl::capture(timeout)
    }
    #[cfg(target_os = "macos")]
    {
        macos_impl::capture(timeout)
    }
    #[cfg(not(any(windows, target_os = "macos")))]
    {
        let _ = timeout;
        unsupported::log_once();
        None
    }
}

#[cfg(not(any(windows, target_os = "macos")))]
mod unsupported {
    use std::sync::Once;

    static LOGGED: Once = Once::new();

    pub(super) fn log_once() {
        LOGGED.call_once(|| {
            log::info!("selected-text capture is not supported on this platform");
        });
    }
}

#[cfg(windows)]
mod windows_impl {
    use std::thread::sleep;
    use std::time::{Duration, Instant};

    use windows::Win32::Foundation::HGLOBAL;
    use windows::Win32::System::DataExchange::{
        CloseClipboard, GetClipboardData, GetClipboardSequenceNumber, OpenClipboard,
    };
    use windows::Win32::System::Memory::{GlobalLock, GlobalUnlock};
    use windows::Win32::UI::Input::KeyboardAndMouse::{
        GetAsyncKeyState, SendInput, INPUT, INPUT_0, INPUT_KEYBOARD, KEYBDINPUT, KEYBD_EVENT_FLAGS,
        KEYEVENTF_KEYUP, VIRTUAL_KEY, VK_C, VK_CONTROL, VK_LWIN, VK_MENU, VK_RWIN, VK_SHIFT,
    };

    /// Clipboard format for NUL-terminated UTF-16 text.
    const CF_UNICODETEXT: u32 = 13;

    /// Grace period for the user to release the hotkey modifiers.
    const MODIFIER_WAIT: Duration = Duration::from_millis(300);

    const MODIFIERS: [VIRTUAL_KEY; 5] = [VK_SHIFT, VK_CONTROL, VK_MENU, VK_LWIN, VK_RWIN];

    fn modifier_is_down(key: VIRTUAL_KEY) -> bool {
        // SAFETY: `GetAsyncKeyState` only reads the current keyboard state; it
        // takes a virtual-key code and returns the key state as an `i16`.
        let state = unsafe { GetAsyncKeyState(i32::from(key.0)) };
        (state as u16 & 0x8000) != 0
    }

    fn send_key(key: VIRTUAL_KEY, release: bool) {
        let flags = if release {
            KEYEVENTF_KEYUP
        } else {
            KEYBD_EVENT_FLAGS(0)
        };
        let input = INPUT {
            r#type: INPUT_KEYBOARD,
            Anonymous: INPUT_0 {
                ki: KEYBDINPUT {
                    wVk: key,
                    wScan: 0,
                    dwFlags: flags,
                    time: 0,
                    dwExtraInfo: 0,
                },
            },
        };
        // SAFETY: the array contains one fully initialised `INPUT` and the size
        // passed is exactly `size_of::<INPUT>()`, as the Win32 API requires.
        let sent = unsafe { SendInput(&[input], std::mem::size_of::<INPUT>() as i32) };
        if sent == 0 {
            log::debug!("SendInput did not deliver a synthetic key event");
        }
    }

    /// Wait until the user lets go of the hotkey modifiers.
    ///
    /// If they are still held at the deadline the keys are released
    /// synthetically so the target application sees a plain `Ctrl+C` rather
    /// than `Ctrl+Alt+C`.
    fn wait_for_modifier_release(timeout: Duration) {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if !MODIFIERS.iter().any(|key| modifier_is_down(*key)) {
                return;
            }
            sleep(Duration::from_millis(10));
        }
        for key in MODIFIERS {
            send_key(key, true);
        }
        sleep(Duration::from_millis(30));
    }

    fn send_ctrl_c() {
        send_key(VK_CONTROL, false);
        sleep(Duration::from_millis(10));
        send_key(VK_C, false);
        sleep(Duration::from_millis(10));
        send_key(VK_C, true);
        sleep(Duration::from_millis(10));
        send_key(VK_CONTROL, true);
    }

    /// Read `CF_UNICODETEXT` while the clipboard is open.
    ///
    /// # Safety
    ///
    /// The caller must have opened the clipboard with `OpenClipboard`.
    unsafe fn read_locked_clipboard() -> Option<String> {
        // SAFETY: the clipboard is open, so the returned handle is owned by the
        // system and stays valid until `CloseClipboard`.
        let handle = unsafe { GetClipboardData(CF_UNICODETEXT) }.ok()?;
        if handle.is_invalid() {
            return None;
        }
        let memory = HGLOBAL(handle.0);
        // SAFETY: `memory` is the clipboard's global memory block for the
        // requested format; `GlobalLock` pins it and returns a pointer to it.
        let pointer = unsafe { GlobalLock(memory) };
        if pointer.is_null() {
            return None;
        }
        let wide = pointer as *const u16;
        let mut length = 0usize;
        // SAFETY: the block is NUL-terminated UTF-16 text.  The cap only guards
        // against a malformed owner that never terminates the string.
        while length < 16_000_000 && unsafe { *wide.add(length) } != 0 {
            length += 1;
        }
        // SAFETY: `wide` points at `length` initialised `u16` values inside the
        // locked block, and the slice does not outlive the unlock below.
        let text = unsafe { String::from_utf16_lossy(std::slice::from_raw_parts(wide, length)) };
        // SAFETY: `memory` was successfully locked above and is unlocked once.
        let _ = unsafe { GlobalUnlock(memory) };
        Some(text)
    }

    fn read_clipboard_text() -> Option<String> {
        // SAFETY: `OpenClipboard(None)` associates the clipboard with the
        // current thread; every successful open is paired with a close below.
        if unsafe { OpenClipboard(None) }.is_err() {
            return None;
        }
        // SAFETY: the clipboard is open for this thread.
        let text = unsafe { read_locked_clipboard() };
        // SAFETY: closes the clipboard opened above; the error is irrelevant.
        let _ = unsafe { CloseClipboard() };
        text
    }

    pub(super) fn capture(timeout: Duration) -> Option<String> {
        // SAFETY: reading the clipboard sequence number has no preconditions.
        let before = unsafe { GetClipboardSequenceNumber() };

        wait_for_modifier_release(MODIFIER_WAIT);
        send_ctrl_c();

        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            // SAFETY: reading the clipboard sequence number has no preconditions.
            if unsafe { GetClipboardSequenceNumber() } != before {
                // Let the clipboard owner publish the data before reading it.
                sleep(Duration::from_millis(20));
                return read_clipboard_text();
            }
            sleep(Duration::from_millis(10));
        }
        log::info!("no clipboard update after Ctrl+C; the selection was not captured");
        None
    }
}

#[cfg(target_os = "macos")]
mod macos_impl {
    use std::process::Command;
    use std::thread::sleep;
    use std::time::{Duration, Instant};

    use arboard::Clipboard;

    fn clipboard_text() -> Option<String> {
        let mut clipboard = Clipboard::new().ok()?;
        clipboard.get_text().ok()
    }

    /// Upper bound for `osascript` itself; without Accessibility permission it
    /// can otherwise wait for a system dialog indefinitely.
    const OSASCRIPT_LIMIT: Duration = Duration::from_secs(2);

    fn send_command_c() -> bool {
        let mut command = Command::new("/usr/bin/osascript");
        command.args([
            "-e",
            r#"tell application "System Events" to keystroke "c" using command down"#,
        ]);
        let Ok(mut child) = command.spawn() else {
            log::info!("could not run osascript");
            return false;
        };
        let deadline = Instant::now() + OSASCRIPT_LIMIT;
        loop {
            match child.try_wait() {
                Ok(Some(status)) => {
                    if status.success() {
                        return true;
                    }
                    log::info!(
                        "osascript could not send Cmd+C (status {status}); check Accessibility"
                    );
                    return false;
                }
                Ok(None) => {}
                Err(error) => {
                    log::info!("could not wait for osascript: {error}");
                    return false;
                }
            }
            if Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                log::info!("osascript did not finish in time; check Accessibility permission");
                return false;
            }
            sleep(Duration::from_millis(20));
        }
    }

    pub(super) fn capture(timeout: Duration) -> Option<String> {
        let before = clipboard_text();
        // Accessibility permission is required; without it `osascript` exits
        // with a non-zero status and the feature degrades to `None`.
        if !send_command_c() {
            return None;
        }

        let deadline = Instant::now() + timeout;
        loop {
            if let Some(text) = clipboard_text() {
                if !text.is_empty() && before.as_deref() != Some(text.as_str()) {
                    return Some(text);
                }
            }
            if Instant::now() >= deadline {
                break;
            }
            sleep(Duration::from_millis(20));
        }
        log::info!("no clipboard update after Cmd+C; the selection was not captured");
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn support_matches_the_platform() {
        assert_eq!(is_supported(), cfg!(any(windows, target_os = "macos")));
    }

    #[test]
    fn capture_without_support_is_a_silent_none() {
        if is_supported() {
            return;
        }
        assert_eq!(capture(Duration::from_millis(5)), None);
        // A second call must not panic or block either.
        assert_eq!(capture(Duration::ZERO), None);
    }
}
