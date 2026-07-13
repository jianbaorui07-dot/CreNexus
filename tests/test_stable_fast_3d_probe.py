from __future__ import annotations

import unittest

from examples.stable_fast_3d_bridge.probe import build_report, check_path


class StableFast3DProbeTests(unittest.TestCase):
    def test_unconfigured_probe_does_not_invent_local_path(self) -> None:
        paths = check_path(None)

        self.assertTrue(all(item["path"] is None for item in paths.values()))
        self.assertTrue(all(not item["exists"] for item in paths.values()))

    def test_report_without_root_is_read_only_and_unconfigured(self) -> None:
        report = build_report(None, "http://127.0.0.1:9", 1)

        self.assertEqual("missing", report["status"])
        self.assertIsNone(report["root"])
        self.assertIn("This probe is read-only.", report["notes"])


if __name__ == "__main__":
    unittest.main()
