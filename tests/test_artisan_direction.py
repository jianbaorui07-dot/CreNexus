from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starbridge_mcp.vectorization.artisan_direction import (
    ArtisanDirectionError,
    build_illustrator_map,
    compile_art_direction,
    load_art_direction,
    load_illustrator_map,
    palette_mapping,
)


class ArtisanDirectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.spec = {
            "base_edit_ref": "edit:0123456789ab",
            "profile_ref": "style:abcdef012345",
            "palette_groups": [["#b94f42", ["#b94f42", "#ba5043"]]],
            "object_names": [["shape-0004", "朱红装饰"]],
            "layer_names": [["subject", "主体色块"]],
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_direction_is_compact_bound_and_readable(self) -> None:
        direction = compile_art_direction(self.spec)
        text = json.dumps(direction, ensure_ascii=False, separators=(",", ":"))
        self.assertRegex(direction["direction_ref"], r"^direction:[0-9a-f]{12}$")
        self.assertLess(len(text.encode("utf-8")), 900)
        self.assertNotIn("path", text.lower())
        path = self.root / "direction.json"
        path.write_text(text, encoding="utf-8")
        self.assertEqual(load_art_direction(str(path)), direction)
        self.assertEqual(palette_mapping(direction), {"#b94f42": "#b94f42", "#ba5043": "#b94f42"})

    def test_duplicate_palette_source_and_unsafe_names_are_rejected(self) -> None:
        duplicate = {
            **self.spec,
            "palette_groups": [
                ["#b94f42", ["#ba5043"]],
                ["#7f302a", ["#ba5043"]],
            ],
        }
        with self.assertRaises(ArtisanDirectionError) as raised:
            compile_art_direction(duplicate)
        self.assertEqual(raised.exception.code, "invalid_palette_groups")
        unsafe = {**self.spec, "object_names": [["shape-0004", "../../客户文件"]]}
        with self.assertRaises(ArtisanDirectionError) as raised:
            compile_art_direction(unsafe)
        self.assertEqual(raised.exception.code, "invalid_object_names")

    def test_tampering_and_empty_direction_fail_closed(self) -> None:
        direction = compile_art_direction(self.spec)
        direction["layer_names"][0][1] = "未签名名称"
        path = self.root / "tampered.json"
        path.write_text(json.dumps(direction, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ArtisanDirectionError) as raised:
            load_art_direction(str(path))
        self.assertEqual(raised.exception.code, "art_direction_integrity_failed")
        with self.assertRaises(ArtisanDirectionError) as raised:
            compile_art_direction(
                {
                    **self.spec,
                    "palette_groups": [],
                    "object_names": [],
                    "layer_names": [],
                }
            )
        self.assertEqual(raised.exception.code, "empty_direction")

    def test_illustrator_map_is_bound_and_integrity_checked(self) -> None:
        mapping = build_illustrator_map(
            direction_ref="direction:0123456789ab",
            svg_sha256="a" * 64,
            edit_ref="edit:abcdef012345",
            layer_names=[["layer-subject", "主体色块"]],
            object_names=[["shape-0002", "朱红装饰"]],
        )
        path = self.root / "illustrator-map.json"
        path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(load_illustrator_map(str(path)), mapping)
        mapping["objects"][0][1] = "篡改名称"
        path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(ArtisanDirectionError) as raised:
            load_illustrator_map(str(path))
        self.assertEqual(raised.exception.code, "illustrator_map_integrity_failed")


if __name__ == "__main__":
    unittest.main()
