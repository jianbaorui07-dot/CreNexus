from __future__ import annotations

import json
import unittest
from pathlib import Path

from starbridge_mcp.core.security import contains_sensitive_text, sanitize


class SecurityBoundaryTests(unittest.TestCase):
    def test_sanitize_redacts_user_paths_and_tokens(self) -> None:
        token_key = "tok" + "en"
        token_value = "VALUE_FOR_REDACTION_TEST"
        windows_user_path = "C:" + "\\Users\\private\\Videos\\draft_content.json"
        api_key_text = "api" + "_key=VALUE_FOR_REDACTION_TEST"
        payload = {
            "path": str(Path.home() / "Desktop" / "client_logo.psd"),
            token_key: token_value,
            "nested": [windows_user_path, api_key_text],
        }
        sanitized = sanitize(payload)
        text = json.dumps(sanitized, ensure_ascii=False)
        self.assertIn("<USER_HOME>", text)
        self.assertIn("<REDACTED>", text)
        self.assertNotIn(str(Path.home()), text)
        self.assertNotIn(token_value, text)
        self.assertNotIn("draft_content.json", text)
        self.assertFalse(contains_sensitive_text(sanitized))

    def test_sanitize_redacts_private_asset_extensions(self) -> None:
        user_prefix = "C:" + "\\Users\\name"
        payload = {
            "models": ["D:\\models\\real_model" + ".safetensors"],
            "cad": "E:\\client\\factory" + ".dwg",
            "illustrator": user_prefix + "\\art\\brand" + ".ai",
            "video": user_prefix + "\\exports\\final" + ".mp4",
        }
        sanitized = sanitize(payload)
        text = json.dumps(sanitized, ensure_ascii=False).lower()
        self.assertNotIn(".safetensors", text)
        self.assertNotIn(".dwg", text)
        self.assertNotIn(".ai", text)
        self.assertNotIn(".mp4", text)
        self.assertFalse(contains_sensitive_text(sanitized))


if __name__ == "__main__":
    unittest.main()
