import { validateDescriptor } from "./batchplay-schema.js";

const photoshop = require("photoshop");
const { action, app, core } = photoshop;

const MODAL_SCHEMA_VERSION = "starbridge.photoshop-modal.v1";
const HISTORY_TARGETS = new Set(["active_document", "handler_document", "none"]);

function boundedTimeout(value) {
  const number = Number(value ?? 5);
  if (!Number.isFinite(number)) return 5;
  return Math.min(30, Math.max(1, number));
}

function redactErrorMessage(error) {
  return String(error?.message || error || "Modal execution failed.")
    .replace(/[A-Za-z]:[\\/][^\s"'<>]*/g, "<redacted-path>")
    .replace(/\/(?:Users|home)\/[^\s"'<>]*/gi, "<redacted-path>")
    .replace(/(bearer\s+)[A-Za-z0-9._-]+/gi, "$1<redacted>")
    .replace(/([?&](?:token|key|secret)=)[^&\s]+/gi, "$1<redacted>")
    .slice(0, 512);
}

function errorCode(error, cancelled = false) {
  if (cancelled || String(error?.message || error) === "user_cancelled") return "user_cancelled";
  if (Number(error?.number) === 9) return "modal_busy";
  if (String(error?.message || error).includes("history")) return "history_control_failed";
  return "modal_job_failed";
}

function normalizeWarnings(values) {
  if (!Array.isArray(values)) return [];
  return values.slice(0, 16).map((value) => redactErrorMessage(value));
}

function normalizeErrors(values) {
  if (!Array.isArray(values)) return [];
  return values.slice(0, 16).map((value) => {
    const rawCode = String(value?.code || "modal_reported_error").toLowerCase();
    const code = /^[a-z][a-z0-9_]{0,63}$/.test(rawCode) ? rawCode : "modal_reported_error";
    return { code, message: redactErrorMessage(value?.message || value) };
  });
}

function createHistoryController(executionContext, target) {
  const hostControl = executionContext?.hostControl;
  const requiredForWrite = target !== "none";
  const supported = Boolean(
    typeof hostControl?.suspendHistory === "function" &&
      typeof hostControl?.resumeHistory === "function",
  );
  const state = {
    target,
    required_for_write: requiredForWrite,
    supported,
    suspended: false,
    committed: false,
    rolled_back: false,
  };
  let suspension = null;

  return {
    state,
    async suspendHistory(documentID, name) {
      if (!requiredForWrite || suspension) return;
      if (!supported) throw new Error("history_control_unavailable");
      if (documentID === undefined || documentID === null) {
        throw new Error("history_document_unavailable");
      }
      suspension = await hostControl.suspendHistory({ documentID, name });
      if (!suspension) throw new Error("history_suspension_failed");
      state.suspended = true;
    },
    ensureHistorySuspended() {
      if (requiredForWrite && (!suspension || !state.suspended)) {
        throw new Error("history_suspension_required");
      }
    },
    async commitHistory() {
      if (!suspension) return;
      await hostControl.resumeHistory(suspension, true);
      state.committed = true;
      suspension = null;
    },
    async rollbackHistory() {
      if (!suspension) return null;
      try {
        await hostControl.resumeHistory(suspension, false);
        state.rolled_back = true;
        suspension = null;
        return null;
      } catch (error) {
        return error;
      }
    },
  };
}

function modalEnvelope({ method, commandName, timeoutSeconds, status, history, errors = [], warnings = [] }) {
  return {
    schema_version: MODAL_SCHEMA_VERSION,
    method,
    command_name: commandName,
    status,
    success: status === "completed",
    cancelled: status === "cancelled",
    timeout_seconds: timeoutSeconds,
    history,
    warnings: warnings.slice(0, 16),
    errors: errors.slice(0, 16),
  };
}

export async function runModalJob(method, params, handler) {
  const commandName = String(params?.commandName || method).slice(0, 96);
  const timeoutSeconds = boundedTimeout(params?.timeoutSeconds);
  const requestedHistoryTarget = String(params?.historyTarget || "active_document");
  const historyTarget = HISTORY_TARGETS.has(requestedHistoryTarget)
    ? requestedHistoryTarget
    : "active_document";
  try {
    const result = await core.executeAsModal(async (executionContext) => {
      const historyController = createHistoryController(executionContext, historyTarget);
      const checkpoint = () => {
        if (executionContext?.isCancelled) throw new Error("user_cancelled");
      };
      try {
        checkpoint();
        if (historyTarget === "active_document") {
          const activeDocument = app?.activeDocument;
          const documentID = activeDocument?.id ?? activeDocument?._id;
          await historyController.suspendHistory(documentID, commandName);
        }
        const payload = await handler(executionContext, {
          checkpoint,
          suspendHistory: historyController.suspendHistory,
        });
        historyController.ensureHistorySuspended();
        checkpoint();
        await historyController.commitHistory();
        const warnings = normalizeWarnings(payload?.warnings);
        const errors = normalizeErrors(payload?.errors);
        const modal = modalEnvelope({
          method,
          commandName,
          timeoutSeconds,
          status: "completed",
          history: historyController.state,
          warnings,
          errors,
        });
        return {
          ...(payload || {}),
          success: true,
          history_state: historyController.state.committed ? commandName : null,
          warnings,
          errors,
          modal,
        };
      } catch (error) {
        const cancelled = Boolean(executionContext?.isCancelled) || errorCode(error) === "user_cancelled";
        const rollbackError = await historyController.rollbackHistory();
        const errors = [
          { code: errorCode(error, cancelled), message: redactErrorMessage(error) },
        ];
        if (rollbackError) {
          errors.push({ code: "history_rollback_failed", message: redactErrorMessage(rollbackError) });
        }
        const status = cancelled ? "cancelled" : "failed";
        return {
          success: false,
          history_state: null,
          warnings: [],
          errors,
          modal: modalEnvelope({
            method,
            commandName,
            timeoutSeconds,
            status,
            history: historyController.state,
            errors,
          }),
        };
      }
    }, { commandName, timeOut: timeoutSeconds });
    return result;
  } catch (error) {
    const errors = [{ code: errorCode(error), message: redactErrorMessage(error) }];
    const status = errorCode(error) === "user_cancelled" ? "cancelled" : "failed";
    const history = {
      target: historyTarget,
      required_for_write: historyTarget !== "none",
      supported: false,
      suspended: false,
      committed: false,
      rolled_back: false,
    };
    return {
      success: false,
      history_state: null,
      warnings: [],
      errors,
      modal: modalEnvelope({
        method,
        commandName,
        timeoutSeconds,
        status,
        history,
        errors,
      }),
    };
  }
}

export async function validateBatchPlay(descriptors) {
  if (!Array.isArray(descriptors) || descriptors.length < 1 || descriptors.length > 32) {
    return [{ index: 0, allowed: false, reason: "descriptors must contain 1 to 32 items" }];
  }
  return (descriptors || []).map((descriptor, index) => ({
    index: index + 1,
    ...validateDescriptor(descriptor),
  }));
}

export async function executeTypedBatchPlay({ descriptors, requireConfirmation = true, sandboxOnly = true, commandName = "StarBridge BatchPlay" }) {
  const validations = await validateBatchPlay(descriptors);
  const blocked = validations.filter((item) => !item.allowed);
  if (blocked.length) {
    return {
      executed: false,
      validation_result: {
        ok: false,
        blocked_count: blocked.length,
        validations,
      },
      warnings: blocked.map((item) => item.reason),
      errors: [],
    };
  }
  if (!requireConfirmation) {
    return {
      executed: false,
      validation_result: { ok: false, blocked_count: 1, validations },
      warnings: [],
      errors: [{ message: "Confirmation is required." }],
    };
  }
  if (!sandboxOnly) {
    return {
      executed: false,
      validation_result: { ok: false, blocked_count: 1, validations },
      warnings: [],
      errors: [{ message: "sandboxOnly=true is required." }],
    };
  }
  return runModalJob("ps.batchplay.execute_confirmed", { commandName, sandboxOnly, historyTarget: "handler_document" }, async (executionContext, modalControl) => {
    const document = app?.activeDocument;
    if (!document || typeof document.duplicate !== "function") {
      throw new Error("active_document_with_duplicate_support_required");
    }
    const hostControl = executionContext?.hostControl;
    if (typeof hostControl?.registerAutoCloseDocument !== "function" || typeof hostControl?.unregisterAutoCloseDocument !== "function") {
      throw new Error("photoshop_auto_close_control_required");
    }
    if (executionContext?.isCancelled) throw new Error("user_cancelled");
    const originalDocumentId = String(document._id || document.id || "");
    const sandboxDocument = await document.duplicate("StarBridge Sandbox", false);
    const sandboxDocumentId = String(sandboxDocument?._id || sandboxDocument?.id || "");
    if (!sandboxDocumentId) throw new Error("sandbox_document_id_unavailable");
    await hostControl.registerAutoCloseDocument(sandboxDocument.id || sandboxDocument._id);
    await modalControl.suspendHistory(sandboxDocument.id || sandboxDocument._id, commandName);
    modalControl.checkpoint();
    const result = await action.batchPlay(descriptors, {});
    modalControl.checkpoint();
    await hostControl.unregisterAutoCloseDocument(sandboxDocument.id || sandboxDocument._id);
    return {
      executed: true,
      sandbox_copy: true,
      original_document_id: originalDocumentId,
      sandbox_document_id: sandboxDocumentId,
      batchplay_result: result,
      validation_result: { ok: true, blocked_count: 0, validations },
    };
  });
}
