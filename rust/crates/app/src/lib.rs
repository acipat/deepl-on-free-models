//! Application layer for DeepL-oFM: the state machine every frontend drives.
//!
//! This crate owns no user interface. The desktop shell (Tauri), the CLI and the
//! tests all talk to [`AppController`]: they call its commands and subscribe to
//! [`AppEvent`]s, and they render [`AppState`] snapshots. That keeps the UI
//! replaceable and lets the whole engine be tested without a window.
//!
//! ```no_run
//! use ofm_app::AppController;
//!
//! let controller = AppController::new();
//! controller.set_source_text("Hello, world!");
//! controller.translate(true);
//! ```

#![deny(missing_docs)]
#![deny(rustdoc::broken_intra_doc_links)]

mod controller;
mod state;

pub use controller::{
    catalog_json, describe, languages_json, localized, offline_controller, providers_json,
    status_line, translation_languages_json, AppController,
};
pub use state::{AppEvent, AppState, BackendStatus, FileJob, FileJobState, WriteState};
