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
    let console =
        env_logger::Builder::from_env(env_logger::Env::default().default_filter_or(if debug {
            "debug"
        } else {
            "info"
        }))
        .build();
    let max_level = console.filter();
    let log_path = ofm_platform::logging::install(console, max_level);
    ofm_platform::logging::install_panic_hook(&log_path);
    log::info!("DeepL-oFM starting; log file: {}", log_path.display());

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
    use ofm_platform::hotkeys::{run_hotkey_loop, HotkeyManager};
    use std::sync::mpsc::channel;

    if !HotkeyManager::is_supported() {
        controller.set_hotkey_message(
            "clipboard",
            Some("Global shortcuts are not available on this system.".to_string()),
        );
        return;
    }

    // `GlobalHotKeyManager` owns a message window and is neither `Send` nor
    // `Sync`, so it cannot be shared: one thread owns it and everything else
    // reaches it through a channel. Registration and polling happen on that
    // thread, which is also where the OS expects them.  The captures
    // themselves run on worker threads: a slow clipboard read or a panicking
    // conversion must never stop the loop that keeps the shortcuts alive.
    let (updates, changes) = channel::<(KeyCombo, KeyCombo)>();
    let settings = controller.state().settings;
    let _ = updates.send((settings.hot_key.clone(), settings.selection_hot_key.clone()));

    // Forward every settings change to the owning thread.
    let mut events = controller.subscribe();
    let watch_controller = Arc::clone(&controller);
    let settings_updates = updates.clone();
    tauri::async_runtime::spawn(async move {
        loop {
            match events.recv().await {
                Ok(AppEvent::Settings { .. }) => {
                    let settings = watch_controller.state().settings;
                    if settings_updates
                        .send((settings.hot_key.clone(), settings.selection_hot_key.clone()))
                        .is_err()
                    {
                        log::warn!("the hotkey thread is gone; shortcut changes cannot be applied");
                        break;
                    }
                }
                // A burst may overflow the channel; skipping one must not stop
                // the watcher, or shortcut changes would stop registering.
                Ok(_) => continue,
                Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                Err(tokio::sync::broadcast::error::RecvError::Closed) => {
                    log::warn!("the controller event stream closed; shortcut changes stop here");
                    break;
                }
            }
        }
    });

    let dispatch_controller = Arc::clone(&controller);
    let dispatch_app = app.clone();
    let report_controller = Arc::clone(&controller);
    let spawned = std::thread::Builder::new()
        .name("ofm-hotkeys-loop".to_string())
        .spawn(move || {
            log::info!("global hotkey thread started");
            let manager = HotkeyManager::new();

            // The loop returns only when the stop flag is set (tests); the
            // shell passes `None`, so reaching the line after it is itself a
            // bug worth an error line in the log.
            let exit = run_hotkey_loop(
                manager,
                &changes,
                move |action| {
                    // Capture before activating our own window.  "Translate
                    // selection" synthesises Ctrl+C into whatever is focused, so
                    // showing and focusing DeepL-oFM first would make the
                    // capture copy our own UI (or nothing).  The window is
                    // brought forward afterwards so the result is visible.
                    match action {
                        "clipboard" => dispatch_controller.translate_clipboard(),
                        "selection" => dispatch_controller.translate_selection(),
                        other => log::debug!("unhandled hotkey action: {other}"),
                    }
                    show_main_window(&dispatch_app);
                },
                move |action, combo, result| {
                    report_controller.set_hotkey_message(
                        action,
                        result
                            .err()
                            .map(|error| error.message_key.replace("%@", &combo.display())),
                    );
                },
                None,
            );
            log::error!(
                "global hotkey loop exited ({exit:?}); global shortcuts are no longer registered"
            );
        });

    if let Err(error) = spawned {
        log::error!("could not start the global hotkey thread: {error}");
        controller.set_hotkey_message(
            "clipboard",
            Some("Global shortcuts could not be started.".to_string()),
        );
        controller.set_hotkey_message(
            "selection",
            Some("Global shortcuts could not be started.".to_string()),
        );
    }
}

/// Show and focus the main window.
///
/// Shared by the tray menu and the tray left-click handler so the two cannot
/// drift apart.
fn show_main_window<R: tauri::Runtime>(app: &tauri::AppHandle<R>) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
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
    use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

    let show = MenuItem::with_id(app, "show", "Show DeepL-oFM", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit DeepL-oFM", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    // The Windows convention - left click opens the window, right click opens
    // the menu - is not the macOS one: a menu-bar icon there is expected to
    // drop its menu on any click, which is what the Swift original does.  Linux
    // sits with macOS: libappindicator does not deliver click events at all, so
    // the menu is the only way in.
    let left_click_opens = cfg!(windows);

    let mut builder = TrayIconBuilder::with_id("main")
        .menu(&menu)
        .tooltip("DeepL-oFM")
        .show_menu_on_left_click(!left_click_opens)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => show_main_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            // `cfg!` is a compile-time literal, so the closure captures nothing;
            // a local `bool` here would have to live for 'static.
            if !cfg!(windows) {
                return;
            }
            // Windows reports both the press and the release; acting on both
            // would open the window twice per click.  A double click emits the
            // click pair first and then its own event, which is deliberately
            // ignored so the window cannot be shown and then hidden again.
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon() {
        builder = builder.icon(icon.clone());
    }

    builder.build(app)?;
    Ok(())
}
