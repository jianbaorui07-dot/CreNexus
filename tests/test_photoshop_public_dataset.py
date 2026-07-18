from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset import (
    PUBLIC_DATASET_REQUEST_SCHEMA,
    PUBLIC_DATASET_SCHEMA,
    _download_public_bytes,
    acquire_public_dataset,
    load_public_dataset_request,
)


class PhotoshopPublicDatasetTests(unittest.TestCase):
    def test_public_dataset_protocol_schemas_are_public_valid_json(self) -> None:
        protocol_root = (
            Path(__file__).resolve().parents[1] / "examples" / "photoshop_bridge" / "protocols"
        )
        expected = {
            "public_image_dataset_request.v1.schema.json": (
                "starbridge.public_image_dataset_request.v1"
            ),
            "public_image_dataset.v1.schema.json": "starbridge.public_image_dataset.v1",
            "public_client_mode_experiment.v1.schema.json": (
                "starbridge.public_client_mode_experiment.v1"
            ),
        }
        for filename, schema_version in expected.items():
            with self.subTest(filename=filename):
                schema = json.loads((protocol_root / filename).read_text(encoding="utf-8"))
                self.assertEqual("object", schema["type"])
                self.assertEqual(schema_version, schema["properties"]["schema_version"]["const"])

    def request(self, path: Path, *, expected_license: str = "cc0") -> None:
        path.write_text(
            json.dumps(
                {
                    "schema_version": PUBLIC_DATASET_REQUEST_SCHEMA,
                    "provider": "wikimedia_commons",
                    "max_width": 1280,
                    "items": [
                        {
                            "id": "public_product",
                            "file_title": "File:Public product.jpg",
                            "expected_license_family": expected_license,
                            "use_case": "product",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def image_bytes(self) -> bytes:
        image = Image.new("RGB", (64, 48), (220, 80, 40))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    def metadata(self, *, license_name: str = "CC0") -> dict[str, object]:
        return {
            "thumburl": "https://upload.wikimedia.org/public-product.jpg",
            "url": "https://upload.wikimedia.org/original-product.jpg",
            "extmetadata": {
                "LicenseShortName": {"value": license_name},
                "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"},
                "Artist": {"value": "<b>Public Artist</b>"},
                "Credit": {"value": "Own work"},
            },
        }

    def test_public_template_is_explicit_and_license_allowlisted(self) -> None:
        root = Path(__file__).resolve().parents[1]
        request_path = root / "examples/photoshop_bridge/public_dataset.example.json"
        payload = load_public_dataset_request(request_path)
        self.assertEqual(PUBLIC_DATASET_REQUEST_SCHEMA, payload["schema_version"])
        self.assertEqual(4, len(payload["items"]))
        self.assertTrue(
            all(
                item["expected_license_family"] in {"public_domain", "cc0"}
                for item in payload["items"]
            )
        )
        schema = json.loads(
            (
                root
                / "examples/photoshop_bridge/protocols/public_image_dataset_request.v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])

    def test_acquisition_writes_license_provenance_without_private_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            output = root / "output"
            self.request(request_path)
            with (
                mock.patch(
                    "starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset._fetch_commons_metadata",
                    return_value={"File:Public product.jpg": self.metadata()},
                ),
                mock.patch(
                    "starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset._download_public_bytes",
                    return_value=self.image_bytes(),
                ),
            ):
                result = acquire_public_dataset(request_path, output)
            self.assertEqual(PUBLIC_DATASET_SCHEMA, result["schema_version"])
            self.assertTrue(result["license_verified"])
            self.assertFalse(result["private_paths_recorded"])
            self.assertTrue((output / "assets/public_product.jpg").is_file())
            record = result["items"][0]
            self.assertEqual("cc0", record["license_family"])
            self.assertEqual("Public Artist", record["artist"])
            self.assertEqual(64, len(record["sha256"]))
            report_text = (output / "dataset_manifest.json").read_text(encoding="utf-8")
            self.assertNotIn(str(root), report_text)

    def test_license_mismatch_stops_before_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request_path = root / "request.json"
            self.request(request_path, expected_license="public_domain")
            with (
                mock.patch(
                    "starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset._fetch_commons_metadata",
                    return_value={"File:Public product.jpg": self.metadata(license_name="CC0")},
                ),
                mock.patch(
                    "starbridge_mcp.adapters.photoshop.semantic_layers.public_dataset._download_public_bytes"
                ) as download,
                self.assertRaisesRegex(ValueError, "License verification failed"),
            ):
                acquire_public_dataset(request_path, root / "output")
            download.assert_not_called()

    def test_download_rejects_non_commons_hosts(self) -> None:
        with self.assertRaisesRegex(ValueError, "not allowlisted"):
            _download_public_bytes("https://example.com/client-image.png")


if __name__ == "__main__":
    unittest.main()
