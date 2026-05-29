from __future__ import annotations

import json
import shlex
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class PackageScriptsTest(unittest.TestCase):
    def setUp(self) -> None:
        package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
        self.scripts: dict[str, str] = package["scripts"]

    def test_scripts_are_grouped_by_clear_prefixes(self) -> None:
        self.assertEqual(
            {
                "bridge:status",
                "bridge:status:json",
                "bridge:status:safe",
                "bridge:status:probe",
                "bridge:capabilities",
                "bridge:capabilities:json",
                "bridge:capabilities:check",
                "starbridge:status",
                "starbridge:status:strict",
                "starbridge:tools",
                "starbridge:tools:safe",
                "starbridge:mcp",
                "status:manifest",
                "status:manifest:json",
                "status:probe",
                "status:probe:json",
                "cad:dxf:dry-run",
                "comfy:probe",
                "comfy:workflow:validate",
                "comfy:txt2img",
                "photoshop:probe",
                "photoshop:diagnose",
                "photoshop:info",
                "photoshop:demo:plan",
                "photoshop:demo",
                "photoshop:manifest",
                "illustrator:info",
                "illustrator:demo:plan",
                "illustrator:demo",
                "illustrator:manifest",
                "preflight",
                "preflight:json",
                "security:check",
                "test",
            },
            set(self.scripts),
        )
        self.assertFalse(any(name.startswith("start:") for name in self.scripts))

    def test_script_file_paths_exist(self) -> None:
        for command in self.scripts.values():
            tokens = shlex.split(command, posix=False)
            paths: list[str] = []
            for index, token in enumerate(tokens):
                normalized = token.strip('"')
                if normalized.endswith(".py") or normalized.endswith(".ps1"):
                    paths.append(normalized)
                if normalized.lower() == "-file" and index + 1 < len(tokens):
                    paths.append(tokens[index + 1].strip('"'))
            for path in paths:
                self.assertTrue((REPO_ROOT / path).exists(), f"missing script path in command: {command}")

    def test_photoshop_diagnose_uses_real_scripts_directory(self) -> None:
        self.assertIn(
            "examples/photoshop_bridge/scripts/diagnose_local.ps1",
            self.scripts["photoshop:diagnose"],
        )

    def test_adobe_demo_scripts_are_registered(self) -> None:
        for name in (
            "illustrator:demo",
            "illustrator:demo:plan",
            "photoshop:demo",
            "photoshop:demo:plan",
        ):
            self.assertIn(name, self.scripts)


if __name__ == "__main__":
    unittest.main()
