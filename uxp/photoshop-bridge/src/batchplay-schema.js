export const ALLOWLIST = {
  get: {
    descriptorId: "get_document_or_layer_info",
    riskLevel: "safe_read_only",
    requiresConfirmation: false,
    sandboxOnly: false,
  },
  make: {
    descriptorId: "create_test_adjustment_layer_in_sandbox",
    riskLevel: "guarded_local_write",
    requiresConfirmation: true,
    sandboxOnly: true,
  },
  set: {
    descriptorId: "rename_or_visibility_in_sandbox",
    riskLevel: "guarded_local_write",
    requiresConfirmation: true,
    sandboxOnly: true,
  },
  move: {
    descriptorId: "move_layer_in_sandbox",
    riskLevel: "guarded_local_write",
    requiresConfirmation: true,
    sandboxOnly: true,
  },
};

export const DENYLIST = new Set([
  "delete",
  "duplicate",
  "mergeLayersNew",
  "flattenImage",
  "rasterizeLayer",
  "placedLayerEditContents",
  "save",
  "javascript",
  "batchPlay",
]);

const PATH_FIELDS = new Set(["file", "filepath", "fullname", "nativepath", "path", "sourcepath", "targetpath", "url"]);

function unsafePayloadReason(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const reason = unsafePayloadReason(item);
      if (reason) return reason;
    }
    return null;
  }
  if (!value || typeof value !== "object") return null;
  const reference = String(value._ref || "").toLowerCase();
  if (["document", "layer"].includes(reference) && ["_id", "_index", "_name"].some(key => key in value)) {
    return `explicit_target:${reference}`;
  }
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.replaceAll("_", "").toLowerCase();
    if (PATH_FIELDS.has(normalized) || normalized.endsWith("path")) return `path_field:${key}`;
    const reason = unsafePayloadReason(item);
    if (reason) return reason;
  }
  return null;
}

export function validateDescriptor(descriptor) {
  const action = String(descriptor?._obj || descriptor?.method || "").trim();
  if (!action) {
    return {
      allowed: false,
      descriptorId: "missing_action",
      riskLevel: "guarded_local_write",
      requiresConfirmation: true,
      sandboxOnly: true,
      reason: "Descriptor is missing _obj or method.",
    };
  }
  if (DENYLIST.has(action)) {
    return {
      allowed: false,
      action,
      descriptorId: `denied_${action}`,
      riskLevel: "guarded_local_write",
      requiresConfirmation: true,
      sandboxOnly: true,
      reason: `Descriptor action ${action} is explicitly denied.`,
    };
  }
  const unsafeReason = unsafePayloadReason(descriptor);
  if (unsafeReason) {
    return {
      allowed: false,
      action,
      descriptorId: `unsafe_${action}`,
      riskLevel: "guarded_local_write",
      requiresConfirmation: true,
      sandboxOnly: true,
      reason: unsafeReason,
    };
  }
  const allowed = ALLOWLIST[action];
  if (!allowed) {
    return {
      allowed: false,
      action,
      descriptorId: `unknown_${action}`,
      riskLevel: "guarded_local_write",
      requiresConfirmation: true,
      sandboxOnly: true,
      reason: `Descriptor action ${action} is not in the allowlist.`,
    };
  }
  return {
    allowed: true,
    action,
    ...allowed,
    reason: "Descriptor is in the typed allowlist.",
  };
}
