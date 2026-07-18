from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.check_text_encoding import check_text_encoding, inspect_text_file


class TextEncodingTests(unittest.TestCase):
    def test_all_repository_public_text_is_valid_utf8_without_known_mojibake(self) -> None:
        self.assertEqual([], check_text_encoding())

    def test_checker_detects_invalid_utf8_and_common_mojibake(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            invalid = Path(directory) / "invalid.md"
            invalid.write_bytes(b"\xff\xfe")
            self.assertTrue(inspect_text_file(invalid))

            mojibake = Path(directory) / "mojibake.md"
            mojibake.write_text("鍥" + "剧墖", encoding="utf-8")
            self.assertTrue(inspect_text_file(mojibake))


if __name__ == "__main__":
    unittest.main()
