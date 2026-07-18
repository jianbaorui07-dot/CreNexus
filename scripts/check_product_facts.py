from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER_PATTERN = re.compile(
    r"^(?P<base>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<label>alpha|beta|rc)\.(?P<number>0|[1-9]\d*))?$"
)


def load_json(relative: str) -> dict[str, Any]:
    return json.loads((REPO_ROOT / relative).read_text(encoding="utf-8"))


def pep440_version(semver: str) -> str:
    match = SEMVER_PATTERN.fullmatch(semver)
    if not match:
        raise ValueError(f"VERSION is not supported SemVer: {semver}")
    base = f"{match.group('base')}.{match.group('minor')}.{match.group('patch')}"
    label = match.group("label")
    if not label:
        return base
    pep_label = {"alpha": "a", "beta": "b", "rc": "rc"}[label]
    return f"{base}{pep_label}{match.group('number')}"


def cargo_package_version(path: Path, package_name: str) -> str:
    text = path.read_text(encoding="utf-8")
    for block in text.split("[[package]]"):
        if re.search(rf'(?m)^name\s*=\s*"{re.escape(package_name)}"\s*$', block):
            match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', block)
            if match:
                return match.group(1)
    raise ValueError(f"{package_name} is missing from {path.relative_to(REPO_ROOT)}")


def check_product_facts() -> list[str]:
    failures: list[str] = []
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    try:
        python_version = pep440_version(version)
    except ValueError as exc:
        return [str(exc)]

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    desktop_package = load_json("apps/starbridge-desktop/package.json")
    tauri_config = load_json("apps/starbridge-desktop/src-tauri/tauri.conf.json")
    manifest = load_json("product/product-manifest.json")
    cargo = tomllib.loads(
        (REPO_ROOT / "apps/starbridge-desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    )
    cargo_lock_version = cargo_package_version(
        REPO_ROOT / "apps/starbridge-desktop/src-tauri/Cargo.lock", "starbridge-desktop"
    )

    versions = {
        "pyproject.toml": (pyproject["project"]["version"], python_version),
        "desktop package.json": (desktop_package["version"], version),
        "tauri.conf.json": (tauri_config["version"], version),
        "Cargo.toml": (cargo["package"]["version"], version),
        "Cargo.lock": (cargo_lock_version, version),
        "product manifest": (manifest["product"]["version"], version),
    }
    for source, (actual, expected) in versions.items():
        if actual != expected:
            failures.append(f"version mismatch in {source}: expected {expected}, got {actual}")

    model = manifest["capabilityModel"]
    allowed_statuses = set(model["allowedStatuses"])
    allowed_evidence = set(model["allowedEvidenceLevels"])
    if allowed_statuses != {"stable", "experimental", "planned", "not_implemented"}:
        failures.append(
            "capabilityModel.allowedStatuses must contain exactly four canonical values"
        )
    if model["connectionStateDefault"] != "unknown":
        failures.append("static product facts must default connectionState to unknown")

    for edition in manifest["editions"]:
        if edition.get("capabilityStatus") not in allowed_statuses:
            failures.append(f"invalid edition capabilityStatus: {edition.get('id')}")

    feature_ids: set[str] = set()
    for feature in manifest["features"]:
        feature_id = str(feature.get("id", ""))
        if not feature_id or feature_id in feature_ids:
            failures.append(f"missing or duplicate feature id: {feature_id}")
        feature_ids.add(feature_id)
        if feature.get("capabilityStatus") not in allowed_statuses:
            failures.append(f"invalid feature capabilityStatus: {feature_id}")
        if feature.get("evidenceLevel") not in allowed_evidence:
            failures.append(f"invalid feature evidenceLevel: {feature_id}")
        for boolean_field in ("recommended", "deprecated"):
            if not isinstance(feature.get(boolean_field), bool):
                failures.append(f"{feature_id} is missing boolean {boolean_field}")
        documentation = REPO_ROOT / str(feature.get("documentation", ""))
        if not documentation.is_file():
            failures.append(f"feature documentation is missing: {feature_id}")

    for required_feature in (
        "projects.basic",
        "jobs.creative_job",
        "workflow.vector_delivery_v1",
        "workflow.comfyui_generation_v1",
        "delivery.basic",
    ):
        if required_feature not in feature_ids:
            failures.append(f"required architecture feature is missing: {required_feature}")

    return failures


def main() -> None:
    failures = check_product_facts()
    if failures:
        for failure in failures:
            print(failure)
        raise SystemExit(1)
    print("product facts check passed")


if __name__ == "__main__":
    main()
