from __future__ import annotations

import unittest

from starbridge_mcp.core.security import contains_sensitive_text, sanitize_details, sanitize_path, sanitize_text


BANNED_OUTPUT_FRAGMENTS = ("C:\\Users\\", "/Users/", "/home/", "AppData", "Desktop", "Documents")


class SecuritySanitizerTests(unittest.TestCase):
    def assert_clean(self, value: object) -> None:
        text = str(value)
        for fragment in BANNED_OUTPUT_FRAGMENTS:
            self.assertNotIn(fragment, text)
        self.assertFalse(contains_sensitive_text(value))

    def test_sanitize_path_redacts_common_private_paths(self) -> None:
        windows_home = "C:" + "\\Users\\SomeName"
        samples = [
            windows_home + "\\Desktop\\file" + ".psd",
            windows_home + "\\AppData\\Local\\Adobe",
            "/Users/somename/Documents/file" + ".ai",
            "/home/somename/models/model" + ".safetensors",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                sanitized = sanitize_path(sample)
                self.assert_clean(sanitized)

    def test_sanitize_text_preserves_normal_bridge_text(self) -> None:
        text = "Photoshop 修图桥 当前未完全就绪，详见 details.notes。"
        self.assertEqual(sanitize_text(text), text)
        self.assert_clean(sanitize_text(text))

    def test_sanitize_details_recurses_dicts_and_lists(self) -> None:
        payload = {
            "bridge": "illustrator",
            "details": [
                {"path": "C:" + "\\Users\\SomeName\\Documents\\client" + ".ai"},
                {"model": "/home/somename/models/model" + ".safetensors"},
            ],
        }
        sanitized = sanitize_details(payload)
        self.assertEqual(sanitized["bridge"], "illustrator")
        self.assert_clean(sanitized)


if __name__ == "__main__":
    unittest.main()
