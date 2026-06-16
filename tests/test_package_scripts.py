from __future__ import annotations

import json
import re
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
                "starbridge:roots",
                "starbridge:evidence:init",
                "starbridge:evidence:validate",
                "starbridge:job-status",
                "starbridge:mcp",
                "starbridge:plan",
                "starbridge:gui-instructions",
                "starbridge:demo:photoshop:gui",
                "starbridge:demo:illustrator:gui",
                "starbridge:demo:capcut:gui",
                "status:manifest",
                "status:manifest:json",
                "status:probe",
                "status:probe:json",
                "cad:dxf:dry-run",
                "comfy:probe",
                "comfy:workflow:validate",
                "comfy:txt2img",
                "photoshop:probe",
                "photoshop:node-proxy",
                "photoshop:diagnose",
                "photoshop:info",
                "photoshop:demo:plan",
                "photoshop:demo",
                "photoshop:manifest",
                "photoshop:camera-raw:tune",
                "photoshop:camera-raw:export",
                "illustrator:info",
                "illustrator:demo:plan",
                "illustrator:demo",
                "illustrator:manifest",
                "preflight",
                "preflight:json",
                "security:check",
                "frontend:dev",
                "frontend:build",
                "test",
                "test:pytest",
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

    def test_pyproject_declares_expected_extras(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^\[project\.optional-dependencies\]\s*(.*?)(?:^\[|\Z)", text)
        self.assertIsNotNone(match)
        extras_block = match.group(1)

        for extra in ("dev", "cad", "comfy", "adobe"):
            self.assertRegex(extras_block, rf"(?m)^{extra}\s*=")
        self.assertIn("pytest>=8", extras_block)
        self.assertIn("ezdxf>=1.3", extras_block)


if __name__ == "__main__":
    unittest.main()
