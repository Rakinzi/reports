use std::{fs, path::PathBuf, sync::Mutex};

use reqwest::Client;
use serde::Serialize;
use tauri::{Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

const BACKEND_PORT: u16 = 38945;
const UI_VERSION_MARKER: &str = "ui-version.txt";
const MAX_BACKEND_OUTPUT_LINES: usize = 24;

#[derive(Clone, Serialize)]
struct BackendStartupStatus {
    state: String,
    pid: Option<u32>,
    exit_code: Option<i32>,
    message: Option<String>,
    recent_output: Vec<String>,
}

impl BackendStartupStatus {
    fn starting() -> Self {
        Self {
            state: "starting".into(),
            pid: None,
            exit_code: None,
            message: None,
            recent_output: Vec::new(),
        }
    }
}

struct BackendState {
    child: Mutex<Option<CommandChild>>,
    startup: Mutex<BackendStartupStatus>,
    url: String,
}

#[tauri::command]
fn get_backend_url(state: State<'_, BackendState>) -> String {
    state.url.clone()
}

#[tauri::command]
fn get_backend_startup_status(state: State<'_, BackendState>) -> BackendStartupStatus {
    state
        .startup
        .lock()
        .expect("backend startup mutex poisoned")
        .clone()
}

#[tauri::command]
async fn download_report(
    _app: tauri::AppHandle,
    backend_url: String,
    report_id: i64,
    target_path: String,
) -> Result<(), String> {
    let target = PathBuf::from(target_path);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }

    let url = format!("{backend_url}/reports/{report_id}/download");
    let bytes = Client::new()
        .get(url)
        .send()
        .await
        .map_err(|err| err.to_string())?
        .error_for_status()
        .map_err(|err| err.to_string())?
        .bytes()
        .await
        .map_err(|err| err.to_string())?;

    fs::write(target, bytes).map_err(|err| err.to_string())
}

fn spawn_backend(app: &tauri::AppHandle) -> Result<CommandChild, String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    let app_data_dir_str = app_data_dir.to_string_lossy().to_string();
    let mplconfig_dir = app_data_dir.join("mplconfig");
    let mplconfig_dir_str = mplconfig_dir.to_string_lossy().to_string();

    fs::create_dir_all(&app_data_dir).map_err(|err| err.to_string())?;
    fs::create_dir_all(&mplconfig_dir).map_err(|err| err.to_string())?;

    let command = app
        .shell()
        .sidecar("reports-api")
        .map_err(|err| err.to_string())?
        .env("REPORTS_APP_DATA_DIR", app_data_dir_str)
        .env("MPLCONFIGDIR", mplconfig_dir_str)
        .env("REPORTS_API_HOST", "127.0.0.1")
        .env("REPORTS_API_PORT", BACKEND_PORT.to_string());

    let (mut rx, child) = command.spawn().map_err(|err| err.to_string())?;
    let pid = child.pid();

    {
        let state = app.state::<BackendState>();
        let mut startup = state.startup.lock().map_err(|err| err.to_string())?;
        startup.state = "starting".into();
        startup.pid = Some(pid);
        startup.exit_code = None;
        startup.message = Some(format!(
            "Backend process started (pid {pid}). Waiting for health check..."
        ));
        startup.recent_output.clear();
    }

    let app_handle = app.clone();
    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            let state = app_handle.state::<BackendState>();
            let mut startup = match state.startup.lock() {
                Ok(guard) => guard,
                Err(_) => break,
            };

            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    let text = String::from_utf8_lossy(&line).trim().to_string();
                    if !text.is_empty() {
                        startup.recent_output.push(text);
                        if startup.recent_output.len() > MAX_BACKEND_OUTPUT_LINES {
                            let drop_count = startup.recent_output.len() - MAX_BACKEND_OUTPUT_LINES;
                            startup.recent_output.drain(0..drop_count);
                        }
                    }
                }
                CommandEvent::Error(error) => {
                    startup.state = "failed".into();
                    startup.message = Some(format!("Backend process error: {error}"));
                }
                CommandEvent::Terminated(payload) => {
                    startup.state = "failed".into();
                    startup.exit_code = payload.code;

                    let recent = startup
                        .recent_output
                        .iter()
                        .rev()
                        .find(|line| !line.is_empty())
                        .cloned();
                    startup.message = Some(match (payload.code, recent) {
                        (Some(code), Some(line)) => {
                            format!("Backend process exited with code {code}. Last output: {line}")
                        }
                        (Some(code), None) => format!("Backend process exited with code {code}."),
                        (None, Some(line)) => {
                            format!("Backend process terminated before startup completed. Last output: {line}")
                        }
                        (None, None) => {
                            "Backend process terminated before startup completed.".into()
                        }
                    });
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(child)
}

fn clear_stale_webview_data(app: &tauri::AppHandle) -> Result<(), String> {
    let app_data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
    fs::create_dir_all(&app_data_dir).map_err(|err| err.to_string())?;

    let current_version = app.package_info().version.to_string();
    let version_marker = app_data_dir.join(UI_VERSION_MARKER);
    let previous_version = fs::read_to_string(&version_marker)
        .ok()
        .map(|value| value.trim().to_string());

    if previous_version.as_deref() == Some(current_version.as_str()) {
        return Ok(());
    }

    if let Some(window) = app.get_webview_window("main") {
        window
            .clear_all_browsing_data()
            .map_err(|err| err.to_string())?;
    }

    if let Ok(cache_dir) = app.path().app_cache_dir() {
        let _ = fs::remove_dir_all(&cache_dir);
        let _ = fs::create_dir_all(&cache_dir);
    }

    fs::write(version_marker, current_version).map_err(|err| err.to_string())
}

pub fn run() {
    let backend_url = format!("http://127.0.0.1:{BACKEND_PORT}");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState {
            child: Mutex::new(None),
            startup: Mutex::new(BackendStartupStatus::starting()),
            url: backend_url,
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_backend_startup_status,
            download_report
        ])
        .setup(|app| {
            clear_stale_webview_data(app.handle())?;
            let child = spawn_backend(app.handle())?;
            let state = app.state::<BackendState>();
            let mut guard = state.child.lock().map_err(|err| err.to_string())?;
            *guard = Some(child);
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            let child = {
                let state = app_handle.state::<BackendState>();
                let mut guard = state.child.lock().expect("backend child mutex poisoned");
                guard.take()
            };

            if let Some(child) = child {
                let _ = child.kill();
            }
        }
    });
}
