from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_ROOT = Path(os.environ.get("SF3D_ROOT", r"D:\AIGC\stable-fast-3d"))
DEFAULT_URL = os.environ.get("SF3D_URL", "http://127.0.0.1:7860")


def check_url(url: str, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {
                "status": "ok",
                "url": url,
                "http_status": response.status,
            }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "status": "missing",
            "url": url,
            "error": str(exc),
        }


def check_path(root: Path) -> dict:
    expected = {
        "root": root,
        "python": root / ".venv" / "Scripts" / "python.exe",
        "gradio_app": root / "gradio_app.py",
        "start_script": root / "start_sf3d_gradio.bat",
        "texture_baker": root / "texture_baker" / "texture_baker" / "baker.py",
    }
    return {
        key: {
            "path": str(path),
            "exists": path.exists(),
        }
        for key, path in expected.items()
    }


def build_report(root: Path, url: str, timeout: int) -> dict:
    paths = check_path(root)
    url_status = check_url(url, timeout)
    cache = {
        "huggingface_hub_cache": os.environ.get("HUGGINGFACE_HUB_CACHE"),
        "u2net_home": os.environ.get("U2NET_HOME"),
    }
    return {
        "bridge_id": "stable_fast_3d",
        "status": "ok"
        if paths["python"]["exists"] and paths["gradio_app"]["exists"]
        else "missing",
        "root": str(root),
        "url": url_status,
        "paths": paths,
        "cache": cache,
        "notes": [
            "This probe is read-only.",
            "It does not submit image-to-3D generation jobs.",
            "Generated assets and model weights are intentionally outside the repository.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe local Stable Fast 3D bridge status.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="Local stable-fast-3d checkout.")
    parser.add_argument("--url", default=DEFAULT_URL, help="Local Gradio URL.")
    parser.add_argument("--timeout", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = build_report(Path(args.root), args.url, args.timeout)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Stable Fast 3D bridge: {report['status']}")
        print(f"Root: {report['root']}")
        print(f"Gradio: {report['url']['status']} ({report['url']['url']})")
        for key, item in report["paths"].items():
            print(f"- {key}: {'ok' if item['exists'] else 'missing'} - {item['path']}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
