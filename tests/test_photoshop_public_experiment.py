from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset import (
    PUBLIC_DATASET_SCHEMA,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.public_experiment import (
    PUBLIC_EXPERIMENT_SCHEMA,
    run_public_client_mode_experiment,
)


class PhotoshopPublicExperimentTests(unittest.TestCase):
    def make_line_art(self, path: Path) -> None:
        image = Image.new("RGB", (300, 220), "white")
        draw = ImageDraw.Draw(image)
        draw.ellipse((35, 25, 260, 175), outline="black", width=4)
        for y in range(45, 170, 9):
            draw.arc((45, y - 20, 250, y + 30), 10, 170, fill="black", width=2)
        image.save(path)

    def make_poster(self, path: Path) -> None:
        image = Image.new("RGB", (260, 360), (22, 48, 82))
        draw = ImageDraw.Draw(image)
        draw.ellipse((55, 75, 210, 235), fill=(232, 115, 55))
        draw.text((35, 285), "PUBLIC POSTER", fill="white")
        image.save(path)

    def test_license_verified_dataset_runs_explicit_client_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset_root = root / "dataset"
            assets = dataset_root / "assets"
            assets.mkdir(parents=True)
            self.make_line_art(assets / "line.png")
            self.make_poster(assets / "poster.png")
            dataset = {
                "schema_version": PUBLIC_DATASET_SCHEMA,
                "license_verified": True,
                "private_paths_recorded": False,
                "items": [
                    {
                        "id": "line_case",
                        "use_case": "line_art",
                        "license_family": "public_domain",
                        "local_asset": "assets/line.png",
                    },
                    {
                        "id": "poster_case",
                        "use_case": "poster",
                        "license_family": "cc0",
                        "local_asset": "assets/poster.png",
                    },
                ],
            }
            manifest_path = dataset_root / "dataset_manifest.json"
            manifest_path.write_text(json.dumps(dataset), encoding="utf-8")
            output = root / "experiment"
            result = run_public_client_mode_experiment(manifest_path, output)
            self.assertTrue(result["ok"])
            self.assertEqual(PUBLIC_EXPERIMENT_SCHEMA, result["schema_version"])
            self.assertEqual(2, result["case_count"])
            self.assertTrue(result["license_verified_inputs"])
            self.assertTrue(result["simulated_client_mode"])
            self.assertFalse(result["automatic_outputs_are_training_labels"])
            self.assertTrue(
                all(
                    case["ground_truth_status"] == "unreviewed_candidate_output"
                    for case in result["cases"]
                )
            )
            report_text = (output / "experiment_report.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)


if __name__ == "__main__":
    unittest.main()
