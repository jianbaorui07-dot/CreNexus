use std::{
    collections::BTreeSet,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine as _};
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use uuid::Uuid;

const LICENSE_SCHEMA: &str = "starbridge-license/v1";
const REQUEST_SCHEMA: &str = "starbridge-license-request/v1";
const MAX_LICENSE_BYTES: usize = 64 * 1024;
const MAX_DEVICES: u8 = 2;
const ACTIVE_LICENSE_FILE: &str = "active.starbridge-license";

const KNOWN_COMMERCIAL_FEATURES: &[&str] = &[
    "vectorization.advanced",
    "batch.processing",
    "integration.adobe",
    "integration.comfyui",
    "integration.blender",
    "updates.offline_signed_packages",
    "support.enterprise_customization",
];

#[derive(Clone, Copy, Debug, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
enum LicenseEdition {
    Pro,
    Enterprise,
}

impl LicenseEdition {
    fn as_str(self) -> &'static str {
        match self {
            Self::Pro => "pro",
            Self::Enterprise => "enterprise",
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct LicensePayload {
    license_id: String,
    edition: LicenseEdition,
    issued_on: String,
    perpetual: bool,
    device_limit: u8,
    device_fingerprints: Vec<String>,
    features: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct LicenseSignature {
    algorithm: String,
    key_id: String,
    value: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct LicenseEnvelope {
    schema: String,
    payload: LicensePayload,
    signature: LicenseSignature,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LicenseStatus {
    state: &'static str,
    edition: &'static str,
    message: String,
    license_id: Option<String>,
    device_limit: u8,
    features: Vec<String>,
    commercial_verifier_configured: bool,
    reason: Option<&'static str>,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct LicenseRequestReceipt {
    request_id: String,
    file_name: String,
    location: &'static str,
    folder_opened: bool,
}

#[derive(Serialize)]
struct LicenseRequest {
    schema: &'static str,
    request_id: String,
    product: &'static str,
    desktop_version: &'static str,
    platform: &'static str,
    requested_edition: &'static str,
    requested_device_limit: u8,
    device_fingerprint: String,
    created_unix_seconds: u64,
}

#[derive(Clone, Copy, Debug)]
struct LicenseError(&'static str);

impl LicenseError {
    fn user_message(self) -> String {
        match self.0 {
            "license_too_large" => "授权文件过大，已拒绝导入。",
            "license_json_invalid" => "授权文件格式无法识别。",
            "license_schema_unsupported" => "授权文件版本不受当前软件支持。",
            "license_payload_invalid" => "授权文件内容不完整或包含无效字段。",
            "license_signature_invalid" => "授权文件签名无效，未导入任何内容。",
            "license_key_unknown" => "授权文件不是由当前 StarBridge 版本认可的密钥签发。",
            "commercial_verifier_not_configured" => "当前 Community 构建未配置商业版验签公钥。",
            "device_not_licensed" => "该授权文件未绑定当前 Windows 设备。",
            "device_identity_unavailable" => "无法读取本机设备标识，未创建或导入授权。",
            "license_storage_failed" => "授权文件无法写入本机应用数据目录。",
            "license_read_failed" => "本机授权文件无法读取。",
            "license_request_failed" => "设备授权申请文件无法创建。",
            _ => "授权操作未完成。",
        }
        .into()
    }
}

struct LicenseVerifier {
    key_id: String,
    key: VerifyingKey,
}

fn community_status(verifier_configured: bool) -> LicenseStatus {
    LicenseStatus {
        state: "community",
        edition: "community",
        message: "Community 免费版正在本机运行，不需要授权文件。".into(),
        license_id: None,
        device_limit: 0,
        features: Vec::new(),
        commercial_verifier_configured: verifier_configured,
        reason: None,
    }
}

fn invalid_status(reason: &'static str, verifier_configured: bool) -> LicenseStatus {
    LicenseStatus {
        state: "invalid",
        edition: "community",
        message: LicenseError(reason).user_message(),
        license_id: None,
        device_limit: 0,
        features: Vec::new(),
        commercial_verifier_configured: verifier_configured,
        reason: Some(reason),
    }
}

fn active_status(payload: LicensePayload) -> LicenseStatus {
    LicenseStatus {
        state: "active",
        edition: payload.edition.as_str(),
        message: "离线授权签名和当前设备绑定均已验证。".into(),
        license_id: Some(payload.license_id),
        device_limit: payload.device_limit,
        features: payload.features,
        commercial_verifier_configured: true,
        reason: None,
    }
}

fn license_directory(root: &Path) -> PathBuf {
    root.join("license")
}

fn active_license_path(root: &Path) -> PathBuf {
    license_directory(root).join(ACTIVE_LICENSE_FILE)
}

fn configured_verifier() -> Result<Option<LicenseVerifier>, LicenseError> {
    let Some(encoded) = option_env!("STARBRIDGE_LICENSE_PUBLIC_KEY_B64") else {
        return Ok(None);
    };
    let decoded = URL_SAFE_NO_PAD
        .decode(encoded)
        .map_err(|_| LicenseError("commercial_verifier_not_configured"))?;
    let bytes: [u8; 32] = decoded
        .try_into()
        .map_err(|_| LicenseError("commercial_verifier_not_configured"))?;
    let key = VerifyingKey::from_bytes(&bytes)
        .map_err(|_| LicenseError("commercial_verifier_not_configured"))?;
    Ok(Some(LicenseVerifier {
        key_id: option_env!("STARBRIDGE_LICENSE_KEY_ID")
            .unwrap_or("starbridge-production-v1")
            .to_owned(),
        key,
    }))
}

fn valid_identifier(value: &str, max_len: usize) -> bool {
    !value.is_empty()
        && value.len() <= max_len
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
}

fn valid_issued_on(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 10
        && bytes[4] == b'-'
        && bytes[7] == b'-'
        && bytes
            .iter()
            .enumerate()
            .all(|(index, byte)| matches!(index, 4 | 7) || byte.is_ascii_digit())
}

fn validate_payload(payload: &LicensePayload) -> Result<(), LicenseError> {
    if !valid_identifier(&payload.license_id, 64)
        || !valid_issued_on(&payload.issued_on)
        || !payload.perpetual
        || payload.device_limit == 0
        || payload.device_limit > MAX_DEVICES
        || payload.device_fingerprints.len() != usize::from(payload.device_limit)
        || payload.features.is_empty()
        || payload.features.len() > 32
    {
        return Err(LicenseError("license_payload_invalid"));
    }

    let mut devices = BTreeSet::new();
    for fingerprint in &payload.device_fingerprints {
        if !fingerprint.starts_with("sb-device-v1:")
            || fingerprint.len() > 96
            || !devices.insert(fingerprint)
        {
            return Err(LicenseError("license_payload_invalid"));
        }
    }

    let known = KNOWN_COMMERCIAL_FEATURES
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let mut features = BTreeSet::new();
    for feature in &payload.features {
        if !known.contains(feature.as_str()) || !features.insert(feature) {
            return Err(LicenseError("license_payload_invalid"));
        }
    }
    Ok(())
}

fn verify_contents(
    contents: &str,
    current_device: &str,
    verifier: &LicenseVerifier,
) -> Result<LicensePayload, LicenseError> {
    if contents.len() > MAX_LICENSE_BYTES {
        return Err(LicenseError("license_too_large"));
    }
    let envelope: LicenseEnvelope =
        serde_json::from_str(contents).map_err(|_| LicenseError("license_json_invalid"))?;
    if envelope.schema != LICENSE_SCHEMA {
        return Err(LicenseError("license_schema_unsupported"));
    }
    if envelope.signature.algorithm != "ed25519" || envelope.signature.key_id != verifier.key_id {
        return Err(LicenseError("license_key_unknown"));
    }
    validate_payload(&envelope.payload)?;

    let signature_bytes = URL_SAFE_NO_PAD
        .decode(&envelope.signature.value)
        .map_err(|_| LicenseError("license_signature_invalid"))?;
    let signature = Signature::from_slice(&signature_bytes)
        .map_err(|_| LicenseError("license_signature_invalid"))?;
    let canonical = serde_jcs::to_vec(&envelope.payload)
        .map_err(|_| LicenseError("license_payload_invalid"))?;
    verifier
        .key
        .verify(&canonical, &signature)
        .map_err(|_| LicenseError("license_signature_invalid"))?;
    if !envelope
        .payload
        .device_fingerprints
        .iter()
        .any(|fingerprint| fingerprint == current_device)
    {
        return Err(LicenseError("device_not_licensed"));
    }
    Ok(envelope.payload)
}

fn hash_device_material(material: &str) -> Result<String, LicenseError> {
    let normalized = material.trim().to_ascii_lowercase();
    if normalized.len() < 8 || normalized.len() > 256 {
        return Err(LicenseError("device_identity_unavailable"));
    }
    let mut digest = Sha256::new();
    digest.update(b"starbridge-device-v1\0");
    digest.update(normalized.as_bytes());
    Ok(format!(
        "sb-device-v1:{}",
        URL_SAFE_NO_PAD.encode(digest.finalize())
    ))
}

#[cfg(windows)]
fn current_device_fingerprint() -> Result<String, LicenseError> {
    use winreg::{
        enums::{HKEY_LOCAL_MACHINE, KEY_READ, KEY_WOW64_64KEY},
        RegKey,
    };

    let machine = RegKey::predef(HKEY_LOCAL_MACHINE)
        .open_subkey_with_flags(
            "SOFTWARE\\Microsoft\\Cryptography",
            KEY_READ | KEY_WOW64_64KEY,
        )
        .map_err(|_| LicenseError("device_identity_unavailable"))?;
    let machine_guid: String = machine
        .get_value("MachineGuid")
        .map_err(|_| LicenseError("device_identity_unavailable"))?;
    hash_device_material(&machine_guid)
}

#[cfg(not(windows))]
fn current_device_fingerprint() -> Result<String, LicenseError> {
    Err(LicenseError("device_identity_unavailable"))
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<(), LicenseError> {
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|_| LicenseError("license_storage_failed"))?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|_| LicenseError("license_storage_failed"))
}

fn replace_active_license(root: &Path, contents: &str) -> Result<(), LicenseError> {
    let directory = license_directory(root);
    fs::create_dir_all(&directory).map_err(|_| LicenseError("license_storage_failed"))?;
    let target = active_license_path(root);
    let transaction = Uuid::new_v4().simple().to_string();
    let temporary = directory.join(format!(".license-{transaction}.tmp"));
    let backup = directory.join(format!(".license-{transaction}.backup"));
    write_synced(&temporary, contents.as_bytes())?;

    let had_existing = target.exists();
    if had_existing && fs::rename(&target, &backup).is_err() {
        let _ = fs::remove_file(&temporary);
        return Err(LicenseError("license_storage_failed"));
    }
    if fs::rename(&temporary, &target).is_err() {
        if had_existing {
            let _ = fs::rename(&backup, &target);
        }
        let _ = fs::remove_file(&temporary);
        return Err(LicenseError("license_storage_failed"));
    }
    if had_existing {
        let _ = fs::remove_file(backup);
    }
    Ok(())
}

pub(crate) fn installed_status(root: &Path) -> LicenseStatus {
    let verifier = match configured_verifier() {
        Ok(verifier) => verifier,
        Err(error) => return invalid_status(error.0, false),
    };
    let target = active_license_path(root);
    if !target.is_file() {
        return community_status(verifier.is_some());
    }
    let Some(verifier) = verifier else {
        return invalid_status("commercial_verifier_not_configured", false);
    };
    let device = match current_device_fingerprint() {
        Ok(device) => device,
        Err(error) => return invalid_status(error.0, true),
    };
    let contents = match fs::read_to_string(target) {
        Ok(contents) => contents,
        Err(_) => return invalid_status("license_read_failed", true),
    };
    match verify_contents(&contents, &device, &verifier) {
        Ok(payload) => active_status(payload),
        Err(error) => invalid_status(error.0, true),
    }
}

pub(crate) fn import_license(root: &Path, contents: &str) -> Result<LicenseStatus, String> {
    let verifier = configured_verifier()
        .map_err(LicenseError::user_message)?
        .ok_or_else(|| LicenseError("commercial_verifier_not_configured").user_message())?;
    let device = current_device_fingerprint().map_err(LicenseError::user_message)?;
    let payload =
        verify_contents(contents, &device, &verifier).map_err(LicenseError::user_message)?;
    replace_active_license(root, contents).map_err(LicenseError::user_message)?;
    Ok(active_status(payload))
}

pub(crate) fn create_request(
    root: &Path,
    desktop_version: &'static str,
) -> Result<(LicenseRequestReceipt, PathBuf), String> {
    let device_fingerprint = current_device_fingerprint().map_err(LicenseError::user_message)?;
    let request_id = Uuid::new_v4().simple().to_string();
    let request = LicenseRequest {
        schema: REQUEST_SCHEMA,
        request_id: request_id.clone(),
        product: "StarBridge",
        desktop_version,
        platform: "windows-x86_64",
        requested_edition: "pro",
        requested_device_limit: MAX_DEVICES,
        device_fingerprint,
        created_unix_seconds: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
    };
    let mut encoded = serde_json::to_vec_pretty(&request)
        .map_err(|_| LicenseError("license_request_failed").user_message())?;
    encoded.push(b'\n');
    let directory = license_directory(root).join("requests");
    fs::create_dir_all(&directory)
        .map_err(|_| LicenseError("license_request_failed").user_message())?;
    let file_name = format!("StarBridge-license-request-{request_id}.json");
    let target = directory.join(&file_name);
    write_synced(&target, &encoded)
        .map_err(|_| LicenseError("license_request_failed").user_message())?;
    Ok((
        LicenseRequestReceipt {
            request_id,
            file_name,
            location: "<LOCAL_APP_DATA>/StarBridge/license/requests",
            folder_opened: false,
        },
        directory,
    ))
}

pub(crate) fn mark_folder_opened(receipt: &mut LicenseRequestReceipt) {
    receipt.folder_opened = true;
}

#[cfg(test)]
mod tests {
    use super::*;
    use ed25519_dalek::{Signer, SigningKey};
    use rand_core::OsRng;

    fn signed_license(signing_key: &SigningKey, device: &str) -> String {
        let payload = LicensePayload {
            license_id: "SB-PRO-TEST-001".into(),
            edition: LicenseEdition::Pro,
            issued_on: "2026-07-17".into(),
            perpetual: true,
            device_limit: 1,
            device_fingerprints: vec![device.into()],
            features: vec!["batch.processing".into(), "vectorization.advanced".into()],
        };
        let canonical = serde_jcs::to_vec(&payload).expect("canonical payload");
        let signature = signing_key.sign(&canonical);
        serde_json::to_string_pretty(&LicenseEnvelope {
            schema: LICENSE_SCHEMA.into(),
            payload,
            signature: LicenseSignature {
                algorithm: "ed25519".into(),
                key_id: "test-key".into(),
                value: URL_SAFE_NO_PAD.encode(signature.to_bytes()),
            },
        })
        .expect("license JSON")
    }

    fn test_verifier(signing_key: &SigningKey) -> LicenseVerifier {
        LicenseVerifier {
            key_id: "test-key".into(),
            key: signing_key.verifying_key(),
        }
    }

    #[test]
    fn device_fingerprint_is_normalized_and_domain_separated() {
        let first = hash_device_material("  A1B2-C3D4-E5F6  ").expect("fingerprint");
        let second = hash_device_material("a1b2-c3d4-e5f6").expect("fingerprint");
        assert_eq!(first, second);
        assert!(first.starts_with("sb-device-v1:"));
        assert!(!first.contains("a1b2"));
    }

    #[test]
    fn valid_signature_unlocks_only_the_bound_device() {
        let signing_key = SigningKey::generate(&mut OsRng);
        let device = hash_device_material("windows-machine-guid-001").expect("device");
        let contents = signed_license(&signing_key, &device);
        let payload = verify_contents(&contents, &device, &test_verifier(&signing_key))
            .expect("valid signed license");
        assert_eq!(payload.edition, LicenseEdition::Pro);
        assert_eq!(payload.device_limit, 1);

        let other = hash_device_material("windows-machine-guid-002").expect("device");
        assert_eq!(
            verify_contents(&contents, &other, &test_verifier(&signing_key))
                .expect_err("wrong device must fail")
                .0,
            "device_not_licensed"
        );
    }

    #[test]
    fn tampering_invalidates_the_signature() {
        let signing_key = SigningKey::generate(&mut OsRng);
        let device = hash_device_material("windows-machine-guid-003").expect("device");
        let contents = signed_license(&signing_key, &device);
        let tampered = contents.replace("\"pro\"", "\"enterprise\"");
        assert_eq!(
            verify_contents(&tampered, &device, &test_verifier(&signing_key))
                .expect_err("tampered license must fail")
                .0,
            "license_signature_invalid"
        );
    }

    #[test]
    fn invalid_payload_cannot_bypass_the_device_limit() {
        let signing_key = SigningKey::generate(&mut OsRng);
        let device = hash_device_material("windows-machine-guid-004").expect("device");
        let contents = signed_license(&signing_key, &device)
            .replace("\"device_limit\": 1", "\"device_limit\": 3");
        assert_eq!(
            verify_contents(&contents, &device, &test_verifier(&signing_key))
                .expect_err("oversized device allowance must fail")
                .0,
            "license_payload_invalid"
        );
    }

    #[cfg(windows)]
    #[test]
    fn exported_request_contains_a_hash_not_a_raw_machine_identifier() {
        let root = std::env::temp_dir().join(format!(
            "starbridge-license-request-test-{}",
            Uuid::new_v4().simple()
        ));
        let (receipt, directory) = create_request(&root, "0.1.0").expect("request export");
        let contents = fs::read_to_string(directory.join(receipt.file_name)).expect("request file");
        let request: serde_json::Value = serde_json::from_str(&contents).expect("request JSON");
        let fingerprint = request["device_fingerprint"]
            .as_str()
            .expect("hashed device fingerprint");
        assert!(fingerprint.starts_with("sb-device-v1:"));
        assert!(!contents.contains("MachineGuid"));
        assert!(!contents.contains("machine_guid"));
        let _ = fs::remove_dir_all(root);
    }
}
