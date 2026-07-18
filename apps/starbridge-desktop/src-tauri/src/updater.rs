use std::{
    sync::{Mutex, MutexGuard},
    time::Duration,
};

use serde::Serialize;
use tauri::{ipc::Channel, AppHandle, State};
use tauri_plugin_updater::{Update, UpdaterExt};
use url::Url;

use crate::{request_graceful_stop, BackendManager};

const UPDATE_ENDPOINT: &str = "https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/releases/latest/download/latest.json";
const UPDATE_SOURCE_LABEL: &str = "GitHub Releases";
const UPDATE_TIMEOUT: Duration = Duration::from_secs(20);

#[derive(Default)]
pub(crate) struct PendingUpdate(Mutex<Option<Update>>);

impl PendingUpdate {
    fn lock(&self) -> MutexGuard<'_, Option<Update>> {
        self.0
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner())
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct UpdateStatus {
    configured: bool,
    source: &'static str,
    current_version: &'static str,
    available: bool,
    version: Option<String>,
    notes: Option<String>,
    published_at: Option<String>,
    signature_required: bool,
    automatic_checks_supported: bool,
}

#[derive(Clone, Serialize)]
#[serde(tag = "event", content = "data")]
pub(crate) enum UpdateProgress {
    #[serde(rename = "started", rename_all = "camelCase")]
    Started { content_length: Option<u64> },
    #[serde(rename = "progress", rename_all = "camelCase")]
    Progress {
        chunk_length: usize,
        downloaded_bytes: u64,
        content_length: Option<u64>,
    },
    #[serde(rename = "verified")]
    Verified,
    #[serde(rename = "installing")]
    Installing,
}

fn public_key() -> Option<&'static str> {
    option_env!("STARBRIDGE_UPDATE_PUBLIC_KEY")
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn empty_status() -> UpdateStatus {
    let configured = public_key().is_some();
    UpdateStatus {
        configured,
        source: UPDATE_SOURCE_LABEL,
        current_version: env!("CARGO_PKG_VERSION"),
        available: false,
        version: None,
        notes: None,
        published_at: None,
        signature_required: true,
        automatic_checks_supported: configured,
    }
}

fn build_updater(app: &AppHandle) -> Result<tauri_plugin_updater::Updater, String> {
    let key = public_key().ok_or_else(|| {
        "正式更新通道尚未配置；需要先注入公开验签公钥并完成签名发布。".to_string()
    })?;
    let endpoint = Url::parse(UPDATE_ENDPOINT)
        .map_err(|_| "更新地址配置无效；请使用正式构建重新安装。".to_string())?;
    app.updater_builder()
        .pubkey(key)
        .endpoints(vec![endpoint])
        .map_err(|_| "无法准备固定的 GitHub 更新地址。".to_string())?
        .timeout(UPDATE_TIMEOUT)
        .build()
        .map_err(|_| "无法初始化更新验签组件；请保留当前版本并稍后重试。".to_string())
}

#[tauri::command]
pub(crate) fn update_channel_status() -> UpdateStatus {
    empty_status()
}

#[tauri::command]
pub(crate) async fn check_for_update(
    app: AppHandle,
    pending_update: State<'_, PendingUpdate>,
) -> Result<UpdateStatus, String> {
    let mut status = empty_status();
    if !status.configured {
        pending_update.lock().take();
        return Ok(status);
    }

    let update = build_updater(&app)?
        .check()
        .await
        .map_err(|_| "暂时无法连接 GitHub 检查更新；当前版本可以继续离线使用。".to_string())?;

    if let Some(candidate) = update.as_ref() {
        status.available = true;
        status.version = Some(candidate.version.clone());
        status.notes = candidate.body.clone();
        status.published_at = candidate.date.map(|date| date.to_string());
    }
    *pending_update.lock() = update;
    Ok(status)
}

#[tauri::command]
pub(crate) async fn install_update(
    expected_version: String,
    confirm_install: bool,
    on_event: Channel<UpdateProgress>,
    pending_update: State<'_, PendingUpdate>,
    backend_manager: State<'_, BackendManager>,
) -> Result<(), String> {
    if !confirm_install {
        return Err("请先确认保存当前工作，再开始安装更新。".into());
    }

    let Some(update) = pending_update.lock().take() else {
        return Err("没有待安装的更新；请先检查更新。".into());
    };
    if update.version != expected_version {
        return Err("更新版本已经变化；请重新检查并确认新的版本说明。".into());
    }

    let _ = on_event.send(UpdateProgress::Started {
        content_length: None,
    });
    let mut downloaded_bytes = 0_u64;
    let event_channel = on_event.clone();
    let bytes = update
        .download(
            move |chunk_length, content_length| {
                downloaded_bytes = downloaded_bytes.saturating_add(chunk_length as u64);
                let _ = event_channel.send(UpdateProgress::Progress {
                    chunk_length,
                    downloaded_bytes,
                    content_length,
                });
            },
            || {},
        )
        .await
        .map_err(|_| "更新包下载或签名验证未通过；已保留当前版本。".to_string())?;

    let _ = on_event.send(UpdateProgress::Verified);
    request_graceful_stop(backend_manager.inner()).await;
    let _ = on_event.send(UpdateProgress::Installing);
    update
        .install(bytes)
        .map_err(|_| "更新安装程序未能启动；请重新打开 StarBridge 后再试。".to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn updater_endpoint_is_fixed_to_the_public_repository() {
        let endpoint = Url::parse(UPDATE_ENDPOINT).expect("valid endpoint");
        assert_eq!(endpoint.scheme(), "https");
        assert_eq!(endpoint.host_str(), Some("github.com"));
        assert_eq!(
            endpoint.path(),
            "/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/releases/latest/download/latest.json"
        );
        assert!(endpoint.query().is_none());
        assert!(endpoint.fragment().is_none());
    }

    #[test]
    fn development_build_does_not_claim_a_live_update_channel() {
        let status = empty_status();
        assert!(status.signature_required);
        assert_eq!(status.source, UPDATE_SOURCE_LABEL);
        if public_key().is_none() {
            assert!(!status.configured);
            assert!(!status.automatic_checks_supported);
        }
    }
}
