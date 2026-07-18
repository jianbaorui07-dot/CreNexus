const PHASES = new Set(["queued", "running", "completed", "failed", "cancelled", "needs_user"]);
const MODES = new Set(["structured", "computer_use"]);
const BRIDGES = new Set(["photoshop", "illustrator", "autocad"]);
const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/;
const PRIVATE_PATH = /(?:[A-Za-z]:[\\/]|\\\\|file:|\/Users\/|\/home\/)/i;
const CONTROL_TEXT = /[\u0000-\u001f\u007f]/;
const UPDATE_FIELDS = new Set(["type", "protocol_version", "session_id", "bridge", "mode", "phase", "step", "message", "progress", "at"]);
const STEP_FIELDS = new Set(["id", "label", "index", "total"]);

function safeIdentifier(value, field) {
  const normalized = String(value || "");
  if (!IDENTIFIER.test(normalized)) throw new Error(`${field}_must_be_safe_identifier`);
  return normalized;
}

function safeDisplayText(value, field, maximum) {
  const normalized = String(value || "").trim();
  if (!normalized || normalized.length > maximum || PRIVATE_PATH.test(normalized) || CONTROL_TEXT.test(normalized)) {
    throw new Error(`${field}_must_be_safe_display_text`);
  }
  return normalized;
}

function boundedInteger(value, field, minimum, maximum) {
  const normalized = Number(value);
  if (!Number.isInteger(normalized) || normalized < minimum || normalized > maximum) {
    throw new Error(`${field}_out_of_range`);
  }
  return normalized;
}

export function normalizeLiveSession(value, expectedBridge) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("session_update_must_be_object");
  }
  if (Object.keys(value).some(field => !UPDATE_FIELDS.has(field))) {
    throw new Error("unknown_session_field");
  }
  if (value.type !== "codex_session" || value.protocol_version !== 1) {
    throw new Error("unsupported_session_protocol");
  }
  const bridge = safeIdentifier(value.bridge, "bridge");
  if (!BRIDGES.has(bridge) || (expectedBridge && bridge !== expectedBridge)) {
    throw new Error("bridge_mismatch");
  }
  const phase = safeIdentifier(value.phase, "phase");
  if (!PHASES.has(phase)) throw new Error("unsupported_session_phase");
  const mode = safeIdentifier(value.mode || "structured", "mode");
  if (!MODES.has(mode)) throw new Error("unsupported_session_mode");

  const step = value.step;
  if (!step || typeof step !== "object" || Array.isArray(step)) {
    throw new Error("step_must_be_object");
  }
  if (Object.keys(step).some(field => !STEP_FIELDS.has(field))) {
    throw new Error("unknown_step_field");
  }
  const index = boundedInteger(step.index, "step_index", 1, 1000);
  const total = boundedInteger(step.total, "step_total", 1, 1000);
  if (index > total) throw new Error("step_index_exceeds_total");

  const parsedAt = new Date(value.at || new Date().toISOString());
  if (Number.isNaN(parsedAt.getTime())) throw new Error("at_must_be_iso_datetime");

  return {
    type: "codex_session",
    protocol_version: 1,
    session_id: safeIdentifier(value.session_id, "session_id"),
    bridge,
    mode,
    phase,
    step: {
      id: safeIdentifier(step.id, "step_id"),
      label: safeDisplayText(step.label, "step_label", 80),
      index,
      total,
    },
    message: safeDisplayText(value.message, "message", 160),
    progress: boundedInteger(value.progress, "progress", 0, 100),
    at: parsedAt.toISOString(),
  };
}

export function rpcLiveSession({ bridge, message, phase, errorMessage = "" }) {
  const method = safeIdentifier(message?.method || "unknown", "method");
  const requestId = String(message?.id ?? "request").replace(/[^A-Za-z0-9_.:-]/g, "-").slice(0, 48) || "request";
  const phaseMessages = {
    running: `Codex 正在执行 ${method}`,
    completed: `Codex 已完成 ${method}`,
    failed: errorMessage ? `Codex 执行失败：${method}` : `Codex 未能完成 ${method}`,
  };
  return normalizeLiveSession(
    {
      type: "codex_session",
      protocol_version: 1,
      session_id: `rpc-${requestId}`,
      bridge,
      mode: "structured",
      phase,
      step: { id: method, label: method, index: 1, total: 1 },
      message: phaseMessages[phase] || `Codex ${phase}: ${method}`,
      progress: phase === "running" ? 50 : 100,
      at: new Date().toISOString(),
    },
    bridge,
  );
}

export function createLiveSessionStore(bridge, broadcast = () => {}) {
  let current = null;
  const history = [];

  return {
    publish(value) {
      const update = normalizeLiveSession(value, bridge);
      current = update;
      history.push(update);
      if (history.length > 50) history.shift();
      broadcast(update);
      return update;
    },
    snapshot() {
      return { ok: true, current, history: [...history] };
    },
    current() {
      return current;
    },
    summary() {
      return current
        ? {
            active: ["queued", "running", "needs_user"].includes(current.phase),
            session_id: current.session_id,
            phase: current.phase,
            progress: current.progress,
            updated_at: current.at,
          }
        : { active: false, session_id: null, phase: null, progress: 0, updated_at: null };
    },
  };
}
