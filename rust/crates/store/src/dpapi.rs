//! Windows DPAPI (user scope) encryption for the file secret backend.
//!
//! `CryptProtectData`/`CryptUnprotectData` bind the ciphertext to the current
//! Windows user profile. This is the same mechanism the Python port uses, so a
//! `secrets.dat` written by either implementation can be read by the other.
//! Everywhere else the backend reports itself as unavailable and the store
//! keeps the secrets in a `0600` JSON file instead.

#[cfg(not(windows))]
use crate::error::StoreError;

#[cfg(windows)]
pub(crate) use platform::{is_available, protect, unprotect};

#[cfg(not(windows))]
pub(crate) const fn is_available() -> bool {
    false
}

#[cfg(not(windows))]
pub(crate) fn protect(_plain: &[u8]) -> Result<Vec<u8>, StoreError> {
    Err(StoreError::Unsupported("DPAPI"))
}

#[cfg(not(windows))]
pub(crate) fn unprotect(_sealed: &[u8]) -> Result<Vec<u8>, StoreError> {
    Err(StoreError::Unsupported("DPAPI"))
}

#[cfg(windows)]
mod platform {
    use std::ffi::c_void;
    use std::io;
    use std::ptr;
    use std::sync::OnceLock;

    use crate::error::StoreError;

    /// `CRYPTPROTECT_UI_FORBIDDEN`: never show a prompt from a headless save.
    const CRYPTPROTECT_UI_FORBIDDEN: u32 = 0x01;

    /// `DATA_BLOB` from `dpapi.h`.
    #[repr(C)]
    struct DataBlob {
        cb_data: u32,
        pb_data: *mut u8,
    }

    #[link(name = "crypt32")]
    extern "system" {
        fn CryptProtectData(
            data_in: *const DataBlob,
            description: *const u16,
            entropy: *const DataBlob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;

        fn CryptUnprotectData(
            data_in: *const DataBlob,
            description: *mut *mut u16,
            entropy: *const DataBlob,
            reserved: *mut c_void,
            prompt: *mut c_void,
            flags: u32,
            data_out: *mut DataBlob,
        ) -> i32;
    }

    #[link(name = "kernel32")]
    extern "system" {
        fn LocalFree(memory: *mut c_void) -> *mut c_void;
    }

    /// Run one DPAPI direction over `input`.
    fn transform(input: &[u8], encrypt: bool) -> io::Result<Vec<u8>> {
        if input.is_empty() {
            return Ok(Vec::new());
        }

        let source = DataBlob {
            cb_data: input.len() as u32,
            pb_data: input.as_ptr() as *mut u8,
        };
        let mut sealed = DataBlob {
            cb_data: 0,
            pb_data: ptr::null_mut(),
        };

        // SAFETY: `source` points at `input` for the whole call, `sealed` is a
        // writable, zero-initialised output blob, and the optional arguments are
        // null, which both functions accept. `CRYPTPROTECT_UI_FORBIDDEN` keeps
        // the call headless. The call returns a non-zero BOOL on success.
        let succeeded = unsafe {
            if encrypt {
                CryptProtectData(
                    &source,
                    ptr::null(),
                    ptr::null(),
                    ptr::null_mut(),
                    ptr::null_mut(),
                    CRYPTPROTECT_UI_FORBIDDEN,
                    &mut sealed,
                )
            } else {
                CryptUnprotectData(
                    &source,
                    ptr::null_mut(),
                    ptr::null(),
                    ptr::null_mut(),
                    ptr::null_mut(),
                    CRYPTPROTECT_UI_FORBIDDEN,
                    &mut sealed,
                )
            }
        };
        if succeeded == 0 {
            return Err(io::Error::last_os_error());
        }

        // SAFETY: on success DPAPI allocated `sealed.pb_data` with `LocalAlloc`
        // and set `cb_data` to its length, so the pair is a valid slice.
        let plain =
            unsafe { std::slice::from_raw_parts(sealed.pb_data, sealed.cb_data as usize).to_vec() };
        // SAFETY: the buffer is owned by us after a successful call and is
        // released exactly once; `LocalFree` accepts the returned pointer.
        unsafe {
            LocalFree(sealed.pb_data as *mut c_void);
        }
        Ok(plain)
    }

    /// Whether DPAPI works for this user, probed once with a round-trip.
    pub(crate) fn is_available() -> bool {
        static AVAILABLE: OnceLock<bool> = OnceLock::new();
        *AVAILABLE.get_or_init(|| {
            let probe = b"ofm-store dpapi probe";
            match transform(probe, true).and_then(|sealed| transform(&sealed, false)) {
                Ok(round_trip) if round_trip == probe => true,
                Ok(_) => {
                    log::warn!("DPAPI round-trip mismatch; storing secrets unencrypted");
                    false
                }
                Err(error) => {
                    log::warn!("DPAPI is unavailable ({error}); storing secrets unencrypted");
                    false
                }
            }
        })
    }

    /// Encrypt `plain` into a DPAPI blob.
    pub(crate) fn protect(plain: &[u8]) -> Result<Vec<u8>, StoreError> {
        transform(plain, true).map_err(|error| StoreError::backend(format!("DPAPI: {error}")))
    }

    /// Decrypt a DPAPI blob produced by [`protect`].
    pub(crate) fn unprotect(sealed: &[u8]) -> Result<Vec<u8>, StoreError> {
        transform(sealed, false).map_err(|error| StoreError::backend(format!("DPAPI: {error}")))
    }
}
