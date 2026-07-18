from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from starbridge_mcp.domain.errors import ConfirmationRequiredError
from starbridge_mcp.storage.asset_store import AssetStore
from starbridge_mcp.storage.project_store import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_project_persists_atomically_and_survives_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = ProjectStore(root / "projects")
            project = store.create("示例项目", "vector-delivery-v1", "安全项目")
            updated = store.save(replace(project, description="更新后的描述"))

            reloaded = ProjectStore(root / "projects").get(project.project_id)
            temporary_files = list((root / "projects").rglob("*.tmp"))

        self.assertEqual("更新后的描述", updated.description)
        self.assertEqual(updated, reloaded)
        self.assertEqual([], temporary_files)

    def test_source_import_requires_confirmation_and_records_no_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "客户源图.png"
            source.write_bytes(b"public-test-fixture")
            assets = AssetStore(root / "app-data" / "projects")

            with self.assertRaises(ConfirmationRequiredError):
                assets.import_source("project-1", source, confirm_import=False)

            imported = assets.import_source("project-1", source, confirm_import=True)
            managed = root / "app-data" / imported.relative_path

            self.assertTrue(managed.is_file())
            self.assertEqual(source.read_bytes(), managed.read_bytes())
            self.assertEqual("客户源图.png", imported.basename)
            self.assertNotIn(str(root), str(imported.to_dict()))


if __name__ == "__main__":
    unittest.main()
