from __future__ import annotations

import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from starbridge_mcp.vectorization.app_model import (
    AppInputError,
    AppParameters,
    build_run_config,
    parameters_for_mode,
    reference_id_for,
    result_metrics,
    validated_input_path,
)

HAS_PYSIDE6 = importlib.util.find_spec("PySide6") is not None


class VectorAppModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_dir.name)
        self.source = self.root / "private-client-filename.png"
        Image.new("RGBA", (16, 12), (20, 80, 180, 220)).save(self.source)

    def tearDown(self) -> None:
        self.temporary_dir.cleanup()

    def test_reference_id_is_deterministic_and_does_not_expose_filename(self) -> None:
        first = reference_id_for(self.source)
        second = reference_id_for(self.source)

        self.assertEqual(first, second)
        self.assertRegex(first, r"^job-[0-9a-f]{12}$")
        self.assertNotIn(self.source.stem, first)

    def test_mode_defaults_and_exact_parameter_lock(self) -> None:
        smart = parameters_for_mode("smart")
        lightweight = parameters_for_mode("lightweight")
        exact = parameters_for_mode("exact")
        artisan = parameters_for_mode("artisan")

        self.assertEqual(smart.colors, 24)
        self.assertEqual(lightweight.colors, 8)
        self.assertIsNone(exact.colors)
        self.assertIsNone(exact.simplify_ratio)
        self.assertEqual(artisan.colors, 16)
        self.assertGreater(artisan.simplify_ratio or 0, smart.simplify_ratio or 0)

        config = build_run_config(
            self.source,
            AppParameters(
                mode="exact",
                colors=99,
                max_dimension=100,
                simplify_ratio=0.05,
                min_region_area=99,
                alpha_threshold=99,
            ),
        )
        self.assertEqual(config.mode, "exact")
        self.assertIsNone(config.colors)
        self.assertIsNone(config.max_dimension)

    def test_input_contract_rejects_missing_or_unsupported_files(self) -> None:
        self.assertEqual(validated_input_path(self.source), self.source.resolve())
        with self.assertRaises(AppInputError):
            validated_input_path(self.root / "missing.png")
        text_file = self.root / "not-an-image.txt"
        text_file.write_text("not an image", encoding="utf-8")
        with self.assertRaises(AppInputError):
            validated_input_path(text_file)

    def test_result_metrics_formats_product_summary(self) -> None:
        metrics = result_metrics(
            {
                "vector": {
                    "color_count": 8,
                    "subpaths": 1234,
                    "points": 5678,
                    "svg_bytes": 2048,
                },
                "elapsed_seconds": 1.234,
                "exact_validation": None,
            }
        )

        self.assertIn(("颜色", "8"), metrics)
        self.assertIn(("子路径", "1,234"), metrics)
        self.assertIn(("SVG", "2.0 KB"), metrics)


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 optional dependency not installed")
class VectorAppGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from starbridge_mcp.vectorization.gui import MainWindow

        self.window = MainWindow()

    def tearDown(self) -> None:
        self.window.close()

    def test_window_defaults_to_smart_and_locks_exact_controls(self) -> None:
        self.assertEqual(self.window.selected_mode, "smart")
        self.assertEqual(self.window.colors_input.value(), 24)

        self.window._select_mode("lightweight")
        self.assertEqual(self.window.selected_mode, "lightweight")
        self.assertEqual(self.window.colors_input.value(), 8)

        self.window._select_mode("exact")
        self.assertEqual(self.window.selected_mode, "exact")
        self.assertFalse(self.window.colors_input.isEnabled())
        self.assertTrue(self.window.exact_note.isVisible() or not self.window.isVisible())

        self.window._select_mode("artisan")
        self.assertEqual(self.window.selected_mode, "artisan")
        self.assertEqual(self.window.colors_input.value(), 16)
        self.assertTrue(self.window.colors_input.isEnabled())

    def test_window_completes_a_background_lightweight_job(self) -> None:
        from starbridge_mcp.vectorization import engine

        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            output_root = root / "examples" / "output" / "vectorization"
            source = root / "ui-source.png"
            Image.new("RGBA", (48, 32), (40, 110, 220, 255)).save(source)
            with (
                mock.patch.object(engine, "REPO_ROOT", root),
                mock.patch.object(engine, "OUTPUT_ROOT", output_root),
            ):
                self.window.set_source(str(source))
                self.window._select_mode("lightweight")
                self.window.start_conversion()
                deadline = time.monotonic() + 10
                while self.window._thread is not None and time.monotonic() < deadline:
                    self.app.processEvents()
                    time.sleep(0.01)
                self.app.processEvents()

            self.assertIsNone(self.window._thread)
            self.assertTrue(self.window.open_output_button.isEnabled())
            self.assertIn("完成", self.window.status_label.text())
            self.assertIsNotNone(self.window.result_preview._source_pixmap)


if __name__ == "__main__":
    unittest.main()
