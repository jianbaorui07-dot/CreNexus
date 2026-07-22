import { BridgeClient } from "./bridge-client.js";
import { executeTypedBatchPlay, runModalJob, validateBatchPlay } from "./batchplay-runner.js";

const photoshop = require("photoshop");
const { action, app } = photoshop;
const uxp = require("uxp");
const { entrypoints } = uxp;
const storage = uxp.storage;
const localFileSystem = storage.localFileSystem;

const CAMERA_RAW_BLOCKED_REASON = "camera_raw_batchplay_descriptor_not_recorded";
const CAMERA_RAW_NEXT_STEP = "Record a verified Camera Raw Filter descriptor with Alchemist or Photoshop Action listener and add it as a fixture.";
const CAMERA_RAW_PROTOCOL_VERSION = "camera_raw_tune.v1";
const CAMERA_RAW_OUTPUT_DIR = "examples/output/photoshop";
const CAMERA_RAW_DEFAULTS = {
  temperature: 4800,
  tint: 10,
  exposure: 0.35,
  contrast: 10,
  highlights: -25,
  shadows: 35,
  whites: 12,
  blacks: -12,
  texture: 18,
  clarity: 8,
  dehaze: 3,
  vibrance: 14,
  saturation: -2,
};
const CAMERA_RAW_RANGES = {
  temperature: [2000, 50000],
  tint: [-150, 150],
  exposure: [-5, 5],
  contrast: [-100, 100],
  highlights: [-100, 100],
  shadows: [-100, 100],
  whites: [-100, 100],
  blacks: [-100, 100],
  texture: [-100, 100],
  clarity: [-100, 100],
  dehaze: [-100, 100],
  vibrance: [-100, 100],
  saturation: [-100, 100],
};

function currentHost() {
  return {
    app: "Photoshop",
    version: String(app?.version || "unknown"),
  };
}

function activeDocumentOrNull() {
  return app?.activeDocument || null;
}

function safeLayerItem(layer, groupPath = []) {
  return {
    id: String(layer?._id || layer?.id || ""),
    name: String(layer?.name || ""),
    kind: String(layer?.kind || "layer"),
    type: String(layer?.kind || "layer"),
    visible: Boolean(layer?.visible ?? true),
    locked: Boolean(layer?.locked ?? false),
    opacity: Number(layer?.opacity ?? 100),
    blendMode: String(layer?.blendMode || "normal"),
    bounds: layer?.bounds ? {
      left: Number(layer.bounds.left || 0),
      top: Number(layer.bounds.top || 0),
      right: Number(layer.bounds.right || 0),
      bottom: Number(layer.bounds.bottom || 0),
    } : null,
    group_path: groupPath.join("/"),
  };
}

function flattenLayers(layers, groupPath = []) {
  const rows = [];
  for (const layer of layers || []) {
    rows.push(safeLayerItem(layer, groupPath));
    if (layer?.layers?.length) {
      rows.push(...flattenLayers(layer.layers, [...groupPath, String(layer.name || "")]));
    }
  }
  return rows;
}

function cameraRawPlan(params = {}) {
  const preset = String(params.preset || "blue_artwork_clean");
  const values = { ...CAMERA_RAW_DEFAULTS };
  const errors = [];
  if (preset !== "blue_artwork_clean") {
    errors.push("preset must be blue_artwork_clean");
  }
  const supplied = params.params || {};
  for (const [key, value] of Object.entries(supplied)) {
    if (!Object.prototype.hasOwnProperty.call(CAMERA_RAW_RANGES, key)) {
      errors.push(`params.${key} is not supported`);
      continue;
    }
    if (typeof value !== "number" || !Number.isFinite(value)) {
      errors.push(`params.${key} must be numeric`);
      continue;
    }
    const [minimum, maximum] = CAMERA_RAW_RANGES[key];
    if (value < minimum || value > maximum) {
      errors.push(`params.${key} must be between ${minimum} and ${maximum}`);
      continue;
    }
    values[key] = value;
  }
  const rawSource = params.source || { mode: "active_document" };
  const sourceMode = String(rawSource.mode || "active_document");
  const source = { mode: sourceMode };
  if (!["active_document", "explicit_path"].includes(sourceMode)) {
    errors.push("source.mode must be active_document or explicit_path");
  }
  if (sourceMode === "explicit_path") {
    if (!rawSource.path) {
      errors.push("source.path is required when source.mode is explicit_path");
    } else {
      source.path = String(rawSource.path);
      source.read_policy = "user_explicit_path_only";
    }
  }
  const rawOutput = params.output || {};
  const outputDir = String(rawOutput.dir || CAMERA_RAW_OUTPUT_DIR).replaceAll("\\", "/");
  if (outputDir !== CAMERA_RAW_OUTPUT_DIR) {
    errors.push(`output.dir must stay inside ${CAMERA_RAW_OUTPUT_DIR}`);
  }
  const formats = Array.isArray(rawOutput.formats) && rawOutput.formats.length ? rawOutput.formats.map((item) => String(item).toLowerCase()) : ["jpg"];
  const unsupportedFormats = formats.filter((item) => !["jpg", "png"].includes(item));
  if (unsupportedFormats.length) {
    errors.push(`output.formats contains unsupported values: ${unsupportedFormats.join(", ")}`);
  }
  const basename = String(rawOutput.basename || "camera_raw_tune_preview");
  if (!basename || basename.includes("/") || basename.includes("\\") || basename.includes(":") || basename.includes("..")) {
    errors.push("output.basename must be a simple file stem");
  }
  return {
    errors,
    plan: {
      protocol_version: CAMERA_RAW_PROTOCOL_VERSION,
      method: "ps.camera_raw.tune",
      preset,
      params: values,
      source,
      output: {
        dir: outputDir,
        basename,
        formats,
        export_after_apply: Boolean(rawOutput.export_after_apply),
      },
      descriptor_status: "missing",
      execution_path: ["Codex", "CreNexus MCP", "Node Proxy", "UXP Plugin", "Photoshop"],
    },
  };
}

async function ping() {
  return {
    plugin_status: "ok",
    photoshop_host: currentHost(),
    plugin_version: "1.0.0",
    now: new Date().toISOString(),
  };
}

async function cameraRawTune(params) {
  const dryRun = params?.dry_run !== false;
  const confirmApply = Boolean(params?.confirm_apply);
  const confirmExport = Boolean(params?.confirm_export);
  const { errors, plan } = cameraRawPlan(params || {});
  if (errors.length) {
    return { ok: false, errors, plan, photoshop_host: currentHost() };
  }
  if (dryRun) {
    return {
      ok: true,
      dry_run: true,
      confirm_apply: confirmApply,
      confirm_export: confirmExport,
      plan,
      photoshop_host: currentHost(),
      warnings: ["Camera Raw tuning dry-run validated; Photoshop was not modified."],
    };
  }
  if (!confirmApply) {
    return {
      ok: false,
      dry_run: false,
      confirm_apply: false,
      confirm_export: confirmExport,
      plan,
      photoshop_host: currentHost(),
      message: "confirm_apply=true is required when dry_run=false.",
    };
  }
  if (plan.output.export_after_apply && !confirmExport) {
    return {
      ok: false,
      dry_run: false,
      confirm_apply: true,
      confirm_export: false,
      plan,
      photoshop_host: currentHost(),
      message: "confirm_export=true is required when output.export_after_apply=true.",
    };
  }
  if (params?.descriptor_fixture_verified === true && Array.isArray(params?.descriptors) && params.descriptors.length) {
    return runModalJob("ps.camera_raw.tune", { commandName: "CreNexus Camera Raw Tune" }, async () => {
      const batchplayResult = await action.batchPlay(params.descriptors, { synchronousExecution: true, modalBehavior: "execute" });
      return {
        ok: true,
        executed: true,
        dry_run: false,
        confirm_apply: true,
        confirm_export: confirmExport,
        batchplay_result: batchplayResult,
        output_files: plan.output.export_after_apply ? plan.output.formats.map((format) => `${plan.output.dir}/${plan.output.basename}.${format}`) : [],
        plan,
        photoshop_host: currentHost(),
        warnings: plan.output.export_after_apply ? ["Camera Raw descriptor applied; export path remains host-dependent in UXP V1."] : [],
      };
    });
  }
  return runModalJob("ps.camera_raw.tune", { commandName: "CreNexus Camera Raw Tune" }, async () => ({
    ok: false,
    dry_run: false,
    confirm_apply: true,
    confirm_export: confirmExport,
    blocked_reason: CAMERA_RAW_BLOCKED_REASON,
    next_step: CAMERA_RAW_NEXT_STEP,
    plan,
    photoshop_host: currentHost(),
  }));
}

async function documentInfo() {
  const document = activeDocumentOrNull();
  if (!document) {
    return { ok: false, installed: true, message: "No active Photoshop document." };
  }
  const activeLayer = document.activeLayers?.[0] || null;
  return {
    ok: true,
    photoshop_host: currentHost(),
    document: {
      document_id: String(document._id || document.id || ""),
      title: String(document.title || document.name || ""),
      name: String(document.title || document.name || ""),
      width: Number(document.width || 0),
      height: Number(document.height || 0),
      resolution: Number(document.resolution || 72),
      color_mode: String(document.mode || ""),
      bit_depth: Number(document.bitsPerChannel || 8),
      active_layer_id: String(activeLayer?._id || activeLayer?.id || ""),
      active_layer_name: String(activeLayer?.name || ""),
      layer_count: Array.isArray(document.layers) ? document.layers.length : 0,
      saved: typeof document.saved === "boolean" ? document.saved : null,
    },
  };
}

async function layersList() {
  const document = activeDocumentOrNull();
  if (!document) {
    return { ok: false, installed: true, message: "No active Photoshop document.", layers: [] };
  }
  return {
    ok: true,
    photoshop_host: currentHost(),
    layers: flattenLayers(document.layers || []),
  };
}

function splitOutputPath(rawPath) {
  const normalized = String(rawPath || "").replace(/\\/g, "/");
  if (!normalized) {
    return { folderUrl: "", filename: "", absolute: "" };
  }
  const lastSlash = normalized.lastIndexOf("/");
  if (lastSlash <= 0) {
    return { folderUrl: "", filename: normalized, absolute: normalized };
  }
  return {
    folderUrl: normalized.slice(0, lastSlash),
    filename: normalized.slice(lastSlash + 1),
    absolute: normalized,
  };
}

function toFileUrl(absoluteFolder) {
  if (!absoluteFolder) {
    return "";
  }
  if (absoluteFolder.startsWith("file:")) {
    return absoluteFolder;
  }
  if (/^[A-Za-z]:/.test(absoluteFolder)) {
    return "file:///" + absoluteFolder;
  }
  return "file://" + absoluteFolder;
}

function assertSandboxOutputPath(params) {
  const normalized = String(params?.output_path || "").replaceAll("\\", "/");
  const absolute = /^[A-Za-z]:\//.test(normalized) || normalized.startsWith("/");
  const allowedMarker = ["/sandbox/", "/output/", "/examples/output/photoshop/"].some(marker => normalized.includes(marker));
  if (params?.sandbox_verified !== true || !absolute || !allowedMarker || !normalized.toLowerCase().endsWith(".png") || normalized.includes("/../")) {
    throw new Error("output_path_outside_sandbox");
  }
  return normalized;
}

async function resolveOutputEntry(absolutePath) {
  const { folderUrl, filename } = splitOutputPath(absolutePath);
  if (!folderUrl || !filename) {
    throw new Error("output_path must be an absolute path with a filename");
  }
  const folderEntry = await localFileSystem.getEntryWithUrl(toFileUrl(folderUrl));
  if (!folderEntry || !folderEntry.isFolder) {
    throw new Error("output folder is not a directory: " + folderUrl);
  }
  const fileEntry = await folderEntry.createFile(filename, { overwrite: true });
  return fileEntry;
}

async function saveActiveDocumentAsPng(document, absolutePath) {
  const fileEntry = await resolveOutputEntry(absolutePath);
  const saveAs = document.saveAs || (document.api && document.api.saveAs);
  if (!saveAs || typeof saveAs.png !== "function") {
    throw new Error("Photoshop UXP DOM does not expose document.saveAs.png on this host");
  }
  await saveAs.png(fileEntry, { compression: 6, interlaced: false }, true);
  return fileEntry;
}

async function activateDocument(document) {
  if (typeof document?.activate === "function") {
    await document.activate();
  }
}

async function closeDocumentWithoutSaving(document) {
  if (typeof document?.closeWithoutSaving === "function") {
    await document.closeWithoutSaving();
    return;
  }
  throw new Error("photoshop_close_without_saving_unavailable");
}

async function saveProductionCopy(document, absolutePath, format) {
  const fileEntry = await resolveOutputEntry(absolutePath);
  const saveAs = document?.saveAs || document?.api?.saveAs;
  if (!saveAs) throw new Error("photoshop_save_as_unavailable");
  if (format === "png" || format === "subject") {
    if (typeof saveAs.png !== "function") throw new Error("photoshop_png_export_unavailable");
    await saveAs.png(fileEntry, { compression: 6, interlaced: false }, true);
  } else if (format === "jpeg") {
    if (typeof saveAs.jpg !== "function") throw new Error("photoshop_jpeg_export_unavailable");
    await saveAs.jpg(fileEntry, { quality: 10 }, true);
  } else if (format === "psd") {
    if (typeof saveAs.psd !== "function") throw new Error("photoshop_psd_export_unavailable");
    await saveAs.psd(fileEntry, {}, true);
  } else {
    throw new Error("unsupported_production_format");
  }
}

async function validateNativePsdReopen(absolutePath, sandboxDocument) {
  const entry = await localFileSystem.getEntryWithUrl(toFileUrl(absolutePath));
  if (!entry || !entry.isFile) throw new Error("photoshop_psd_reopen_file_unavailable");
  const reopened = await app.open(entry);
  try {
    const width = Number(reopened?.width || 0);
    const height = Number(reopened?.height || 0);
    const layerCount = Array.isArray(reopened?.layers) ? reopened.layers.length : 0;
    const expectedWidth = Number(sandboxDocument?.width || 0);
    const expectedHeight = Number(sandboxDocument?.height || 0);
    const expectedLayerCount = Array.isArray(sandboxDocument?.layers)
      ? sandboxDocument.layers.length
      : 0;
    if (
      width <= 0
      || height <= 0
      || width !== expectedWidth
      || height !== expectedHeight
      || layerCount < 1
      || layerCount !== expectedLayerCount
    ) throw new Error("photoshop_psd_reopen_invalid_document");
    return {
      validated: true,
      width,
      height,
      layer_count: layerCount,
    };
  } finally {
    await closeDocumentWithoutSaving(reopened);
    await activateDocument(sandboxDocument);
  }
}

function assertProductionParams(params) {
  if (params?.confirm_write !== true || params?.managed_source_verified !== true || params?.safe_roots_verified !== true) {
    throw new Error("production_proxy_verification_required");
  }
  const sourcePath = String(params?.source_path || "");
  const stagingOutputs = params?.staging_outputs || {};
  if (!sourcePath || !Object.keys(stagingOutputs).length) throw new Error("production_paths_required");
  return { sourcePath, stagingOutputs };
}

async function importProjectLayer(sandboxDocument, sourcePath) {
  const sourceEntry = await localFileSystem.getEntryWithUrl(toFileUrl(sourcePath));
  if (!sourceEntry || !sourceEntry.isFile) throw new Error("managed_source_file_unavailable");
  const sourceDocument = await app.open(sourceEntry);
  try {
    const sourceLayer = sourceDocument?.activeLayers?.[0] || sourceDocument?.layers?.[0];
    if (!sourceLayer || typeof sourceLayer.duplicate !== "function") throw new Error("managed_source_layer_unavailable");
    await sourceLayer.duplicate(sandboxDocument);
  } finally {
    await closeDocumentWithoutSaving(sourceDocument);
  }
  await activateDocument(sandboxDocument);
  const importedLayer = sandboxDocument?.activeLayers?.[0] || null;
  if (importedLayer) importedLayer.name = "StarBridge Imported Asset";
  return Boolean(importedLayer);
}

async function applyProductionAdjustments(params) {
  const canvas = params?.canvas || {};
  const adjustment = params?.adjustment || {};
  const descriptors = [];
  if (canvas.resize === true) {
    descriptors.push({
      _obj: "canvasSize",
      width: { _unit: "pixelsUnit", _value: Number(canvas.width) },
      height: { _unit: "pixelsUnit", _value: Number(canvas.height) },
      horizontal: { _enum: "horizontalLocation", _value: "horizontalCenter" },
      vertical: { _enum: "verticalLocation", _value: "verticalCenter" },
    });
  }
  const brightness = Number(adjustment.brightness || 0);
  const contrast = Number(adjustment.contrast || 0);
  if (brightness !== 0 || contrast !== 0) {
    descriptors.push({
      _obj: "make",
      _target: [{ _ref: "adjustmentLayer" }],
      using: {
        _obj: "adjustmentLayer",
        name: "StarBridge Brightness Contrast",
        type: { _obj: "brightnessEvent", brightness, contrast, useLegacy: false },
      },
    });
  }
  const saturation = Number(adjustment.saturation || 0);
  if (saturation !== 0) {
    descriptors.push({
      _obj: "make",
      _target: [{ _ref: "adjustmentLayer" }],
      using: {
        _obj: "adjustmentLayer",
        name: "StarBridge Saturation",
        type: {
          _obj: "hueSaturation",
          presetKind: { _enum: "presetKindType", _value: "presetKindCustom" },
          saturation,
        },
      },
    });
  }
  if (descriptors.length) await action.batchPlay(descriptors, { synchronousExecution: true, modalBehavior: "execute" });
  return descriptors.length;
}

async function exportSubjectCopy(document, absolutePath) {
  await action.batchPlay([
    { _obj: "autoCutout", sampleAllLayers: false },
    { _obj: "copyToLayer" },
  ], { synchronousExecution: true, modalBehavior: "execute" });
  const subjectLayer = document?.activeLayers?.[0];
  if (!subjectLayer) throw new Error("photoshop_subject_layer_unavailable");
  subjectLayer.name = "StarBridge Subject";
  const visibility = (document.layers || []).map((layer) => ({ layer, visible: Boolean(layer.visible) }));
  try {
    for (const item of visibility) item.layer.visible = item.layer === subjectLayer;
    await saveProductionCopy(document, absolutePath, "subject");
  } finally {
    for (const item of visibility) item.layer.visible = item.visible;
  }
}

async function productionExecuteConfirmed(params) {
  const { sourcePath, stagingOutputs } = assertProductionParams(params);
  const originalDocument = activeDocumentOrNull();
  if (!originalDocument || typeof originalDocument.duplicate !== "function") {
    return { ok: false, executed: false, message: "An active Photoshop document is required." };
  }
  return runModalJob(
    "ps.production.execute_confirmed",
    { commandName: "StarBridge Photoshop Production", historyTarget: "handler_document", timeoutSeconds: 45 },
    async (executionContext, modalControl) => {
      const hostControl = executionContext?.hostControl;
      if (typeof hostControl?.registerAutoCloseDocument !== "function" || typeof hostControl?.unregisterAutoCloseDocument !== "function") {
        throw new Error("photoshop_auto_close_control_required");
      }
      modalControl.checkpoint();
      const sandboxDocument = await originalDocument.duplicate("StarBridge Sandbox Copy", false);
      const sandboxId = sandboxDocument?.id ?? sandboxDocument?._id;
      if (sandboxId === undefined || sandboxId === null) throw new Error("sandbox_document_id_unavailable");
      await hostControl.registerAutoCloseDocument(sandboxId);
      await modalControl.suspendHistory(sandboxId, "StarBridge Photoshop Production");
      await activateDocument(sandboxDocument);
      modalControl.checkpoint();
      const imported = await importProjectLayer(sandboxDocument, sourcePath);
      modalControl.checkpoint();
      const adjustmentCount = await applyProductionAdjustments(params);
      modalControl.checkpoint();
      for (const [format, outputPath] of Object.entries(stagingOutputs)) {
        if (format !== "subject") await saveProductionCopy(sandboxDocument, String(outputPath), format);
      }
      if (params?.export_subject === true) {
        if (!stagingOutputs.subject) throw new Error("subject_output_path_required");
        await exportSubjectCopy(sandboxDocument, String(stagingOutputs.subject));
      }
      const nativeReopen = stagingOutputs.psd
        ? await validateNativePsdReopen(String(stagingOutputs.psd), sandboxDocument)
        : { validated: false, skipped: true };
      modalControl.checkpoint();
      await hostControl.unregisterAutoCloseDocument(sandboxId);
      return {
        ok: true,
        executed: true,
        sandbox_copy: true,
        source_overwritten: false,
        imported_project_layer: imported,
        adjustment_count: adjustmentCount,
        output_formats: Object.keys(stagingOutputs),
        native_reopen_validated: nativeReopen.validated === true,
        native_reopen_skipped: nativeReopen.skipped === true,
        rollback_supported: true,
        photoshop_host: currentHost(),
        warnings: [],
      };
    },
  );
}

async function previewExport(params) {
  const document = activeDocumentOrNull();
  if (!document) {
    return { ok: false, installed: true, message: "No active Photoshop document." };
  }
  if (params?.dry_run === true) {
    return {
      ok: true,
      dry_run: true,
      preview_path: String(params.output_path || ""),
      document_name: String(document.title || document.name || ""),
      width: Number(document.width || 0),
      height: Number(document.height || 0),
      photoshop_host: currentHost(),
      warnings: ["dry_run=true: no PNG was written."],
    };
  }
  if (!params?.confirm_write) {
    return { ok: false, message: "confirm_write=true is required." };
  }
  const absolutePath = String(params?.output_path || "");
  if (!absolutePath) {
    return { ok: false, message: "output_path is required for real preview export." };
  }
  assertSandboxOutputPath(params);
  return runModalJob("ps.preview.export", { commandName: "CreNexus Preview Export" }, async () => {
    const fileEntry = await saveActiveDocumentAsPng(document, absolutePath);
    return {
      ok: true,
      executed: true,
      preview_path: absolutePath,
      written_path: String(fileEntry?.nativePath || absolutePath),
      document_name: String(document.title || document.name || ""),
      width: Number(document.width || 0),
      height: Number(document.height || 0),
      format: "png",
      layers_snapshot: flattenLayers(document.layers || []),
      photoshop_host: currentHost(),
      warnings: [],
    };
  });
}

async function batchplayValidate(params) {
  const descriptors = params?.descriptors || (params?.descriptor ? [params.descriptor] : []);
  const validations = await validateBatchPlay(descriptors);
  return {
    ok: validations.every((item) => item.allowed),
    validations,
    photoshop_host: currentHost(),
  };
}

async function batchplayExecuteConfirmed(params) {
  const descriptors = params?.descriptors || (params?.descriptor ? [params.descriptor] : []);
  const result = await executeTypedBatchPlay({
    descriptors,
    requireConfirmation: Boolean(params?.confirm_write),
    sandboxOnly: true,
    commandName: "CreNexus Typed BatchPlay",
  });
  const document = activeDocumentOrNull();
  return {
    ...result,
    preview_path: String(params?.output_path || ""),
    layers_snapshot: document ? flattenLayers(document.layers || []) : [],
    photoshop_host: currentHost(),
  };
}

const handlers = {
  "starbridge.ping": ping,
  "ps.document.info": documentInfo,
  "ps.layers.list": layersList,
  "ps.preview.export": previewExport,
  "ps.camera_raw.tune": cameraRawTune,
  "ps.batchplay.validate.local": batchplayValidate,
  "ps.batchplay.execute_confirmed": batchplayExecuteConfirmed,
  "ps.production.execute_confirmed": productionExecuteConfirmed,
};

const panelElements = {
  card: document.querySelector("#session-card"),
  phase: document.querySelector("#session-phase"),
  step: document.querySelector("#session-step"),
  message: document.querySelector("#session-message"),
  progress: document.querySelector("#session-progress"),
  progressTrack: document.querySelector(".progress-track"),
  mode: document.querySelector("#session-mode"),
  time: document.querySelector("#session-time"),
  connection: document.querySelector("#connection"),
};

const phaseLabels = {
  queued: "已排队",
  running: "Codex 正在工作",
  completed: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  needs_user: "等待确认",
};

function setPanelText(element, value) {
  if (element) element.textContent = value;
}

function onBridgeStatus(status) {
  const labels = { connecting: "连接中", connected: "已连接", disconnected: "已断开", error: "连接异常" };
  setPanelText(panelElements.connection, labels[status] || status);
}

function onLiveSession(update) {
  const progress = Math.max(0, Math.min(100, Number(update?.progress || 0)));
  if (panelElements.card) panelElements.card.dataset.phase = String(update?.phase || "idle");
  setPanelText(panelElements.phase, phaseLabels[update?.phase] || String(update?.phase || "等待任务"));
  setPanelText(panelElements.step, `${update?.step?.index || 0}/${update?.step?.total || 0} · ${update?.step?.label || ""}`);
  setPanelText(panelElements.message, String(update?.message || ""));
  setPanelText(panelElements.mode, update?.mode === "computer_use" ? "界面操作" : "结构化命令");
  setPanelText(panelElements.time, update?.at ? new Date(update.at).toLocaleTimeString() : "—");
  if (panelElements.progress) panelElements.progress.style.width = `${progress}%`;
  if (panelElements.progressTrack) panelElements.progressTrack.setAttribute("aria-valuenow", String(progress));
}

const client = new BridgeClient({ handlers, onStatus: onBridgeStatus, onSession: onLiveSession });
document.querySelector("#reconnect")?.addEventListener("click", () => client.reconnect());
client.connect();

if (entrypoints) {
  entrypoints.setup({
    commands: {
      starbridgePing: async () => ping(),
    },
    panels: {
      starbridgePhotoshopLivePanel: {
        show() {
          onBridgeStatus(client.connected ? "connected" : "connecting");
        },
      },
    },
  });
}
