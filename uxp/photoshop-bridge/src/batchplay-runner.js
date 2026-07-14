import { validateDescriptor } from "./batchplay-schema.js";

const photoshop = require("photoshop");
const { action, app, core } = photoshop;

export async function runModalJob(method, params, handler) {
  const commandName = params?.commandName || method;
  try {
    const result = await core.executeAsModal(async (executionContext) => {
      const payload = await handler(executionContext);
      return {
        success: true,
        history_state: executionContext?.historyStateInfo?.name || commandName,
        warnings: payload?.warnings || [],
        errors: payload?.errors || [],
        ...(payload || {}),
      };
    }, { commandName });
    return result;
  } catch (error) {
    return {
      success: false,
      history_state: null,
      warnings: [],
      errors: [{ message: String(error?.message || error), name: String(error?.name || "Error") }],
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
  return runModalJob("ps.batchplay.execute_confirmed", { commandName, sandboxOnly }, async (executionContext) => {
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
    if (executionContext?.isCancelled) throw new Error("user_cancelled");
    const result = await action.batchPlay(descriptors, {});
    if (executionContext?.isCancelled) throw new Error("user_cancelled");
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
