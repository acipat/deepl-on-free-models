//! Platform-specific [`Speaker`] implementations.
//!
//! Exactly one of the three modules below is compiled.

#[cfg(target_os = "macos")]
mod macos {
    use std::io::Write;
    use std::path::Path;
    use std::process::{Child, Command, Stdio};
    use std::sync::{Mutex, MutexGuard};

    use super::super::{locale_matches, parse_say_voice_list, truncate, MAX_CHARS};

    const SAY: &str = "/usr/bin/say";

    /// A speaker backed by the macOS `say` command.
    pub struct Speaker {
        child: Mutex<Option<Child>>,
    }

    impl Speaker {
        /// Maximum number of characters handed to `say`.
        pub const MAX_CHARS: usize = MAX_CHARS;

        /// Create a speaker; no process is started until [`Self::speak`].
        pub fn new() -> Self {
            Self {
                child: Mutex::new(None),
            }
        }

        /// Whether `/usr/bin/say` exists on this system.
        pub fn is_available(&self) -> bool {
            Path::new(SAY).is_file()
        }

        /// Native voices as `(id, label)` pairs, sorted by label.
        pub fn voices(&self) -> Vec<(String, String)> {
            let output = match Command::new(SAY).arg("-v").arg("?").output() {
                Ok(output) if output.status.success() => output,
                _ => {
                    log::debug!("could not list macOS voices");
                    return Vec::new();
                }
            };
            let text = String::from_utf8_lossy(&output.stdout);
            let mut voices: Vec<(String, String)> = parse_say_voice_list(&text)
                .into_iter()
                .map(|voice| (voice.name.clone(), voice.name))
                .collect();
            voices.sort_by_key(|(_, label)| label.to_lowercase());
            voices
        }

        /// Speak `text`, optionally with a specific voice or language.
        pub fn speak(&self, text: &str, voice_id: &str, language_code: &str) -> bool {
            let trimmed = text.trim();
            if trimmed.is_empty() || !self.is_available() {
                return false;
            }
            self.stop();

            let mut command = Command::new(SAY);
            let wanted = voice_id.trim();
            let language_voice;
            let voice = if !wanted.is_empty() {
                wanted
            } else {
                language_voice = voice_for_language(language_code);
                language_voice.as_deref().unwrap_or_default()
            };
            if !voice.is_empty() {
                command.arg("-v").arg(voice);
            }
            command
                .stdin(Stdio::piped())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            let Ok(mut child) = command.spawn() else {
                log::debug!("could not start /usr/bin/say");
                return false;
            };
            if let Some(mut stdin) = child.stdin.take() {
                if stdin.write_all(truncate(trimmed).as_bytes()).is_err() {
                    let _ = child.kill();
                    let _ = child.wait();
                    return false;
                }
            }
            *self.lock_child() = Some(child);
            true
        }

        /// Stop the current utterance with `SIGTERM`.
        pub fn stop(&self) {
            let Some(mut child) = self.take_child() else {
                return;
            };
            let pid = child.id().to_string();
            let _ = Command::new("/bin/kill").arg("-TERM").arg(pid).status();
            let _ = child.wait();
        }

        /// Whether `say` is still running.
        pub fn is_speaking(&self) -> bool {
            let mut guard = self.lock_child();
            let running = match guard.as_mut() {
                Some(child) => matches!(child.try_wait(), Ok(None)),
                None => false,
            };
            if !running {
                *guard = None;
            }
            running
        }

        fn lock_child(&self) -> MutexGuard<'_, Option<Child>> {
            self.child
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
        }

        fn take_child(&self) -> Option<Child> {
            self.lock_child().take()
        }
    }

    impl Default for Speaker {
        fn default() -> Self {
            Self::new()
        }
    }

    fn voice_for_language(language_code: &str) -> Option<String> {
        let code = language_code.trim();
        if code.is_empty() || code.eq_ignore_ascii_case("auto") {
            return None;
        }
        let output = Command::new(SAY).arg("-v").arg("?").output().ok()?;
        let text = String::from_utf8_lossy(&output.stdout);
        parse_say_voice_list(&text)
            .into_iter()
            .find(|voice| locale_matches(&voice.locale, code))
            .map(|voice| voice.name)
    }
}

#[cfg(windows)]
mod windows {
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender, SyncSender};
    use std::sync::{Arc, Mutex, MutexGuard};
    use std::thread::{self, JoinHandle};
    use std::time::Duration;

    use windows::core::{w, GUID, PCWSTR, PWSTR};
    use windows::Win32::Media::Speech::{
        ISpObjectToken, ISpObjectTokenCategory, ISpVoice, SPF_ASYNC, SPF_IS_XML,
        SPF_PURGEBEFORESPEAK,
    };
    use windows::Win32::System::Com::{
        CoCreateInstance, CoInitializeEx, CoTaskMemFree, CoUninitialize, CLSCTX_ALL,
        COINIT_APARTMENTTHREADED,
    };

    use super::super::{truncate, MAX_CHARS};

    const CLSID_SP_VOICE: GUID = GUID::from_u128(0x96749377_3391_11d2_9ee3_00c04f797396);
    const CLSID_SP_OBJECT_TOKEN_CATEGORY: GUID =
        GUID::from_u128(0xa910187f_0c7a_45ac_92cc_59edafb77b53);
    const VOICE_CATEGORY: PCWSTR = w!("HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices");

    enum Command {
        Speak {
            text: String,
            voice_id: String,
            language_code: String,
        },
        Stop,
        Shutdown,
    }

    /// A speaker backed by SAPI through a dedicated COM worker thread.
    pub struct Speaker {
        sender: Mutex<Option<Sender<Command>>>,
        speaking: Arc<AtomicBool>,
        available: bool,
        worker: Mutex<Option<JoinHandle<()>>>,
    }

    impl Speaker {
        /// Maximum number of characters handed to SAPI.
        pub const MAX_CHARS: usize = MAX_CHARS;

        /// Create the speaker and start its COM worker.
        pub fn new() -> Self {
            let (init_tx, init_rx) = mpsc::sync_channel::<bool>(1);
            let (sender, receiver) = mpsc::channel();
            let speaking = Arc::new(AtomicBool::new(false));
            let worker_speaking = Arc::clone(&speaking);
            let spawned = thread::Builder::new()
                .name("ofm-sapi".to_string())
                .spawn(move || worker(init_tx, receiver, worker_speaking));
            match spawned {
                Ok(handle) => {
                    let available = init_rx
                        .recv_timeout(Duration::from_secs(2))
                        .unwrap_or(false);
                    Self {
                        sender: Mutex::new(if available { Some(sender) } else { None }),
                        speaking,
                        available,
                        worker: Mutex::new(Some(handle)),
                    }
                }
                Err(error) => {
                    log::info!("could not start the SAPI worker: {error}");
                    Self {
                        sender: Mutex::new(None),
                        speaking,
                        available: false,
                        worker: Mutex::new(None),
                    }
                }
            }
        }

        /// Whether SAPI could be initialised.
        pub fn is_available(&self) -> bool {
            self.available
        }

        /// Installed SAPI voices as `(id, label)` pairs, sorted by label.
        pub fn voices(&self) -> Vec<(String, String)> {
            if !self.available {
                return Vec::new();
            }
            // SAFETY: initialises COM for the calling thread; balanced below.
            let initialized = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) }.0 == 0;
            // SAFETY: COM is initialised above for this thread; the token
            // objects are released before `CoUninitialize` below.
            let mut voices: Vec<(String, String)> = unsafe { voice_tokens() }
                .into_iter()
                .map(|(id, label, _)| (id, label))
                .collect();
            if initialized {
                // SAFETY: balances the successful initialisation above.
                unsafe { CoUninitialize() };
            }
            voices.sort_by_key(|(_, label)| label.to_lowercase());
            voices
        }

        /// Speak `text` asynchronously with the chosen voice or language.
        pub fn speak(&self, text: &str, voice_id: &str, language_code: &str) -> bool {
            let trimmed = text.trim();
            if trimmed.is_empty() || !self.available {
                return false;
            }
            let Some(sender) = self.sender() else {
                return false;
            };
            sender
                .send(Command::Speak {
                    text: truncate(trimmed).to_string(),
                    voice_id: voice_id.trim().to_string(),
                    language_code: language_code.trim().to_string(),
                })
                .is_ok()
        }

        /// Purge the current utterance.
        pub fn stop(&self) {
            if let Some(sender) = self.sender() {
                let _ = sender.send(Command::Stop);
            }
        }

        /// Whether SAPI is still speaking.
        pub fn is_speaking(&self) -> bool {
            self.speaking.load(Ordering::SeqCst)
        }

        fn sender(&self) -> Option<Sender<Command>> {
            self.lock_sender().as_ref().cloned()
        }

        fn lock_sender(&self) -> MutexGuard<'_, Option<Sender<Command>>> {
            self.sender
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
        }
    }

    impl Default for Speaker {
        fn default() -> Self {
            Self::new()
        }
    }

    impl Drop for Speaker {
        fn drop(&mut self) {
            if let Some(sender) = self.lock_sender().take() {
                let _ = sender.send(Command::Shutdown);
            }
            if let Some(handle) = self
                .worker
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner())
                .take()
            {
                let _ = handle.join();
            }
        }
    }

    fn worker(init: SyncSender<bool>, receiver: Receiver<Command>, speaking: Arc<AtomicBool>) {
        // SAFETY: COM initialisation for this dedicated worker thread.
        let initialized = unsafe { CoInitializeEx(None, COINIT_APARTMENTTHREADED) }.0 == 0;
        // SAFETY: creates the SAPI voice object on the thread that will use it.
        let voice: Option<ISpVoice> =
            unsafe { CoCreateInstance(&CLSID_SP_VOICE, None, CLSCTX_ALL) }.ok();
        let _ = init.send(voice.is_some());
        let Some(voice) = voice else {
            if initialized {
                // SAFETY: balances the initialisation above.
                unsafe { CoUninitialize() };
            }
            return;
        };

        loop {
            match receiver.recv_timeout(Duration::from_millis(100)) {
                Ok(Command::Speak {
                    text,
                    voice_id,
                    language_code,
                }) => {
                    apply_voice(&voice, &voice_id, &language_code);
                    let wide: Vec<u16> = text.encode_utf16().chain(std::iter::once(0)).collect();
                    let flags = (SPF_IS_XML.0 | SPF_ASYNC.0) as u32;
                    // SAFETY: `wide` is NUL-terminated UTF-16 that outlives the
                    // call; SAPI copies the text before returning.
                    let started =
                        unsafe { voice.Speak(PCWSTR(wide.as_ptr()), flags, None) }.is_ok();
                    speaking.store(started, Ordering::SeqCst);
                }
                Ok(Command::Stop) => {
                    // SAFETY: purging with a null string is the documented way
                    // to stop the asynchronous utterance.
                    let _ =
                        unsafe { voice.Speak(PCWSTR::null(), SPF_PURGEBEFORESPEAK.0 as u32, None) };
                    speaking.store(false, Ordering::SeqCst);
                }
                Ok(Command::Shutdown) => break,
                Err(RecvTimeoutError::Timeout) => {
                    // SAFETY: polling with a zero timeout only inspects state.
                    let done = unsafe { voice.WaitUntilDone(0) }.is_ok();
                    speaking.store(!done, Ordering::SeqCst);
                }
                Err(RecvTimeoutError::Disconnected) => break,
            }
        }

        if initialized {
            // SAFETY: balances the initialisation at the top of the worker.
            unsafe { CoUninitialize() };
        }
    }

    fn apply_voice(voice: &ISpVoice, voice_id: &str, language_code: &str) {
        // SAFETY: runs on the worker thread with COM initialised.
        let tokens = unsafe { voice_tokens() };
        if !voice_id.is_empty() {
            if let Some((_, _, token)) = tokens
                .iter()
                .find(|(id, label, _)| id == voice_id || label == voice_id)
            {
                // SAFETY: `token` is a live SAPI voice token.
                let _ = unsafe { voice.SetVoice(token) };
                return;
            }
        }
        let code = language_code.trim();
        if code.is_empty() || code.eq_ignore_ascii_case("auto") {
            return;
        }
        if let Some((_, _, token)) = tokens
            .iter()
            .find(|(_, label, _)| label_matches_language(label, code))
        {
            // SAFETY: `token` is a live SAPI voice token.
            let _ = unsafe { voice.SetVoice(token) };
        }
    }

    fn label_matches_language(label: &str, code: &str) -> bool {
        let Some(name) = language_name(code) else {
            return false;
        };
        label.to_lowercase().contains(&name.to_lowercase())
    }

    fn language_name(code: &str) -> Option<&'static str> {
        match code.to_ascii_lowercase().as_str() {
            "en" => Some("English"),
            "uk" => Some("Ukrainian"),
            "ru" => Some("Russian"),
            "de" => Some("German"),
            "fr" => Some("French"),
            "es" => Some("Spanish"),
            "pl" => Some("Polish"),
            "pt" => Some("Portuguese"),
            "it" => Some("Italian"),
            _ => None,
        }
    }

    /// Enumerate the installed SAPI voices as `(id, label, token)`.
    ///
    /// # Safety
    ///
    /// COM must be initialised on the calling thread.
    unsafe fn voice_tokens() -> Vec<(String, String, ISpObjectToken)> {
        let mut voices = Vec::new();
        // SAFETY: COM is initialised on the calling thread.
        let category: ISpObjectTokenCategory =
            match unsafe { CoCreateInstance(&CLSID_SP_OBJECT_TOKEN_CATEGORY, None, CLSCTX_ALL) } {
                Ok(category) => category,
                Err(_) => return voices,
            };
        // SAFETY: `VOICE_CATEGORY` is a static, NUL-terminated category id.
        if unsafe { category.SetId(VOICE_CATEGORY, false) }.is_err() {
            return voices;
        }
        // SAFETY: no required or optional attribute filters.
        let tokens = match unsafe { category.EnumTokens(PCWSTR::null(), PCWSTR::null()) } {
            Ok(tokens) => tokens,
            Err(_) => return voices,
        };
        let mut count = 0u32;
        // SAFETY: `count` points to a valid `u32` for the duration of the call.
        if unsafe { tokens.GetCount(&mut count) }.is_err() {
            return voices;
        }
        for index in 0..count {
            // SAFETY: `index` is below the count reported by the enumerator.
            let Ok(token) = (unsafe { tokens.Item(index) }) else {
                continue;
            };
            // SAFETY: the token owns its id string, released after copying.
            let id = match unsafe { token.GetId() } {
                Ok(id) => take_pwstr(id),
                Err(_) => continue,
            };
            // SAFETY: `Name` is the documented display-name attribute.
            let label = match unsafe { token.GetStringValue(w!("Name")) } {
                Ok(name) => take_pwstr(name),
                Err(_) => id.clone(),
            };
            voices.push((id, label, token));
        }
        voices
    }

    /// Copy and free a `CoTaskMemAlloc`-owned SAPI string.
    ///
    /// # Safety
    ///
    /// `value` must be a string allocated by a SAPI/COM API that returns
    /// `PWSTR` ownership to the caller.
    unsafe fn take_pwstr(value: PWSTR) -> String {
        if value.is_null() {
            return String::new();
        }
        // SAFETY: the string is NUL-terminated and owned by the caller.
        let text = unsafe { value.to_string() }.unwrap_or_default();
        // SAFETY: SAPI allocates these strings with `CoTaskMemAlloc`.
        unsafe { CoTaskMemFree(Some(value.0 as *const core::ffi::c_void)) };
        text
    }
}

#[cfg(not(any(windows, target_os = "macos")))]
mod unsupported {
    use std::sync::Once;

    use super::super::MAX_CHARS;

    static LOGGED: Once = Once::new();

    /// A silent speaker used on platforms without a speech backend.
    pub struct Speaker {
        _private: (),
    }

    impl Speaker {
        /// Maximum number of characters that would be spoken.
        pub const MAX_CHARS: usize = MAX_CHARS;

        /// Create the no-op speaker and log the limitation once.
        pub fn new() -> Self {
            LOGGED.call_once(|| {
                log::info!("text-to-speech is not available on this platform");
            });
            Self { _private: () }
        }

        /// Always `false` on this platform.
        pub fn is_available(&self) -> bool {
            false
        }

        /// Always empty on this platform.
        pub fn voices(&self) -> Vec<(String, String)> {
            Vec::new()
        }

        /// Always `false` on this platform.
        pub fn speak(&self, text: &str, voice_id: &str, language_code: &str) -> bool {
            let _ = (text, voice_id, language_code);
            false
        }

        /// No-op.
        pub fn stop(&self) {}

        /// Always `false` on this platform.
        pub fn is_speaking(&self) -> bool {
            false
        }
    }

    impl Default for Speaker {
        fn default() -> Self {
            Self::new()
        }
    }
}

#[cfg(target_os = "macos")]
pub use macos::Speaker;

#[cfg(windows)]
pub use windows::Speaker;

#[cfg(not(any(windows, target_os = "macos")))]
pub use unsupported::Speaker;
