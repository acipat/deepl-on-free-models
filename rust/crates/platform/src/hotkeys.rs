//! System-wide hotkeys.
//!
//! Registration is delegated to [`global_hotkey`], which uses `RegisterHotKey`
//! on Windows and Carbon on macOS.  The manager owns a background thread that
//! turns hotkey events into action names and a channel that [`HotkeyManager::poll`]
//! drains, so callers never block on the platform event loop.
//!
//! Linux has no supported backend here: [`HotkeyManager::is_supported`] is
//! `false`, registration returns an error and polling returns nothing.
//!
//! **Threading note:** `global_hotkey` requires the manager to be created on a
//! thread with an event loop (the main/UI thread on macOS, any message-pumping
//! thread on Windows).  Create the manager there; the internal background
//! thread only reads the global event channel.  On Windows the owning thread
//! must call [`pump_messages`] before every [`HotkeyManager::poll`], because
//! `RegisterHotKey` posts `WM_HOTKEY` to a window owned by that thread and a
//! sleeping thread never dispatches it.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{self, Receiver, Sender};
use std::sync::{Arc, Mutex, Once};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

use global_hotkey::hotkey::{Code, HotKey, Modifiers};
use global_hotkey::{GlobalHotKeyEvent, GlobalHotKeyManager, HotKeyState};
use ofm_config::KeyCombo;

/// `MOD_ALT` as defined by Win32.
pub const MOD_ALT: u32 = 0x0001;
/// `MOD_CONTROL` as defined by Win32.
pub const MOD_CONTROL: u32 = 0x0002;
/// `MOD_SHIFT` as defined by Win32.
pub const MOD_SHIFT: u32 = 0x0004;
/// `MOD_WIN` as defined by Win32.
pub const MOD_WIN: u32 = 0x0008;
/// `MOD_NOREPEAT` as defined by Win32.
pub const MOD_NOREPEAT: u32 = 0x4000;
/// `WM_HOTKEY` as defined by Win32.
pub const WM_HOTKEY: u32 = 0x0312;

/// Message key used when the platform has no hotkey backend.
pub const MESSAGE_UNSUPPORTED: &str = "Global shortcuts are only available on Windows and macOS.";
/// Message key used when a combo lacks Ctrl/Alt or has an unknown key.
pub const MESSAGE_INVALID: &str = "This shortcut needs Ctrl or Alt.";
/// Message key used when the operating system refuses a registration.
pub const MESSAGE_COULD_NOT_REGISTER: &str = "Could not register %@. The shortcut may be taken.";

static UNSUPPORTED_LOGGED: Once = Once::new();

/// A registration problem with a localisable, user-facing message key.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct HotkeyError {
    /// English message template; `%@` is replaced by the combo display.
    pub message_key: &'static str,
}

impl HotkeyError {
    /// Create an error for `message_key`.
    pub const fn new(message_key: &'static str) -> Self {
        Self { message_key }
    }

    /// Localised message with the placeholder replaced by "this shortcut".
    pub fn message(&self) -> String {
        ofm_i18n::t(self.message_key).replace("%@", "this shortcut")
    }

    /// Localised message with the placeholder replaced by `combo_display`.
    pub fn message_with(&self, combo_display: &str) -> String {
        ofm_i18n::t(self.message_key).replace("%@", combo_display)
    }
}

impl std::fmt::Display for HotkeyError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message())
    }
}

impl std::error::Error for HotkeyError {}

// --------------------------------------------------------------------------- //
// Combo translation (platform independent, unit-tested on Linux)
// --------------------------------------------------------------------------- //

#[allow(dead_code)] // reference Win32 translation, exercised by the tests
fn named_virtual_key(key: &str) -> Option<u32> {
    let value = match key {
        "space" => 0x20,
        "tab" => 0x09,
        "enter" | "return" => 0x0D,
        "escape" | "esc" => 0x1B,
        "backspace" => 0x08,
        "delete" | "del" => 0x2E,
        "insert" | "ins" => 0x2D,
        "home" => 0x24,
        "end" => 0x23,
        "pageup" | "pgup" | "prior" => 0x21,
        "pagedown" | "pgdn" | "next" => 0x22,
        "left" => 0x25,
        "up" => 0x26,
        "right" => 0x27,
        "down" => 0x28,
        "printscreen" | "print" => 0x2C,
        "menu" => 0x5D,
        "pause" => 0x13,
        "capslock" => 0x14,
        "numlock" => 0x90,
        "scrolllock" => 0x91,
        "plus" => 0xBB,
        "minus" => 0xBD,
        "comma" => 0xBC,
        "period" => 0xBE,
        "slash" => 0xBF,
        "backslash" => 0xDC,
        "semicolon" => 0xBA,
        "quote" => 0xDE,
        "grave" => 0xC0,
        "bracketleft" => 0xDB,
        "bracketright" => 0xDD,
        _ => return None,
    };
    Some(value)
}

/// US-layout virtual-key codes for unshifted punctuation.
#[allow(dead_code)] // reference Win32 translation, exercised by the tests
fn punctuation_virtual_key(character: char) -> Option<u32> {
    let value = match character {
        ';' => 0xBA,
        '=' => 0xBB,
        ',' => 0xBC,
        '-' => 0xBD,
        '.' => 0xBE,
        '/' => 0xBF,
        '`' => 0xC0,
        '[' => 0xDB,
        '\\' => 0xDC,
        ']' => 0xDD,
        '\'' => 0xDE,
        _ => return None,
    };
    Some(value)
}

/// Characters that need Shift on a US layout: character -> virtual-key code.
#[allow(dead_code)] // reference Win32 translation, exercised by the tests
fn shifted_virtual_key(character: char) -> Option<u32> {
    let value = match character {
        '!' => 0x31,
        '@' => 0x32,
        '#' => 0x33,
        '$' => 0x34,
        '%' => 0x35,
        '^' => 0x36,
        '&' => 0x37,
        '*' => 0x38,
        '(' => 0x39,
        ')' => 0x30,
        ':' => 0xBA,
        '+' => 0xBB,
        '<' => 0xBC,
        '_' => 0xBD,
        '>' => 0xBE,
        '?' => 0xBF,
        '~' => 0xC0,
        '{' => 0xDB,
        '|' => 0xDC,
        '}' => 0xDD,
        '"' => 0xDE,
        _ => return None,
    };
    Some(value)
}

/// Return `(virtual_key, needs_shift)` for a [`KeyCombo::key`] value.
#[allow(dead_code)] // reference Win32 translation, exercised by the tests
fn virtual_key(key: &str) -> (u32, bool) {
    let value = key.trim();
    if value.is_empty() {
        return (0, false);
    }
    let mut characters = value.chars();
    let Some(character) = characters.next() else {
        return (0, false);
    };
    if characters.next().is_none() {
        if character.is_ascii_alphabetic() {
            return (u32::from(character.to_ascii_uppercase()), false);
        }
        if character.is_ascii_digit() {
            return (u32::from(character), false);
        }
        if let Some(code) = punctuation_virtual_key(character) {
            return (code, false);
        }
        if let Some(code) = shifted_virtual_key(character) {
            return (code, true);
        }
        return (0, false);
    }
    let lowered = value.to_ascii_lowercase();
    if let Some(code) = named_virtual_key(&lowered) {
        return (code, false);
    }
    if let Some(number) = lowered
        .strip_prefix('f')
        .and_then(|digits| digits.parse::<u32>().ok())
        .filter(|number| (1..=24).contains(number))
    {
        return (0x70 + number - 1, false);
    }
    (0, false)
}

/// Translate a [`KeyCombo`] into `(MOD_* flags, virtual-key code)`.
#[allow(dead_code)] // reference Win32 translation, exercised by the tests
fn modifiers_and_vk(combo: &KeyCombo) -> (u32, u32) {
    let mut modifiers = 0;
    if combo.ctrl {
        modifiers |= MOD_CONTROL;
    }
    if combo.alt {
        modifiers |= MOD_ALT;
    }
    if combo.shift {
        modifiers |= MOD_SHIFT;
    }
    if combo.meta {
        modifiers |= MOD_WIN;
    }
    let (code, needs_shift) = virtual_key(&combo.key);
    if needs_shift {
        modifiers |= MOD_SHIFT;
    }
    (modifiers, code)
}

fn modifiers_for(combo: &KeyCombo) -> Modifiers {
    let mut modifiers = Modifiers::empty();
    if combo.ctrl {
        modifiers |= Modifiers::CONTROL;
    }
    if combo.alt {
        modifiers |= Modifiers::ALT;
    }
    if combo.shift {
        modifiers |= Modifiers::SHIFT;
    }
    if combo.meta {
        modifiers |= Modifiers::META;
    }
    modifiers
}

/// Translate a [`KeyCombo::key`] value into a `global_hotkey` code.
fn code_for(key: &str) -> Option<(Code, bool)> {
    let value = key.trim();
    if value.is_empty() {
        return None;
    }
    let mut characters = value.chars();
    let character = characters.next()?;
    if characters.next().is_none() {
        if character.is_ascii_alphabetic() {
            return format!("Key{}", character.to_ascii_uppercase())
                .parse()
                .ok()
                .map(|code| (code, false));
        }
        if character.is_ascii_digit() {
            return format!("Digit{character}")
                .parse()
                .ok()
                .map(|code| (code, false));
        }
        if let Some((name, shift)) = punctuation_code(character) {
            return name.parse().ok().map(|code| (code, shift));
        }
        return None;
    }
    let lowered = value.to_ascii_lowercase();
    let name = match lowered.as_str() {
        "space" => "Space",
        "tab" => "Tab",
        "enter" | "return" => "Enter",
        "escape" | "esc" => "Escape",
        "backspace" => "Backspace",
        "delete" | "del" => "Delete",
        "insert" | "ins" => "Insert",
        "home" => "Home",
        "end" => "End",
        "pageup" | "pgup" | "prior" => "PageUp",
        "pagedown" | "pgdn" | "next" => "PageDown",
        "left" => "ArrowLeft",
        "up" => "ArrowUp",
        "right" => "ArrowRight",
        "down" => "ArrowDown",
        "printscreen" | "print" => "PrintScreen",
        "menu" => "ContextMenu",
        "pause" => "Pause",
        "capslock" => "CapsLock",
        "numlock" => "NumLock",
        "scrolllock" => "ScrollLock",
        "plus" => "Equal",
        "minus" => "Minus",
        "comma" => "Comma",
        "period" => "Period",
        "slash" => "Slash",
        "backslash" => "Backslash",
        "semicolon" => "Semicolon",
        "quote" => "Quote",
        "grave" => "Backquote",
        "bracketleft" => "BracketLeft",
        "bracketright" => "BracketRight",
        _ => {
            let number = lowered.strip_prefix('f')?.parse::<u32>().ok()?;
            if !(1..=24).contains(&number) {
                return None;
            }
            return format!("F{number}").parse().ok().map(|code| (code, false));
        }
    };
    let shift = matches!(lowered.as_str(), "plus");
    name.parse().ok().map(|code| (code, shift))
}

fn punctuation_code(character: char) -> Option<(&'static str, bool)> {
    let value = match character {
        ';' => ("Semicolon", false),
        '=' => ("Equal", false),
        ',' => ("Comma", false),
        '-' => ("Minus", false),
        '.' => ("Period", false),
        '/' => ("Slash", false),
        '`' => ("Backquote", false),
        '[' => ("BracketLeft", false),
        '\\' => ("Backslash", false),
        ']' => ("BracketRight", false),
        '\'' => ("Quote", false),
        '!' => ("Digit1", true),
        '@' => ("Digit2", true),
        '#' => ("Digit3", true),
        '$' => ("Digit4", true),
        '%' => ("Digit5", true),
        '^' => ("Digit6", true),
        '&' => ("Digit7", true),
        '*' => ("Digit8", true),
        '(' => ("Digit9", true),
        ')' => ("Digit0", true),
        ':' => ("Semicolon", true),
        '+' => ("Equal", true),
        '<' => ("Comma", true),
        '_' => ("Minus", true),
        '>' => ("Period", true),
        '?' => ("Slash", true),
        '~' => ("Backquote", true),
        '{' => ("BracketLeft", true),
        '|' => ("Backslash", true),
        '}' => ("BracketRight", true),
        '"' => ("Quote", true),
        _ => return None,
    };
    Some(value)
}

// --------------------------------------------------------------------------- //
// Windows message pump
// --------------------------------------------------------------------------- //

/// Pump pending Win32 messages for the calling thread.
///
/// `global_hotkey` registers shortcuts with `RegisterHotKey`, so Windows posts
/// `WM_HOTKEY` to the hidden window that the crate creates in
/// [`HotkeyManager::new`].  A window only receives messages while the thread
/// that created it runs a message loop; `HotkeyManager::poll` merely drains a
/// channel filled by that window's procedure.  The owning thread must
/// therefore pump before each poll, otherwise registration succeeds but no
/// shortcut ever fires.
///
/// The pump is non-blocking: it removes and dispatches every message already
/// queued and returns.  On platforms without Win32 this is a no-op.
#[cfg(windows)]
pub fn pump_messages() {
    use windows::Win32::UI::WindowsAndMessaging::{
        DispatchMessageW, PeekMessageW, TranslateMessage, MSG, PM_REMOVE,
    };

    let mut message = MSG::default();
    // SAFETY: `message` is a valid destination for `PeekMessageW`; `None`
    // selects every window owned by this thread and the zero filters accept
    // every message.  `PM_REMOVE` removes each message before dispatch, so the
    // loop always makes progress.
    while unsafe { PeekMessageW(&mut message, None, 0, 0, PM_REMOVE) }.as_bool() {
        // SAFETY: `PeekMessageW` initialised `message`; translating and
        // dispatching it is the same work a classic `GetMessageW` loop does.
        unsafe {
            let _ = TranslateMessage(&message);
            let _ = DispatchMessageW(&message);
        }
    }
}

/// Pump pending Win32 messages for the calling thread.
///
/// This is a no-op on platforms that do not use a Win32 message loop.
#[cfg(not(windows))]
pub fn pump_messages() {}

// --------------------------------------------------------------------------- //
// Manager
// --------------------------------------------------------------------------- //

/// Registers system-wide shortcuts and hands presses back as action names.
pub struct HotkeyManager {
    manager: Option<GlobalHotKeyManager>,
    registered: HashMap<String, HotKey>,
    actions: Arc<Mutex<HashMap<u32, String>>>,
    pressed: Receiver<String>,
    _pressed_tx: Sender<String>,
    stop: Arc<AtomicBool>,
    worker: Option<JoinHandle<()>>,
}

impl HotkeyManager {
    /// Create a manager and start its background event thread.
    ///
    /// Create it on the thread that owns the platform event loop.
    pub fn new() -> Self {
        let (pressed_tx, pressed) = mpsc::channel();
        let actions = Arc::new(Mutex::new(HashMap::new()));
        let stop = Arc::new(AtomicBool::new(false));
        let mut manager = None;
        let mut worker = None;
        if Self::is_supported() {
            match GlobalHotKeyManager::new() {
                Ok(created) => {
                    manager = Some(created);
                    let actions = Arc::clone(&actions);
                    let stop = Arc::clone(&stop);
                    let sender = pressed_tx.clone();
                    match thread::Builder::new()
                        .name("ofm-hotkeys-events".to_string())
                        .spawn(move || poll_events(sender, actions, stop))
                    {
                        Ok(handle) => worker = Some(handle),
                        Err(error) => {
                            log::warn!("could not start the hotkey event thread: {error}");
                        }
                    }
                }
                Err(error) => {
                    log::warn!("could not initialise the global hotkey manager: {error}");
                }
            }
        }
        Self {
            manager,
            registered: HashMap::new(),
            actions,
            pressed,
            _pressed_tx: pressed_tx,
            stop,
            worker,
        }
    }

    /// Whether this platform has a hotkey backend.
    pub const fn is_supported() -> bool {
        cfg!(any(windows, target_os = "macos"))
    }

    /// Register `action` for `combo`, replacing an existing binding.
    pub fn register(&mut self, action: &str, combo: &KeyCombo) -> Result<(), HotkeyError> {
        let name = action.trim();
        if name.is_empty() {
            return Err(HotkeyError::new(MESSAGE_INVALID));
        }
        if !Self::is_supported() {
            UNSUPPORTED_LOGGED.call_once(|| {
                log::info!("global shortcuts are not supported on this platform");
            });
            return Err(HotkeyError::new(MESSAGE_UNSUPPORTED));
        }
        if !combo.is_valid() {
            return Err(HotkeyError::new(MESSAGE_INVALID));
        }
        let Some((code, implied_shift)) = code_for(&combo.key) else {
            log::warn!("unsupported hotkey key: {:?}", combo.key);
            return Err(HotkeyError::new(MESSAGE_INVALID));
        };
        let mut modifiers = modifiers_for(combo);
        if implied_shift {
            modifiers |= Modifiers::SHIFT;
        }
        let hotkey = HotKey::new(Some(modifiers), code);

        if self.registered.contains_key(name) {
            self.remove_registration(name);
        }
        let Some(manager) = self.manager.as_ref() else {
            return Err(HotkeyError::new(MESSAGE_COULD_NOT_REGISTER));
        };
        if let Err(error) = manager.register(hotkey) {
            log::warn!("could not register {} ({}): {error}", combo.display(), code);
            return Err(HotkeyError::new(MESSAGE_COULD_NOT_REGISTER));
        }
        if let Ok(mut actions) = self.actions.lock() {
            actions.insert(hotkey.id(), name.to_string());
        }
        self.registered.insert(name.to_string(), hotkey);
        Ok(())
    }

    /// Remove every registered shortcut.
    pub fn unregister_all(&mut self) {
        let hotkeys: Vec<HotKey> = self.registered.drain().map(|(_, hotkey)| hotkey).collect();
        if let Some(manager) = self.manager.as_ref() {
            for hotkey in hotkeys {
                if let Err(error) = manager.unregister(hotkey) {
                    log::debug!("could not unregister a hotkey: {error}");
                }
            }
        }
        if let Ok(mut actions) = self.actions.lock() {
            actions.clear();
        }
    }

    /// Actions pressed since the previous call.
    ///
    /// Call this on the thread that created the manager, after
    /// [`pump_messages`], so Windows can dispatch pending `WM_HOTKEY` events.
    pub fn poll(&mut self) -> Vec<String> {
        let mut pressed = Vec::new();
        while let Ok(action) = self.pressed.try_recv() {
            pressed.push(action);
        }
        pressed
    }

    fn remove_registration(&mut self, action: &str) {
        if let Some(hotkey) = self.registered.remove(action) {
            if let Some(manager) = self.manager.as_ref() {
                if let Err(error) = manager.unregister(hotkey) {
                    log::debug!("could not unregister {action}: {error}");
                }
            }
            if let Ok(mut actions) = self.actions.lock() {
                actions.remove(&hotkey.id());
            }
        }
    }
}

impl Default for HotkeyManager {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for HotkeyManager {
    fn drop(&mut self) {
        self.unregister_all();
        self.stop.store(true, Ordering::SeqCst);
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

// --------------------------------------------------------------------------- //
// Dispatch loop
// --------------------------------------------------------------------------- //

/// How often the owning thread pumps messages and polls for presses.
const POLL_INTERVAL: Duration = Duration::from_millis(60);

/// Whether a failed registration is due for another attempt.
///
/// Kept pure so a test can move the clock instead of sleeping for half a minute.
fn retry_due(failed_at: Instant, now: Instant) -> bool {
    now.saturating_duration_since(failed_at) >= REGISTRATION_RETRY
}

/// How long to wait before retrying a registration that failed.
///
/// A shortcut is refused while another process holds it - two copies of the
/// application, or a tool that owns the same combination - and that conflict
/// usually disappears. Retrying only on the next settings event left the
/// shortcuts dead for the rest of the session.
const REGISTRATION_RETRY: Duration = Duration::from_secs(30);

/// Ticks between heartbeat lines (five minutes at [`POLL_INTERVAL`]).
///
/// A log that stops beating proves the loop is blocked; a log that keeps
/// beating while a press has no "finished" line proves the capture is blocked.
const HEARTBEAT_TICKS: u64 = 5_000;

/// The manager operations the dispatch loop needs.
///
/// [`HotkeyManager`] is the real implementation; tests use a fake so a
/// panicking or blocking action can be delivered without a window or an event
/// loop.
pub trait HotkeyBackend {
    /// Remove every registered shortcut.
    fn unregister_all(&mut self);
    /// Register `action` for `combo`, replacing an existing binding.
    fn register(&mut self, action: &str, combo: &KeyCombo) -> Result<(), HotkeyError>;
    /// Actions pressed since the previous call.
    fn poll(&mut self) -> Vec<String>;
}

impl HotkeyBackend for HotkeyManager {
    fn unregister_all(&mut self) {
        HotkeyManager::unregister_all(self);
    }

    fn register(&mut self, action: &str, combo: &KeyCombo) -> Result<(), HotkeyError> {
        HotkeyManager::register(self, action, combo)
    }

    fn poll(&mut self) -> Vec<String> {
        HotkeyManager::poll(self)
    }
}

/// Why [`run_hotkey_loop`] returned.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum LoopExit {
    /// The caller's stop flag was set (tests only; the shell never sets it).
    Stopped,
}

/// Clears the one-capture flag even when the worker unwinds.
struct CaptureGuard {
    active: Arc<AtomicBool>,
}

impl Drop for CaptureGuard {
    fn drop(&mut self) {
        self.active.store(false, Ordering::SeqCst);
    }
}

/// The polling and dispatch body of the hotkey thread.
///
/// This is separate from [`run_hotkey_loop`] so tests can drive it
/// deterministically with a fake [`HotkeyBackend`].  The body never performs a
/// capture itself: every action is handed to a worker thread, so a slow or
/// panicking capture cannot stop registration or later presses.
pub struct HotkeyLoop<B, D, R> {
    backend: B,
    dispatch: Arc<D>,
    report: R,
    applied: Option<(KeyCombo, KeyCombo)>,
    /// The pair whose registration failed, and when, so it can be retried.
    last_attempt: Option<((KeyCombo, KeyCombo), Instant)>,
    capture: Arc<AtomicBool>,
}

impl<B, D, R> HotkeyLoop<B, D, R>
where
    B: HotkeyBackend,
    D: Fn(&str) + Send + Sync + 'static,
    R: FnMut(&str, &KeyCombo, Result<(), HotkeyError>),
{
    /// Wrap a backend and the two callbacks the loop drives.
    ///
    /// `dispatch` runs on a worker thread for each accepted press; `report`
    /// receives the outcome of every registration attempt.
    pub fn new(backend: B, dispatch: D, report: R) -> Self {
        Self {
            backend,
            dispatch: Arc::new(dispatch),
            report,
            applied: None,
            last_attempt: None,
            capture: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Apply queued settings changes and start workers for pressed actions.
    ///
    /// Returns `false` when the settings channel is closed; the loop keeps
    /// polling presses in that case, it only loses the ability to re-register.
    pub fn tick(&mut self, changes: &Receiver<(KeyCombo, KeyCombo)>) -> bool {
        let mut connected = true;
        loop {
            match changes.try_recv() {
                Ok((clipboard, selection)) => self.apply(&clipboard, &selection),
                Err(mpsc::TryRecvError::Empty) => break,
                Err(mpsc::TryRecvError::Disconnected) => {
                    connected = false;
                    break;
                }
            }
        }
        // Retry a pair that could not be registered, roughly twice a minute.
        if let Some((pair, failed_at)) = &self.last_attempt {
            if retry_due(*failed_at, Instant::now()) {
                let (clipboard, selection) = pair.clone();
                log::info!(
                    "retrying the hotkey registration: {} and {}",
                    clipboard.display(),
                    selection.display()
                );
                self.applied = None;
                self.apply(&clipboard, &selection);
            }
        }
        for action in self.backend.poll() {
            self.start(action);
        }
        connected
    }

    /// Register a new pair, unless it is the one already applied.
    fn apply(&mut self, clipboard: &KeyCombo, selection: &KeyCombo) {
        let pair = (clipboard.clone(), selection.clone());
        if self.applied.as_ref() == Some(&pair) {
            // Every settings change emits the whole snapshot; re-registering an
            // unchanged pair opens a window in which another process can take
            // the combination, after which registration fails permanently.
            log::debug!("hotkey combinations unchanged; keeping the existing registration");
            return;
        }

        // Never trade a working registration for one that cannot exist. A
        // settings event carrying an empty combo would otherwise unregister both
        // shortcuts and fail to install replacements, leaving the application
        // without any until it is restarted.
        if !clipboard.is_valid() || !selection.is_valid() {
            log::warn!(
                "hotkey combinations are not registrable (clipboard {}, selection {}); \
                 keeping the existing registration",
                clipboard.display(),
                selection.display()
            );
            return;
        }

        self.backend.unregister_all();
        let mut registered = true;
        for (action, combo) in [("clipboard", clipboard), ("selection", selection)] {
            let result = self.backend.register(action, combo);
            match &result {
                Ok(()) => log::info!("registered the {action} shortcut: {}", combo.display()),
                Err(error) => log::warn!(
                    "could not register the {action} shortcut {}: {error}",
                    combo.display()
                ),
            }
            registered &= result.is_ok();
            (self.report)(action, combo, result);
        }
        // A failed attempt leaves `applied` empty, so the same pair is retried
        // on the next settings event - but that event may never come, and the
        // other process holding the combination may well have exited by then.
        // `tick` therefore retries this pair on a timer as well.
        if registered {
            self.applied = Some(pair);
            self.last_attempt = None;
        } else {
            self.applied = None;
            self.last_attempt = Some((pair, Instant::now()));
        }
    }

    /// Hand one action to its own worker thread.
    fn start(&mut self, action: String) {
        log::info!("global hotkey pressed: {action}");
        if self.capture.swap(true, Ordering::SeqCst) {
            // A repeat while a capture is still running must not start a second
            // one: two captures fight over the clipboard and the source text.
            log::warn!("ignoring the {action} shortcut: the previous capture is still running");
            return;
        }
        let guard = CaptureGuard {
            active: Arc::clone(&self.capture),
        };
        let dispatch = Arc::clone(&self.dispatch);
        let worker_action = action.clone();
        let name = format!("ofm-hotkey-{action}");
        let spawned = thread::Builder::new().name(name).spawn(move || {
            // Dropped on normal return and on unwind, releasing the gate.
            let _guard = guard;
            dispatch(&worker_action);
            log::info!("the {worker_action} shortcut finished");
        });
        if let Err(error) = spawned {
            log::error!("could not start the {action} shortcut worker: {error}");
        }
    }
}

/// Own the manager on one thread: pump Win32 messages, apply settings, poll and
/// dispatch presses until `stop` is set (tests) or the process exits.
///
/// Pass `None` from the shell: the loop then runs for the lifetime of the
/// process, and any return is an error the caller must log.
pub fn run_hotkey_loop<B, D, R>(
    backend: B,
    changes: &Receiver<(KeyCombo, KeyCombo)>,
    dispatch: D,
    report: R,
    stop: Option<&AtomicBool>,
) -> LoopExit
where
    B: HotkeyBackend,
    D: Fn(&str) + Send + Sync + 'static,
    R: FnMut(&str, &KeyCombo, Result<(), HotkeyError>),
{
    let mut state = HotkeyLoop::new(backend, dispatch, report);
    let mut warned = false;
    let mut ticks: u64 = 0;
    loop {
        // On Windows the manager's hidden window only dispatches `WM_HOTKEY`
        // while its owning thread pumps the message queue.
        pump_messages();
        if !state.tick(changes) && !warned {
            log::error!(
                "the hotkey settings channel closed; shortcuts keep working but will not \
                 follow settings changes"
            );
            warned = true;
        }
        ticks += 1;
        if ticks % HEARTBEAT_TICKS == 0 {
            log::info!("hotkey loop alive; shortcuts are still being polled");
        }
        if stop.is_some_and(|flag| flag.load(Ordering::Relaxed)) {
            return LoopExit::Stopped;
        }
        thread::sleep(POLL_INTERVAL);
    }
}

fn poll_events(
    sender: Sender<String>,
    actions: Arc<Mutex<HashMap<u32, String>>>,
    stop: Arc<AtomicBool>,
) {
    let receiver = GlobalHotKeyEvent::receiver();
    while !stop.load(Ordering::Relaxed) {
        match receiver.recv_timeout(Duration::from_millis(50)) {
            Ok(event) => {
                if event.state() != HotKeyState::Pressed {
                    continue;
                }
                let action = actions
                    .lock()
                    .ok()
                    .and_then(|actions| actions.get(&event.id()).cloned());
                if let Some(action) = action {
                    if sender.send(action).is_err() {
                        break;
                    }
                }
            }
            Err(_) => {
                // Nothing arrived; loop again so `stop` is observed promptly.
                thread::sleep(Duration::from_millis(5));
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn combo(key: &str, ctrl: bool, alt: bool, shift: bool, meta: bool) -> KeyCombo {
        KeyCombo {
            key: key.to_string(),
            ctrl,
            alt,
            shift,
            meta,
        }
    }

    #[test]
    fn ctrl_alt_t() {
        let (modifiers, vk) = modifiers_and_vk(&combo("t", true, true, false, false));
        assert_eq!(modifiers, MOD_CONTROL | MOD_ALT);
        assert_eq!(vk, u32::from(b'T'));
    }

    #[test]
    fn ctrl_shift_f5() {
        let (modifiers, vk) = modifiers_and_vk(&combo("f5", true, false, true, false));
        assert_eq!(modifiers, MOD_CONTROL | MOD_SHIFT);
        assert_eq!(vk, 0x74);
    }

    #[test]
    fn alt_1() {
        let (modifiers, vk) = modifiers_and_vk(&combo("1", false, true, false, false));
        assert_eq!(modifiers, MOD_ALT);
        assert_eq!(vk, 0x31);
    }

    #[test]
    fn modifier_translation_details() {
        assert_eq!(
            modifiers_and_vk(&combo("t", true, false, false, false)).0,
            MOD_CONTROL
        );
        assert_eq!(
            modifiers_and_vk(&combo("t", false, false, false, true)).0,
            MOD_WIN
        );
        assert_eq!(
            modifiers_and_vk(&combo("t", false, false, false, false)),
            (0, u32::from(b'T'))
        );
        assert_eq!(
            modifiers_and_vk(&combo("t", false, false, true, false)),
            (MOD_SHIFT, u32::from(b'T'))
        );
    }

    #[test]
    fn named_keys_and_punctuation() {
        assert_eq!(
            modifiers_and_vk(&combo("space", true, false, false, false)).1,
            0x20
        );
        assert_eq!(
            modifiers_and_vk(&combo("F12", true, false, false, false)).1,
            0x7B
        );
        assert_eq!(
            modifiers_and_vk(&combo("+", true, false, false, false)),
            (MOD_CONTROL | MOD_SHIFT, 0xBB)
        );
    }

    #[test]
    fn unknown_key_has_no_virtual_key() {
        assert_eq!(
            modifiers_and_vk(&combo("definitely-not-a-key", true, false, false, false)),
            (MOD_CONTROL, 0)
        );
        assert_eq!(
            modifiers_and_vk(&combo("", true, false, false, false)),
            (MOD_CONTROL, 0)
        );
    }

    #[test]
    fn standard_combo_matches_the_contract() {
        let (modifiers, vk) = modifiers_and_vk(&KeyCombo::standard());
        assert_eq!(modifiers, MOD_CONTROL | MOD_ALT);
        assert_eq!(vk, u32::from(b'T'));
    }

    #[test]
    fn code_translation_for_global_hotkey() {
        assert_eq!(code_for("t"), Some((Code::KeyT, false)));
        assert_eq!(code_for("T"), Some((Code::KeyT, false)));
        assert_eq!(code_for("1"), Some((Code::Digit1, false)));
        assert_eq!(code_for("f12"), Some((Code::F12, false)));
        assert_eq!(code_for("space"), Some((Code::Space, false)));
        assert_eq!(code_for("+"), Some((Code::Equal, true)));
        assert_eq!(code_for("definitely-not-a-key"), None);
        assert_eq!(code_for(""), None);
    }

    #[test]
    fn global_modifiers_translation() {
        let modifiers = modifiers_for(&combo("t", true, true, true, true));
        assert!(modifiers.contains(Modifiers::CONTROL));
        assert!(modifiers.contains(Modifiers::ALT));
        assert!(modifiers.contains(Modifiers::SHIFT));
        assert!(modifiers.contains(Modifiers::META));
        assert!(modifiers_for(&combo("t", false, false, false, false)).is_empty());
    }

    #[test]
    fn support_matches_the_platform() {
        assert_eq!(
            HotkeyManager::is_supported(),
            cfg!(any(windows, target_os = "macos"))
        );
    }

    #[test]
    fn register_without_support_returns_a_typed_error() {
        if HotkeyManager::is_supported() {
            return;
        }
        let mut manager = HotkeyManager::new();
        let error = manager
            .register("translate", &combo("t", true, true, false, false))
            .expect_err("registration must fail on this platform");
        assert_eq!(error.message_key, MESSAGE_UNSUPPORTED);
        assert!(error.message().contains("Windows"));
        assert!(manager.poll().is_empty());
    }

    #[test]
    fn invalid_combo_is_rejected_before_registration() {
        if HotkeyManager::is_supported() {
            return;
        }
        let mut manager = HotkeyManager::new();
        let error = manager
            .register("translate", &combo("t", false, false, false, false))
            .expect_err("a combo without Ctrl/Alt is invalid");
        // Unsupported platforms report the platform first; supported ones
        // report the invalid combo.
        assert!(error.message_key == MESSAGE_INVALID || error.message_key == MESSAGE_UNSUPPORTED);
    }

    #[test]
    fn unregister_without_registration_is_silent() {
        let mut manager = HotkeyManager::new();
        manager.unregister_all();
        assert!(manager.poll().is_empty());
        manager.unregister_all();
    }

    #[test]
    fn error_message_contains_the_combo_display() {
        let error = HotkeyError::new(MESSAGE_COULD_NOT_REGISTER);
        let message = error.message_with("Ctrl+Alt+T");
        assert!(message.contains("Ctrl+Alt+T"));
        assert_eq!(error.to_string(), error.message());
    }

    #[test]
    fn mod_constants_match_win32() {
        assert_eq!((MOD_ALT, MOD_CONTROL, MOD_SHIFT), (0x0001, 0x0002, 0x0004));
        assert_eq!(MOD_NOREPEAT, 0x4000);
        assert_eq!(WM_HOTKEY, 0x0312);
    }

    // ------------------------------------------------------------- loop tests

    use std::collections::VecDeque;
    use std::sync::atomic::AtomicUsize;
    use std::time::Instant;

    /// A manager that records calls and serves queued actions, so the loop can
    /// be tested without a window, a message pump or a real shortcut.
    struct FakeBackend {
        pressed: Arc<Mutex<VecDeque<Vec<String>>>>,
        unregisters: Arc<AtomicUsize>,
        registrations: Arc<AtomicUsize>,
        /// How many upcoming registrations to refuse, to model a combination
        /// another process is holding.
        fail_next: Arc<AtomicUsize>,
    }

    impl FakeBackend {
        fn new() -> Self {
            Self {
                pressed: Arc::new(Mutex::new(VecDeque::new())),
                unregisters: Arc::new(AtomicUsize::new(0)),
                registrations: Arc::new(AtomicUsize::new(0)),
                fail_next: Arc::new(AtomicUsize::new(0)),
            }
        }
    }

    impl HotkeyBackend for FakeBackend {
        fn unregister_all(&mut self) {
            self.unregisters.fetch_add(1, Ordering::SeqCst);
        }

        fn register(&mut self, _action: &str, _combo: &KeyCombo) -> Result<(), HotkeyError> {
            self.registrations.fetch_add(1, Ordering::SeqCst);
            // Plain load-and-decrement: `fetch_update` is deprecated on newer
            // stable and `try_update` does not exist on 1.96, and this fake is
            // only ever touched from one test thread.
            if self.fail_next.load(Ordering::SeqCst) > 0 {
                self.fail_next.fetch_sub(1, Ordering::SeqCst);
                return Err(HotkeyError::new("This shortcut needs Ctrl or Alt."));
            }
            Ok(())
        }

        fn poll(&mut self) -> Vec<String> {
            self.pressed
                .lock()
                .unwrap_or_else(|poison| poison.into_inner())
                .pop_front()
                .unwrap_or_default()
        }
    }

    fn default_pair() -> (KeyCombo, KeyCombo) {
        (KeyCombo::standard(), KeyCombo::selection())
    }

    /// Queue one poll's actions from the test thread.
    fn push_actions(pressed: &Arc<Mutex<VecDeque<Vec<String>>>>, actions: &[&str]) {
        let actions = actions.iter().map(|action| action.to_string()).collect();
        pressed
            .lock()
            .unwrap_or_else(|poison| poison.into_inner())
            .push_back(actions);
    }

    #[test]
    fn identical_settings_events_do_not_unregister_the_shortcuts() {
        let (updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        let unregisters = Arc::clone(&backend.unregisters);
        let registrations = Arc::clone(&backend.registrations);
        let mut hotkeys = HotkeyLoop::new(backend, |_| {}, |_, _, _| {});

        updates.send(default_pair()).expect("send settings");
        assert!(hotkeys.tick(&changes));
        assert_eq!(unregisters.load(Ordering::SeqCst), 1);
        assert_eq!(registrations.load(Ordering::SeqCst), 2);

        // Two further events with the same combinations are what every
        // settings save emits; they must not touch the registration.
        unregisters.store(0, Ordering::SeqCst);
        registrations.store(0, Ordering::SeqCst);
        updates.send(default_pair()).expect("send settings");
        updates.send(default_pair()).expect("send settings");
        assert!(hotkeys.tick(&changes));
        assert_eq!(
            unregisters.load(Ordering::SeqCst),
            0,
            "an unchanged pair must not unregister the working shortcuts"
        );
        assert_eq!(
            registrations.load(Ordering::SeqCst),
            0,
            "an unchanged pair must not register again"
        );
    }

    #[test]
    fn an_empty_pair_never_replaces_a_working_registration() {
        // The failure from the field: a settings event arrived with an empty
        // shortcut, the working ones were unregistered, both registrations then
        // failed with "This shortcut needs Ctrl or Alt", and the application had
        // no shortcuts until it was restarted.
        let (updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        let unregisters = Arc::clone(&backend.unregisters);
        let registrations = Arc::clone(&backend.registrations);
        let mut hotkeys = HotkeyLoop::new(backend, |_| {}, |_, _, _| {});

        updates.send(default_pair()).expect("send settings");
        assert!(hotkeys.tick(&changes));
        unregisters.store(0, Ordering::SeqCst);
        registrations.store(0, Ordering::SeqCst);

        updates
            .send((KeyCombo::default(), KeyCombo::default()))
            .expect("send settings");
        assert!(hotkeys.tick(&changes));
        assert_eq!(
            unregisters.load(Ordering::SeqCst),
            0,
            "an unusable pair must not unregister the working shortcuts"
        );
        assert_eq!(
            registrations.load(Ordering::SeqCst),
            0,
            "an unusable pair must not be registered"
        );
        assert_eq!(
            hotkeys.applied,
            Some(default_pair()),
            "the working pair stays the applied one"
        );
    }

    #[test]
    fn a_failed_registration_is_scheduled_for_a_retry() {
        let (updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        backend.fail_next.store(2, Ordering::SeqCst);
        let mut hotkeys = HotkeyLoop::new(backend, |_| {}, |_, _, _| {});

        updates.send(default_pair()).expect("send settings");
        assert!(hotkeys.tick(&changes));
        assert!(
            hotkeys.applied.is_none(),
            "a pair that did not register is not remembered as applied"
        );
        let (pair, failed_at) = hotkeys
            .last_attempt
            .clone()
            .expect("the failed pair is kept for a retry");
        assert_eq!(pair, default_pair());
        assert!(!retry_due(failed_at, Instant::now()));
        assert!(retry_due(failed_at, failed_at + REGISTRATION_RETRY));
    }

    #[test]
    fn a_changed_pair_is_registered_again() {
        let (updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        let unregisters = Arc::clone(&backend.unregisters);
        let registrations = Arc::clone(&backend.registrations);
        let mut hotkeys = HotkeyLoop::new(backend, |_| {}, |_, _, _| {});

        updates.send(default_pair()).expect("send settings");
        assert!(hotkeys.tick(&changes));
        unregisters.store(0, Ordering::SeqCst);
        registrations.store(0, Ordering::SeqCst);

        let mut changed = KeyCombo::selection();
        changed.key = "f".to_string();
        updates
            .send((KeyCombo::standard(), changed))
            .expect("send settings");
        assert!(hotkeys.tick(&changes));
        assert_eq!(unregisters.load(Ordering::SeqCst), 1);
        assert_eq!(registrations.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn a_panicking_capture_does_not_stop_later_presses() {
        let (_updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        let pressed = Arc::clone(&backend.pressed);
        let (started, events) = mpsc::channel();
        let running = Arc::new(AtomicBool::new(false));
        let stop = Arc::clone(&running);
        let loop_thread = thread::spawn(move || {
            run_hotkey_loop(
                backend,
                &changes,
                move |action| {
                    let _ = started.send(action.to_string());
                    if action == "panic" {
                        panic!("expected panic from a hotkey worker");
                    }
                },
                |_, _, _| {},
                Some(&stop),
            )
        });

        push_actions(&pressed, &["panic"]);
        assert_eq!(
            events.recv_timeout(Duration::from_secs(2)),
            Ok("panic".to_string()),
            "the panicking action never started"
        );
        // The worker unwinds and drops its capture guard; retry the next press
        // until it is accepted so a loaded CI box cannot lose the race.
        let deadline = Instant::now() + Duration::from_secs(3);
        loop {
            push_actions(&pressed, &["later"]);
            match events.recv_timeout(Duration::from_millis(50)) {
                Ok(action) => {
                    assert_eq!(action, "later");
                    break;
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    assert!(
                        Instant::now() < deadline,
                        "the loop died with the panicking worker"
                    );
                }
                Err(error) => panic!("the event channel closed: {error}"),
            }
        }

        running.store(true, Ordering::SeqCst);
        assert_eq!(loop_thread.join().expect("loop thread"), LoopExit::Stopped);
    }

    #[test]
    fn a_blocked_capture_skips_repeats_and_accepts_a_later_press() {
        let (_updates, changes) = mpsc::channel();
        let backend = FakeBackend::new();
        let pressed = Arc::clone(&backend.pressed);
        let (started, events) = mpsc::channel();
        let (release, released) = mpsc::channel::<()>();
        let released = Arc::new(Mutex::new(released));
        let running = Arc::new(AtomicBool::new(false));
        let stop = Arc::clone(&running);
        let loop_thread = thread::spawn(move || {
            run_hotkey_loop(
                backend,
                &changes,
                move |action| {
                    let _ = started.send(format!("start:{action}"));
                    if action == "block" {
                        if let Ok(released) = released.lock() {
                            let _ = released.recv();
                        }
                        let _ = started.send("end:block".to_string());
                    }
                },
                |_, _, _| {},
                Some(&stop),
            )
        });

        push_actions(&pressed, &["block"]);
        assert_eq!(
            events.recv_timeout(Duration::from_secs(2)),
            Ok("start:block".to_string())
        );
        push_actions(&pressed, &["repeat"]);
        assert_eq!(
            events.recv_timeout(Duration::from_millis(250)),
            Err(mpsc::RecvTimeoutError::Timeout),
            "a queued repeat must not run a second capture concurrently"
        );

        release.send(()).expect("release the capture");
        assert_eq!(
            events.recv_timeout(Duration::from_secs(2)),
            Ok("end:block".to_string())
        );
        push_actions(&pressed, &["later"]);
        assert_eq!(
            events.recv_timeout(Duration::from_secs(2)),
            Ok("start:later".to_string()),
            "a press after the blocked capture must still arrive"
        );

        running.store(true, Ordering::SeqCst);
        assert_eq!(loop_thread.join().expect("loop thread"), LoopExit::Stopped);
    }
}
