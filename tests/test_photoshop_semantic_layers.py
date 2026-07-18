from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image, ImageDraw

from starbridge_mcp.adapters.photoshop.semantic_layers.cli import _public_payload
from starbridge_mcp.adapters.photoshop.semantic_layers.intent import (
    INTENT_SCHEMA_VERSION,
    normalise_intent_profile,
    recommended_intent_profile,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.manifest import (
    SCHEMA_VERSION,
    load_manifest,
    resolve_layer_sources,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.pipeline import (
    PIPELINE_VERSION,
    DecompositionOptions,
    _cache_key,
    _validate_review_patch,
    apply_review_patch,
    batch_decompose,
    decompose_image,
    plan_image,
)
from starbridge_mcp.adapters.photoshop.semantic_layers.regression import (
    REGRESSION_SCHEMA_VERSION,
    run_synthetic_regression,
)

IMAGE_RUNTIME_DISCOVERABLE = all(
    importlib.util.find_spec(module_name) is not None for module_name in ("cv2", "numpy", "PIL")
)
REQUIRE_IMAGE_RUNTIME = os.environ.get("STARBRIDGE_REQUIRE_IMAGE_TO_PSD_RUNTIME") == "1"

if REQUIRE_IMAGE_RUNTIME and not IMAGE_RUNTIME_DISCOVERABLE:
    raise RuntimeError(
        "STARBRIDGE_REQUIRE_IMAGE_TO_PSD_RUNTIME=1 but Pillow, numpy, or OpenCV is missing"
    )


class PhotoshopSemanticLayersTests(unittest.TestCase):
    def make_line_art(self, path: Path) -> None:
        image = Image.new("RGB", (320, 420), (242, 230, 201))
        draw = ImageDraw.Draw(image)
        ink = (174, 73, 52)
        draw.ellipse((55, 70, 265, 300), outline=ink, width=3)
        for offset in range(0, 150, 12):
            draw.arc(
                (70 + offset // 4, 95, 245, 285 - offset // 5),
                20,
                320,
                fill=ink,
                width=2,
            )
        draw.ellipse((132, 173, 190, 231), outline=ink, width=3)
        for x in range(138, 189, 6):
            draw.line((x, 178, 188 - (x - 138), 226), fill=ink, width=2)
        draw.rectangle((265, 342, 300, 383), outline=ink, width=3)
        draw.line((269, 348, 296, 377), fill=ink, width=2)
        draw.line((296, 348, 269, 377), fill=ink, width=2)
        image.save(path)

    def make_poster_and_mask(self, image_path: Path, mask_path: Path) -> None:
        image = Image.new("RGB", (240, 180), (18, 42, 80))
        draw = ImageDraw.Draw(image)
        draw.rectangle((70, 65, 170, 165), fill=(235, 102, 44))
        draw.text((20, 20), "TITLE", fill=(255, 255, 255))
        image.save(image_path)
        cutout = Image.new("RGBA", image.size, (0, 0, 0, 0))
        cutout.paste(image.crop((70, 65, 170, 165)), (70, 65))
        alpha = Image.new("L", image.size, 0)
        ImageDraw.Draw(alpha).rectangle((70, 65, 169, 164), fill=255)
        cutout.putalpha(alpha)
        cutout.save(mask_path)

    def make_horizontal_line_art(self, path: Path) -> None:
        image = Image.new("RGB", (420, 240), (242, 230, 201))
        draw = ImageDraw.Draw(image)
        ink = (174, 73, 52)
        draw.rounded_rectangle((28, 82, 335, 158), radius=28, outline=ink, width=3)
        for offset in range(0, 260, 18):
            draw.arc((35 + offset, 88, 110 + offset, 153), 20, 320, fill=ink, width=2)
        draw.rectangle((360, 182, 402, 226), outline=ink, width=3)
        image.save(path)

    def make_monochrome_line_art(self, path: Path) -> None:
        image = Image.new("RGB", (360, 280), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        ink = (12, 12, 12)
        draw.ellipse((48, 42, 305, 215), outline=ink, width=4)
        draw.polygon([(286, 105), (338, 82), (306, 135)], outline=ink)
        for y in range(65, 205, 10):
            draw.arc((65, y - 25, 292, y + 35), 8, 172, fill=ink, width=2)
        for x in (85, 145, 230, 280):
            draw.line((x, 190, x - 10, 258), fill=ink, width=4)
        image.save(path)

    def make_photo_like_composition(self, path: Path) -> None:
        image = Image.new("RGB", (320, 320), (230, 230, 230))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 150, 319), fill=(250, 250, 250))
        draw.rectangle((150, 0, 319, 319), fill=(90, 135, 175))
        draw.ellipse((95, 30, 235, 180), fill=(214, 164, 132), outline=(80, 50, 40), width=3)
        draw.rectangle((65, 170, 265, 319), fill=(90, 105, 120))
        image.save(path)

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_plan_detects_line_art_without_recording_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "line-art.png"
            self.make_line_art(source)
            result = plan_image(source)
            self.assertEqual("line_art_on_texture", result["recommended_strategy"]["id"])
            self.assertEqual(source.name, result["source"]["name"])
            self.assertNotIn(str(source.parent), json.dumps(result))
            self.assertFalse(result["writes_files"])
            self.assertTrue(result["client_questions"])
            self.assertEqual(
                INTENT_SCHEMA_VERSION,
                result["recommended_intent_profile"]["schema_version"],
            )
            self.assertEqual(64, len(result["intent_profile_sha256"]))

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_auto_strategy_separates_monochrome_line_art_from_photo_like_composition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            line_art = root / "monochrome.png"
            photo = root / "photo.png"
            job = root / "line-job"
            self.make_monochrome_line_art(line_art)
            self.make_photo_like_composition(photo)
            line_plan = plan_image(line_art)
            photo_plan = plan_image(photo)
            self.assertEqual("monochrome_line_art", line_plan["recommended_strategy"]["id"])
            self.assertEqual("poster_basic", photo_plan["recommended_strategy"]["id"])
            result = decompose_image(
                line_art,
                job,
                intent=recommended_intent_profile("monochrome_line_art"),
            )
            self.assertGreater(result["quality"]["recomposition_similarity"], 0.98)
            manifest = load_manifest(job / "manifest.json")
            self.assertEqual("monochrome_line_art", manifest["strategy"]["id"])
            self.assertEqual(
                "local_monochrome_line_art",
                manifest["analysis"]["subject"]["engine"],
            )

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_explicit_intent_controls_layer_granularity_and_is_part_of_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "line-art.png"
            job = root / "job"
            self.make_line_art(source)
            profile = recommended_intent_profile("line_art_on_texture")
            profile["subject_granularity"] = "whole_subject"
            profile["decoration_policy"] = "keep_with_subject"
            profile["review_budget"]["max_active_crops"] = 1
            result = decompose_image(source, job, intent=profile)
            self.assertFalse(result["cached"])
            manifest = load_manifest(job / "manifest.json")
            self.assertEqual("explicit", manifest["intent"]["status"])
            self.assertEqual(profile, manifest["intent"]["profile"])
            self.assertEqual(
                "intent_requests_whole_subject",
                manifest["analysis"]["subject"]["semantic_subdivision"]["reason"],
            )
            self.assertFalse(manifest["analysis"]["semantic_regions"])
            self.assertNotIn("seal", {layer["id"] for layer in manifest["layers"]})
            packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            self.assertEqual(1, packet["token_saving"]["max_active_ambiguity_crops"])

            changed = dict(profile)
            changed["subject_granularity"] = "major_instances"
            changed_result = decompose_image(source, job, intent=changed)
            self.assertFalse(changed_result["cached"])
            changed_manifest = load_manifest(job / "manifest.json")
            self.assertTrue(
                changed_manifest["analysis"]["subject"]["semantic_subdivision"]["activated"]
            )

    def test_intent_rejects_pixel_bearing_learning_records(self) -> None:
        profile = recommended_intent_profile("poster_basic")
        profile["learning"]["record_decisions"] = True
        profile["learning"]["include_pixels"] = True
        with self.assertRaisesRegex(ValueError, "Pixel-bearing"):
            normalise_intent_profile(
                profile,
                strategy_id="poster_basic",
                text_mode="conservative",
                review_region_limit=8,
            )
        feedback_profile = recommended_intent_profile("poster_basic")
        feedback_profile["feedback"]["github_metrics_upload"] = True
        feedback_profile["feedback"]["include_customer_content"] = True
        with self.assertRaisesRegex(ValueError, "Customer content"):
            normalise_intent_profile(
                feedback_profile,
                strategy_id="poster_basic",
                text_mode="conservative",
                review_region_limit=8,
            )

    def test_public_intent_template_is_valid_and_private_data_free(self) -> None:
        root = Path(__file__).resolve().parents[1]
        template_path = root / "examples/photoshop_bridge/layer_intent.example.json"
        text = template_path.read_text(encoding="utf-8")
        profile = json.loads(text)
        normalised = normalise_intent_profile(
            profile,
            strategy_id="poster_basic",
            text_mode="conservative",
            review_region_limit=8,
        )
        self.assertEqual(INTENT_SCHEMA_VERSION, normalised["schema_version"])
        self.assertFalse(normalised["learning"]["record_decisions"])
        self.assertFalse(normalised["learning"]["include_pixels"])
        self.assertFalse(normalised["feedback"]["github_metrics_upload"])
        self.assertFalse(normalised["feedback"]["include_customer_content"])
        self.assertNotIn(str(Path.home()), text)
        for name in (
            "layer_intent.v1.schema.json",
            "layer_review_patch.v1.schema.json",
            "github_issue_metrics.v1.schema.json",
        ):
            schema = json.loads(
                (root / "examples/photoshop_bridge/protocols" / name).read_text(encoding="utf-8")
            )
            self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])

    def test_review_patch_rejects_unknown_or_unbounded_decisions(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported review patch keys"):
            _validate_review_patch(
                {
                    "schema_version": "starbridge.layer_review_patch.v1",
                    "arbitrary_code": "do not execute",
                }
            )
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            _validate_review_patch(
                {
                    "schema_version": "starbridge.layer_review_patch.v1",
                    "semantic_regions": [
                        {
                            "region_id": "region_01",
                            "accepted": True,
                            "confidence": 1.5,
                        }
                    ],
                }
            )

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_public_synthetic_regression_covers_multiple_layer_intents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            result = run_synthetic_regression(root / "regression")
            self.assertTrue(result["ok"])
            self.assertEqual(REGRESSION_SCHEMA_VERSION, result["schema_version"])
            self.assertEqual(4, result["case_count"])
            self.assertTrue(result["generated_public_inputs"])
            self.assertFalse(result["private_paths_recorded"])
            cases = {item["job_id"]: item for item in result["cases"]}
            self.assertTrue(cases["poster_editable_text"]["editable_text_present"])
            self.assertFalse(cases["poster_pixel_text_reference"]["editable_text_present"])
            self.assertTrue(
                cases["poster_pixel_text_reference"]["checks"]["editable_text_contract"]
            )
            self.assertFalse(cases["poster_original_background"]["background_repair_applied"])
            self.assertTrue(cases["poster_original_background"]["checks"]["background_contract"])
            report_text = (root / "regression/regression_report.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_line_art_decomposition_builds_exclusive_local_review_regions(self) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "line-art.png"
            job = root / "job"
            self.make_line_art(source)
            result = decompose_image(source, job)
            self.assertTrue(result["ok"])
            manifest = load_manifest(job / "manifest.json")
            self.assertEqual(SCHEMA_VERSION, manifest["schema_version"])
            self.assertEqual("line_art_on_texture", manifest["strategy"]["id"])
            names = {layer["name"] for layer in manifest["layers"]}
            self.assertIn("右下印章_独立可移动", names)
            subdivision = manifest["analysis"]["subject"]["semantic_subdivision"]
            self.assertTrue(subdivision["activated"])
            self.assertGreaterEqual(subdivision["region_count"], 6)
            self.assertTrue(subdivision["mutually_exclusive"])
            self.assertTrue(subdivision["warped_boundaries"])
            self.assertGreaterEqual(subdivision["boundary_density_reduction"], 0.0)
            continuity = subdivision["stroke_continuity"]
            self.assertTrue(continuity["enabled"])
            self.assertLessEqual(
                continuity["split_component_count_after"],
                continuity["split_component_count_before"],
            )
            self.assertLess(continuity["changed_foreground_ratio"], 0.1)
            central = manifest["analysis"]["subject"]["candidates"][0]["central_circle"]
            self.assertTrue(central["detected"])
            self.assertLess(central["center_offset_ratio"], 0.08)
            self.assertEqual(PIPELINE_VERSION, manifest["pipeline"]["version"])
            region_layers = [
                layer
                for layer in manifest["layers"]
                if layer.get("semantic_status") == "region_candidate_unreviewed"
            ]
            self.assertEqual(subdivision["region_count"], len(region_layers))
            support_sum = np.zeros((420, 320), dtype=np.uint8)
            for layer in region_layers:
                with Image.open(job / layer["source"]) as layer_image:
                    support_sum += (
                        np.asarray(layer_image.convert("RGBA"), dtype=np.uint8)[:, :, 3] > 0
                    ).astype(np.uint8)
            self.assertLessEqual(int(support_sum.max()), 1)
            self.assertGreater(result["quality"]["recomposition_similarity"], 0.98)
            self.assertGreater(
                result["quality"]["semantic_subdivision"]["layer_editability_score"],
                0.0,
            )
            review_packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            semantic_items = [
                item for item in review_packet["items"] if item["kind"] == "semantic_region_label"
            ]
            self.assertTrue(semantic_items)
            self.assertTrue(
                all("crop" in item and "overlay" not in item for item in semantic_items)
            )
            self.assertTrue(resolve_layer_sources(job / "manifest.json", manifest))
            self.assertTrue((job / "preview/recomposed.png").is_file())
            self.assertTrue((job / "review_packet.json").is_file())

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_semantic_review_patch_renames_region_without_reprocessing_pixels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "line-art.png"
            job = root / "job"
            self.make_line_art(source)
            intent = recommended_intent_profile("line_art_on_texture")
            intent["learning"]["record_decisions"] = True
            decompose_image(source, job, intent=intent)
            initial_manifest = load_manifest(job / "manifest.json")
            region_ids = [
                item["region_id"] for item in initial_manifest["analysis"]["semantic_regions"]
            ]
            patch = root / "semantic-patch.json"
            patch.write_text(
                json.dumps(
                    {
                        "schema_version": "starbridge.layer_review_patch.v1",
                        "semantic_regions": [
                            {
                                "region_id": region_id,
                                "name": f"神兽区域_{index:02d}_已确认",
                                "semantic_label": "神兽",
                                "accepted": True,
                                "confidence": 0.93,
                            }
                            for index, region_id in enumerate(region_ids, start=1)
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = apply_review_patch(job / "manifest.json", patch)
            self.assertFalse(result["reprocessed_pixels"])
            self.assertEqual(region_ids, result["changed_semantic_regions"])
            self.assertTrue(result["semantic_review_progress"]["labels_confirmed"])
            manifest = load_manifest(job / "manifest.json")
            layer = next(item for item in manifest["layers"] if item["id"] == "ring_region_01")
            self.assertEqual("神兽区域_01_已确认", layer["name"])
            self.assertEqual("region_candidate_accepted", layer["semantic_status"])
            self.assertTrue(
                manifest["analysis"]["subject"]["semantic_subdivision"]["semantic_labels_confirmed"]
            )
            self.assertFalse(
                any(
                    str(reason).startswith("环形纹样已拆成互斥几何候选区域")
                    for reason in manifest["quality"]["manual_review_reasons"]
                )
            )

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_stroke_review_patch_moves_only_local_alpha_and_advances_queue(self) -> None:
        import numpy as np

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "line-art.png"
            job = root / "job"
            self.make_line_art(source)
            intent = recommended_intent_profile("line_art_on_texture")
            intent["learning"]["record_decisions"] = True
            decompose_image(source, job, intent=intent)
            manifest = load_manifest(job / "manifest.json")
            region_ids = [item["region_id"] for item in manifest["analysis"]["semantic_regions"]]
            semantic_patch = root / "semantic-patch.json"
            semantic_patch.write_text(
                json.dumps(
                    {
                        "schema_version": "starbridge.layer_review_patch.v1",
                        "semantic_regions": [
                            {
                                "region_id": region_id,
                                "name": f"confirmed_region_{index:02d}",
                                "semantic_label": "ornamental_beast",
                                "accepted": True,
                                "confidence": 0.93,
                            }
                            for index, region_id in enumerate(region_ids, start=1)
                        ],
                    }
                ),
                encoding="utf-8",
            )
            apply_review_patch(job / "manifest.json", semantic_patch)
            packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            self.assertEqual("stroke_ambiguity_assignment", packet["stage"])
            self.assertLessEqual(len(packet["items"]), 2)
            self.assertTrue(
                all(item["kind"] == "stroke_ambiguity_assignment" for item in packet["items"])
            )

            manifest = load_manifest(job / "manifest.json")
            ambiguities = manifest["analysis"]["stroke_ambiguities"]
            self.assertTrue(ambiguities)
            ambiguity = ambiguities[0]
            component_id = ambiguity["component_id"]
            target_region_id = ambiguity["candidate_regions"][0]["region_id"]
            region_layers = [
                layer
                for layer in manifest["layers"]
                if layer.get("semantic_status") == "region_candidate_accepted"
            ]

            def union_alpha() -> object:
                alpha_planes = []
                for layer in region_layers:
                    with Image.open(job / layer["source"]) as image:
                        alpha_planes.append(
                            np.asarray(image.convert("RGBA"), dtype=np.uint8)[:, :, 3]
                        )
                return np.max(np.stack(alpha_planes), axis=0)

            before_union = union_alpha()
            before_unresolved = manifest["quality"]["semantic_subdivision"][
                "unresolved_stroke_components"
            ]
            stroke_patch = root / "stroke-patch.json"
            stroke_patch.write_text(
                json.dumps(
                    {
                        "schema_version": "starbridge.layer_review_patch.v1",
                        "stroke_assignments": [
                            {
                                "component_id": component_id,
                                "target_region_id": target_region_id,
                                "confidence": 0.91,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = apply_review_patch(job / "manifest.json", stroke_patch)
            self.assertTrue(result["reprocessed_pixels"])
            self.assertFalse(result["full_image_analysis_repeated"])
            self.assertFalse(result["background_recomputed"])
            self.assertEqual([component_id], result["stroke_assignment"]["assigned_components"])
            np.testing.assert_array_equal(before_union, union_alpha())

            manifest = load_manifest(job / "manifest.json")
            ambiguity = next(
                item
                for item in manifest["analysis"]["stroke_ambiguities"]
                if item["component_id"] == component_id
            )
            self.assertEqual("assigned", ambiguity["status"])
            self.assertEqual(target_region_id, ambiguity["target_region_id"])
            self.assertEqual(1, manifest["pipeline"]["artifact_revision"])
            self.assertEqual(
                before_unresolved - 1,
                manifest["quality"]["semantic_subdivision"]["unresolved_stroke_components"],
            )
            packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            active_ids = {item.get("component_id") for item in packet["items"]}
            self.assertNotIn(component_id, active_ids)
            self.assertLessEqual(len(packet["items"]), 2)
            dataset = job / "learning/decision_examples.jsonl"
            self.assertTrue(dataset.is_file())
            dataset_text = dataset.read_text(encoding="utf-8")
            examples = [json.loads(line) for line in dataset_text.splitlines()]
            self.assertTrue(examples)
            self.assertTrue(all(not item["includes_pixels"] for item in examples))
            self.assertNotIn(str(root), dataset_text)
            self.assertNotIn(".png", dataset_text.lower())
            self.assertGreaterEqual(manifest["learning"]["example_count"], 1)
            self.assertFalse(manifest["learning"]["source_paths_recorded"])

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_non_circular_line_art_keeps_a_coarse_subject_layer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "horizontal-line-art.png"
            job = root / "job"
            self.make_horizontal_line_art(source)
            decompose_image(
                source,
                job,
                options=DecompositionOptions(preset="line_art_on_texture"),
            )
            manifest = load_manifest(job / "manifest.json")
            subdivision = manifest["analysis"]["subject"]["semantic_subdivision"]
            self.assertFalse(subdivision["activated"])
            names = {layer["name"] for layer in manifest["layers"]}
            self.assertIn("主体线稿_整体_可调色", names)

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_cache_and_manifest_only_review_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "poster.png"
            mask = root / "subject.png"
            job = root / "job"
            self.make_poster_and_mask(source, mask)
            analysis = {
                "subject_mask_path": str(mask),
                "text_regions": [
                    {
                        "id": "text_01",
                        "bbox": [18, 15, 100, 42],
                        "content": "",
                        "confidence": 0.55,
                    }
                ],
            }
            options = DecompositionOptions(preset="poster_basic")
            first = decompose_image(source, job, options=options, analysis=analysis)
            second = decompose_image(source, job, options=options, analysis=analysis)
            self.assertFalse(first["cached"])
            self.assertTrue(second["cached"])
            patch = root / "patch.json"
            patch.write_text(
                json.dumps(
                    {
                        "schema_version": "starbridge.layer_review_patch.v1",
                        "text_regions": [
                            {
                                "region_id": "text_01",
                                "content": "TITLE",
                                "confidence": 0.96,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            patched = apply_review_patch(job / "manifest.json", patch)
            self.assertFalse(patched["reprocessed_pixels"])
            self.assertEqual(2, patched["iteration"])
            manifest = load_manifest(job / "manifest.json")
            text_layer = next(layer for layer in manifest["layers"] if layer["type"] == "text")
            self.assertEqual("TITLE", text_layer["content"])
            self.assertTrue(text_layer["visible"])

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_unconfirmed_grabcut_mask_requires_review_and_records_rejection_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "photo.png"
            unused_mask = root / "unused.png"
            job = root / "job"
            self.make_poster_and_mask(source, unused_mask)
            intent = recommended_intent_profile("character_basic", text_mode="off")
            intent["learning"]["record_decisions"] = True
            decompose_image(
                source,
                job,
                options=DecompositionOptions(preset="character_basic", text_mode="off"),
                intent=intent,
            )
            manifest = load_manifest(job / "manifest.json")
            self.assertEqual("unreviewed", manifest["analysis"]["subject"]["review_status"])
            self.assertTrue(
                any(
                    reason.startswith("本地主体遮罩尚未由客户确认")
                    for reason in manifest["quality"]["manual_review_reasons"]
                )
            )
            packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            self.assertEqual("candidate_review", packet["stage"])
            self.assertEqual("subject_mask", packet["items"][0]["kind"])
            patch = root / "subject-review.json"
            patch.write_text(
                json.dumps(
                    {
                        "schema_version": "starbridge.layer_review_patch.v1",
                        "subject_masks": [
                            {
                                "mask_id": "subject_01",
                                "accepted": False,
                                "quality_score": 0.35,
                                "failure_modes": ["over_selection"],
                                "confidence": 0.98,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = apply_review_patch(job / "manifest.json", patch)
            self.assertFalse(result["reprocessed_pixels"])
            self.assertTrue(result["subject_review"]["reviewed"])
            self.assertFalse(result["subject_review"]["accepted"])
            manifest = load_manifest(job / "manifest.json")
            self.assertEqual("rejected", manifest["analysis"]["subject"]["review_status"])
            self.assertTrue(
                any(
                    reason.startswith("客户复核已拒绝当前主体遮罩")
                    for reason in manifest["quality"]["manual_review_reasons"]
                )
            )
            packet = json.loads((job / "review_packet.json").read_text(encoding="utf-8"))
            self.assertEqual("complete", packet["stage"])
            examples = [
                json.loads(line)
                for line in (job / "learning/decision_examples.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual("subject_mask_review", examples[0]["decision_type"])
            self.assertFalse(examples[0]["decision"]["accepted"])
            self.assertEqual(["over_selection"], examples[0]["decision"]["failure_modes"])

    @unittest.skipUnless(IMAGE_RUNTIME_DISCOVERABLE, "image-to-psd runtime is not installed")
    def test_batch_resume_uses_content_hash_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            outputs = root / "outputs"
            inputs.mkdir()
            self.make_line_art(inputs / "one.png")
            self.make_line_art(inputs / "two.png")
            first = batch_decompose(inputs, outputs, workers=2)
            second = batch_decompose(inputs, outputs, workers=2)
            self.assertEqual(2, first["completed"])
            self.assertEqual(0, first["failed"])
            self.assertEqual(2, second["cached"])
            report_text = (outputs / "batch_report.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)
            self.assertTrue(all("job_id" in item for item in second["results"]))

    def test_photoshop_builder_is_confirmed_and_sandboxed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        script = (
            root / "examples" / "photoshop_bridge" / "scripts" / "build_editable_psd.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("[switch]$ConfirmWrite", script)
        self.assertIn("Test-IsInside", script)
        self.assertIn("examples\\output\\photoshop", script)
        self.assertIn("saveOptions.layers = true", script)
        self.assertIn("validatePersistedDocument", script)
        self.assertIn("validated_after_reopen=true", script)
        self.assertIn("private_paths_recorded = $false", script)

    def test_cli_public_payload_redacts_paths_outside_repo(self) -> None:
        result = _public_payload(
            {
                "job_dir": str(Path.home() / "private-job"),
                "nested": [str(Path(__file__).resolve())],
            }
        )
        self.assertEqual("<LOCAL_PATH>", result["job_dir"])
        self.assertFalse(Path(result["nested"][0]).is_absolute())
        self.assertNotIn(str(Path.home()), json.dumps(result))

    def test_pipeline_revision_is_part_of_the_content_cache_key(self) -> None:
        options = DecompositionOptions()
        current = _cache_key("source-hash", options, {})
        with mock.patch(
            "starbridge_mcp.adapters.photoshop.semantic_layers.pipeline.PIPELINE_VERSION",
            "starbridge.image_to_editable_psd.pipeline.future",
        ):
            future = _cache_key("source-hash", options, {})
        self.assertNotEqual(current, future)


if __name__ == "__main__":
    unittest.main()
