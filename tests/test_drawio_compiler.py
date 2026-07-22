from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from starbridge_mcp.adapters.drawio.compiler import compile_input, compile_spec, recipe_spec
from starbridge_mcp.adapters.drawio.model import (
    DiagramCell,
    document_cell_hashes,
    document_sha256,
    from_drawio_xml,
    to_drawio_xml,
)
from starbridge_mcp.adapters.drawio.service import DiagramForgeService
from starbridge_mcp.adapters.drawio.validation import validate_document


class DiagramForgeCompilerTests(unittest.TestCase):
    def test_probe_accepts_explicit_drawio_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            executable = root / "drawio.exe"
            executable.write_bytes(b"test")
            with patch.dict(os.environ, {"DRAWIO_EXE": str(executable)}):
                details = DiagramForgeService(root).probe({})["details"]

        self.assertTrue(details["drawio_desktop_available"])
        self.assertTrue(details["pdf_export"])

    def test_probe_rejects_missing_explicit_drawio_executable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with patch.dict(os.environ, {"DRAWIO_EXE": str(root / "missing.exe")}):
                details = DiagramForgeService(root).probe({})["details"]

        self.assertFalse(details["drawio_desktop_available"])
        self.assertFalse(details["pdf_export"])

    def test_research_recipe_has_expected_structure_and_stable_ids(self) -> None:
        first = compile_spec(recipe_spec("research-framework-v1"))
        second = compile_spec(recipe_spec("research-framework-v1"))

        self.assertEqual(first.to_dict(), second.to_dict())
        report = validate_document(first)
        self.assertTrue(report.ok)
        self.assertEqual(report.metrics["vertex_count"], 8)
        self.assertEqual(report.metrics["connector_count"], 7)
        self.assertEqual(report.metrics["layer_count"], 2)

    def test_mermaid_and_csv_inputs_compile(self) -> None:
        mermaid = compile_input(
            input_format="mermaid", content="flowchart LR\nA[Input] --> B[Process]\nB --> C[Output]"
        )
        csv_document = compile_input(
            input_format="csv",
            content="id,label,source,target\na,Alpha,,\nb,Beta,,\ne1,flow,a,b\n",
        )

        self.assertTrue(validate_document(mermaid).ok)
        self.assertTrue(validate_document(csv_document).ok)
        self.assertEqual(len(csv_document.pages[0].cells), 3)

    def test_native_xml_roundtrip_preserves_element_hashes(self) -> None:
        document = compile_spec(recipe_spec("system-architecture-v1"))
        xml_text = to_drawio_xml(document)
        reopened = from_drawio_xml(xml_text)

        self.assertEqual(document_cell_hashes(document), document_cell_hashes(reopened))
        self.assertEqual(document_sha256(document), document_sha256(reopened))
        self.assertTrue(validate_document(reopened).ok)
        imported = compile_input(input_format="drawio_xml", content=xml_text)
        self.assertEqual(document_cell_hashes(document), document_cell_hashes(imported))

    def test_container_parent_relationship_is_preserved(self) -> None:
        document = compile_spec(
            {
                "title": "Container",
                "pages": [
                    {
                        "name": "Page",
                        "nodes": [
                            {
                                "key": "container",
                                "label": "Container",
                                "container": True,
                                "width": 400,
                                "height": 300,
                            },
                            {"key": "child", "label": "Child", "parent_key": "container"},
                        ],
                    }
                ],
            }
        )
        cells = {cell.metadata["semantic_key"]: cell for cell in document.pages[0].cells}

        self.assertEqual(cells["child"].parent, cells["container"].cell_id)
        self.assertTrue(validate_document(document).ok)
        reopened = from_drawio_xml(to_drawio_xml(document))
        self.assertEqual(
            next(
                cell for cell in reopened.pages[0].cells if cell.cell_id == cells["child"].cell_id
            ).parent,
            cells["container"].cell_id,
        )

    def test_validation_rejects_dangling_connector(self) -> None:
        document = compile_spec(recipe_spec("system-architecture-v1"))
        page = document.pages[0]
        page.cells.append(
            DiagramCell(
                cell_id="dangling-edge",
                kind="edge",
                parent=next(iter(page.layers)),
                source=next(cell.cell_id for cell in page.cells if cell.kind == "vertex"),
                target="missing",
            )
        )

        report = validate_document(document)
        self.assertFalse(report.ok)
        self.assertIn("missing_edge_target", {item["code"] for item in report.errors})

    def test_validation_rejects_active_html_and_external_image_styles(self) -> None:
        document = compile_spec(recipe_spec("system-architecture-v1"))
        vertices = [cell for cell in document.pages[0].cells if cell.kind == "vertex"]
        vertices[0].label = '<img src="https://example.invalid/private.png">'
        vertices[1].style += "image=https://example.invalid/private.png;"

        report = validate_document(document)
        codes = {item["code"] for item in report.errors}

        self.assertFalse(report.ok)
        self.assertIn("unsafe_html_label", codes)
        self.assertIn("unsafe_external_style", codes)


class DiagramForgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = DiagramForgeService(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create(self) -> dict:
        return self.service.create(
            {
                "input_format": "spec",
                "recipe_id": "research-framework-v1",
                "output_base": "sandbox/diagramforge/research",
                "confirm_write": True,
            }
        )

    def test_write_requires_confirmation(self) -> None:
        result = self.service.create(
            {"recipe_id": "research-framework-v1", "output_base": "sandbox/nope"}
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "confirmation_required")

    def test_create_writes_native_preview_manifest_and_reopens(self) -> None:
        result = self._create()

        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["validated_after_reopen"])
        self.assertTrue(result["details"]["roundtrip_hash_match"])
        files = result["details"]["files"]
        self.assertEqual(len(files), 3)
        for relative in files:
            self.assertTrue((self.root / relative).is_file())
        manifest = json.loads((self.root / files[-1]).read_text(encoding="utf-8"))
        self.assertTrue(manifest["validated_after_reopen"])
        self.assertFalse(manifest["source_paths_persisted"])

    def test_patch_changes_one_element_and_preserves_unrelated_hashes(self) -> None:
        self._create()
        relative = "sandbox/diagramforge/research.drawio"
        before = self.service.inspect({"path": relative})
        hashes = before["details"]["cell_hashes"]
        before_document_hash = before["details"]["document_sha256"]
        target = next(iter(hashes))

        result = self.service.patch(
            {
                "path": relative,
                "patches": [{"op": "set_label", "element_id": target, "label": "Updated target"}],
                "confirm_write": True,
            }
        )

        self.assertTrue(result["ok"])
        self.assertTrue(result["details"]["unrelated_region_hashes_stable"])
        self.assertEqual(result["details"]["unchanged_element_count"], len(hashes) - 1)

        rolled_back = self.service.rollback({"path": relative, "confirm_write": True})
        restored = self.service.inspect({"path": relative})
        self.assertTrue(rolled_back["ok"])
        self.assertEqual(restored["details"]["document_sha256"], before_document_hash)
        self.assertEqual(restored["details"]["cell_hashes"], hashes)

    def test_paths_cannot_escape_safe_roots(self) -> None:
        with self.assertRaises(ValueError):
            self.service.inspect({"path": "../private.drawio"})

    def test_batch_plan_is_idempotent_and_resumable(self) -> None:
        jobs = [
            {"recipe_id": "system-architecture-v1", "parameters": {"title": "A"}},
            {"recipe_id": "system-architecture-v1", "parameters": {"title": "B"}},
        ]
        first = self.service.batch({"jobs": jobs, "concurrency_limit": 4})
        completed = [first["details"]["jobs"][0]["job_id"]]
        resumed = self.service.batch({"jobs": jobs, "completed_job_ids": completed})

        self.assertEqual(
            first["details"]["jobs"], self.service.batch({"jobs": jobs})["details"]["jobs"]
        )
        self.assertEqual(resumed["details"]["completed_count"], 1)
        self.assertEqual(resumed["details"]["pending_count"], 1)

    def test_export_uses_safe_default_relative_path(self) -> None:
        self._create()

        result = self.service.export(
            {
                "path": "sandbox/diagramforge/research.drawio",
                "format": "svg",
                "confirm_write": True,
            }
        )

        self.assertTrue(result["ok"])
        self.assertTrue((self.root / "sandbox/diagramforge/research.drawio.svg").is_file())

    def test_handoff_plan_is_hash_bound_and_redacts_source_path(self) -> None:
        self._create()

        result = self.service.handoff_plan(
            {
                "path": "sandbox/diagramforge/research.drawio.svg",
                "target": "photoshop",
            }
        )

        self.assertTrue(result["ok"])
        self.assertFalse(result["details"]["writes_files"])
        self.assertTrue(result["details"]["downstream_confirmation_required"])
        self.assertFalse(result["details"]["source_path_exposed"])
        self.assertNotIn(str(self.root), json.dumps(result))


if __name__ == "__main__":
    unittest.main()
