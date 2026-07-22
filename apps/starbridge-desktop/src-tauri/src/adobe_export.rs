use serde::Serialize;
use std::fs;
use std::io::Read;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};
use tauri::AppHandle;

use super::{starbridge_data_root, valid_vector_id};

const EXPORT_TIMEOUT: Duration = Duration::from_secs(120);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdobeExportReceipt {
    format: String,
    file_name: String,
    size_bytes: u64,
    source_basename: String,
    native_reopen_validated: bool,
    source_overwritten: bool,
}

fn valid_relative_artifact(relative_path: &str) -> bool {
    let path = Path::new(relative_path);
    !path.as_os_str().is_empty()
        && !path.is_absolute()
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn resolve_source(
    data_root: &Path,
    project_id: &str,
    relative_path: &str,
    format: &str,
) -> Result<PathBuf, String> {
    if !valid_vector_id(project_id, "project-") || !valid_relative_artifact(relative_path) {
        return Err("交付来源无效，请重新选择项目产物。".into());
    }
    let artifacts_root = data_root.join("artifacts");
    let project_root = artifacts_root.join(project_id);
    let source = data_root.join(relative_path);
    let resolved_project = project_root
        .canonicalize()
        .map_err(|_| "项目交付目录不存在。".to_string())?;
    let resolved_source = source
        .canonicalize()
        .map_err(|_| "所选交付产物不存在。".to_string())?;
    if !resolved_source.is_file() || !resolved_source.starts_with(&resolved_project) {
        return Err("所选产物超出当前项目的安全交付目录。".into());
    }
    let extension = resolved_source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let compatible = match format {
        "psd" => matches!(extension.as_str(), "png" | "jpg" | "jpeg"),
        "ai" => extension == "svg",
        _ => false,
    };
    if !compatible {
        return Err(match format {
            "psd" => "PSD 导出请选择真实 PNG 或 JPEG 预览产物。".into(),
            "ai" => "AI 导出请选择真实 SVG 矢量产物。".into(),
            _ => "只支持导出 PSD 或 AI 文件。".into(),
        });
    }
    Ok(resolved_source)
}

fn normalized_target(mut target: PathBuf, format: &str) -> Result<PathBuf, String> {
    match target.extension().and_then(|value| value.to_str()) {
        None => {
            target.set_extension(format);
        }
        Some(extension) if extension.eq_ignore_ascii_case(format) => {}
        Some(_) => return Err(format!("目标文件扩展名必须是 .{format}。")),
    }
    if target.exists() {
        return Err("目标文件已经存在。CreNexus 不会覆盖它，请选择新文件名。".into());
    }
    if !target.is_absolute() {
        return Err("请选择一个完整的本机保存路径。".into());
    }
    Ok(target)
}

const PHOTOSHOP_SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$source = $env:CRENEXUS_ADOBE_SOURCE
$target = $env:CRENEXUS_ADOBE_TARGET
if (-not $source -or -not $target) { throw 'missing export environment' }
$sourceJs = $source.Replace('\', '/') | ConvertTo-Json -Compress
$targetJs = $target.Replace('\', '/') | ConvertTo-Json -Compress
$jsx = @"
var previousDialogs = app.displayDialogs;
var sourceFile = new File($sourceJs);
var outputFile = new File($targetJs);
var bridgeResult = '';
try {
    app.displayDialogs = DialogModes.NO;
    if (!sourceFile.exists || outputFile.exists) throw new Error('invalid source or existing target');
    var document = app.open(sourceFile);
    document.activeLayer.name = 'CreNexus Artwork';
    var options = new PhotoshopSaveOptions();
    options.layers = true;
    options.alphaChannels = true;
    document.saveAs(outputFile, options, false, Extension.LOWERCASE);
    document.close(SaveOptions.DONOTSAVECHANGES);
    var persisted = app.open(outputFile);
    var valid = persisted.width.as('px') > 0 && persisted.height.as('px') > 0 && persisted.layers.length > 0;
    persisted.close(SaveOptions.DONOTSAVECHANGES);
    if (!valid) throw new Error('native reopen validation failed');
    bridgeResult = 'CRENEXUS_EXPORT_OK';
} catch (error) {
    try { if (outputFile.exists) outputFile.remove(); } catch (cleanupError) {}
    throw error;
} finally {
    app.displayDialogs = previousDialogs;
}
bridgeResult;
"@
$application = New-Object -ComObject Photoshop.Application
$result = $application.DoJavaScript($jsx)
if ($result -ne 'CRENEXUS_EXPORT_OK') { throw 'photoshop export validation failed' }
Write-Output 'CRENEXUS_EXPORT_OK'
"#;

const ILLUSTRATOR_SCRIPT: &str = r#"
$ErrorActionPreference = 'Stop'
$source = $env:CRENEXUS_ADOBE_SOURCE
$target = $env:CRENEXUS_ADOBE_TARGET
if (-not $source -or -not $target) { throw 'missing export environment' }
$sourceJs = $source.Replace('\', '/') | ConvertTo-Json -Compress
$targetJs = $target.Replace('\', '/') | ConvertTo-Json -Compress
$jsx = @"
var previousInteraction = app.userInteractionLevel;
var sourceFile = new File($sourceJs);
var outputFile = new File($targetJs);
var bridgeResult = '';
try {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    if (!sourceFile.exists || outputFile.exists) throw new Error('invalid source or existing target');
    var document = app.open(sourceFile);
    var options = new IllustratorSaveOptions();
    options.pdfCompatible = true;
    options.compressed = true;
    document.saveAs(outputFile, options);
    document.close(SaveOptions.DONOTSAVECHANGES);
    var persisted = app.open(outputFile);
    var valid = persisted.artboards.length > 0 && persisted.pageItems.length > 0;
    persisted.close(SaveOptions.DONOTSAVECHANGES);
    if (!valid) throw new Error('native reopen validation failed');
    bridgeResult = 'CRENEXUS_EXPORT_OK';
} catch (error) {
    try { if (outputFile.exists) outputFile.remove(); } catch (cleanupError) {}
    throw error;
} finally {
    app.userInteractionLevel = previousInteraction;
}
bridgeResult;
"@
$application = New-Object -ComObject Illustrator.Application
$result = $application.DoJavaScript($jsx)
if ($result -ne 'CRENEXUS_EXPORT_OK') { throw 'illustrator export validation failed' }
Write-Output 'CRENEXUS_EXPORT_OK'
"#;

#[cfg(windows)]
fn execute_adobe_export(source: &Path, target: &Path, format: &str) -> Result<(), String> {
    use std::os::windows::process::CommandExt;

    let script = if format == "psd" {
        PHOTOSHOP_SCRIPT
    } else {
        ILLUSTRATOR_SCRIPT
    };
    let mut child = Command::new("powershell.exe")
        .args([
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ])
        .env("CRENEXUS_ADOBE_SOURCE", source)
        .env("CRENEXUS_ADOBE_TARGET", target)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .creation_flags(0x08000000)
        .spawn()
        .map_err(|_| "无法启动本机 Adobe 导出桥接。".to_string())?;

    let started = Instant::now();
    loop {
        match child.try_wait() {
            Ok(Some(status)) => {
                let output = child
                    .wait_with_output()
                    .map_err(|_| "无法读取 Adobe 导出结果。".to_string())?;
                if !status.success()
                    || !String::from_utf8_lossy(&output.stdout).contains("CRENEXUS_EXPORT_OK")
                {
                    let _ = fs::remove_file(target);
                    return Err(match format {
                        "psd" => "Photoshop 没有完成 PSD 保存或原生重开验证；源产物未被修改。",
                        _ => "Illustrator 没有完成 AI 保存或原生重开验证；源产物未被修改。",
                    }
                    .into());
                }
                return Ok(());
            }
            Ok(None) if started.elapsed() < EXPORT_TIMEOUT => {
                thread::sleep(Duration::from_millis(100));
            }
            Ok(None) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_file(target);
                return Err("Adobe 导出超过 120 秒，已停止等待并清理未完成文件。".into());
            }
            Err(_) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_file(target);
                return Err("无法确认 Adobe 导出进程状态。".into());
            }
        }
    }
}

#[cfg(not(windows))]
fn execute_adobe_export(_source: &Path, _target: &Path, _format: &str) -> Result<(), String> {
    Err("PSD/AI 原生导出当前只支持 Windows。".into())
}

fn validate_native_file(path: &Path, format: &str) -> Result<u64, String> {
    let mut file = fs::File::open(path).map_err(|_| "Adobe 导出文件不存在。".to_string())?;
    let size = file
        .metadata()
        .map_err(|_| "无法读取 Adobe 导出文件信息。".to_string())?
        .len();
    let mut bytes = [0_u8; 16];
    let header_size = file
        .read(&mut bytes)
        .map_err(|_| "无法读取 Adobe 导出文件签名。".to_string())?;
    let header = &bytes[..header_size];
    let valid_signature = match format {
        "psd" => header.starts_with(b"8BPS"),
        "ai" => header.starts_with(b"%PDF-") || header.starts_with(b"%!PS-Adobe"),
        _ => false,
    };
    if size < 64 || !valid_signature {
        let _ = fs::remove_file(path);
        return Err("Adobe 导出文件没有通过原生格式签名验证，未完成文件已清理。".into());
    }
    Ok(size)
}

#[tauri::command]
pub async fn export_adobe_file(
    app: AppHandle,
    project_id: String,
    artifact_relative_path: String,
    format: String,
    confirm_export: bool,
) -> Result<Option<AdobeExportReceipt>, String> {
    if !confirm_export {
        return Err("导出到用户选择的路径前需要明确确认。".into());
    }
    if !matches!(format.as_str(), "psd" | "ai") {
        return Err("只支持导出 PSD 或 AI 文件。".into());
    }
    let data_root = starbridge_data_root(&app)?;
    let source = resolve_source(&data_root, &project_id, &artifact_relative_path, &format)?;
    let suggested_name = format!(
        "{}.{format}",
        source
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("CreNexus-delivery")
    );
    let picker_format = format.clone();
    let target = tauri::async_runtime::spawn_blocking(move || {
        let label = if picker_format == "psd" {
            "Photoshop 文档"
        } else {
            "Illustrator 文件"
        };
        rfd::FileDialog::new()
            .add_filter(label, &[picker_format.as_str()])
            .set_file_name(&suggested_name)
            .set_title("选择 CreNexus 交付文件的保存路径")
            .save_file()
    })
    .await
    .map_err(|_| "无法打开保存路径选择窗口。".to_string())?;
    let Some(target) = target else {
        return Ok(None);
    };
    let target = normalized_target(target, &format)?;
    let source_for_export = source.clone();
    let target_for_export = target.clone();
    let format_for_export = format.clone();
    tauri::async_runtime::spawn_blocking(move || {
        if target_for_export.exists() {
            return Err("目标文件已经存在。CreNexus 不会覆盖它，请选择新文件名。".into());
        }
        execute_adobe_export(&source_for_export, &target_for_export, &format_for_export)
    })
    .await
    .map_err(|_| "Adobe 导出任务意外停止。".to_string())??;
    let size_bytes = validate_native_file(&target, &format)?;
    Ok(Some(AdobeExportReceipt {
        format,
        file_name: target
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("delivery")
            .to_string(),
        size_bytes,
        source_basename: source
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("artifact")
            .to_string(),
        native_reopen_validated: true,
        source_overwritten: false,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn relative_artifacts_reject_escape_and_absolute_paths() {
        assert!(valid_relative_artifact(
            "artifacts/project-test/job-test/vector.svg"
        ));
        assert!(!valid_relative_artifact("../private/vector.svg"));
        assert!(!valid_relative_artifact("C:/private/vector.svg"));
        assert!(!valid_relative_artifact(""));
    }

    #[test]
    fn target_extension_and_overwrite_policy_are_strict() {
        let base = std::env::temp_dir().join(format!("crenexus-adobe-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&base).expect("temp export directory");
        let without_extension = normalized_target(base.join("delivery"), "ai").expect("target");
        assert_eq!(
            without_extension
                .extension()
                .and_then(|value| value.to_str()),
            Some("ai")
        );
        assert!(normalized_target(base.join("delivery.psd"), "ai").is_err());
        fs::write(&without_extension, b"existing").expect("existing target");
        assert!(normalized_target(without_extension.clone(), "ai").is_err());
        fs::remove_file(without_extension).expect("remove target");
        fs::remove_dir(base).expect("remove temp directory");
    }

    #[test]
    fn native_signature_validation_rejects_disguised_files() {
        let base =
            std::env::temp_dir().join(format!("crenexus-signature-{}", uuid::Uuid::new_v4()));
        fs::create_dir_all(&base).expect("temp signature directory");
        let valid_psd = base.join("valid.psd");
        fs::write(&valid_psd, [b"8BPS".as_slice(), &[0_u8; 80]].concat()).expect("psd");
        assert!(validate_native_file(&valid_psd, "psd").is_ok());
        let disguised_ai = base.join("disguised.ai");
        fs::write(&disguised_ai, [b"<svg".as_slice(), &[0_u8; 80]].concat()).expect("ai");
        assert!(validate_native_file(&disguised_ai, "ai").is_err());
        assert!(!disguised_ai.exists());
        fs::remove_file(valid_psd).expect("remove psd");
        fs::remove_dir(base).expect("remove temp directory");
    }
}
