use std::{
    path::PathBuf,
    sync::{Arc, Mutex, MutexGuard},
    time::Duration,
};

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Manager, RunEvent, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};
use uuid::Uuid;

mod licensing;

const READY_PREFIX: &str = "STARBRIDGE_READY ";
const APP_DATA_ENV: &str = "STARBRIDGE_APP_DATA_DIR";
const SESSION_ENV: &str = "STARBRIDGE_SESSION_TOKEN";
const SESSION_HEADER: &str = "X-StarBridge-Session";
const MAX_RECOVERY_ATTEMPTS: u8 = 1;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(15);
const RECOVERY_BACKOFF: Duration = Duration::from_millis(1200);

#[derive(Clone, Copy, Default, Serialize)]
#[serde(rename_all = "snake_case")]
enum RuntimePhase {
    #[default]
    Starting,
    Connected,
    Offline,
    Recovering,
    Failed,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    state: RuntimePhase,
    message: String,
    backend_pid: Option<u32>,
    port: Option<u16>,
    recovery_attempts: u8,
    technical_details: Option<String>,
}

struct RuntimeInner {
    phase: RuntimePhase,
    message: String,
    backend_pid: Option<u32>,
    port: Option<u16>,
    session_credential: Option<String>,
    recovery_attempts: u8,
    technical_details: Option<String>,
    child: Option<CommandChild>,
    desired_stop: bool,
    shutdown_in_progress: bool,
    supervisor_running: bool,
    generation: u64,
}

impl Default for RuntimeInner {
    fn default() -> Self {
        Self {
            phase: RuntimePhase::Starting,
            message: "正在准备本地安全服务。".into(),
            backend_pid: None,
            port: None,
            session_credential: None,
            recovery_attempts: 0,
            technical_details: None,
            child: None,
            desired_stop: false,
            shutdown_in_progress: false,
            supervisor_running: false,
            generation: 0,
        }
    }
}

#[derive(Clone, Default)]
struct BackendManager {
    inner: Arc<Mutex<RuntimeInner>>,
}

impl BackendManager {
    fn lock(&self) -> MutexGuard<'_, RuntimeInner> {
        self.inner
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    fn snapshot(&self) -> RuntimeStatus {
        let inner = self.lock();
        RuntimeStatus {
            state: inner.phase,
            message: inner.message.clone(),
            backend_pid: inner.backend_pid,
            port: inner.port,
            recovery_attempts: inner.recovery_attempts,
            technical_details: inner.technical_details.clone(),
        }
    }

    fn begin_app_shutdown(&self) -> bool {
        let mut inner = self.lock();
        if inner.shutdown_in_progress {
            return false;
        }
        inner.shutdown_in_progress = true;
        inner.desired_stop = true;
        true
    }
}

#[derive(Deserialize)]
struct ReadyMessage {
    port: u16,
    pid: u32,
    host: String,
    session_required: bool,
}

#[derive(Deserialize)]
struct ApiRequest {
    method: String,
    path: String,
    body: Option<Value>,
}

#[derive(Serialize)]
struct ApiResponse {
    status: u16,
    body: Value,
}

#[derive(Serialize)]
struct VersionInfo {
    desktop: &'static str,
    backend: Option<String>,
}

enum ProcessOutcome {
    RequestedStop,
    UnexpectedExit(&'static str),
}

fn set_phase(
    manager: &BackendManager,
    generation: u64,
    phase: RuntimePhase,
    message: &str,
    technical_details: Option<&str>,
) {
    let mut inner = manager.lock();
    if inner.generation != generation {
        return;
    }
    inner.phase = phase;
    inner.message = message.into();
    inner.technical_details = technical_details.map(str::to_owned);
}

fn parse_ready(bytes: &[u8]) -> Option<ReadyMessage> {
    let text = String::from_utf8_lossy(bytes);
    let payload = text.trim().strip_prefix(READY_PREFIX)?;
    serde_json::from_str(payload).ok()
}

fn take_and_kill_child(manager: &BackendManager) {
    let child = manager.lock().child.take();
    if let Some(child) = child {
        let _ = child.kill();
    }
}

async fn run_backend_once(
    app: &AppHandle,
    manager: &BackendManager,
    generation: u64,
) -> ProcessOutcome {
    let session_credential = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    let parent_pid = std::process::id().to_string();
    let command = match app.shell().sidecar("starbridge-sidecar") {
        Ok(command) => command,
        Err(_) => return ProcessOutcome::UnexpectedExit("sidecar_not_staged"),
    }
    .args(["--desktop", "--parent-pid", parent_pid.as_str()])
    .env(SESSION_ENV, &session_credential);

    let (mut events, child) = match command.spawn() {
        Ok(process) => process,
        Err(_) => return ProcessOutcome::UnexpectedExit("sidecar_spawn_failed"),
    };
    let child_pid = child.pid();
    {
        let mut inner = manager.lock();
        if inner.generation != generation {
            let _ = child.kill();
            return ProcessOutcome::RequestedStop;
        }
        inner.child = Some(child);
        inner.backend_pid = Some(child_pid);
        inner.port = None;
        inner.session_credential = Some(session_credential);
        inner.technical_details = None;
    }

    let ready = loop {
        let event = match tokio::time::timeout(STARTUP_TIMEOUT, events.recv()).await {
            Ok(Some(event)) => event,
            Ok(None) => {
                take_and_kill_child(manager);
                return ProcessOutcome::UnexpectedExit("sidecar_event_stream_closed");
            }
            Err(_) => {
                take_and_kill_child(manager);
                return ProcessOutcome::UnexpectedExit("sidecar_startup_timeout");
            }
        };
        match event {
            CommandEvent::Stdout(bytes) => {
                if let Some(ready) = parse_ready(&bytes) {
                    break ready;
                }
            }
            CommandEvent::Terminated(_) => {
                let requested = manager.lock().desired_stop;
                return if requested {
                    ProcessOutcome::RequestedStop
                } else {
                    ProcessOutcome::UnexpectedExit("sidecar_exited_before_ready")
                };
            }
            CommandEvent::Error(_) => {
                return ProcessOutcome::UnexpectedExit("sidecar_stream_error");
            }
            _ => {}
        }
    };

    if ready.host != "127.0.0.1" || !ready.session_required || ready.pid != child_pid {
        take_and_kill_child(manager);
        return ProcessOutcome::UnexpectedExit("sidecar_ready_validation_failed");
    }
    {
        let mut inner = manager.lock();
        if inner.generation != generation {
            drop(inner);
            take_and_kill_child(manager);
            return ProcessOutcome::RequestedStop;
        }
        inner.phase = RuntimePhase::Connected;
        inner.message = "本地安全服务已连接。".into();
        inner.port = Some(ready.port);
        inner.backend_pid = Some(ready.pid);
        inner.technical_details = None;
    }

    while let Some(event) = events.recv().await {
        match event {
            CommandEvent::Terminated(_) => {
                let mut inner = manager.lock();
                if inner.generation != generation {
                    return ProcessOutcome::RequestedStop;
                }
                inner.child = None;
                inner.port = None;
                inner.backend_pid = None;
                inner.session_credential = None;
                return if inner.desired_stop {
                    ProcessOutcome::RequestedStop
                } else {
                    ProcessOutcome::UnexpectedExit("sidecar_exited_unexpectedly")
                };
            }
            CommandEvent::Error(_) => {
                return ProcessOutcome::UnexpectedExit("sidecar_stream_error");
            }
            _ => {}
        }
    }
    ProcessOutcome::UnexpectedExit("sidecar_event_stream_closed")
}

fn start_supervisor(app: AppHandle, manager: BackendManager, reset_recovery: bool) {
    let generation = {
        let mut inner = manager.lock();
        inner.generation = inner.generation.saturating_add(1);
        inner.supervisor_running = true;
        inner.desired_stop = false;
        inner.shutdown_in_progress = false;
        if reset_recovery {
            inner.recovery_attempts = 0;
        }
        inner.phase = RuntimePhase::Starting;
        inner.message = "正在准备本地安全服务。".into();
        inner.technical_details = None;
        inner.generation
    };

    tauri::async_runtime::spawn(async move {
        loop {
            let outcome = run_backend_once(&app, &manager, generation).await;
            if manager.lock().generation != generation {
                return;
            }
            match outcome {
                ProcessOutcome::RequestedStop => {
                    let mut inner = manager.lock();
                    inner.phase = RuntimePhase::Offline;
                    inner.message = "本地服务已停止。".into();
                    inner.supervisor_running = false;
                    inner.child = None;
                    return;
                }
                ProcessOutcome::UnexpectedExit(code) => {
                    record_runtime_diagnostic(&app, code);
                    let should_recover = {
                        let mut inner = manager.lock();
                        inner.child = None;
                        inner.port = None;
                        inner.backend_pid = None;
                        inner.session_credential = None;
                        if !inner.desired_stop && inner.recovery_attempts < MAX_RECOVERY_ATTEMPTS {
                            inner.recovery_attempts += 1;
                            inner.phase = RuntimePhase::Recovering;
                            inner.message = "本地服务异常退出，正在进行一次有限恢复。".into();
                            inner.technical_details = Some(code.into());
                            true
                        } else {
                            inner.phase = RuntimePhase::Failed;
                            inner.message = "本地服务未能恢复，请查看诊断信息。".into();
                            inner.technical_details = Some(code.into());
                            inner.supervisor_running = false;
                            false
                        }
                    };
                    if !should_recover {
                        return;
                    }
                    tokio::time::sleep(RECOVERY_BACKOFF).await;
                    set_phase(
                        &manager,
                        generation,
                        RuntimePhase::Starting,
                        "正在重新启动本地安全服务。",
                        None,
                    );
                }
            }
        }
    });
}

fn loopback_client() -> Result<reqwest::Client, &'static str> {
    reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(10))
        .build()
        .map_err(|_| "loopback_client_failed")
}

fn p1_request_allowed(request: &ApiRequest) -> bool {
    if request.method != "GET" || request.body.is_some() {
        return false;
    }
    if !request.path.starts_with("/api/")
        || request.path.contains("..")
        || request.path.contains('%')
        || request.path.contains('#')
    {
        return false;
    }
    const SAFE_ROUTES: &[&str] = &[
        "/api/health",
        "/api/bootstrap",
        "/api/status",
        "/api/capabilities",
        "/api/tools",
        "/api/resources",
        "/api/recipes",
        "/api/catalog",
        "/api/tiers",
        "/api/hybrid",
        "/api/audit/history",
    ];
    SAFE_ROUTES
        .iter()
        .any(|route| request.path == *route || request.path.starts_with(&format!("{route}?")))
}

#[tauri::command]
fn backend_status(manager: State<'_, BackendManager>) -> RuntimeStatus {
    manager.snapshot()
}

#[tauri::command]
async fn backend_request(
    request: ApiRequest,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !p1_request_allowed(&request) {
        return Err("P1 桌面代理只允许读取状态与安全启动数据。".into());
    }
    let (port, session_credential) = {
        let inner = manager.lock();
        if !matches!(inner.phase, RuntimePhase::Connected) {
            return Err("本地服务尚未连接。".into());
        }
        (
            inner.port.ok_or("本地服务端口尚未就绪。")?,
            inner
                .session_credential
                .clone()
                .ok_or("桌面会话尚未就绪。")?,
        )
    };
    let client = loopback_client().map_err(str::to_owned)?;
    let url = format!("http://127.0.0.1:{port}{}", request.path);
    let response = client
        .get(url)
        .header(SESSION_HEADER, session_credential)
        .send()
        .await
        .map_err(|_| "本地服务没有响应。".to_string())?;
    let status = response.status().as_u16();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "无法读取本地服务响应。".to_string())?;
    if bytes.len() > 2 * 1024 * 1024 {
        return Err("本地服务响应超过桌面端允许的大小。".into());
    }
    let body =
        serde_json::from_slice(&bytes).map_err(|_| "本地服务返回了无法识别的结果。".to_string())?;
    Ok(ApiResponse { status, body })
}

async fn request_graceful_stop(manager: &BackendManager) {
    let connection = {
        let mut inner = manager.lock();
        inner.desired_stop = true;
        inner
            .port
            .zip(inner.session_credential.clone())
            .map(|(port, credential)| (port, credential))
    };
    if let Some((port, session_credential)) = connection {
        if let Ok(client) = loopback_client() {
            let _ = client
                .post(format!("http://127.0.0.1:{port}/api/lifecycle/shutdown"))
                .header(SESSION_HEADER, session_credential)
                .json(&serde_json::json!({}))
                .send()
                .await;
        }
    }
    for _ in 0..20 {
        if manager.lock().child.is_none() {
            return;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    take_and_kill_child(manager);
}

#[tauri::command]
async fn restart_backend(
    app: AppHandle,
    manager: State<'_, BackendManager>,
) -> Result<RuntimeStatus, String> {
    request_graceful_stop(&manager).await;
    start_supervisor(app, manager.inner().clone(), true);
    Ok(manager.snapshot())
}

fn starbridge_data_root(app: &AppHandle) -> Result<PathBuf, String> {
    if let Some(configured) = std::env::var_os(APP_DATA_ENV) {
        let configured = PathBuf::from(configured);
        return if configured.is_absolute() {
            Ok(configured)
        } else {
            std::env::current_dir()
                .map(|current| current.join(configured))
                .map_err(|_| "无法确定 StarBridge 应用数据目录。".to_string())
        };
    }
    if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA") {
        return Ok(PathBuf::from(local_app_data).join("StarBridge"));
    }
    app.path()
        .app_local_data_dir()
        .map_err(|_| "无法确定 StarBridge 应用数据目录。".to_string())
}

fn record_runtime_diagnostic(app: &AppHandle, code: &str) {
    let Ok(root) = starbridge_data_root(app) else {
        return;
    };
    let diagnostics = root.join("diagnostics");
    if std::fs::create_dir_all(&diagnostics).is_err() {
        return;
    }
    let payload = serde_json::json!({
        "event": "sidecar_exit",
        "code": code,
        "summary": "StarBridge local service exited unexpectedly.",
        "contains_traceback": false,
        "contains_session_credential": false
    });
    let target = diagnostics.join(format!("sidecar-{}.json", Uuid::new_v4().simple()));
    if let Ok(mut encoded) = serde_json::to_vec_pretty(&payload) {
        encoded.push(b'\n');
        let _ = std::fs::write(target, encoded);
    }
}

#[tauri::command]
fn open_logs_directory(app: AppHandle) -> Result<String, String> {
    let logs = starbridge_data_root(&app)?.join("logs");
    std::fs::create_dir_all(&logs).map_err(|_| "无法准备日志目录。".to_string())?;
    open::that(logs).map_err(|_| "无法打开日志目录。".to_string())?;
    Ok("<LOCAL_APP_DATA>/StarBridge/logs".into())
}

#[tauri::command]
fn version_info() -> VersionInfo {
    VersionInfo {
        desktop: env!("CARGO_PKG_VERSION"),
        backend: Some("0.1.0".into()),
    }
}

#[tauri::command]
fn license_status(app: AppHandle) -> Result<licensing::LicenseStatus, String> {
    let root = starbridge_data_root(&app)?;
    Ok(licensing::installed_status(&root))
}

#[tauri::command]
fn create_license_request(app: AppHandle) -> Result<licensing::LicenseRequestReceipt, String> {
    let root = starbridge_data_root(&app)?;
    let (mut receipt, directory) = licensing::create_request(&root, env!("CARGO_PKG_VERSION"))?;
    if open::that(directory).is_ok() {
        licensing::mark_folder_opened(&mut receipt);
    }
    Ok(receipt)
}

#[tauri::command]
fn import_license_file(
    app: AppHandle,
    contents: String,
) -> Result<licensing::LicenseStatus, String> {
    let root = starbridge_data_root(&app)?;
    licensing::import_license(&root, &contents)
}

pub fn run() {
    let manager = BackendManager::default();
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .manage(manager.clone())
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_request,
            restart_backend,
            open_logs_directory,
            version_info,
            license_status,
            create_license_request,
            import_license_file
        ])
        .setup({
            let manager = manager.clone();
            move |app| {
                start_supervisor(app.handle().clone(), manager, true);
                Ok(())
            }
        })
        .build(tauri::generate_context!())
        .expect("StarBridge Desktop could not initialize");

    app.run(move |app_handle, event| {
        if let RunEvent::ExitRequested { api, code, .. } = event {
            if code.is_none() {
                api.prevent_exit();
                let manager = app_handle.state::<BackendManager>().inner().clone();
                if manager.begin_app_shutdown() {
                    let app_handle = app_handle.clone();
                    tauri::async_runtime::spawn(async move {
                        request_graceful_stop(&manager).await;
                        app_handle.exit(0);
                    });
                }
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(method: &str, path: &str, body: Option<Value>) -> ApiRequest {
        ApiRequest {
            method: method.into(),
            path: path.into(),
            body,
        }
    }

    #[test]
    fn p1_proxy_allows_only_read_only_routes() {
        assert!(p1_request_allowed(&request("GET", "/api/bootstrap", None)));
        assert!(p1_request_allowed(&request(
            "GET",
            "/api/recipes?bridge=all",
            None
        )));
        assert!(!p1_request_allowed(&request(
            "POST",
            "/api/bootstrap",
            Some(serde_json::json!({}))
        )));
        assert!(!p1_request_allowed(&request("GET", "/api/run", None)));
    }

    #[test]
    fn p1_proxy_rejects_encoded_or_traversal_paths() {
        for path in [
            "/api/../bootstrap",
            "/api/%2e%2e/bootstrap",
            "/api/bootstrap#fragment",
        ] {
            assert!(!p1_request_allowed(&request("GET", path, None)), "{path}");
        }
    }

    #[test]
    fn ready_message_parser_requires_the_protocol_prefix() {
        let ready = parse_ready(
            br#"STARBRIDGE_READY {"port":49152,"pid":1234,"host":"127.0.0.1","session_required":true}"#,
        )
        .expect("valid readiness message");
        assert_eq!(ready.port, 49152);
        assert_eq!(ready.pid, 1234);
        assert_eq!(ready.host, "127.0.0.1");
        assert!(ready.session_required);
        assert!(parse_ready(br#"{"port":49152}"#).is_none());
    }
}
