//! Tauri v2 shell for DeepL-oFM.
//!
//! The shell owns the window, the tray, the global shortcuts and the bridge:
//! every command is a thin wrapper around [`ofm_app::AppController`], and every
//! state change reaches the frontend as an `app://event` payload. Building this
//! crate needs the platform WebView libraries, so it is excluded from the
//! workspace default members.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use ofm_app::{AppController, AppEvent};
use tauri::{Emitter, Manager};

/// Shared controller handed to every command.
pub struct Shared {
    pub controller: Arc<AppController>,
    /// Command-line actions awaiting consumption by the frontend.
    pub startup: Mutex<Startup>,
}

/// Command-line actions the window applies after it has loaded.
#[derive(Debug, Default, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Startup {
    /// Open the model catalogue.
    pub catalog: bool,
    /// Text the Write tab should start with.
    pub write_text: Option<String>,
    /// Tab requested on the command line.
    pub tab: Option<String>,
}

/// Parse the flags the Python build accepted so existing shortcuts keep working.
fn parse_arguments(arguments: &[String]) -> Option<Startup> {
    let mut startup = Startup::default();
    let mut index = 0;
    while index < arguments.len() {
        let argument = arguments[index].as_str();
        let next = || arguments.get(index + 1).cloned();
        match argument {
            "--prefill" | "--open-file" | "--translate-file" | "--write-text" | "--tab" => {
                let Some(value) = next() else {
                    eprintln!("{argument} needs a value");
                    break;
                };
                match argument {
                    "--tab" => startup.tab = Some(value),
                    "--write-text" => startup.write_text = Some(value),
                    // `--prefill` and the file flags are applied to the
                    // controller before the webview loads, so they are not part
                    // of the startup payload.
                    _ => {}
                }
                index += 1;
            }
            "--catalog" => startup.catalog = true,
            // Handled by `main` before this runs.
            "--debug" | "--translate-clipboard" | "--connect" | "--load-fallback-models" => {}
            "--help" | "-h" => {
                println!(
                    "DeepL-oFM\n\n\
                     --prefill <text>          start with this text\n\
                     --tab <translate|files|write|history>\n\
                     --open-file <path>        translate a document at launch\n\
                     --translate-file <path>   same as --open-file\n\
                     --write-text <text>       open Write with a draft\n\
                     --translate-clipboard     translate the clipboard at launch\n\
                     --connect                 connect and load the model list\n\
                     --load-fallback-models    load the fallback model list\n\
                     --catalog                 open the model catalogue\n\
                     --debug                   verbose log"
                );
                return None;
            }
            other => eprintln!("unknown argument: {other}"),
        }
        index += 1;
    }
    Some(startup)
}

/// Controller mutations requested on the command line.
fn apply_startup_actions(controller: &Arc<AppController>, arguments: &[String]) {
    let mut index = 0;
    while index < arguments.len() {
        match arguments[index].as_str() {
            "--prefill" => {
                if let Some(value) = arguments.get(index + 1) {
                    controller.set_tab("translate");
                    controller.set_source_text(value);
                    index += 1;
                }
            }
            "--tab" => {
                if let Some(value) = arguments.get(index + 1) {
                    controller.set_tab(value);
                    index += 1;
                }
            }
            "--open-file" | "--translate-file" => {
                if let Some(value) = arguments.get(index + 1) {
                    controller.set_tab("files");
                    controller.start_file_translation(std::path::Path::new(value), None);
                    index += 1;
                }
            }
            "--write-text" => {
                if arguments.get(index + 1).is_some() {
                    controller.set_tab("write");
                    index += 1;
                }
            }
            "--translate-clipboard" => controller.translate_clipboard(),
            "--connect" => controller.connect_and_load_models(),
            "--load-fallback-models" => controller.load_fallback_models(),
            _ => {}
        }
        index += 1;
    }
}

fn main() {
    let arguments: Vec<String> = std::env::args().skip(1).collect();
    let Some(startup) = parse_arguments(&arguments) else {
        return;
    };
    let debug = arguments.iter().any(|argument| argument == "--debug");
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(if debug {
        "debug"
    } else {
        "info"
    }))
    .init();

    let controller = Arc::new(AppController::new());

    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, argv, _cwd| {
            let arguments = argv.get(1..).unwrap_or_default();
            let Some(startup) = parse_arguments(arguments) else {
                return;
            };
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
            let shared = app.state::<Shared>();
            apply_startup_actions(&shared.controller, arguments);
            if startup.catalog || startup.write_text.is_some() || startup.tab.is_some() {
                {
                    let mut pending = shared.startup.lock().unwrap_or_else(|p| p.into_inner());
                    pending.catalog |= startup.catalog;
                    if startup.tab.is_some() || startup.write_text.is_some() {
                        pending.tab = startup.tab;
                    }
                    if startup.write_text.is_some() {
                        pending.write_text = startup.write_text;
                    }
                }
                let _ = app.emit("app://event", serde_json::json!({ "type": "startup" }));
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(Shared {
            controller: Arc::clone(&controller),
            startup: Mutex::new(startup),
        })
        .setup(move |app| {
            install_tray(&app.handle().clone())?;
            install_hotkeys(&app.handle().clone(), Arc::clone(&controller));

            // Forward controller events to the webview and keep the tray in sync.
            let handle = app.handle().clone();
            let mut events = controller.subscribe();
            let tray_controller = Arc::clone(&controller);
            let tray_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    match events.recv().await {
                        Ok(event) => {
                            if matches!(event, AppEvent::Settings { .. }) {
                                sync_tray_visibility(&tray_handle, &tray_controller);
                            }
                            if let Ok(payload) = serde_json::to_value(&event) {
                                let _ = handle.emit("app://event", payload);
                            }
                        }
                        // A slow frontend may miss events; the next one carries
                        // enough information for it to refresh the whole state.
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
                    }
                }
            });

            // Probe at launch like the Python build, then warm a local model up
            // only when the setting asks for it.
            controller.check_connection();
            controller.warm_up();
            apply_startup_actions(&controller, &arguments);
            sync_tray_visibility(&app.handle().clone(), &controller);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let controller = window.app_handle().state::<Shared>().controller.clone();
                // Closing hides the window when the app lives in the tray; on
                // macOS a window-less app stays reachable through the Dock.
                if controller.show_in_menu_bar() || cfg!(target_os = "macos") {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_state,
            commands::get_startup,
            commands::translate_text,
            commands::cancel,
            commands::set_source_text,
            commands::set_source_language,
            commands::set_target_language,
            commands::swap_languages,
            commands::set_style,
            commands::set_tone,
            commands::set_result_view,
            commands::clear_source,
            commands::copy_translation,
            commands::copy_source,
            commands::translate_clipboard,
            commands::translate_selection,
            commands::speak,
            commands::stop_speaking,
            commands::check_connection,
            commands::connect_and_load_models,
            commands::load_fallback_models,
            commands::apply_catalog_entry,
            commands::apply_model,
            commands::get_catalog,
            commands::get_diagnostics,
            commands::get_settings,
            commands::save_settings,
            commands::get_login_item,
            commands::set_login_item,
            commands::open_login_item_settings,
            commands::set_interface_language,
            commands::set_tab,
            commands::translate_file,
            commands::cancel_file_translation,
            commands::save_translated_file,
            commands::clear_file_job,
            commands::write_text,
            commands::cancel_write,
            commands::history_list,
            commands::history_search,
            commands::history_delete,
            commands::history_clear,
            commands::load_history_entry,
            commands::list_models,
            commands::list_voices,
            commands::pick_save_path,
            commands::preview_prompt,
            commands::read_clipboard,
            commands::copy_text,
            commands::open_url,
            commands::reveal_in_folder,
            commands::pick_file,
            commands::get_translations,
        ])
        .build(tauri::generate_context!())
        .expect("failed to build DeepL-oFM")
        .run(|app, event| {
            // macOS: clicking the Dock icon with no window reopens it.
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen {
                has_visible_windows,
                ..
            } = event
            {
                if !has_visible_windows {
                    if let Some(window) = app.get_webview_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }
            #[cfg(not(target_os = "macos"))]
            let _ = (app, event);
        });
}

/// Register both global shortcuts and dispatch them from a polling thread.
fn install_hotkeys(app: &tauri::AppHandle, controller: Arc<AppController>) {
    use ofm_config::KeyCombo;
    use ofm_platform::hotkeys::HotkeyManager;
    use std::sync::mpsc::{channel, Sender};

    if !HotkeyManager::is_supported() {
        controller.set_hotkey_message(
            "clipboard",
            Some("Global shortcuts are not available on this system.".to_string()),
        );
        return;
    }

    // `GlobalHotKeyManager` owns a message window and is neither `Send` nor
    // `Sync`, so it cannot be shared: one thread owns it and everything else
    // reaches it through a channel. Registration, polling and dispatch all
    // happen on that thread, which is also where the OS expects them.
    let (updates, changes) = channel::<(KeyCombo, KeyCombo)>();
    let settings = controller.state().settings;
    let _ = updates.send((settings.hot_key.clone(), settings.selection_hot_key.clone()));

    // Forward every settings change to the owning thread.
    let mut events = controller.subscribe();
    let watch_controller = Arc::clone(&controller);
    let settings_updates: Sender<(KeyCombo, KeyCombo)> = updates.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            match events.recv().await {
                Ok(AppEvent::Settings { .. }) => {
                    let settings = watch_controller.state().settings;
                    if settings_updates
                        .send((settings.hot_key.clone(), settings.selection_hot_key.clone()))
                        .is_err()
                    {
                        break;
                    }
                }
                // A burst may overflow the channel; skipping one must not stop
                // the watcher, or shortcut changes would stop registering.
                Ok(_) => continue,
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    });

    let dispatch_controller = Arc::clone(&controller);
    let dispatch_app = app.clone();
    std::thread::spawn(move || {
        let mut manager = HotkeyManager::new();

        loop {
            // Windows posts `WM_HOTKEY` to a hidden window created on this
            // thread by `HotkeyManager::new`; the window procedure (which fills
            // the channel read by `poll`) only runs while this thread pumps its
            // message queue.  `poll` itself just drains that channel, so without
            // the pump the shortcuts register but never fire.  Pumping here is
            // the correct fix for `global-hotkey`: the crate only requires the
            // manager and a Win32 message loop to share a thread (not the main
            // thread), and this thread already owns registration, the settings
            // channel and dispatch.  Moving the manager to Tauri's main loop
            // would need an extra timer to poll it and would split that
            // ownership.  The pump is a no-op on other platforms.
            ofm_platform::hotkeys::pump_messages();

            // Apply pending shortcut changes first, then dispatch presses.
            while let Ok((clipboard, selection)) = changes.try_recv() {
                apply_shortcuts(&mut manager, &dispatch_controller, &clipboard, &selection);
            }
            for action in manager.poll() {
                // Capture before activating our own window.  "Translate
                // selection" synthesises Ctrl+C into whatever is focused, so
                // showing and focusing DeepL-oFM first would make the capture
                // copy our own UI (or nothing).  `translate_selection` blocks
                // until the capture and clipboard wait finish; the window is
                // brought forward afterwards so the result is visible.
                match action.as_str() {
                    "clipboard" => dispatch_controller.translate_clipboard(),
                    "selection" => dispatch_controller.translate_selection(),
                    other => log::debug!("unhandled hotkey action: {other}"),
                }
                if let Some(window) = dispatch_app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            std::thread::sleep(Duration::from_millis(60));
        }
    });
}

/// Register both shortcuts on the owning thread, reporting failures to the UI.
fn apply_shortcuts(
    manager: &mut ofm_platform::hotkeys::HotkeyManager,
    controller: &Arc<AppController>,
    clipboard: &ofm_config::KeyCombo,
    selection: &ofm_config::KeyCombo,
) {
    manager.unregister_all();

    let clipboard_error = manager.register("clipboard", clipboard).err();
    controller.set_hotkey_message(
        "clipboard",
        clipboard_error.map(|error| error.message_key.replace("%@", &clipboard.display())),
    );

    let selection_error = manager.register("selection", selection).err();
    controller.set_hotkey_message(
        "selection",
        selection_error.map(|error| error.message_key.replace("%@", &selection.display())),
    );
}

/// Show or hide the tray icon to match the setting.
fn sync_tray_visibility(app: &tauri::AppHandle, controller: &Arc<AppController>) {
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_visible(controller.show_in_menu_bar());
    }
}

/// Menu-bar icon with "Show" and "Quit", mirroring the macOS app.
fn install_tray(app: &tauri::AppHandle) -> Result<(), Box<dyn std::error::Error>> {
    use tauri::menu::{Menu, MenuItem};
    use tauri::tray::TrayIconBuilder;

    let show = MenuItem::with_id(app, "show", "Show DeepL-oFM", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit DeepL-oFM", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    let mut builder = TrayIconBuilder::with_id("main")
        .menu(&menu)
        .tooltip("DeepL-oFM")
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => app.exit(0),
            _ => {}
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}
