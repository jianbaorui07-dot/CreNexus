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
                "starbridge:backend",
                "starbridge:plan",
                "starbridge:gui-instructions",
                "starbridge:demo:photoshop:gui",
                "starbridge:demo:illustrator:gui",
                "starbridge:demo:capcut:gui",
                "install:check",
                "install:check:json",
                "install:bootstrap",
                "install:bootstrap:dry-run",
                "install:quick",
                "install:quick:dry-run",
                "install:from-url",
                "install:from-url:dry-run",
                "mcp:registry:preview",
                "codex:coordinator:self-test",
                "codex:coordinator:plan",
                "codex:coordinator:install:dry-run",
                "package:python:check",
                "status:manifest",
                "status:manifest:json",
                "status:probe",
                "status:probe:json",
                "cad:dxf:dry-run",
                "blender:scene:plan",
                "blender:reference:plan",
                "comfy:probe",
                "comfy:workflow:validate",
                "comfy:templates:list",
                "comfy:templates:get",
                "comfy:templates:from",
                "comfy:lifecycle:template",
                "comfy:txt2img",
                "drawio:probe",
                "drawio:capabilities",
                "drawio:plan",
                "drawio:demo",
                "drawio:validate",
                "drawio:rollback",
                "drawio:export",
                "drawio:handoff",
                "drawio:batch",
                "photoshop:probe",
                "photoshop:node-proxy",
                "photoshop:diagnose",
                "photoshop:info",
                "photoshop:demo:plan",
                "photoshop:demo",
                "photoshop:manifest",
                "photoshop:layers",
                "photoshop:layers:regression",
                "photoshop:camera-raw:tune",
                "photoshop:camera-raw:export",
                "illustrator:info",
                "illustrator:realtime:proxy",
                "illustrator:realtime:adapter",
                "illustrator:realtime:capture",
                "illustrator:preflight:plan",
                "illustrator:vectorize",
                "illustrator:vectorize:offline",
                "illustrator:vectorize:legacy-quantized",
                "vector-app:start",
                "illustrator:demo:plan",
                "illustrator:demo",
                "illustrator:manifest",
                "capcut:draft:structure",
                "preflight",
                "preflight:json",
                "security:check",
                "product:facts:check",
                "text:encoding:check",
                "canvas:dev",
                "canvas:build",
                "canvas:mcp",
                "frontend:dev",
                "frontend:build",
                "desktop:install",
                "desktop:test",
                "desktop:build",
                "desktop:prerequisites",
                "desktop:sidecar:build",
                "desktop:sidecar:test",
                "brand:build",
                "site:build",
                "app:dev",
                "test",
                "test:pytest",
                "lint",
                "format",
                "format-check",
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
                self.assertTrue(
                    (REPO_ROOT / path).exists(), f"missing script path in command: {command}"
                )

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

    def test_illustrator_exact_vector_shortcut_is_primary(self) -> None:
        self.assertEqual(
            "python examples/illustrator_bridge/scripts/exact_pixel_vector.py",
            self.scripts["illustrator:vectorize:offline"],
        )
        self.assertEqual(
            "python examples/illustrator_bridge/scripts/trace_photo_preview.py",
            self.scripts["illustrator:vectorize:legacy-quantized"],
        )

    def test_comfy_template_shortcuts_are_registered(self) -> None:
        self.assertEqual(
            "python examples/comfy_bridge/workflow_templates.py list --json",
            self.scripts["comfy:templates:list"],
        )
        self.assertEqual(
            "python examples/comfy_bridge/workflow_templates.py get --template-id txt2img_basic_v1 --json",
            self.scripts["comfy:templates:get"],
        )
        self.assertEqual(
            "python examples/comfy_bridge/workflow_templates.py from-template --template-id txt2img_basic_v1 --json",
            self.scripts["comfy:templates:from"],
        )
        self.assertEqual(
            "python examples/comfy_bridge/workflow_lifecycle.py --template-id txt2img_basic_v1 --json",
            self.scripts["comfy:lifecycle:template"],
        )

    def test_pyproject_declares_expected_extras(self) -> None:
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^\[project\.optional-dependencies\]\s*(.*?)(?:^\[|\Z)", text)
        self.assertIsNotNone(match)
        extras_block = match.group(1)

        for extra in (
            "dev",
            "cad",
            "comfy",
            "adobe",
            "image-to-psd",
            "illustrator-trace",
            "illustrator-vector",
            "vectorization",
            "vector-refinement",
            "vector-app",
        ):
            self.assertRegex(extras_block, rf"(?m)^{extra}\s*=")
        self.assertIn("pytest>=8", extras_block)
        self.assertIn("ezdxf>=1.3", extras_block)
        self.assertIn('starbridge-backend = "starbridge_mcp.backend:main"', text)


if __name__ == "__main__":
    unittest.main()
