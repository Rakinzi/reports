use std::{
    fs,
    path::PathBuf,
    sync::Mutex,
};

use reqwest::Client;
use tauri::{Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

const BACKEND_PORT: u16 = 38945;

struct BackendState {
    child: Mutex<Option<CommandChild>>,
    url: String,
}

#[tauri::command]
fn get_backend_url(state: State<'_, BackendState>) -> String {
    state.url.clone()
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
    let app_data_dir = app
        .path()
        .app_data_dir()
        .map_err(|err| err.to_string())?;
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

    let (_rx, child) = command.spawn().map_err(|err| err.to_string())?;
    Ok(child)
}

pub fn run() {
    let backend_url = format!("http://127.0.0.1:{BACKEND_PORT}");

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BackendState {
            child: Mutex::new(None),
            url: backend_url,
        })
        .invoke_handler(tauri::generate_handler![get_backend_url, download_report])
        .setup(|app| {
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
