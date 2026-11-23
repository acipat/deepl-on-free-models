//! Tauri commands: a thin, boring bridge between the webview and `ofm-app`.
//!
//! Every command returns `Result<serde_json::Value, String>`; a `String` error is
//! already localised by the controller and is safe to show to the user.

use std::path::Path;

use ofm_app::AppController;
use serde_json::{json, Value};
use tauri::State;

use crate::Shared;

fn controller<'a>(state: &'a State<'_, Shared>) -> &'a AppController {
    state.controller.as_ref()
}

fn state_json(controller: &AppController) -> Value {
    serde_json::to_value(controller.state()).unwrap_or_else(|_| json!({}))
}

// ---------------------------------------------------------------- state

#[tauri::command]
pub fn get_state(state: State<'_, Shared>) -> Result<Value, String> {
    Ok(state_json(controller(&state)))
}

/// Command-line actions the window has not consumed yet.
#[tauri::command]
pub fn get_startup(state: State<'_, Shared>) -> Result<Value, String> {
    let startup = state
        .startup
        .lock()
        .unwrap_or_else(|poison| poison.into_inner())
        .clone();
    Ok(serde_json::to_value(startup).unwrap_or_else(|_| json!({})))
}

#[tauri::command]
pub fn get_settings(state: State<'_, Shared>) -> Result<Value, String> {
    Ok(serde_json::to_value(&controller(&state).state().settings).unwrap_or_else(|_| json!({})))
}

#[tauri::command]
pub fn save_settings(state: State<'_, Shared>, settings: Value) -> Result<Value, String> {
    controller(&state).save_settings_json(&settings);
    Ok(state_json(controller(&state)))
}

/// "Open at login" state: `{ "status": ..., "error": ... }`.
#[tauri::command]
pub fn get_login_item(state: State<'_, Shared>) -> Result<Value, String> {
    let snapshot = controller(&state).state();
    Ok(json!({
        "status": snapshot.login_item_status,
        "error": snapshot.login_item_error,
    }))
}

/// Turn "Open at login" on or off; the controller emits `loginItem`.
#[tauri::command]
pub fn set_login_item(state: State<'_, Shared>, enabled: bool) -> Result<(), String> {
    controller(&state).set_login_item(enabled);
    Ok(())
}

/// Open the system page where login items are approved.
#[tauri::command]
pub fn open_login_item_settings(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).open_login_item_settings();
    Ok(())
}

#[tauri::command]
pub fn get_catalog() -> Result<Value, String> {
    Ok(ofm_app::catalog_json())
}

// ------------------------------------------------------------ translate

#[tauri::command]
pub fn set_source_text(state: State<'_, Shared>, text: String) -> Result<(), String> {
    controller(&state).set_source_text(&text);
    Ok(())
}

#[tauri::command]
pub fn set_source_language(state: State<'_, Shared>, code: String) -> Result<(), String> {
    controller(&state).set_source_language(&code);
    Ok(())
}

#[tauri::command]
pub fn set_target_language(state: State<'_, Shared>, code: String) -> Result<(), String> {
    controller(&state).set_target_language(&code);
    Ok(())
}

#[tauri::command]
pub fn swap_languages(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).swap_languages();
    Ok(())
}

#[tauri::command]
pub fn set_style(state: State<'_, Shared>, style: String) -> Result<(), String> {
    controller(&state).set_style(&style);
    Ok(())
}

#[tauri::command]
pub fn set_tone(state: State<'_, Shared>, tone: String) -> Result<(), String> {
    controller(&state).set_tone(&tone);
    Ok(())
}

#[tauri::command]
pub fn set_result_view(state: State<'_, Shared>, mode: String) -> Result<(), String> {
    controller(&state).set_result_view(&mode);
    Ok(())
}

#[tauri::command]
pub fn clear_source(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).clear_source();
    Ok(())
}

#[tauri::command]
pub fn translate_text(state: State<'_, Shared>, force: Option<bool>) -> Result<(), String> {
    controller(&state).translate(force.unwrap_or(true));
    Ok(())
}

#[tauri::command]
pub fn cancel(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).cancel();
    Ok(())
}

#[tauri::command]
pub fn copy_translation(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).copy_translation();
    Ok(())
}

#[tauri::command]
pub fn copy_source(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).copy_source();
    Ok(())
}

#[tauri::command]
pub fn translate_clipboard(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).translate_clipboard();
    Ok(())
}

#[tauri::command]
pub fn translate_selection(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).translate_selection();
    Ok(())
}

#[tauri::command]
pub fn speak(state: State<'_, Shared>, target: String) -> Result<(), String> {
    controller(&state).speak(&target);
    Ok(())
}

#[tauri::command]
pub fn stop_speaking(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).stop_speaking();
    Ok(())
}

// -------------------------------------------------------------- backend

#[tauri::command]
pub fn check_connection(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).check_connection();
    Ok(())
}

#[tauri::command]
pub fn connect_and_load_models(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).connect_and_load_models();
    Ok(())
}

#[tauri::command]
pub fn load_fallback_models(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).load_fallback_models();
    Ok(())
}

#[tauri::command]
pub fn apply_catalog_entry(state: State<'_, Shared>, model_id: String) -> Result<(), String> {
    if let Some(entry) = ofm_config::ModelCatalog::entry(&model_id) {
        controller(&state).apply_catalog_entry(entry);
    }
    Ok(())
}

#[tauri::command]
pub fn set_interface_language(state: State<'_, Shared>, code: String) -> Result<(), String> {
    if let Some(language) = ofm_i18n::AppLanguage::from_code(&code) {
        controller(&state).set_interface_language(language);
    }
    Ok(())
}

#[tauri::command]
pub fn set_tab(state: State<'_, Shared>, tab: String) -> Result<(), String> {
    controller(&state).set_tab(&tab);
    Ok(())
}

// ---------------------------------------------------------------- files

#[tauri::command]
pub fn translate_file(
    state: State<'_, Shared>,
    path: String,
    target: Option<String>,
) -> Result<(), String> {
    controller(&state).start_file_translation(Path::new(&path), target.as_deref());
    Ok(())
}

#[tauri::command]
pub fn cancel_file_translation(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).cancel_file_translation();
    Ok(())
}

#[tauri::command]
pub fn save_translated_file(state: State<'_, Shared>, path: String) -> Result<(), String> {
    controller(&state).save_translated_file(Path::new(&path));
    Ok(())
}

#[tauri::command]
pub fn clear_file_job(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).clear_file_job();
    Ok(())
}

// ---------------------------------------------------------------- write

#[tauri::command]
pub fn write_text(
    state: State<'_, Shared>,
    text: String,
    target_code: Option<String>,
) -> Result<(), String> {
    controller(&state).write_text(&text, target_code.as_deref().unwrap_or("auto"));
    Ok(())
}

#[tauri::command]
pub fn cancel_write(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).cancel_write();
    Ok(())
}

// -------------------------------------------------------------- history

#[tauri::command]
pub fn history_list(state: State<'_, Shared>) -> Result<Value, String> {
    Ok(serde_json::to_value(controller(&state).state().history).unwrap_or_else(|_| json!([])))
}

#[tauri::command]
pub fn history_search(state: State<'_, Shared>, query: String) -> Result<Value, String> {
    let entries = controller(&state).history_search(&query);
    Ok(serde_json::to_value(entries).unwrap_or_else(|_| json!([])))
}

#[tauri::command]
pub fn history_delete(state: State<'_, Shared>, id: String) -> Result<(), String> {
    controller(&state).history_delete(&id);
    Ok(())
}

#[tauri::command]
pub fn history_clear(state: State<'_, Shared>) -> Result<(), String> {
    controller(&state).history_clear();
    Ok(())
}

#[tauri::command]
pub fn load_history_entry(state: State<'_, Shared>, id: String) -> Result<(), String> {
    controller(&state).load_history_entry(&id);
    Ok(())
}

// ------------------------------------------------------- auxiliary queries

/// Model list of the configured server (catalogue dialog).
#[tauri::command]
pub async fn list_models(state: State<'_, Shared>) -> Result<Value, String> {
    let models = controller(&state)
        .fetch_models()
        .await
        .map_err(|error| error.message())?;
    Ok(serde_json::to_value(models).unwrap_or_else(|_| json!([])))
}

/// Voices the system speech engine offers: `[{ id, label }]`.
#[tauri::command]
pub fn list_voices(state: State<'_, Shared>) -> Result<Value, String> {
    let voices = controller(&state).voices();
    Ok(Value::Array(
        voices
            .into_iter()
            .map(|(id, label)| json!({ "id": id, "label": label }))
            .collect(),
    ))
}

/// Ask the user where to save the translated document.
#[tauri::command]
pub async fn pick_save_path(
    app: tauri::AppHandle,
    suggested_name: String,
) -> Result<Value, String> {
    use tauri_plugin_dialog::DialogExt;
    let chosen = app
        .dialog()
        .file()
        .set_file_name(&suggested_name)
        .blocking_save_file();
    Ok(match chosen.and_then(|path| path.into_path().ok()) {
        Some(path) => json!(path.to_string_lossy()),
        None => Value::Null,
    })
}

/// The prompt that would be sent for the given style, tone and target.
#[tauri::command]
pub fn preview_prompt(
    state: State<'_, Shared>,
    style: Option<String>,
    tone: Option<String>,
    target_code: Option<String>,
) -> Result<Value, String> {
    let text = controller(&state).prompt_preview_for(
        style.as_deref().unwrap_or("auto"),
        tone.as_deref().unwrap_or("standard"),
        target_code.as_deref().unwrap_or("en"),
    );
    Ok(json!({ "prompt": text }))
}

/// Clipboard content as Markdown (rich text when the app copies HTML).
#[tauri::command]
pub fn read_clipboard() -> Result<Value, String> {
    let text = ofm_platform::pasteboard::clipboard_markdown()
        .or_else(ofm_platform::pasteboard::clipboard_text);
    Ok(match text {
        Some(text) => json!(text),
        None => Value::Null,
    })
}

// ------------------------------------------------------- clipboard and shell

/// Put arbitrary text on the clipboard (Write tab, history rows).
#[tauri::command]
pub fn copy_text(text: String) -> Result<(), String> {
    ofm_platform::pasteboard::set_clipboard_text(&text, None, None);
    Ok(())
}

/// Open a link in the user's browser.
#[tauri::command]
pub fn open_url(app: tauri::AppHandle, url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("Only http and https links can be opened.".to_string());
    }
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .open_url(url, None::<&str>)
        .map_err(|error| error.to_string())
}

/// Show a translated file in the system file manager.
#[tauri::command]
pub fn reveal_in_folder(app: tauri::AppHandle, path: String) -> Result<(), String> {
    use tauri_plugin_opener::OpenerExt;
    app.opener()
        .reveal_item_in_dir(std::path::Path::new(&path))
        .map_err(|error| error.to_string())
}

/// Pick a document to translate.
#[tauri::command]
pub async fn pick_file(app: tauri::AppHandle) -> Result<Value, String> {
    use tauri_plugin_dialog::DialogExt;
    let filters = DocumentFilter::all();
    let chosen = app
        .dialog()
        .file()
        .add_filter("Documents", &filters)
        .blocking_pick_file();
    Ok(match chosen.and_then(|path| path.into_path().ok()) {
        Some(path) => json!(path.to_string_lossy()),
        None => Value::Null,
    })
}

/// Extensions the Files tab accepts.
struct DocumentFilter;

impl DocumentFilter {
    fn all() -> Vec<&'static str> {
        vec!["txt", "text", "md", "markdown", "mdown", "pdf", "docx"]
    }
}

/// Interface strings for the active language: `{ englishKey: translation }`.
#[tauri::command]
pub fn get_translations(state: State<'_, Shared>) -> Result<Value, String> {
    Ok(controller(&state).translations_json())
}

/// Select a model by id (catalogue entry or a model found on the server).
#[tauri::command]
pub fn apply_model(state: State<'_, Shared>, model_id: String) -> Result<(), String> {
    controller(&state).apply_model(&model_id);
    Ok(())
}

/// Paths, versions and the secret-store backend for the About section.
#[tauri::command]
pub fn get_diagnostics(state: State<'_, Shared>) -> Result<Value, String> {
    Ok(controller(&state).diagnostics_json())
}
