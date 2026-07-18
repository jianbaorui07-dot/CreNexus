export const METHODS = Object.freeze([
  "illustrator.get_state",
  "illustrator.document_info",
  "illustrator.select_object",
  "illustrator.set_fill",
  "illustrator.move_object",
  "illustrator.create_path",
  "illustrator.zoom_to_selection",
  "illustrator.apply_artisan_map",
  "illustrator.readback_artisan_map",
  "illustrator.commit_artisan_map",
  "illustrator.rollback_artisan_map",
]);

export const WRITE_METHODS = new Set([
  "illustrator.select_object",
  "illustrator.set_fill",
  "illustrator.move_object",
  "illustrator.create_path",
  "illustrator.apply_artisan_map",
  "illustrator.rollback_artisan_map",
]);

function safeName(value) { return typeof value === "string" && value.length > 0 && value.length <= 64 && /^[\p{L}\p{N} _-]+$/u.test(value); }
function validRows(value, pattern, maximum) {
  if (!Array.isArray(value) || value.length > maximum) return false;
  const ids = new Set();
  return value.every(row => Array.isArray(row) && row.length === 2 && pattern.test(String(row[0])) && safeName(row[1]) && !ids.has(row[0]) && Boolean(ids.add(row[0])));
}

export function validateRequest(message) {
  if (!message || message.jsonrpc !== "2.0" || !("id" in message)) return "invalid_jsonrpc_request";
  if (!METHODS.includes(message.method)) return "method_not_allowed";
  if (!message.params || typeof message.params !== "object" || Array.isArray(message.params)) return "params_must_be_object";
  if (WRITE_METHODS.has(message.method) && message.params.confirm_write !== true) return "confirm_write=true_required";
  if (message.params.object_id !== undefined && !/^item:\d+$/.test(String(message.params.object_id))) return "object_id_must_be_session_local";
  if (["illustrator.apply_artisan_map", "illustrator.readback_artisan_map", "illustrator.commit_artisan_map", "illustrator.rollback_artisan_map"].includes(message.method)) {
    if (!/^apply:[0-9a-f]{12}$/.test(String(message.params.transaction_ref || "")) || !/^imap:[0-9a-f]{12}$/.test(String(message.params.map_ref || ""))) return "artisan_refs_invalid";
  }
  if (message.method === "illustrator.apply_artisan_map") {
    if (!Number.isInteger(message.params.expected_state_revision) || message.params.expected_state_revision < 1) return "state_revision_invalid";
    if (!validRows(message.params.layers, /^layer-[a-z][a-z-]{0,31}$/, 4) || !validRows(message.params.objects, /^shape-[0-9]{4,}$/, 128)) return "artisan_name_map_invalid";
  }
  return null;
}

export function rpcResult(id, result) { return {jsonrpc: "2.0", id, result}; }
export function rpcError(id, code, message) { return {jsonrpc: "2.0", id: id ?? null, error: {code, message}}; }
