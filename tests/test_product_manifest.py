from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "product" / "product-manifest.json"
ALLOWED_STATUSES = {"available-local", "experimental", "planned", "unsupported"}


class ProductManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_product_is_explicitly_local_only(self) -> None:
        product = self.manifest["product"]
        data_policy = self.manifest["dataPolicy"]
        self.assertFalse(product["serverRequired"])
        self.assertFalse(data_policy["backgroundNetworkService"])
        self.assertEqual(data_policy["coreComputation"], "local-only")
        self.assertEqual(data_policy["userImages"], "local-only")
        self.assertEqual(data_policy["licenseFiles"], "local-only")
        self.assertEqual(data_policy["telemetry"], "disabled")

    def test_public_and_private_source_boundary_is_machine_readable(self) -> None:
        boundary = self.manifest["sourceBoundary"]
        self.assertEqual(boundary["communitySource"], "public")
        self.assertEqual(boundary["commercialSource"], "private")
        self.assertFalse(boundary["commercialRepositoryCreated"])
        self.assertFalse(boundary["premiumImplementationsAllowedInCommunityRepository"])

    def test_pro_offer_is_proposed_not_claimed_as_launched(self) -> None:
        editions = {edition["id"]: edition for edition in self.manifest["editions"]}
        self.assertEqual(editions["community"]["status"], "available-local")
        self.assertEqual(editions["pro"]["status"], "planned")
        self.assertEqual(editions["pro"]["earlyBirdPriceCny"], 399)
        self.assertEqual(editions["pro"]["priceStatus"], "proposed")
        self.assertEqual(editions["pro"]["minimumDevices"], 1)
        self.assertEqual(editions["pro"]["deviceLimit"], 2)

    def test_feature_statuses_and_document_links_are_valid(self) -> None:
        for feature in self.manifest["features"]:
            self.assertIn(feature["status"], ALLOWED_STATUSES)
            documentation = ROOT / feature["documentation"]
            self.assertTrue(documentation.is_file(), feature["id"])

    def test_no_production_key_or_public_installer_is_claimed(self) -> None:
        licensing = self.manifest["licensing"]
        self.assertFalse(licensing["networkActivation"])
        self.assertFalse(licensing["productionPrivateKeyInRepository"])
        self.assertFalse(licensing["productionPrivateKeyInApplication"])
        self.assertFalse(licensing["productionPublicKeyConfigured"])
        self.assertFalse(self.manifest["download"]["publicInstallerAvailable"])


if __name__ == "__main__":
    unittest.main()
