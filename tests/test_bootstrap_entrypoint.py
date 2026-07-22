from __future__ import annotations

import json
import ntpath
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("powershell"), "Windows PowerShell is required")
class BootstrapEntrypointTests(unittest.TestCase):
    def test_profile_is_forwarded_by_name_and_dry_run_returns_json(self) -> None:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(REPO_ROOT / "bootstrap.ps1"),
                "-Profile",
                "auto",
                "-SkipNode",
                "-SkipCodexConfig",
                "-DryRun",
                "-Json",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("auto", payload["profile_requested"])
        self.assertIn(payload["profile_applied"], {"core", "standard"})
        self.assertTrue(payload["ok"])


@unittest.skipUnless(
    os.name != "nt" and shutil.which("bash"),
    "Bash on a POSIX platform is required",
)
class PosixBootstrapEntrypointTests(unittest.TestCase):
    def run_bootstrap(self, repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(repo_root / "bootstrap.sh"), *arguments],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def make_config_fixture(
        self, temporary_root: Path, directory_name: str = "CreNexus config with spaces"
    ) -> tuple[Path, dict[str, str]]:
        repo_root = temporary_root / directory_name
        fake_bin = temporary_root / "bin"
        (repo_root / "starbridge_mcp").mkdir(parents=True)
        coordinator = repo_root / "plugins/starbridge-version-coordinator/scripts"
        coordinator.mkdir(parents=True)
        (coordinator / "version_coordinator_mcp.py").write_text("", encoding="utf-8")
        (repo_root / "pyproject.toml").write_text("[project]\nname = 'fixture'\n", encoding="utf-8")
        (repo_root / "package.json").write_text("{}\n", encoding="utf-8")
        shutil.copy2(REPO_ROOT / "bootstrap.sh", repo_root / "bootstrap.sh")

        fake_bin.mkdir()
        fake_python = fake_bin / "python3"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "set -eu\n"
            "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"--version\" ]]; then echo 'Python 3.12.1'; exit 0; fi\n"
            "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-c\" && \"${3:-}\" == *STARBRIDGE_VENV_PREFIX_CHECK* ]]; then\n"
            "  prefix=$(cd -P \"$(dirname \"$0\")/..\" && pwd -P)\n"
            "  base=/fixture/base\n"
            "  printf '%s\\n' \"$prefix\" \"$base\" 'Python 3.12.1' \\\n"
            "    \"$prefix/bin\" \"$prefix/lib/python3.12/site-packages\" \\\n"
            "    \"$prefix/lib/python3.12/site-packages\" \"$prefix\" \"$base/include\" \\\n"
            "    \"$prefix/bin\" \"$prefix/lib/python3.12/site-packages\" \\\n"
            "    \"$prefix/lib/python3.12/site-packages\" \"$prefix\" \\\n"
            "    \"$prefix/include/site/python3.12/starbridge-bootstrap-probe\"\n"
            "  exit 0\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-\" ]]; then\n"
            f"  exec {shlex.quote(sys.executable)} \"$@\"\n"
            "fi\n"
            "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-m\" && \"${3:-}\" == \"venv\" ]]; then\n"
            "  mkdir -p \"$4/bin\" \"$4/lib/python3.12/site-packages\"\n"
            "  cp \"$0\" \"$4/bin/python\"\n"
            "  chmod +x \"$4/bin/python\"\n"
            "  printf 'home = fixture\\n' > \"$4/pyvenv.cfg\"\n"
            "fi\n",
            encoding="utf-8",
        )
        fake_python.chmod(0o755)
        environment = os.environ | {"PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}
        return repo_root, environment

    def run_fixture_bootstrap(
        self, repo_root: Path, environment: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(repo_root / "bootstrap.sh"), "--profile", "core", "--skip-node", "--json"],
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=environment,
        )

    def load_toml(self, path: Path) -> dict[str, object]:
        try:
            import tomllib
        except ModuleNotFoundError:  # Python 3.10 project environments install tomli.
            import tomli as tomllib

        with path.open("rb") as source:
            return tomllib.load(source)

    def assert_no_config_temporaries(self, config_path: Path) -> None:
        self.assertEqual([], list(config_path.parent.glob(".config.toml.*")))

    def windows_managed_config(
        self,
        base: str = "[existing]\r\nkeep = true",
        root: str = r"C:\CreNexus",
        pythonpath: str | None = None,
    ) -> bytes:
        python = ntpath.join(root, ".venv", "Scripts", "python.exe")
        coordinator = ntpath.join(
            root,
            "plugins",
            "starbridge-version-coordinator",
            "scripts",
            "version_coordinator_mcp.py",
        )
        lines = [
            "# BEGIN STARBRIDGE QUICKSTART (managed by scripts/quickstart.ps1)",
            "[mcp_servers.starbridge]",
            f"command = {json.dumps(python)}",
            'args = ["-m", "starbridge_mcp.mcp_server"]',
            f"cwd = {json.dumps(root)}",
            "",
            "[mcp_servers.starbridge.env]",
            'STARBRIDGE_PHOTOSHOP_SAFE_ONLY = "1"',
            'STARBRIDGE_PHOTOSHOP_DEFAULT_DRY_RUN = "1"',
            'STARBRIDGE_PHOTOSHOP_ALLOW_DESTRUCTIVE = "0"',
        ]
        if pythonpath is not None:
            lines.append(f"PYTHONPATH = {json.dumps(pythonpath)}")
        lines.extend(
            [
                "",
                "[mcp_servers.starbridge-version-coordinator]",
                f"command = {json.dumps(python)}",
                f"args = [{json.dumps(coordinator)}]",
                f"cwd = {json.dumps(root)}",
                "# END STARBRIDGE QUICKSTART",
                "",
            ]
        )
        block = "\r\n".join(lines)
        return (base + "\r\n" + block).encode("utf-8")

    def make_fake_existing_venv(
        self,
        repo_root: Path,
        trace: Path,
        overrides: dict[str, str] | None = None,
    ) -> dict[str, str]:
        venv = repo_root / ".venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "lib/python3.12/site-packages").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
        prefix = str(venv.resolve())
        base = "/fixture/base"
        values = {
            "prefix": prefix,
            "base_prefix": base,
            "version": "Python 3.12.1",
            "sys_scripts": f"{prefix}/bin",
            "sys_purelib": f"{prefix}/lib/python3.12/site-packages",
            "sys_platlib": f"{prefix}/lib/python3.12/site-packages",
            "sys_data": prefix,
            "sys_include": f"{base}/include",
            "pip_scripts": f"{prefix}/bin",
            "pip_purelib": f"{prefix}/lib/python3.12/site-packages",
            "pip_platlib": f"{prefix}/lib/python3.12/site-packages",
            "pip_data": prefix,
            "pip_headers": f"{prefix}/include/site/python3.12/starbridge-bootstrap-probe",
        }
        values.update(overrides or {})
        ordered = (
            "prefix",
            "base_prefix",
            "version",
            "sys_scripts",
            "sys_purelib",
            "sys_platlib",
            "sys_data",
            "sys_include",
            "pip_scripts",
            "pip_purelib",
            "pip_platlib",
            "pip_data",
            "pip_headers",
        )
        output_arguments = " ".join(shlex.quote(values[name]) for name in ordered)
        venv_python = venv / "bin/python"
        venv_python.write_text(
            "#!/usr/bin/env bash\n"
            f"printf '%s:%s\\n' \"${{1:-}}\" \"${{2:-}}\" >> {shlex.quote(str(trace))}\n"
            "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-c\" && \"${3:-}\" == *STARBRIDGE_VENV_PREFIX_CHECK* ]]; then\n"
            f"  printf '%s\\n' {output_arguments}\n"
            "  exit 0\n"
            "fi\n"
            "exit 92\n",
            encoding="utf-8",
        )
        venv_python.chmod(0o755)
        return values

    def configure_offline_build_backend(self, repo_root: Path) -> None:
        (repo_root / "pyproject.toml").write_text(
            "[build-system]\n"
            "requires = []\n"
            "build-backend = 'offline_backend'\n"
            "backend-path = ['.']\n\n"
            "[project]\n"
            "name = 'fixture'\n"
            "version = '1.0'\n",
            encoding="utf-8",
        )
        (repo_root / "offline_backend.py").write_text(
            "from pathlib import Path\n"
            "from zipfile import ZIP_DEFLATED, ZipFile\n\n"
            "DIST_INFO = 'fixture-1.0.dist-info'\n"
            "METADATA = (\n"
            "    'Metadata-Version: 2.1\\nName: fixture\\nVersion: 1.0\\n'\n"
            "    'Provides-Extra: dev\\nProvides-Extra: vectorization\\n'\n"
            ")\n"
            "WHEEL = (\n"
            "    'Wheel-Version: 1.0\\nGenerator: starbridge-test\\n'\n"
            "    'Root-Is-Purelib: true\\nTag: py3-none-any\\n'\n"
            ")\n\n"
            "def get_requires_for_build_wheel(config_settings=None):\n"
            "    return []\n\n"
            "def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):\n"
            "    target = Path(metadata_directory, DIST_INFO)\n"
            "    target.mkdir()\n"
            "    target.joinpath('METADATA').write_text(METADATA, encoding='utf-8')\n"
            "    target.joinpath('WHEEL').write_text(WHEEL, encoding='utf-8')\n"
            "    return DIST_INFO\n\n"
            "def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):\n"
            "    wheel_name = 'fixture-1.0-py3-none-any.whl'\n"
            "    entries = {\n"
            "        'starbridge_mcp/__init__.py': '',\n"
            "        'starbridge_mcp/server.py': '',\n"
            "        f'{DIST_INFO}/METADATA': METADATA,\n"
            "        f'{DIST_INFO}/WHEEL': WHEEL,\n"
            "    }\n"
            "    record = ''.join(f'{name},,\\n' for name in entries)\n"
            "    record += f'{DIST_INFO}/RECORD,,\\n'\n"
            "    entries[f'{DIST_INFO}/RECORD'] = record\n"
            "    with ZipFile(Path(wheel_directory, wheel_name), 'w', ZIP_DEFLATED) as wheel:\n"
            "        for name, content in entries.items():\n"
            "            wheel.writestr(name, content)\n"
            "    return wheel_name\n",
            encoding="utf-8",
        )

    def python_injection_environment(
        self, temporary_root: Path, trace: Path
    ) -> dict[str, str]:
        attacker = temporary_root / "python-injection"
        (attacker / "venv").mkdir(parents=True)
        tracer_code = (
            "from pathlib import Path\n"
            f"with Path({str(trace)!r}).open('a', encoding='utf-8') as target:\n"
            "    target.write('executed\\n')\n"
        )
        (attacker / "sitecustomize.py").write_text(tracer_code, encoding="utf-8")
        (attacker / "venv/__init__.py").write_text("", encoding="utf-8")
        (attacker / "venv/__main__.py").write_text(tracer_code, encoding="utf-8")
        startup = attacker / "startup.py"
        startup.write_text(tracer_code, encoding="utf-8")

        userbase = temporary_root / "python-userbase"
        user_site = userbase / (
            f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
        )
        user_site.mkdir(parents=True)
        (user_site / "sitecustomize.py").write_text(tracer_code, encoding="utf-8")
        return {
            "PYTHONPATH": str(attacker),
            "PYTHONUSERBASE": str(userbase),
            "PYTHONHOME": str(temporary_root / "invalid-python-home"),
            "PYTHONSTARTUP": str(startup),
            "PYTHONWARNINGS": "error::RuntimeWarning",
            "__PYVENV_LAUNCHER__": str(temporary_root / "outside-launcher"),
        }

    def test_help_describes_safe_platform_boundaries(self) -> None:
        completed = self.run_bootstrap(REPO_ROOT, "--help")

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("Usage: bash ./bootstrap.sh", completed.stdout)
        self.assertIn("never installed or changed", completed.stdout)
        self.assertIn("never\ninvokes the Tauri desktop application", completed.stdout)

    def test_profiles_keep_python_extra_contract_and_dry_run_is_json(self) -> None:
        expected_extras = {
            "core": {"dev", "vectorization"},
            "standard": {"dev", "vectorization", "cad", "comfy", "adobe", "illustrator-vector"},
            "all": {
                "dev",
                "vectorization",
                "cad",
                "comfy",
                "adobe",
                "illustrator-vector",
                "illustrator-trace",
                "vector-refinement",
                "vector-app",
            },
        }
        for profile, extras in expected_extras.items():
            with self.subTest(profile=profile):
                completed = self.run_bootstrap(
                    REPO_ROOT,
                    "--profile",
                    profile,
                    "--skip-node",
                    "--skip-codex-config",
                    "--dry-run",
                    "--json",
                )

                self.assertEqual(0, completed.returncode, completed.stderr)
                payload = json.loads(completed.stdout)
                self.assertTrue(payload["ok"])
                self.assertEqual(profile, payload["profile_requested"])
                self.assertEqual(profile, payload["profile_applied"])
                self.assertEqual(extras, set(payload["extras"]))
                self.assertEqual(".venv/bin/python", payload["venv"])
                self.assertIsNone(payload["codex_config"])
                self.assertTrue(
                    any(
                        step["name"] == "install Python extras" and step["status"] == "planned"
                        for step in payload["steps"]
                    )
                )

    def test_dry_run_resolves_a_repository_path_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            linked_repo = Path(temporary_directory) / "CreNexus checkout with spaces"
            linked_repo.symlink_to(REPO_ROOT, target_is_directory=True)
            completed = self.run_bootstrap(
                linked_repo,
                "--profile",
                "core",
                "--skip-node",
                "--skip-codex-config",
                "--dry-run",
                "--json",
            )

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(str(REPO_ROOT.resolve()), payload["repo"])
            venv_step = next(
                step for step in payload["steps"] if step["name"] == "create virtual environment"
            )
            self.assertIn(str(REPO_ROOT.resolve()), venv_step["detail"])

    def test_config_write_preserves_valid_base_bytes_and_is_idempotent(self) -> None:
        cases = {
            "empty": b"",
            "crlf": b"[existing]\r\nkeep = true\r\n",
            "no_final_newline": b"[existing]\nkeep = true",
            "other_mcp": b'[mcp_servers.user-managed]\ncommand = "keep"\n',
        }
        for name, original in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f'CreNexus {name} with spaces "and quote" \\ path'
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(original)

                snapshots = []
                for _ in range(3):
                    completed = self.run_fixture_bootstrap(repo_root, environment)
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    self.assertTrue(json.loads(completed.stdout)["ok"])
                    snapshots.append(codex_config.read_bytes())

                self.assertEqual(snapshots[0], snapshots[1])
                self.assertEqual(snapshots[1], snapshots[2])
                self.assertTrue(snapshots[0].startswith(original))
                config_text = snapshots[0].decode("utf-8")
                self.assertEqual(
                    1,
                    config_text.count(
                        "# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf="
                    ),
                )
                self.assertIn('\\"and quote\\"', config_text)
                self.assertIn('\\\\ path', config_text)
                parsed = self.load_toml(codex_config)
                servers = parsed["mcp_servers"]
                physical_repo = repo_root.resolve()
                self.assertEqual(
                    f"{physical_repo}/.venv/bin/python", servers["starbridge"]["command"]
                )
                self.assertEqual(str(physical_repo), servers["starbridge"]["cwd"])
                if name == "other_mcp":
                    self.assertEqual("keep", servers["user-managed"]["command"])
                self.assert_no_config_temporaries(codex_config)

    def test_legacy_exact_managed_block_is_migrated_without_rewriting_user_config(self) -> None:
        original = b"[existing]\nkeep = true\n"
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            repo_root, environment = self.make_config_fixture(Path(temporary_directory), "legacy")
            codex_config = repo_root / ".codex/config.toml"
            codex_config.parent.mkdir()
            codex_config.write_bytes(original)

            first_run = self.run_fixture_bootstrap(repo_root, environment)
            self.assertEqual(0, first_run.returncode, first_run.stderr)
            current = codex_config.read_bytes()
            legacy = current.replace(
                b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=1)",
                b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh)",
            )
            self.assertNotEqual(current, legacy)
            codex_config.write_bytes(legacy)

            migrated_run = self.run_fixture_bootstrap(repo_root, environment)

            self.assertEqual(0, migrated_run.returncode, migrated_run.stderr)
            self.assertEqual(current, codex_config.read_bytes())
            self.assertTrue(codex_config.read_bytes().startswith(original))
            self.load_toml(codex_config)
            self.assert_no_config_temporaries(codex_config)

    def test_cross_platform_managed_markers_and_crlf_are_byte_stable(self) -> None:
        for name in ("windows_crlf", "posix_crlf", "legacy_crlf"):
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(Path(temporary_directory), name)
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                base = b"[existing]\r\nkeep = true"

                if name == "windows_crlf":
                    codex_config.write_bytes(self.windows_managed_config())
                else:
                    codex_config.write_bytes(b"[existing]\nkeep = true")
                    initial = self.run_fixture_bootstrap(repo_root, environment)
                    self.assertEqual(0, initial.returncode, initial.stderr)
                    converted = codex_config.read_bytes().replace(b"\r\n", b"\n")
                    converted = converted.replace(b"\n", b"\r\n")
                    if name == "legacy_crlf":
                        converted = converted.replace(
                            b"# BEGIN STARBRIDGE QUICKSTART "
                            b"(managed by bootstrap.sh; prefix-lf=1)",
                            b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh)",
                        )
                    codex_config.write_bytes(converted)

                snapshots = []
                for _ in range(3):
                    completed = self.run_fixture_bootstrap(repo_root, environment)
                    self.assertEqual(0, completed.returncode, completed.stderr)
                    snapshots.append(codex_config.read_bytes())

                self.assertEqual(snapshots[0], snapshots[1])
                self.assertEqual(snapshots[1], snapshots[2])
                self.assertTrue(snapshots[0].startswith(base))
                self.assertNotIn(b"managed by scripts/quickstart.ps1", snapshots[0])
                self.assertEqual(
                    1,
                    snapshots[0].count(
                        b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf="
                    ),
                )
                self.load_toml(codex_config)
                self.assert_no_config_temporaries(codex_config)

    def test_windows_managed_root_accepts_only_canonical_resolve_path_forms(self) -> None:
        accepted = (
            r"C:\CreNexus",
            r"C:\Creative Work\CreNexus",
            "C:\\",
            r"\\server\share\CreNexus",
            r"\\server\share",
        )
        for index, root in enumerate(accepted):
            with self.subTest(root=root), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f"windows-good-{index}"
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(self.windows_managed_config(root=root))

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.load_toml(codex_config)
                self.assertNotIn("scripts/quickstart.ps1", codex_config.read_text(encoding="utf-8"))
                self.assert_no_config_temporaries(codex_config)

    def test_windows_managed_root_rejects_noncanonical_or_non_source_forms(self) -> None:
        rejected = (
            r"relative\repo",
            "/tmp/fake-win-repo",
            r"C:repo",
            r"C:\CreNexus\..\Other",
            r"C:\CreNexus\.",
            r"c:\CreNexus",
            "C:\\CreNexus\\",
            'C:\\Cre"Nexus',
            r"\\server",
            r"\\server\share\CreNexus\..\Other",
            r"C:\CreNexus\\Nested",
            r"C:\Work\file:stream",
            "C:\\Work\\trailing ",
            r"C:\Work\trailing.",
            "C:\\Work\\control\x1f",
        )
        for index, root in enumerate(rejected):
            with self.subTest(root=root), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f"windows-bad-{index}"
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                original = self.windows_managed_config(root=root)
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("ambiguous managed block", completed.stderr)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)

    def test_windows_managed_root_rejects_reserved_device_segments(self) -> None:
        rejected = (
            r"C:\CON\Repo",
            r"C:\AUX",
            r"C:\NUL.txt",
            r"C:\Work\COM1",
            r"C:\Work\LPT9.log",
            r"C:\Folder\PRN.txt",
            r"C:\Work\con.any.extension",
            r"C:\Work\CON .txt",
            r"C:\Work\COM1 .log",
            r"C:\Work\COM¹",
            r"C:\Work\LPT².log",
            r"C:\Work\com³.any.extension",
            r"C:\Work\CONIN$",
            r"C:\Work\conout$.log",
            r"\\server\share\AUX.txt",
            r"\\server\NUL\Repo",
            r"\\server\share\COM¹.txt",
            r"\\server\LPT³\Repo",
            r"\\server\share\CONOUT$",
        )
        accepted = (
            r"C:\console\Repo",
            r"C:\auxiliary",
            r"C:\Work\COM10",
            r"C:\Work\LPT0.log",
            r"C:\Work\NULled.txt",
            r"C:\Work\COM⁰",
            r"C:\Work\COM⁴.txt",
            r"C:\Work\LPT¹backup",
            r"C:\Work\CONINBOX$",
            r"C:\Work\CONOUTPUT$",
            r"\\server\share\console",
        )
        for index, root in enumerate(rejected):
            with self.subTest(kind="rejected", root=root), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f"windows-device-bad-{index}"
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                original = self.windows_managed_config(root=root)
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)

        for index, root in enumerate(accepted):
            with self.subTest(kind="accepted", root=root), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f"windows-device-good-{index}"
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(self.windows_managed_config(root=root))

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.load_toml(codex_config)
                self.assert_no_config_temporaries(codex_config)

    def test_windows_managed_block_rejects_pythonpath_not_emitted_by_quickstart(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            repo_root, environment = self.make_config_fixture(
                Path(temporary_directory), "windows-pythonpath"
            )
            codex_config = repo_root / ".codex/config.toml"
            codex_config.parent.mkdir()
            original = self.windows_managed_config(
                root=r"C:\CreNexus", pythonpath=r"C:\CreNexus"
            )
            codex_config.write_bytes(original)

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertNotEqual(0, completed.returncode)
            self.assertEqual(original, codex_config.read_bytes())
            self.assert_no_config_temporaries(codex_config)

    def test_windows_managed_args_and_cwd_must_derive_from_the_same_root(self) -> None:
        root = r"C:\CreNexus"
        other = r"D:\Other"
        valid_text = self.windows_managed_config(root=root).decode("utf-8")
        coordinator = ntpath.join(
            root,
            "plugins",
            "starbridge-version-coordinator",
            "scripts",
            "version_coordinator_mcp.py",
        )
        other_coordinator = ntpath.join(
            other,
            "plugins",
            "starbridge-version-coordinator",
            "scripts",
            "version_coordinator_mcp.py",
        )
        bad_args = valid_text.replace(
            f"args = [{json.dumps(coordinator)}]",
            f"args = [{json.dumps(other_coordinator)}]",
        )
        cwd_line = f"cwd = {json.dumps(root)}"
        head, separator, tail = valid_text.rpartition(cwd_line)
        self.assertTrue(separator)
        bad_coordinator_cwd = head + f"cwd = {json.dumps(other)}" + tail

        for name, text in {
            "coordinator_args": bad_args,
            "coordinator_cwd": bad_coordinator_cwd,
        }.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), name
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                original = text.encode("utf-8")
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)

    def test_managed_block_with_unmanaged_toml_data_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            repo_root, environment = self.make_config_fixture(Path(temporary_directory), "managed-extra")
            codex_config = repo_root / ".codex/config.toml"
            codex_config.parent.mkdir()

            first_run = self.run_fixture_bootstrap(repo_root, environment)
            self.assertEqual(0, first_run.returncode, first_run.stderr)
            original = codex_config.read_bytes().replace(
                b"# END STARBRIDGE QUICKSTART\n",
                b"[unmanaged]\nkeep = true\n# END STARBRIDGE QUICKSTART\n",
            )
            codex_config.write_bytes(original)

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("ambiguous managed block", completed.stderr)
            self.assertEqual(original, codex_config.read_bytes())
            self.assert_no_config_temporaries(codex_config)

    def test_marker_text_in_toml_strings_and_prefix_comments_is_preserved(self) -> None:
        begin = b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=0)"
        end = b"# END STARBRIDGE QUICKSTART"
        cases = {
            "multiline_basic": b'message = """\n' + begin + b"\n" + end + b'\n"""\n',
            "multiline_literal": b"message = '''\n" + begin + b"\n" + end + b"\n'''\n",
            "prefix_comment": begin + b" documentation only\n[existing]\nkeep = true\n",
            "ordinary_string": b'value = "' + begin + b'"\n',
        }
        for name, original in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(Path(temporary_directory), name)
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertTrue(codex_config.read_bytes().startswith(original))
                self.load_toml(codex_config)
                self.assert_no_config_temporaries(codex_config)

    def test_exact_markers_without_the_expected_schema_fail_closed(self) -> None:
        begin = b"# BEGIN STARBRIDGE QUICKSTART (managed by bootstrap.sh; prefix-lf=0)\n"
        end = b"# END STARBRIDGE QUICKSTART\n"
        cases = {
            "unclosed_exact_marker": begin + b"[existing]\nkeep = true\n",
            "repeated_exact_marker": begin + end + begin + end,
            "nonmanaged_data_inside_exact_markers": begin + b"[existing]\nkeep = true\n" + end,
            "ordinary_exact_marker_comments": begin + end,
        }
        for name, original in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(Path(temporary_directory), name)
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("no configuration changes were made", completed.stderr)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)

    def test_config_conflicts_fail_closed_without_rewriting_bytes(self) -> None:
        cases = {
            "server_table": b'[mcp_servers.starbridge]\ncommand = "user-managed"\n',
            "server_subtable": b'[mcp_servers.starbridge.env]\nSAFE = "0"\n',
            "server_key": b'[mcp_servers]\nstarbridge = "user-managed"\n',
            "coordinator_table": b'[mcp_servers.starbridge-version-coordinator]\ncommand = "user-managed"\n',
        }
        for name, original in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
                repo_root, environment = self.make_config_fixture(Path(temporary_directory), name)
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("refusing to overwrite", completed.stderr)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)

    def test_invalid_toml_fails_closed(self) -> None:
        original = b"[broken\n"
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            repo_root, environment = self.make_config_fixture(Path(temporary_directory), "invalid_toml")
            codex_config = repo_root / ".codex/config.toml"
            codex_config.parent.mkdir()
            codex_config.write_bytes(original)

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("no configuration changes were made", completed.stderr)
            self.assertEqual(original, codex_config.read_bytes())
            self.assert_no_config_temporaries(codex_config)

    def test_codex_directory_must_be_a_real_repository_local_directory(self) -> None:
        cases = ["external_symlink", "dangling_symlink", "regular_file"]
        if hasattr(os, "mkfifo"):
            cases.append("fifo")

        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                repo_root, environment = self.make_config_fixture(temporary_root, name)
                codex_dir = repo_root / ".codex"
                outside = temporary_root / "outside-codex"
                if name == "external_symlink":
                    outside.mkdir()
                    codex_dir.symlink_to(outside, target_is_directory=True)
                elif name == "dangling_symlink":
                    codex_dir.symlink_to(outside, target_is_directory=True)
                elif name == "regular_file":
                    codex_dir.write_bytes(b"user data\n")
                else:
                    os.mkfifo(codex_dir)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn(".codex must be a real directory", completed.stderr)
                self.assertFalse((repo_root / ".venv").exists())
                if name == "external_symlink":
                    self.assertEqual([], list(outside.iterdir()))
                elif name == "dangling_symlink":
                    self.assertFalse(outside.exists())
                elif name == "regular_file":
                    self.assertEqual(b"user data\n", codex_dir.read_bytes())
                else:
                    self.assertTrue(stat.S_ISFIFO(codex_dir.lstat().st_mode))

    def test_external_venv_symlink_never_executes_its_python(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "external-venv")
            outside_venv = temporary_root / "outside-venv"
            (outside_venv / "bin").mkdir(parents=True)
            (outside_venv / "pyvenv.cfg").write_text("home = outside\n", encoding="utf-8")
            trace = temporary_root / "outside-python.trace"
            outside_python = outside_venv / "bin/python"
            outside_python.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'executed\\n' >> {shlex.quote(str(trace))}\n"
                "exit 99\n",
                encoding="utf-8",
            )
            outside_python.chmod(0o755)
            (repo_root / ".venv").symlink_to(outside_venv, target_is_directory=True)

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn(".venv must be a real directory", completed.stderr)
            self.assertFalse(trace.exists())
            self.assertFalse((repo_root / ".codex").exists())

    def test_venv_critical_subpaths_fail_before_any_python_execution(self) -> None:
        cases = ["bin_symlink", "lib_symlink", "lib_file", "site_packages_symlink"]
        if hasattr(os, "mkfifo"):
            cases.append("include_fifo")

        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                repo_root, environment = self.make_config_fixture(temporary_root, name)
                venv = repo_root / ".venv"
                venv.mkdir()
                (venv / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
                outside = temporary_root / "outside-scheme"
                outside.mkdir()
                trace = temporary_root / "venv-subpath.trace"
                tracer = (
                    "#!/usr/bin/env bash\n"
                    f"printf 'executed\\n' >> {shlex.quote(str(trace))}\n"
                    "exit 93\n"
                )

                if name == "bin_symlink":
                    (outside / "python").write_text(tracer, encoding="utf-8")
                    (outside / "python").chmod(0o755)
                    (venv / "bin").symlink_to(outside, target_is_directory=True)
                    (venv / "lib").mkdir()
                else:
                    (venv / "bin").mkdir()
                    (venv / "bin/python").write_text(tracer, encoding="utf-8")
                    (venv / "bin/python").chmod(0o755)
                    if name == "lib_symlink":
                        (venv / "lib").symlink_to(outside, target_is_directory=True)
                    elif name == "lib_file":
                        (venv / "lib").write_text("not a directory\n", encoding="utf-8")
                    else:
                        (venv / "lib/python3.12").mkdir(parents=True)
                        if name == "site_packages_symlink":
                            (venv / "lib/python3.12/site-packages").symlink_to(
                                outside, target_is_directory=True
                            )
                        else:
                            (venv / "lib/python3.12/site-packages").mkdir()
                            os.mkfifo(venv / "include")

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertFalse(trace.exists())
                self.assertFalse((repo_root / ".codex").exists())
                self.assertEqual(
                    ["python"] if name == "bin_symlink" else [],
                    sorted(path.name for path in outside.iterdir()),
                )

    def test_venv_writable_install_schemes_must_remain_inside_venv(self) -> None:
        cases = (
            "sys_scripts",
            "sys_purelib",
            "sys_platlib",
            "sys_data",
            "pip_scripts",
            "pip_purelib",
            "pip_platlib",
            "pip_data",
            "pip_headers",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                repo_root, environment = self.make_config_fixture(temporary_root, name)
                outside = temporary_root / f"outside-{name}"
                trace = temporary_root / "venv-scheme.trace"
                self.make_fake_existing_venv(
                    repo_root, trace, overrides={name: str(outside)}
                )

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("installation scheme resolved outside", completed.stderr)
                self.assertEqual(["-I:-c"], trace.read_text(encoding="utf-8").splitlines())
                self.assertFalse(outside.exists())
                self.assertFalse((repo_root / ".codex").exists())

    def test_venv_sys_prefix_must_match_the_repository_local_venv(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "wrong-prefix")
            system_trace = temporary_root / "path-python.trace"
            path_python = temporary_root / "bin/python3"
            path_python.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'executed\\n' >> {shlex.quote(str(system_trace))}\n"
                "echo 'Python 3.12.1'\n",
                encoding="utf-8",
            )
            path_python.chmod(0o755)
            venv = repo_root / ".venv"
            (venv / "bin").mkdir(parents=True)
            (venv / "lib/python3.12/site-packages").mkdir(parents=True)
            (venv / "pyvenv.cfg").write_text("home = fixture\n", encoding="utf-8")
            outside_prefix = temporary_root / "outside-prefix"
            outside_prefix.mkdir()
            trace = temporary_root / "venv-python.trace"
            venv_python = venv / "bin/python"
            venv_python.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'STARBRIDGE_VENV_PREFIX_CHECK\\n' >> {shlex.quote(str(trace))}\n"
                "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-c\" && \"${3:-}\" == *STARBRIDGE_VENV_PREFIX_CHECK* ]]; then\n"
                f"  prefix={shlex.quote(str(outside_prefix.resolve()))}\n"
                "  base=/fixture/base\n"
                "  printf '%s\\n' \"$prefix\" \"$base\" 'Python 3.12.1' \\\n"
                "    \"$prefix/bin\" \"$prefix/lib/python3.12/site-packages\" \\\n"
                "    \"$prefix/lib/python3.12/site-packages\" \"$prefix\" \"$base/include\" \\\n"
                "    \"$prefix/bin\" \"$prefix/lib/python3.12/site-packages\" \\\n"
                "    \"$prefix/lib/python3.12/site-packages\" \"$prefix\" \\\n"
                "    \"$prefix/include/site/python3.12/starbridge-bootstrap-probe\"\n"
                "  exit 0\n"
                "fi\n"
                "exit 91\n",
                encoding="utf-8",
            )
            venv_python.chmod(0o755)

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("sys.prefix outside", completed.stderr)
            trace_lines = trace.read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(trace_lines))
            self.assertIn("STARBRIDGE_VENV_PREFIX_CHECK", trace_lines[0])
            self.assertFalse(system_trace.exists())
            self.assertFalse((repo_root / ".codex").exists())

    def test_new_and_existing_repository_local_venv_both_work(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "local-venv")
            fake_python = temporary_root / "bin/python3"
            fake_python.unlink()
            fake_python.symlink_to(sys.executable)
            self.configure_offline_build_backend(repo_root)
            environment = environment | {
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }

            first = self.run_fixture_bootstrap(repo_root, environment)
            second = self.run_fixture_bootstrap(repo_root, environment)

            self.assertEqual(0, first.returncode, first.stderr)
            self.assertEqual(0, second.returncode, second.stderr)
            first_step = json.loads(first.stdout)["steps"][0]
            second_step = json.loads(second.stdout)["steps"][0]
            self.assertEqual("completed", first_step["status"])
            self.assertEqual("skipped_existing", second_step["status"])
            self.assertFalse((repo_root / ".venv").is_symlink())
            self.assertTrue((repo_root / ".venv/pyvenv.cfg").is_file())
            prefix = subprocess.run(
                [str(repo_root / ".venv/bin/python"), "-c", "import os,sys; print(os.path.realpath(sys.prefix))"],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            ).stdout.strip()
            self.assertEqual(str((repo_root / ".venv").resolve()), prefix)

    def test_new_venv_isolated_before_probe_and_creation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "new-isolated")
            self.configure_offline_build_backend(repo_root)
            injection_trace = temporary_root / "python-injection.trace"
            environment_trace = temporary_root / "python-environment.trace"
            path_python = temporary_root / "bin/python3"
            path_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s|%s|%s|%s|%s|%s\\n' "
                "\"${PYTHONPATH-unset}\" \"${PYTHONUSERBASE-unset}\" "
                "\"${PYTHONHOME-unset}\" \"${PYTHONSTARTUP-unset}\" "
                "\"${PYTHONWARNINGS-unset}\" \"${__PYVENV_LAUNCHER__-unset}\" "
                f">> {shlex.quote(str(environment_trace))}\n"
                f"exec {shlex.quote(sys.executable)} \"$@\"\n",
                encoding="utf-8",
            )
            path_python.chmod(0o755)
            environment = environment | self.python_injection_environment(
                temporary_root, injection_trace
            )
            environment |= {
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(injection_trace.exists())
            self.assertGreaterEqual(
                len(environment_trace.read_text(encoding="utf-8").splitlines()), 2
            )
            self.assertEqual(
                {"unset|unset|unset|unset|unset|unset"},
                set(environment_trace.read_text(encoding="utf-8").splitlines()),
            )
            self.assertTrue((repo_root / ".venv/pyvenv.cfg").is_file())
            self.load_toml(repo_root / ".codex/config.toml")

    def test_existing_venv_helpers_and_verification_ignore_python_environment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "existing-isolated")
            self.configure_offline_build_backend(repo_root)
            subprocess.run(
                [sys.executable, "-m", "venv", str(repo_root / ".venv")],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            injection_trace = temporary_root / "python-injection.trace"
            environment = environment | self.python_injection_environment(
                temporary_root, injection_trace
            )
            environment |= {
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            }

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertEqual(0, completed.returncode, completed.stderr)
            self.assertFalse(injection_trace.exists())
            self.load_toml(repo_root / ".codex/config.toml")
            self.assert_no_config_temporaries(repo_root / ".codex/config.toml")

    def test_pip_target_overrides_and_config_files_cannot_write_outside_venv(self) -> None:
        cases = (
            "target",
            "prefix",
            "root",
            "userbase",
            "explicit_config",
            "user_config",
            "site_config",
            "python_runtime_env",
        )
        for name in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                temporary_root = Path(temporary_directory)
                repo_root, environment = self.make_config_fixture(temporary_root, name)
                self.configure_offline_build_backend(repo_root)
                venv = repo_root / ".venv"
                subprocess.run(
                    [sys.executable, "-m", "venv", str(venv)],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                outside = temporary_root / f"outside-{name}"
                home = temporary_root / "home"
                home.mkdir()
                environment = environment | {
                    "HOME": str(home),
                    "PIP_NO_INDEX": "1",
                    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                }
                if name == "target":
                    environment["PIP_TARGET"] = str(outside)
                elif name == "prefix":
                    environment["PIP_PREFIX"] = str(outside)
                elif name == "root":
                    environment["PIP_ROOT"] = str(outside)
                elif name == "userbase":
                    environment["PIP_USER"] = "1"
                    environment["PYTHONUSERBASE"] = str(outside)
                elif name == "explicit_config":
                    config = temporary_root / "attacker-pip.conf"
                    config.write_text(
                        "[install]\n"
                        f"target = {outside}\n"
                        f"prefix = {outside}\n"
                        "user = true\n",
                        encoding="utf-8",
                    )
                    environment["PIP_CONFIG_FILE"] = str(config)
                    environment["PYTHONUSERBASE"] = str(outside)
                elif name == "user_config":
                    user_config = home / ".config/pip"
                    user_config.mkdir(parents=True)
                    (user_config / "pip.conf").write_text(
                        f"[global]\nroot = {outside}\n", encoding="utf-8"
                    )
                elif name == "site_config":
                    (venv / "pip.conf").write_text(
                        f"[install]\ntarget = {outside}\n", encoding="utf-8"
                    )
                else:
                    attacker = temporary_root / "attacker-pythonpath/pip"
                    attacker.mkdir(parents=True)
                    attacker_trace = temporary_root / "attacker-pythonpath.trace"
                    (attacker / "__init__.py").write_text("", encoding="utf-8")
                    (attacker / "__main__.py").write_text(
                        "from pathlib import Path\n"
                        f"Path({str(attacker_trace)!r}).write_text('executed')\n",
                        encoding="utf-8",
                    )
                    environment["PYTHONPATH"] = str(attacker.parent)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertEqual(0, completed.returncode, completed.stderr)
                self.assertFalse(outside.exists())
                if name == "python_runtime_env":
                    self.assertFalse(attacker_trace.exists())
                self.assertTrue((venv / "lib").is_dir())
                self.load_toml(repo_root / ".codex/config.toml")

    def test_pip_sanitization_preserves_network_and_certificate_environment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cre nexus bootstrap ") as temporary_directory:
            temporary_root = Path(temporary_directory)
            repo_root, environment = self.make_config_fixture(temporary_root, "pip-env")
            identity_trace = temporary_root / "identity.trace"
            values = self.make_fake_existing_venv(repo_root, identity_trace)
            ordered = (
                "prefix",
                "base_prefix",
                "version",
                "sys_scripts",
                "sys_purelib",
                "sys_platlib",
                "sys_data",
                "sys_include",
                "pip_scripts",
                "pip_purelib",
                "pip_platlib",
                "pip_data",
                "pip_headers",
            )
            output_arguments = " ".join(shlex.quote(values[name]) for name in ordered)
            pip_trace = temporary_root / "pip-env.trace"
            venv_python = repo_root / ".venv/bin/python"
            venv_python.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-c\" ]]; then\n"
                f"  printf '%s\\n' {output_arguments}\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-m\" && \"${3:-}\" == \"pip\" ]]; then\n"
                f"  printf '%s|%s|%s|%s|%s|%s|%s\\n' \"${{PIP_TARGET-unset}}\" \"${{PIP_CONFIG_FILE-unset}}\" \"${{HTTPS_PROXY-unset}}\" \"${{PIP_PROXY-unset}}\" \"${{PIP_CERT-unset}}\" \"${{SSL_CERT_FILE-unset}}\" \"${{REQUESTS_CA_BUNDLE-unset}}\" >> {shlex.quote(str(pip_trace))}\n"
                "  exit 0\n"
                "fi\n"
                "if [[ \"${1:-}\" == \"-I\" && \"${2:-}\" == \"-\" ]]; then\n"
                f"  exec {shlex.quote(sys.executable)} \"$@\"\n"
                "fi\n"
                "exit 0\n",
                encoding="utf-8",
            )
            venv_python.chmod(0o755)
            environment = environment | {
                "PIP_TARGET": str(temporary_root / "outside-target"),
                "PIP_CONFIG_FILE": str(temporary_root / "bad-pip.conf"),
                "HTTPS_PROXY": "http://proxy.invalid:8443",
                "PIP_PROXY": "http://pip-proxy.invalid:8080",
                "PIP_CERT": "/certs/pip.pem",
                "SSL_CERT_FILE": "/certs/ssl.pem",
                "REQUESTS_CA_BUNDLE": "/certs/requests.pem",
            }

            completed = self.run_fixture_bootstrap(repo_root, environment)

            self.assertEqual(0, completed.returncode, completed.stderr)
            expected = (
                "unset|/dev/null|http://proxy.invalid:8443|"
                "http://pip-proxy.invalid:8080|/certs/pip.pem|"
                "/certs/ssl.pem|/certs/requests.pem"
            )
            self.assertEqual(
                [expected, expected], pip_trace.read_text(encoding="utf-8").splitlines()
            )
            self.assertFalse((temporary_root / "outside-target").exists())

    def test_nonregular_config_paths_fail_before_temporary_file_creation(self) -> None:
        cases: dict[str, tuple[str, bytes | None]] = {
            "directory": ("directory", None),
            "symlink": ("symlink", b"[existing]\nkeep = true\n"),
        }
        if hasattr(os, "mkfifo"):
            cases["fifo"] = ("fifo", None)

        for name, (kind, original) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(Path(temporary_directory), name)
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                if kind == "directory":
                    codex_config.mkdir()
                elif kind == "symlink":
                    target = repo_root / "user-managed.toml"
                    target.write_bytes(original or b"")
                    codex_config.symlink_to(target)
                else:
                    os.mkfifo(codex_config)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("regular non-symlink file", completed.stderr)
                if kind == "directory":
                    self.assertTrue(codex_config.is_dir())
                elif kind == "symlink":
                    self.assertTrue(codex_config.is_symlink())
                    self.assertEqual(original, (repo_root / "user-managed.toml").read_bytes())
                else:
                    self.assertTrue(stat.S_ISFIFO(codex_config.lstat().st_mode))
                self.assert_no_config_temporaries(codex_config)

    def test_control_character_repository_paths_fail_before_config_writes(self) -> None:
        for character in ("\n", "\r", "\x1f"):
            with self.subTest(character=repr(character)), tempfile.TemporaryDirectory(
                prefix="cre nexus bootstrap "
            ) as temporary_directory:
                repo_root, environment = self.make_config_fixture(
                    Path(temporary_directory), f"unsafe{character}checkout"
                )
                codex_config = repo_root / ".codex/config.toml"
                codex_config.parent.mkdir()
                original = b"[existing]\nkeep = true\n"
                codex_config.write_bytes(original)

                completed = self.run_fixture_bootstrap(repo_root, environment)

                self.assertNotEqual(0, completed.returncode)
                self.assertIn("ASCII control characters", completed.stderr)
                self.assertEqual(original, codex_config.read_bytes())
                self.assert_no_config_temporaries(codex_config)


if __name__ == "__main__":
    unittest.main()
