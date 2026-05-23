from __future__ import annotations

import binascii
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from examples.photoshop_bridge.write_practice_report import (  # noqa: E402
    add_expected_practice_paths,
    artifact_info,
    collect_artifacts,
    png_alpha_summary,
    png_dimensions,
    render_artifact_table,
)


def minimal_png(width: int, height: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", ihdr) + png_chunk(b"IEND", b"")


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = binascii.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)


def rgba_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    if len(pixels) != width * height:
        raise ValueError("pixel count does not match image size")

    rows = []
    for y in range(height):
        row = bytearray([0])
        for rgba in pixels[y * width : (y + 1) * width]:
            row.extend(rgba)
        rows.append(bytes(row))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", ihdr)
        + png_chunk(b"IDAT", zlib.compress(b"".join(rows)))
        + png_chunk(b"IEND", b"")
    )


class PhotoshopReportTest(unittest.TestCase):
    def test_png_dimensions_reads_header_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo.png"
            path.write_bytes(minimal_png(320, 240))

            self.assertEqual(png_dimensions(path), (320, 240))

    def test_artifact_info_records_png_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "demo.png"
            path.write_bytes(rgba_png(2, 1, [(0, 0, 0, 0), (255, 0, 0, 255)]))

            info = artifact_info("测试图片", str(path))

            self.assertTrue(info["exists"])
            self.assertEqual(info["png_width"], 2)
            self.assertEqual(info["png_height"], 1)
            self.assertEqual(len(info["sha256"]), 64)
            self.assertTrue(info["alpha_summary"]["has_alpha_channel"])

    def test_failed_practice_keeps_expected_artifact_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            practice_dir = Path(temp_dir) / "practice"
            practice_dir.mkdir()
            expected_input = practice_dir / "subject_input_clean.png"
            expected_input.write_bytes(rgba_png(1, 1, [(0, 0, 0, 255)]))

            practice = add_expected_practice_paths({"ok": False, "stderr": "Photoshop busy"}, practice_dir)
            artifacts = collect_artifacts({"practice": practice})

            self.assertEqual(practice["subject_input"], str(expected_input))
            self.assertEqual(len(artifacts), 3)
            self.assertFalse(artifacts[0]["exists"])
            self.assertTrue(artifacts[1]["exists"])
            self.assertFalse(artifacts[2]["exists"])

    def test_png_alpha_summary_counts_alpha_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "alpha.png"
            path.write_bytes(
                rgba_png(
                    3,
                    1,
                    [
                        (0, 0, 0, 0),
                        (0, 0, 0, 128),
                        (0, 0, 0, 255),
                    ],
                )
            )

            summary = png_alpha_summary(path)

            self.assertTrue(summary["supported"])
            self.assertTrue(summary["has_alpha_channel"])
            self.assertEqual(summary["transparent_pixels"], 1)
            self.assertEqual(summary["translucent_pixels"], 1)
            self.assertEqual(summary["opaque_pixels"], 1)
            self.assertEqual(
                summary["visible_bbox"],
                {
                    "left": 1,
                    "top": 0,
                    "right": 2,
                    "bottom": 0,
                    "width": 2,
                    "height": 1,
                    "area": 2,
                    "visible_pixels": 2,
                    "coverage_ratio": 0.666667,
                    "bbox_fill_ratio": 1.0,
                    "edge_margins": {
                        "left": 1,
                        "top": 0,
                        "right": 0,
                        "bottom": 0,
                    },
                },
            )

    def test_artifact_table_contains_chinese_headers(self) -> None:
        rows = render_artifact_table(
            [
                {
                    "role": "测试图片",
                    "path": "D:/demo.png",
                    "exists": True,
                    "bytes": 123,
                    "sha256": "abcdef1234567890",
                    "png_width": 10,
                    "png_height": 20,
                    "alpha_summary": {
                        "supported": True,
                        "has_alpha_channel": True,
                        "transparent_pixels": 1,
                        "translucent_pixels": 2,
                        "opaque_pixels": 3,
                        "visible_bbox": {
                            "width": 2,
                            "height": 3,
                            "coverage_ratio": 0.25,
                            "edge_margins": {
                                "left": 4,
                                "top": 5,
                                "right": 6,
                                "bottom": 7,
                            },
                        },
                    },
                }
            ]
        )
        table = "\n".join(rows)

        self.assertIn("产物", table)
        self.assertIn("图片尺寸", table)
        self.assertIn("10 x 20", table)
        self.assertIn("透明 1", table)
        self.assertIn("主体边界", table)
        self.assertIn("2 x 3", table)
        self.assertIn("边距 4/5/6/7", table)


if __name__ == "__main__":
    unittest.main()
