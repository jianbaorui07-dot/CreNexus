from __future__ import annotations

import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any

from starbridge_mcp.vectorization.artisan_direction import (
    build_illustrator_map,
    compile_art_direction,
)
from starbridge_mcp.vectorization.artisan_edit import build_edit_index
from starbridge_mcp.vectorization.artisan_illustrator import (
    ArtisanIllustratorError,
    compile_apply_plan,
    execute_apply_plan,
    load_apply_plan,
    probe_illustrator_state,
)
from starbridge_mcp.vectorization.svg_verify import verify_svg_artifact


class FakeTransport:
    def __init__(
        self,
        *,
        revision: int = 7,
        readback_ok: bool = True,
        commit_ok: bool = True,
        unavailable: bool = False,
    ) -> None:
        self.revision = revision
        self.readback_ok = readback_ok
        self.commit_ok = commit_ok
        self.unavailable = unavailable
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((operation, payload))
        if self.unavailable:
            raise urllib.error.URLError("offline")
        if operation == "state":
            return {
                "ok": True,
                "revision": self.revision,
                "stale": False,
                "state": {"document": {"page_items": 2}},
            }
        method = payload["method"]
        params = payload["params"]
        if method == "illustrator.apply_artisan_map":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "ok": True,
                    "applied_layers": len(params["layers"]),
                    "applied_objects": len(params["objects"]),
                },
            }
        if method == "illustrator.readback_artisan_map":
            expected = 2
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "ok": self.readback_ok,
                    "matched": expected if self.readback_ok else expected - 1,
                    "expected": expected,
                },
            }
        if method == "illustrator.rollback_artisan_map":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {"ok": True, "restored": 2},
            }
        if method == "illustrator.commit_artisan_map":
            return {
                "jsonrpc": "2.0",
                "id": payload["id"],
                "result": {
                    "ok": self.commit_ok,
                    "committed": 2 if self.commit_ok else 1,
                },
            }
        raise AssertionError(method)


class ArtisanIllustratorApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.svg = self.root / "vector.svg"
        self.svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" '
            'viewBox="0 0 100 100">\n'
            '<g id="layer-subject" data-role="subject">\n'
            '<path id="shape-0002" data-role="subject" data-depth="0" '
            'data-parent="none" data-name="朱红装饰" fill="#b94f42" '
            'fill-rule="evenodd" stroke="none" '
            'd="M 10 10 L 30 10 L 30 30 L 10 30 Z"/>\n'
            "</g>\n"
            "</svg>\n",
            encoding="utf-8",
        )
        evidence = verify_svg_artifact(self.svg)
        base_index = build_edit_index(
            structure_ref="artisan:0123456789ab",
            strategy="paint-base",
            svg_sha256=evidence["sha256"],
            objects=[["shape-0002", "paint-region", [10, 10, 20, 20], 4, 1, "朱红装饰"]],
        )
        direction = compile_art_direction(
            {
                "base_edit_ref": base_index["edit_ref"],
                "profile_ref": "style:abcdef012345",
                "palette_groups": [],
                "object_names": [["shape-0002", "朱红装饰"]],
                "layer_names": [["subject", "主体色块"]],
            }
        )
        current_index = build_edit_index(
            structure_ref="artisan:0123456789ab",
            strategy="manual-direction-v1",
            svg_sha256=evidence["sha256"],
            objects=[["shape-0002", "paint-region", [10, 10, 20, 20], 4, 1, "朱红装饰"]],
            parent_edit_ref=base_index["edit_ref"],
        )
        mapping = build_illustrator_map(
            direction_ref=direction["direction_ref"],
            svg_sha256=evidence["sha256"],
            edit_ref=current_index["edit_ref"],
            layer_names=[["layer-subject", "主体色块"]],
            object_names=[["shape-0002", "朱红装饰"]],
        )
        self.index = self.root / "index.json"
        self.direction = self.root / "direction.json"
        self.mapping = self.root / "map.json"
        self.index.write_text(json.dumps(current_index, ensure_ascii=False), encoding="utf-8")
        self.direction.write_text(json.dumps(direction, ensure_ascii=False), encoding="utf-8")
        self.mapping.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
        plan = compile_apply_plan(
            svg_path=str(self.svg),
            index_path=str(self.index),
            direction_path=str(self.direction),
            map_path=str(self.mapping),
            expected_state_revision=7,
        )
        self.plan = self.root / "plan.json"
        self.plan.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        self.plan_value = plan

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def execute(self, transport: FakeTransport, *, confirm: bool = True) -> dict[str, Any]:
        return execute_apply_plan(
            plan_path=str(self.plan),
            map_path=str(self.mapping),
            confirm_write=confirm,
            approval_ref=self.plan_value["approval_ref"] if confirm else "approve:000000000000",
            transport=transport,
        )

    def test_apply_plan_is_compact_bound_and_contains_no_names_or_paths(self) -> None:
        text = self.plan.read_text(encoding="utf-8")
        plan = load_apply_plan(str(self.plan))
        self.assertRegex(plan["plan_ref"], r"^apply-plan:[0-9a-f]{12}$")
        self.assertRegex(plan["approval_ref"], r"^approve:[0-9a-f]{12}$")
        self.assertLess(len(text.encode("utf-8")), 1000)
        self.assertNotIn("朱红", text)
        self.assertNotIn(str(self.root), text)

    def test_explicit_approval_is_required_before_transport(self) -> None:
        transport = FakeTransport()
        receipt = self.execute(transport, confirm=False)
        self.assertEqual(receipt["status"], "awaiting_approval")
        self.assertFalse(receipt["executed"])
        self.assertEqual(transport.calls, [])

    def test_confirmed_apply_and_readback_complete(self) -> None:
        transport = FakeTransport()
        receipt = self.execute(transport)
        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["status"], "completed")
        self.assertTrue(receipt["verified"])
        receipt_text = json.dumps(receipt, ensure_ascii=False, separators=(",", ":"))
        self.assertLess(len(receipt_text.encode("utf-8")), 1000)
        self.assertNotIn("朱红", receipt_text)
        self.assertNotIn(str(self.root), receipt_text)
        methods = [
            payload["method"] for operation, payload in transport.calls if operation == "rpc"
        ]
        self.assertEqual(
            methods,
            [
                "illustrator.apply_artisan_map",
                "illustrator.readback_artisan_map",
                "illustrator.commit_artisan_map",
            ],
        )
        apply_params = transport.calls[1][1]["params"]
        self.assertTrue(apply_params["confirm_write"])
        self.assertEqual(apply_params["expected_state_revision"], 7)

    def test_readback_failure_rolls_back(self) -> None:
        transport = FakeTransport(readback_ok=False)
        receipt = self.execute(transport)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "rolled_back")
        self.assertTrue(receipt["rolled_back"])
        methods = [
            payload["method"] for operation, payload in transport.calls if operation == "rpc"
        ]
        self.assertEqual(methods[-1], "illustrator.rollback_artisan_map")

    def test_commit_failure_rolls_back_verified_changes(self) -> None:
        transport = FakeTransport(commit_ok=False)
        receipt = self.execute(transport)
        self.assertFalse(receipt["ok"])
        self.assertEqual(receipt["status"], "rolled_back")
        self.assertEqual(receipt["error_code"], "commit_failed")
        methods = [
            payload["method"] for operation, payload in transport.calls if operation == "rpc"
        ]
        self.assertEqual(methods[-1], "illustrator.rollback_artisan_map")

    def test_stale_or_unavailable_session_soft_fails_without_write(self) -> None:
        stale = FakeTransport(revision=8)
        receipt = self.execute(stale)
        self.assertEqual(receipt["status"], "stale_plan")
        self.assertFalse(any(operation == "rpc" for operation, _ in stale.calls))
        unavailable = FakeTransport(unavailable=True)
        receipt = self.execute(unavailable)
        self.assertEqual(receipt["status"], "not_available")
        self.assertFalse(receipt["executed"])

    def test_probe_returns_only_compact_redacted_session_readiness(self) -> None:
        result = probe_illustrator_state(transport=FakeTransport())
        self.assertTrue(result["ready"])
        self.assertEqual(result["state_revision"], 7)
        self.assertNotIn("state", result)
        unavailable = probe_illustrator_state(transport=FakeTransport(unavailable=True))
        self.assertEqual(unavailable["status"], "not_available")

    def test_plan_rejects_a_mismatched_svg_set(self) -> None:
        self.svg.write_text(self.svg.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with self.assertRaises(ArtisanIllustratorError) as raised:
            compile_apply_plan(
                svg_path=str(self.svg),
                index_path=str(self.index),
                direction_path=str(self.direction),
                map_path=str(self.mapping),
                expected_state_revision=7,
            )
        self.assertEqual(raised.exception.code, "illustrator_apply_binding_mismatch")


if __name__ == "__main__":
    unittest.main()
