from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

from starbridge_mcp.adapters.autocad.live_session import (
    AutoCadVisibleSession,
    format_autocad_prompt,
    normalize_live_update,
)

ROOT = Path(__file__).resolve().parents[1]


def update(**overrides: object) -> dict:
    value = {
        "type": "codex_session",
        "protocol_version": 1,
        "session_id": "cad-demo",
        "bridge": "autocad",
        "mode": "structured",
        "phase": "running",
        "step": {"id": "dimensions", "label": "绘制尺寸", "index": 3, "total": 5},
        "message": "Codex 正在绘制尺寸标注",
        "progress": 60,
        "at": "2026-07-18T00:00:00Z",
    }
    value.update(overrides)
    return value


class FakeUtility:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def Prompt(self, value: str) -> None:  # noqa: N802 - AutoCAD COM casing
        self.prompts.append(value)


class FakeDocument:
    def __init__(self) -> None:
        self.Utility = FakeUtility()
        self.regens: list[int] = []

    def Regen(self, viewport: int) -> None:  # noqa: N802 - AutoCAD COM casing
        self.regens.append(viewport)


class FakeApplication:
    def __init__(self) -> None:
        self.ActiveDocument = FakeDocument()
        self.Visible = False


class LiveSessionProtocolTests(unittest.TestCase):
    def test_schema_and_python_normalizer_share_core_fields(self) -> None:
        schema = json.loads(
            (ROOT / "examples" / "live_session" / "starbridge_live_session.v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        normalized = normalize_live_update(update(), expected_bridge="autocad")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(set(schema["required"]), set(normalized))
        self.assertEqual("autocad", normalized["bridge"])

    def test_private_path_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "message_must_be_safe_display_text"):
            normalize_live_update(update(message="正在打开 C:/private/client.dwg"))

    def test_extra_fields_and_control_text_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown_session_field"):
            normalize_live_update(update(file_path="client.dwg"))
        with self.assertRaisesRegex(ValueError, "message_must_be_safe_display_text"):
            normalize_live_update(update(message="第一行\n第二行"))

    def test_autocad_prompt_is_visible_and_sanitized(self) -> None:
        prompt = format_autocad_prompt(update())
        self.assertIn("[Codex 60% · 3/5]", prompt)
        self.assertIn("绘制尺寸标注", prompt)

    def test_autocad_publisher_uses_active_document_prompt_and_regen(self) -> None:
        application = FakeApplication()
        result = AutoCadVisibleSession(application).publish(update())
        self.assertTrue(result["published"])
        self.assertTrue(application.Visible)
        self.assertEqual([1], application.ActiveDocument.regens)
        self.assertEqual(1, len(application.ActiveDocument.Utility.prompts))

    def test_cli_defaults_to_validation_only(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/publish_live_session.py",
                "--bridge",
                "autocad",
                "--message",
                "Codex 正在检查绘图",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["published"])


if __name__ == "__main__":
    unittest.main()
