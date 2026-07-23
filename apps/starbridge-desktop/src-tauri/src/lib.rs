use std::{
    net::{Ipv4Addr, SocketAddrV4, TcpListener},
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

mod adobe_export;
mod licensing;
mod updater;

const READY_PREFIX: &str = "STARBRIDGE_READY ";
const APP_DATA_ENV: &str = "STARBRIDGE_APP_DATA_DIR";
const SESSION_ENV: &str = "STARBRIDGE_SESSION_TOKEN";
const SESSION_HEADER: &str = "X-KORYAO-Session";
const MAX_RECOVERY_ATTEMPTS: u8 = 1;
const STARTUP_TIMEOUT: Duration = Duration::from_secs(15);
const MAX_READY_BUFFER_BYTES: usize = 64 * 1024;
const RECOVERY_BACKOFF: Duration = Duration::from_millis(1200);
const MAX_TYPED_RESPONSE_BYTES: usize = 12 * 1024 * 1024;
const MAX_VECTOR_PARAMETERS_BYTES: usize = 4 * 1024;

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

#[derive(Default)]
struct ReadyStreamDecoder {
    buffer: Vec<u8>,
}

impl ReadyStreamDecoder {
    fn push(&mut self, chunk: &[u8]) -> Result<Option<ReadyMessage>, ()> {
        if self.buffer.len().saturating_add(chunk.len()) > MAX_READY_BUFFER_BYTES {
            return Err(());
        }
        self.buffer.extend_from_slice(chunk);

        while let Some(newline) = self.buffer.iter().position(|byte| *byte == b'\n') {
            let line: Vec<u8> = self.buffer.drain(..=newline).collect();
            if let Some(ready) = parse_ready(&line) {
                return Ok(Some(ready));
            }
        }

        Ok(parse_ready(&self.buffer))
    }
}

fn take_and_kill_child(manager: &BackendManager) {
    let child = manager.lock().child.take();
    if let Some(child) = child {
        let _ = child.kill();
    }
}

fn select_loopback_port() -> Result<u16, &'static str> {
    let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0))
        .map_err(|_| "loopback_port_unavailable")?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|_| "loopback_port_unavailable")
}

async fn authenticated_startup_probe(port: u16, session_credential: &str) -> bool {
    let client = match reqwest::Client::builder()
        .no_proxy()
        .connect_timeout(Duration::from_millis(250))
        .timeout(Duration::from_millis(500))
        .build()
    {
        Ok(client) => client,
        Err(_) => return false,
    };
    client
        .get(format!("http://127.0.0.1:{port}/api/bootstrap"))
        .header(SESSION_HEADER, session_credential)
        .send()
        .await
        .is_ok_and(|response| response.status().is_success())
}

async fn run_backend_once(
    app: &AppHandle,
    manager: &BackendManager,
    generation: u64,
) -> ProcessOutcome {
    let session_credential = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    let parent_pid = std::process::id().to_string();
    let requested_port = match select_loopback_port() {
        Ok(port) => port,
        Err(code) => return ProcessOutcome::UnexpectedExit(code),
    };
    let requested_port_text = requested_port.to_string();
    let app_data_root = match starbridge_data_root(app) {
        Ok(path) => path,
        Err(_) => return ProcessOutcome::UnexpectedExit("app_data_root_unavailable"),
    };
    let command = match app.shell().sidecar("starbridge-sidecar") {
        Ok(command) => command,
        Err(_) => return ProcessOutcome::UnexpectedExit("sidecar_not_staged"),
    }
    .args([
        "--desktop",
        "--parent-pid",
        parent_pid.as_str(),
        "--port",
        requested_port_text.as_str(),
    ])
    .env(SESSION_ENV, &session_credential)
    .env(APP_DATA_ENV, app_data_root.as_os_str());

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
        inner.session_credential = Some(session_credential.clone());
        inner.technical_details = None;
    }

    let mut ready_decoder = ReadyStreamDecoder::default();
    let startup_deadline = tokio::time::Instant::now() + STARTUP_TIMEOUT;
    let ready = loop {
        let now = tokio::time::Instant::now();
        if now >= startup_deadline {
            take_and_kill_child(manager);
            return ProcessOutcome::UnexpectedExit("sidecar_startup_timeout");
        }
        let poll_window = std::cmp::min(
            Duration::from_millis(200),
            startup_deadline.saturating_duration_since(now),
        );
        let event = match tokio::time::timeout(poll_window, events.recv()).await {
            Ok(Some(event)) => Some(event),
            Ok(None) => {
                take_and_kill_child(manager);
                return ProcessOutcome::UnexpectedExit("sidecar_event_stream_closed");
            }
            Err(_) => None,
        };
        match event {
            Some(CommandEvent::Stdout(bytes)) => match ready_decoder.push(&bytes) {
                Ok(Some(ready)) => break ready,
                Ok(None) => {}
                Err(()) => {
                    take_and_kill_child(manager);
                    return ProcessOutcome::UnexpectedExit("sidecar_ready_buffer_overflow");
                }
            },
            Some(CommandEvent::Terminated(_)) => {
                let requested = manager.lock().desired_stop;
                return if requested {
                    ProcessOutcome::RequestedStop
                } else {
                    ProcessOutcome::UnexpectedExit("sidecar_exited_before_ready")
                };
            }
            Some(CommandEvent::Error(_)) => {
                return ProcessOutcome::UnexpectedExit("sidecar_stream_error");
            }
            _ => {}
        }
        if authenticated_startup_probe(requested_port, &session_credential).await {
            break ReadyMessage {
                port: requested_port,
                pid: child_pid,
                host: "127.0.0.1".into(),
                session_required: true,
            };
        }
    };

    if ready.host != "127.0.0.1"
        || !ready.session_required
        || ready.pid != child_pid
        || ready.port != requested_port
    {
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
        "/api/connections",
        "/api/model/status",
        "/api/status",
        "/api/capabilities",
        "/api/tools",
        "/api/resources",
        "/api/recipes",
        "/api/catalog",
        "/api/tiers",
        "/api/hybrid",
        "/api/audit/history",
        "/api/workflows",
        "/api/projects",
        "/api/jobs",
    ];
    if request.method == "GET" && request.body.is_none() {
        if SAFE_ROUTES
            .iter()
            .any(|route| request.path == *route || request.path.starts_with(&format!("{route}?")))
        {
            return true;
        }
        let parts: Vec<&str> = request.path.trim_matches('/').split('/').collect();
        return matches!(parts.as_slice(), ["api", "projects", id] if valid_vector_id(id, "project-"))
            || matches!(parts.as_slice(), ["api", "projects", id, "delivery"] if valid_vector_id(id, "project-"))
            || matches!(parts.as_slice(), ["api", "jobs", id] if valid_vector_id(id, "job-"))
            || matches!(parts.as_slice(), ["api", "jobs", id, "events"] if valid_vector_id(id, "job-"));
    }
    if request.method == "POST" && request.body.as_ref().is_some_and(Value::is_object) {
        if matches!(request.path.as_str(), "/api/projects" | "/api/jobs") {
            return true;
        }
        if matches!(
            request.path.as_str(),
            "/api/model/plan" | "/api/model/evaluate" | "/api/model/repair"
        ) {
            return true;
        }
        let parts: Vec<&str> = request.path.trim_matches('/').split('/').collect();
        return matches!(parts.as_slice(), ["api", "jobs", id, action]
            if valid_vector_id(id, "job-") && matches!(*action, "run" | "cancel"));
    }
    false
}

fn backend_connection(manager: &BackendManager) -> Result<(u16, String), String> {
    let inner = manager.lock();
    if !matches!(inner.phase, RuntimePhase::Connected) {
        return Err("本地服务尚未连接；请稍后重试或在设置与诊断中重新启动。".into());
    }
    Ok((
        inner.port.ok_or("本地服务端口尚未就绪。")?,
        inner
            .session_credential
            .clone()
            .ok_or("桌面会话尚未就绪。")?,
    ))
}

async fn call_backend_json(
    manager: &BackendManager,
    method: &str,
    path: &str,
    body: Option<Value>,
) -> Result<ApiResponse, String> {
    let (port, session_credential) = backend_connection(manager)?;
    let client = loopback_client().map_err(str::to_owned)?;
    let url = format!("http://127.0.0.1:{port}{path}");
    let mut request = match method {
        "GET" => client.get(url),
        "POST" => client.post(url),
        _ => return Err("桌面命令使用了不受支持的本机请求方式。".into()),
    }
    .header(SESSION_HEADER, session_credential);
    if let Some(payload) = body {
        request = request.json(&payload);
    }
    let response = request
        .send()
        .await
        .map_err(|_| "本地服务没有响应；请在设置与诊断中重新启动后再试。".to_string())?;
    let status = response.status().as_u16();
    let bytes = response
        .bytes()
        .await
        .map_err(|_| "无法读取本地服务响应；请重新运行本次任务。".to_string())?;
    if bytes.len() > MAX_TYPED_RESPONSE_BYTES {
        return Err("本地预览超过桌面端允许的大小；请缩小图片后重试。".into());
    }
    let body = serde_json::from_slice(&bytes)
        .map_err(|_| "本地服务返回了无法识别的结果；请查看技术详情。".to_string())?;
    Ok(ApiResponse { status, body })
}

fn valid_vector_id(value: &str, prefix: &str) -> bool {
    value.len() <= 80
        && value.starts_with(prefix)
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
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
        return Err("桌面代理拒绝了未列入白名单的本机请求。".into());
    }
    call_backend_json(&manager, &request.method, &request.path, request.body).await
}

#[tauri::command]
async fn install_codex_connector(
    confirm_install: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    call_backend_json(
        &manager,
        "POST",
        "/api/connections/codex/install",
        Some(serde_json::json!({ "confirm_install": confirm_install })),
    )
    .await
}

#[tauri::command]
async fn reset_codex_connection(
    confirm_reset: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    call_backend_json(
        &manager,
        "POST",
        "/api/connections/codex/reset",
        Some(serde_json::json!({ "confirm_reset": confirm_reset })),
    )
    .await
}

fn valid_creative_application_id(application_id: &str) -> bool {
    matches!(
        application_id,
        "photoshop" | "illustrator" | "comfyui" | "autocad" | "blender" | "jianying_capcut"
    )
}

#[tauri::command]
async fn pair_creative_application(
    application_id: String,
    confirm_pairing: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_creative_application_id(&application_id) {
        return Err("软件配对标识无效；请从连接中心重新选择。".into());
    }
    call_backend_json(
        &manager,
        "POST",
        "/api/connections/applications/pair",
        Some(serde_json::json!({
            "application_id": application_id,
            "confirm_pairing": confirm_pairing
        })),
    )
    .await
}

#[tauri::command]
async fn reconnect_creative_application(
    application_id: String,
    confirm_reconnect: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_creative_application_id(&application_id) {
        return Err("软件配对标识无效；请从连接中心重新选择。".into());
    }
    call_backend_json(
        &manager,
        "POST",
        "/api/connections/applications/reconnect",
        Some(serde_json::json!({
            "application_id": application_id,
            "confirm_reconnect": confirm_reconnect
        })),
    )
    .await
}

#[tauri::command]
async fn disconnect_creative_application(
    application_id: String,
    confirm_disconnect: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_creative_application_id(&application_id) {
        return Err("软件配对标识无效；请从连接中心重新选择。".into());
    }
    call_backend_json(
        &manager,
        "POST",
        "/api/connections/applications/disconnect",
        Some(serde_json::json!({
            "application_id": application_id,
            "confirm_disconnect": confirm_disconnect
        })),
    )
    .await
}

#[tauri::command]
fn open_codex_pairing(pairing_code: String) -> Result<(), String> {
    let valid = pairing_code.len() == 8
        && pairing_code
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || matches!(byte, b'2'..=b'9'));
    if !valid {
        return Err("配对码无效；请在连接中心重新生成。".into());
    }
    let prompt = format!(
        "请调用 KORYAO MCP 工具 starbridge.desktop_pair，参数 pairing_code=\"{pairing_code}\"、dry_run=false、confirm_pairing=true、confirm_write=true。完成后告诉我关联结果；不要读取或输出任何 Codex 登录凭据。"
    );
    let mut link = url::Url::parse("codex://new").map_err(|_| "无法创建 Codex 深链接。")?;
    link.query_pairs_mut().append_pair("prompt", &prompt);
    open::that(link.as_str()).map_err(|_| {
        "无法打开 Codex；请确认 Codex 已安装，然后复制连接中心的配对指令。".to_string()
    })
}

fn valid_codex_prompt(prompt: &str) -> bool {
    let trimmed = prompt.trim();
    !trimmed.is_empty()
        && trimmed.len() <= 4000
        && !trimmed.chars().any(|character| character == '\0')
}

#[tauri::command]
fn open_codex_task(prompt: String, confirm_open: bool) -> Result<(), String> {
    if !confirm_open {
        return Err("打开 Codex 对话前需要明确确认。".into());
    }
    if !valid_codex_prompt(&prompt) {
        return Err("Codex 指令不能为空，且不能超过 4000 字节。".into());
    }
    let mut link =
        url::Url::parse("codex://new").map_err(|_| "无法创建 Codex 对话链接。".to_string())?;
    link.query_pairs_mut().append_pair("prompt", prompt.trim());
    open::that(link.as_str()).map_err(|_| {
        "无法打开 Codex；请确认 Codex 已安装，并从连接中心完成本次会话关联。".to_string()
    })
}

const GITHUB_PROJECT_URL: &str = "https://github.com/jianbaorui07-dot/KORYAO-basic";

#[tauri::command]
fn open_github_project() -> Result<(), String> {
    let target = url::Url::parse(GITHUB_PROJECT_URL)
        .map_err(|_| "KORYAO GitHub 项目地址无效。".to_string())?;
    if target.scheme() != "https" || target.host_str() != Some("github.com") {
        return Err("KORYAO GitHub 项目地址未通过安全检查。".into());
    }
    open::that(target.as_str()).map_err(|_| "无法打开浏览器；请稍后重试。".to_string())
}

#[tauri::command]
async fn choose_vector_input(
    manager: State<'_, BackendManager>,
) -> Result<Option<ApiResponse>, String> {
    let selected = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .add_filter("图片", &["png", "jpg", "jpeg"])
            .set_title("选择一张要矢量化的图片")
            .pick_file()
    })
    .await
    .map_err(|_| "无法打开文件选择窗口；请重新尝试。".to_string())?;
    let Some(path) = selected else {
        return Ok(None);
    };
    let response = call_backend_json(
        &manager,
        "POST",
        "/api/vectorization/selections",
        Some(serde_json::json!({ "input_path": path.to_string_lossy() })),
    )
    .await?;
    Ok(Some(response))
}

#[tauri::command]
async fn import_project_asset(
    project_id: String,
    confirm_import: bool,
    manager: State<'_, BackendManager>,
) -> Result<Option<ApiResponse>, String> {
    if !valid_vector_id(&project_id, "project-") {
        return Err("项目编号无效；请返回项目页后重试。".into());
    }
    if !confirm_import {
        return Err("复制素材到 KORYAO 项目目录前需要明确确认。".into());
    }
    let selected = tauri::async_runtime::spawn_blocking(|| {
        rfd::FileDialog::new()
            .add_filter("图片", &["png", "jpg", "jpeg"])
            .set_title("选择一张要导入项目的图片")
            .pick_file()
    })
    .await
    .map_err(|_| "无法打开文件选择窗口；请重新尝试。".to_string())?;
    let Some(path) = selected else {
        return Ok(None);
    };
    let response = call_backend_json(
        &manager,
        "POST",
        &format!("/api/projects/{project_id}/assets"),
        Some(serde_json::json!({
            "inputPath": path.to_string_lossy(),
            "confirmImport": true
        })),
    )
    .await?;
    Ok(Some(response))
}

#[tauri::command]
async fn start_vectorization(
    selection_id: String,
    mode: String,
    parameters: Value,
    confirm_run: bool,
    confirm_write: bool,
    confirm_export: bool,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_vector_id(&selection_id, "selection-") {
        return Err("所选图片会话无效；请重新选择图片。".into());
    }
    if !matches!(mode.as_str(), "artisan" | "smart" | "lightweight" | "exact") {
        return Err("请选择可用的 Community 矢量模式。".into());
    }
    if !parameters.is_object()
        || serde_json::to_vec(&parameters)
            .map_or(true, |value| value.len() > MAX_VECTOR_PARAMETERS_BYTES)
    {
        return Err("处理参数无效；请恢复默认参数后重试。".into());
    }
    call_backend_json(
        &manager,
        "POST",
        "/api/vectorization/jobs",
        Some(serde_json::json!({
            "selection_id": selection_id,
            "mode": mode,
            "parameters": parameters,
            "confirm_run": confirm_run,
            "confirm_write": confirm_write,
            "confirm_export": confirm_export
        })),
    )
    .await
}

#[tauri::command]
async fn vectorization_job(
    job_id: String,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_vector_id(&job_id, "vector-") {
        return Err("任务编号无效；请返回任务记录后重试。".into());
    }
    call_backend_json(
        &manager,
        "GET",
        &format!("/api/vectorization/jobs/{job_id}"),
        None,
    )
    .await
}

#[tauri::command]
async fn vectorization_history(manager: State<'_, BackendManager>) -> Result<ApiResponse, String> {
    call_backend_json(&manager, "GET", "/api/vectorization/history", None).await
}

#[tauri::command]
async fn open_vector_output(
    job_id: String,
    manager: State<'_, BackendManager>,
) -> Result<ApiResponse, String> {
    if !valid_vector_id(&job_id, "vector-") {
        return Err("任务编号无效；请返回任务记录后重试。".into());
    }
    call_backend_json(
        &manager,
        "POST",
        &format!("/api/vectorization/jobs/{job_id}/open-output"),
        Some(serde_json::json!({})),
    )
    .await
}

#[tauri::command]
fn open_project_artifacts(app: AppHandle, project_id: String) -> Result<String, String> {
    if !valid_vector_id(&project_id, "project-") {
        return Err("项目编号无效，请重新选择项目后再试。".into());
    }
    let artifacts_root = starbridge_data_root(&app)?.join("artifacts");
    let project_directory = artifacts_root.join(&project_id);
    if !project_directory.is_dir() {
        return Err("这个项目还没有可打开的真实交付目录。".into());
    }
    let resolved_root = artifacts_root
        .canonicalize()
        .map_err(|_| "无法验证项目交付根目录。".to_string())?;
    let resolved_directory = project_directory
        .canonicalize()
        .map_err(|_| "无法验证项目交付目录。".to_string())?;
    if resolved_directory == resolved_root || !resolved_directory.starts_with(&resolved_root) {
        return Err("项目交付目录超出 KORYAO 安全范围。".into());
    }
    open::that(resolved_directory)
        .map_err(|_| "无法打开项目交付目录，请从交付记录重试。".to_string())?;
    Ok(format!("<LOCAL_APP_DATA>/KORYAO/artifacts/{project_id}"))
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
                .map_err(|_| "无法确定 KORYAO 应用数据目录。".to_string())
        };
    }
    if let Some(local_app_data) = std::env::var_os("LOCALAPPDATA") {
        return Ok(PathBuf::from(local_app_data).join("KORYAO"));
    }
    app.path()
        .app_local_data_dir()
        .map_err(|_| "无法确定 KORYAO 应用数据目录。".to_string())
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
        "summary": "KORYAO local service exited unexpectedly.",
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
    Ok("<LOCAL_APP_DATA>/KORYAO/logs".into())
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
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(manager.clone())
        .manage(updater::PendingUpdate::default())
        .invoke_handler(tauri::generate_handler![
            backend_status,
            backend_request,
            install_codex_connector,
            reset_codex_connection,
            pair_creative_application,
            reconnect_creative_application,
            disconnect_creative_application,
            open_codex_pairing,
            open_codex_task,
            open_github_project,
            choose_vector_input,
            import_project_asset,
            start_vectorization,
            vectorization_job,
            vectorization_history,
            open_vector_output,
            open_project_artifacts,
            adobe_export::export_adobe_file,
            adobe_export::list_adobe_exports,
            restart_backend,
            open_logs_directory,
            version_info,
            license_status,
            create_license_request,
            import_license_file,
            updater::update_channel_status,
            updater::check_for_update,
            updater::install_update
        ])
        .setup({
            let manager = manager.clone();
            move |app| {
                start_supervisor(app.handle().clone(), manager, true);
                Ok(())
            }
        })
        .build(tauri::generate_context!())
        .expect("KORYAO Desktop could not initialize");

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
    fn p1_proxy_allows_product_reads_and_narrow_workflow_writes() {
        assert!(p1_request_allowed(&request("GET", "/api/bootstrap", None)));
        assert!(p1_request_allowed(&request(
            "GET",
            "/api/model/status",
            None
        )));
        assert!(p1_request_allowed(&request(
            "POST",
            "/api/model/plan",
            Some(serde_json::json!({"schema": "koryao-model-contract/v1"})),
        )));
        assert!(p1_request_allowed(&request(
            "GET",
            "/api/recipes?bridge=all",
            None
        )));
        assert!(p1_request_allowed(&request(
            "POST",
            "/api/projects",
            Some(serde_json::json!({}))
        )));
        assert!(p1_request_allowed(&request(
            "POST",
            "/api/jobs/job-123/run",
            Some(serde_json::json!({}))
        )));
        assert!(!p1_request_allowed(&request(
            "POST",
            "/api/projects/project-123/assets",
            Some(serde_json::json!({ "inputPath": "private" }))
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
    fn creative_pairing_accepts_only_the_fixed_application_ids() {
        for application_id in [
            "photoshop",
            "illustrator",
            "comfyui",
            "autocad",
            "blender",
            "jianying_capcut",
        ] {
            assert!(valid_creative_application_id(application_id));
        }
        assert!(!valid_creative_application_id("../../private"));
        assert!(!valid_creative_application_id("unknown"));
    }

    #[test]
    fn codex_prompt_requires_bounded_visible_text() {
        assert!(valid_codex_prompt("继续客户验收"));
        assert!(!valid_codex_prompt("   "));
        assert!(!valid_codex_prompt("包含\0控制字符"));
        assert!(!valid_codex_prompt(&"x".repeat(4001)));
    }

    #[test]
    fn github_project_button_is_fixed_to_the_public_repository() {
        let target = url::Url::parse(GITHUB_PROJECT_URL).expect("valid project URL");
        assert_eq!(target.scheme(), "https");
        assert_eq!(target.host_str(), Some("github.com"));
        assert_eq!(target.path(), "/jianbaorui07-dot/KORYAO-basic");
        assert!(target.query().is_none());
        assert!(target.fragment().is_none());
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

    #[test]
    fn ready_stream_decoder_accepts_a_message_split_across_chunks() {
        let mut decoder = ReadyStreamDecoder::default();
        assert!(decoder
            .push(br#"STARBRIDGE_READY {"port":49152,"pid":1234,"host":"127."#)
            .expect("bounded input")
            .is_none());
        let ready = decoder
            .push(br#"0.0.1","session_required":true}"#)
            .expect("bounded input")
            .expect("split readiness message");
        assert_eq!(ready.port, 49152);
        assert_eq!(ready.pid, 1234);
    }

    #[test]
    fn ready_stream_decoder_ignores_prior_complete_log_lines() {
        let mut decoder = ReadyStreamDecoder::default();
        let ready = decoder
            .push(
                b"booting local service\nSTARBRIDGE_READY {\"port\":49152,\"pid\":1234,\"host\":\"127.0.0.1\",\"session_required\":true}\n",
            )
            .expect("bounded input")
            .expect("readiness after log line");
        assert_eq!(ready.port, 49152);
    }

    #[test]
    fn ready_stream_decoder_rejects_unbounded_stdout() {
        let mut decoder = ReadyStreamDecoder::default();
        assert!(decoder.push(&vec![b'x'; MAX_READY_BUFFER_BYTES]).is_ok());
        assert!(decoder.push(b"x").is_err());
    }
}
