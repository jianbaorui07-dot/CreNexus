from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "uxp" / "photoshop-bridge" / "src" / "batchplay-runner.js"
SCHEMA = ROOT / "examples" / "photoshop_bridge" / "protocols" / "modal_execution.v1.schema.json"


class PhotoshopUxpModalEnvelopeTests(unittest.TestCase):
    def test_schema_is_closed_and_has_bounded_terminal_states(self) -> None:
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            {"completed", "cancelled", "failed"},
            set(schema["properties"]["status"]["enum"]),
        )
        timeout = schema["properties"]["timeout_seconds"]
        self.assertEqual(1, timeout["minimum"])
        self.assertEqual(30, timeout["maximum"])
        self.assertFalse(schema["properties"]["history"]["additionalProperties"])
        self.assertIn("required_for_write", schema["properties"]["history"]["required"])

    def test_runner_uses_timeout_cancellation_and_explicit_history_outcome(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")

        for required in (
            "timeOut: timeoutSeconds",
            "executionContext?.isCancelled",
            "hostControl.suspendHistory",
            "hostControl.resumeHistory",
            "resumeHistory(suspension, true)",
            "resumeHistory(suspension, false)",
            '"cancelled"',
            '"failed"',
            'status: "completed"',
            'MODAL_SCHEMA_VERSION = "starbridge.photoshop-modal.v1"',
            "schema_version: MODAL_SCHEMA_VERSION",
        ):
            self.assertIn(required, source)

    def test_runner_reports_commit_rollback_cancel_and_redacts_paths(self) -> None:
        script = f"""
import fs from "node:fs";
const calls = {{ options: [], resumes: [] }};
const executionContext = {{
  isCancelled: false,
  hostControl: {{
    suspendHistory: async (options) => ({{ id: "history-1", ...options }}),
    resumeHistory: async (suspension, commit) => calls.resumes.push(commit),
  }},
}};
globalThis.require = (name) => {{
  if (name !== "photoshop") throw new Error("unexpected_module");
  return {{
    action: {{ batchPlay: async () => [] }},
    app: {{ activeDocument: {{ id: 42 }} }},
    core: {{
      executeAsModal: async (handler, options) => {{
        calls.options.push(options);
        return handler(executionContext);
      }},
    }},
  }};
}};
let source = fs.readFileSync({json.dumps(str(RUNNER))}, "utf8");
source = source.replace(
  'import {{ validateDescriptor }} from "./batchplay-schema.js";',
  'const validateDescriptor = () => ({{ allowed: true }});',
);
const moduleUrl = `data:text/javascript;base64,${{Buffer.from(source).toString("base64")}}`;
const runner = await import(moduleUrl);
const success = await runner.runModalJob(
  "ps.test.write",
  {{ commandName: "Test Commit", timeoutSeconds: 7 }},
  async () => ({{ warnings: ["C:/Users/<USER_HOME>/source.psd"] }}),
);
const failed = await runner.runModalJob(
  "ps.test.write",
  {{ commandName: "Test Rollback" }},
  async () => {{ throw new Error("C:/Users/<USER_HOME>/source.psd failed"); }},
);
const cancelled = await runner.runModalJob(
  "ps.test.write",
  {{ commandName: "Test Cancel" }},
  async (context) => {{ context.isCancelled = true; throw new Error("user_cancelled"); }},
);
process.stdout.write(JSON.stringify({{ success, failed, cancelled, calls }}));
"""
        process = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads(process.stdout)

        self.assertEqual("completed", payload["success"]["modal"]["status"])
        self.assertTrue(payload["success"]["modal"]["history"]["committed"])
        self.assertTrue(payload["success"]["modal"]["history"]["required_for_write"])
        self.assertEqual(7, payload["success"]["modal"]["timeout_seconds"])
        self.assertEqual(7, payload["calls"]["options"][0]["timeOut"])
        self.assertIn("<redacted-path>", payload["success"]["warnings"][0])
        self.assertEqual("failed", payload["failed"]["modal"]["status"])
        self.assertTrue(payload["failed"]["modal"]["history"]["rolled_back"])
        self.assertIn("<redacted-path>", payload["failed"]["errors"][0]["message"])
        self.assertEqual("cancelled", payload["cancelled"]["modal"]["status"])
        self.assertTrue(payload["cancelled"]["modal"]["cancelled"])

    def test_required_history_fails_closed_before_handler_or_completion(self) -> None:
        script = f"""
import fs from "node:fs";
let handlerCalledWithoutControl = false;
const contexts = [
  {{ isCancelled: false, hostControl: {{}} }},
  {{
    isCancelled: false,
    hostControl: {{
      suspendHistory: async (options) => ({{ id: "history-1", ...options }}),
      resumeHistory: async () => {{}},
    }},
  }},
];
globalThis.require = () => ({{
  action: {{ batchPlay: async () => [] }},
  app: {{ activeDocument: {{ id: 42 }} }},
  core: {{ executeAsModal: async (handler) => handler(contexts.shift()) }},
}});
let source = fs.readFileSync({json.dumps(str(RUNNER))}, "utf8");
source = source.replace(
  'import {{ validateDescriptor }} from "./batchplay-schema.js";',
  'const validateDescriptor = () => ({{ allowed: true }});',
);
const runner = await import(`data:text/javascript;base64,${{Buffer.from(source).toString("base64")}}`);
const unsupported = await runner.runModalJob(
  "ps.test.write",
  {{ historyTarget: "active_document" }},
  async () => {{ handlerCalledWithoutControl = true; return {{}}; }},
);
const omitted = await runner.runModalJob(
  "ps.test.write",
  {{ historyTarget: "handler_document" }},
  async () => ({{}}),
);
process.stdout.write(JSON.stringify({{ unsupported, omitted, handlerCalledWithoutControl }}));
"""
        process = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        payload = json.loads(process.stdout)

        self.assertFalse(payload["handlerCalledWithoutControl"])
        for key in ("unsupported", "omitted"):
            result = payload[key]
            self.assertFalse(result["success"])
            self.assertEqual("failed", result["modal"]["status"])
            self.assertTrue(result["modal"]["history"]["required_for_write"])
            self.assertEqual("history_control_failed", result["errors"][0]["code"])

    def test_runner_redacts_error_paths_and_keeps_batchplay_on_sandbox_copy(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")

        self.assertIn("redacted-path", source)
        self.assertIn("document.duplicate", source)
        self.assertIn("registerAutoCloseDocument", source)
        self.assertIn("unregisterAutoCloseDocument", source)
        self.assertIn('historyTarget: "handler_document"', source)
        self.assertNotIn("synchronousExecution: true", source)


if __name__ == "__main__":
    unittest.main()
