from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "product" / "product-manifest.json"
ALLOWED_STATUSES = {
    "stable",
    "experimental",
    "planned",
    "not_implemented",
}
ALLOWED_EVIDENCE_LEVELS = {"none", "schema", "unit", "integration", "local_app", "release"}


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
        self.assertEqual(boundary["communityRepository"], "jianbaorui07-dot/KORYAO-basic")
        self.assertEqual(boundary["communitySource"], "public-proprietary-current")
        self.assertEqual(boundary["currentLicense"], "KORYAO Proprietary License")
        self.assertTrue(boundary["historicalLicenseRightsPreserved"])
        self.assertEqual(boundary["commercialSource"], "private-planned")
        self.assertFalse(boundary["commercialRepositoryCreated"])
        self.assertEqual(
            "jianbaorui07-dot/KORYAO-Model-Private",
            boundary["modelRuntimeRepository"],
        )
        self.assertTrue(boundary["modelRuntimeRepositoryCreated"])
        self.assertEqual("private", boundary["modelRuntimeRepositoryVisibility"])
        self.assertEqual(
            "jianbaorui07-dot/KORYAO-Data-Private",
            boundary["modelDataRepository"],
        )
        self.assertTrue(boundary["modelDataRepositoryCreated"])
        self.assertEqual("private", boundary["modelDataRepositoryVisibility"])
        self.assertFalse(boundary["premiumImplementationsAllowedInCommunityRepository"])

    def test_pro_offer_is_proposed_not_claimed_as_launched(self) -> None:
        editions = {edition["id"]: edition for edition in self.manifest["editions"]}
        self.assertEqual(editions["community"]["capabilityStatus"], "stable")
        self.assertEqual(editions["pro"]["capabilityStatus"], "planned")
        self.assertEqual(editions["pro"]["earlyBirdPriceCny"], 399)
        self.assertEqual(editions["pro"]["priceStatus"], "proposed-not-for-sale")
        self.assertEqual(editions["pro"]["minimumDevices"], 1)
        self.assertEqual(editions["pro"]["maximumDevices"], 2)
        self.assertEqual(editions["pro"]["defaultDeviceLimit"], "owner-decision-pending")

    def test_public_mit_vector_modes_remain_community_features(self) -> None:
        features = {feature["id"]: feature for feature in self.manifest["features"]}
        for feature_id in (
            "vectorization.artisan",
            "vectorization.smart",
            "vectorization.lightweight",
            "vectorization.exact",
        ):
            self.assertEqual(features[feature_id]["edition"], "community")
            self.assertEqual(features[feature_id]["capabilityStatus"], "stable")
        self.assertNotIn("vectorization.advanced", features)

    def test_basic_project_job_and_delivery_foundation_remain_community(self) -> None:
        features = {feature["id"]: feature for feature in self.manifest["features"]}
        for feature_id in (
            "projects.basic",
            "jobs.creative_job",
            "workflow.vector_delivery_v1",
            "delivery.basic",
        ):
            self.assertEqual("community", features[feature_id]["edition"])
        self.assertEqual("pro", features["batch.processing"]["edition"])
        self.assertEqual("pro", features["projects.advanced_recovery"]["edition"])

    def test_closed_model_contract_is_public_but_implementation_is_not(self) -> None:
        features = {feature["id"]: feature for feature in self.manifest["features"]}
        contract = features["model.contract_v1"]
        self.assertEqual("community", contract["edition"])
        self.assertEqual("experimental", contract["capabilityStatus"])
        self.assertEqual("integration", contract["evidenceLevel"])
        client = features["model.local_runtime_client_v1"]
        self.assertEqual("community", client["edition"])
        self.assertEqual("integration", client["evidenceLevel"])
        boundary = self.manifest["sourceBoundary"]
        self.assertTrue(boundary["modelRuntimeRepositoryCreated"])
        self.assertFalse(boundary["communityBuildContainsPrivateProSource"])

    def test_feature_statuses_and_document_links_are_valid(self) -> None:
        for feature in self.manifest["features"]:
            self.assertIn(feature["capabilityStatus"], ALLOWED_STATUSES)
            self.assertIn(feature["evidenceLevel"], ALLOWED_EVIDENCE_LEVELS)
            self.assertIsInstance(feature["recommended"], bool)
            self.assertIsInstance(feature["deprecated"], bool)
            documentation = ROOT / feature["documentation"]
            self.assertTrue(documentation.is_file(), feature["id"])

    def test_no_production_key_or_official_signed_installer_is_claimed(self) -> None:
        licensing = self.manifest["licensing"]
        self.assertFalse(licensing["networkActivation"])
        self.assertFalse(licensing["productionPrivateKeyInRepository"])
        self.assertFalse(licensing["productionPrivateKeyInApplication"])
        self.assertFalse(licensing["productionPublicKeyConfigured"])
        download = self.manifest["download"]
        self.assertTrue(download["publicInstallerAvailable"])
        self.assertFalse(download["officialSignedInstallerAvailable"])
        self.assertEqual(download["status"], "public-unsigned-internal-preview")
        self.assertEqual(download["authenticode"], "not-signed")
        self.assertEqual(len(download["sha256"]), 64)
        self.assertFalse(self.manifest["releaseReadiness"]["authenticodeSigned"])
        self.assertFalse(self.manifest["releaseReadiness"]["paidReleaseReady"])
        self.assertFalse(self.manifest["website"]["published"])
        self.assertTrue(self.manifest["website"]["downloadRouteOpen"])

    def test_updater_is_implemented_without_claiming_a_live_release_channel(self) -> None:
        features = {feature["id"]: feature for feature in self.manifest["features"]}
        updater = features["updates.github_signed_release"]
        self.assertEqual(updater["edition"], "community")
        self.assertEqual(updater["capabilityStatus"], "experimental")
        self.assertTrue(updater["requiresUserConfirmation"])
        readiness = self.manifest["releaseReadiness"]
        self.assertTrue(readiness["inAppUpdaterImplemented"])
        self.assertFalse(readiness["updaterProductionPublicKeyConfigured"])
        self.assertTrue(self.manifest["download"]["publicInstallerAvailable"])
        self.assertFalse(self.manifest["download"]["officialSignedInstallerAvailable"])


if __name__ == "__main__":
    unittest.main()
