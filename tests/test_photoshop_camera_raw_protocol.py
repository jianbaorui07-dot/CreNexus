from __future__ import annotations

import unittest
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from examples.photoshop_bridge.scripts.camera_raw_tune import build_arguments
from starbridge_mcp.adapters.photoshop.camera_raw_protocol import build_camera_raw_tune_protocol, camera_raw_xmp_document, load_verified_descriptor_fixture
from starbridge_mcp.mcp_server import handle_request


REPO_ROOT = Path(__file__).resolve().parents[1]


class PhotoshopCameraRawProtocolTests(unittest.TestCase):
    def test_script_builds_reusable_tool_arguments(self) -> None:
        args = SimpleNamespace(
            source_path="<user-provided-raw-file>",
            source_mode="active_document",
            preset="blue_artwork_clean",
            descriptor_fixture_path=None,
            output_dir="examples/output/photoshop",
            basename="review",
            formats=["jpg"],
            export_after_apply=True,
            dry_run=True,
            confirm_apply=False,
            confirm_export=False,
            temperature=None,
            tint=None,
            exposure=0.5,
            contrast=8,
            highlights=20,
            shadows=-6,
            whites=20,
            blacks=-7,
            texture=11,
            clarity=None,
            dehaze=None,
            vibrance=12,
            saturation=None,
        )

        arguments = build_arguments(args)

        self.assertEqual("ps.camera_raw.tune", arguments["method"])
        self.assertEqual("explicit_path", arguments["source"]["mode"])
        self.assertEqual("examples/output/photoshop", arguments["output"]["dir"])
        self.assertEqual(0.5, arguments["params"]["exposure"])
        self.assertEqual(12, arguments["params"]["vibrance"])

    def test_xmp_document_contains_camera_raw_settings(self) -> None:
        xmp = camera_raw_xmp_document({"Exposure2012": "0.5", "Contrast2012": "8", "Vibrance": "12"})

        self.assertIn('xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"', xmp)
        self.assertIn('crs:Exposure2012="0.5"', xmp)
        self.assertIn('crs:Contrast2012="8"', xmp)
        self.assertIn('crs:Vibrance="12"', xmp)

    def test_export_script_refuses_without_confirmations(self) -> None:
        script_path = REPO_ROOT / "examples/photoshop_bridge/scripts/camera_raw_export.ps1"
        if shutil.which("powershell") is None and shutil.which("pwsh") is None:
            script = script_path.read_text(encoding="utf-8")
            self.assertIn("ConfirmApply", script)
            self.assertIn("ConfirmExport", script)
            self.assertIn("Refusing Camera Raw export without explicit confirmation", script)
            return

        powershell = shutil.which("powershell") or shutil.which("pwsh")
        assert powershell is not None
        completed = subprocess.run(
            [
                powershell,
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-InputPath",
                "missing.CR2",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout)

        self.assertFalse(payload["ok"])
        self.assertTrue(payload["dry_run"])
        self.assertIn("ConfirmApply", " ".join(payload["warnings"]))

    def test_protocol_builds_from_parameter_object(self) -> None:
        plan, errors = build_camera_raw_tune_protocol(
            {
                "source": {"mode": "explicit_path", "path": "<user-provided-raw-file>"},
                "output": {"dir": "examples/output/photoshop", "basename": "raw_tune_review", "formats": ["jpg"]},
                "params": {
                    "exposure": 0.5,
                    "contrast": 8,
                    "highlights": 20,
                    "shadows": -6,
                    "whites": 20,
                    "blacks": -7,
                    "texture": 11,
                    "vibrance": 12,
                },
            },
            REPO_ROOT,
        )

        self.assertEqual([], errors)
        assert plan is not None
        self.assertEqual("camera_raw_tune.v1", plan["protocol_version"])
        self.assertEqual("0.5", plan["xmp_settings"]["Exposure2012"])
        self.assertEqual("explicit_path", plan["source"]["mode"])
        self.assertEqual("<user-provided-raw-file>", plan["source"]["path"])
        self.assertEqual("examples/output/photoshop", plan["output"]["dir"])
        self.assertEqual(0.5, plan["params"]["exposure"])

    def test_protocol_rejects_output_escape(self) -> None:
        plan, errors = build_camera_raw_tune_protocol({"output": {"dir": "sandbox"}, "params": {}}, REPO_ROOT)

        self.assertIsNone(plan)
        self.assertIn("examples/output/photoshop", " ".join(errors))

    def test_protocol_rejects_unsafe_basename(self) -> None:
        plan, errors = build_camera_raw_tune_protocol(
            {"output": {"dir": "examples/output/photoshop", "basename": "../escape"}, "params": {}},
            REPO_ROOT,
        )

        self.assertIsNone(plan)
        self.assertIn("output.basename", " ".join(errors))

    def test_export_after_apply_requires_confirm_export_for_real_run(self) -> None:
        response = handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "ps.camera_raw.tune",
                    "arguments": {
                        "dry_run": False,
                        "confirm_apply": True,
                        "confirm_export": False,
                        "output": {"dir": "examples/output/photoshop", "export_after_apply": True},
                    },
                },
            }
        )
        assert response is not None
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("confirm_export", payload["message"])

    def test_descriptor_fixture_must_be_verified(self) -> None:
        plan, errors = build_camera_raw_tune_protocol({"params": {"exposure": 0.5}}, REPO_ROOT)
        self.assertEqual([], errors)
        assert plan is not None
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "protocol_version": "camera_raw_tune.v1",
                        "method": "ps.camera_raw.tune",
                        "descriptor_kind": "camera_raw_filter",
                        "verified": False,
                        "descriptors": [{"_obj": "Adobe Camera Raw Filter"}],
                    }
                ),
                encoding="utf-8",
            )
            fixture, fixture_errors = load_verified_descriptor_fixture({"descriptor_fixture_path": str(fixture_path)}, plan)

        self.assertIsNone(fixture)
        self.assertIn("verified=true", " ".join(fixture_errors))

    def test_verified_fixture_renders_parameter_template(self) -> None:
        plan, errors = build_camera_raw_tune_protocol({"params": {"exposure": 0.5}}, REPO_ROOT)
        self.assertEqual([], errors)
        assert plan is not None
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "protocol_version": "camera_raw_tune.v1",
                        "method": "ps.camera_raw.tune",
                        "descriptor_kind": "camera_raw_filter",
                        "verified": True,
                        "verified_by": "local_user",
                        "descriptors": [{"_obj": "Adobe Camera Raw Filter", "exposure": "{{params.exposure}}"}],
                    }
                ),
                encoding="utf-8",
            )
            fixture, fixture_errors = load_verified_descriptor_fixture({"descriptor_fixture_path": str(fixture_path)}, plan)

        self.assertEqual([], fixture_errors)
        assert fixture is not None
        self.assertTrue(fixture["verified"])
        self.assertEqual(0.5, fixture["descriptors"][0]["exposure"])

    def test_confirmed_run_with_verified_fixture_waits_for_uxp_connection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "fixture.json"
            fixture_path.write_text(
                json.dumps(
                    {
                        "protocol_version": "camera_raw_tune.v1",
                        "method": "ps.camera_raw.tune",
                        "descriptor_kind": "camera_raw_filter",
                        "verified": True,
                        "verified_by": "local_user",
                        "descriptors": [{"_obj": "Adobe Camera Raw Filter", "exposure": "{{params.exposure}}"}],
                    }
                ),
                encoding="utf-8",
            )
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "ps.camera_raw.tune",
                        "arguments": {
                            "dry_run": False,
                            "confirm_apply": True,
                            "descriptor_fixture_path": str(fixture_path),
                            "params": {"exposure": 0.5},
                        },
                    },
                }
            )
        assert response is not None
        payload = response["result"]["structuredContent"]

        self.assertFalse(payload["ok"])
        self.assertIn("UXP is not connected", payload["message"])
        self.assertTrue(payload["details"]["descriptor_fixture"]["available"])


if __name__ == "__main__":
    unittest.main()
