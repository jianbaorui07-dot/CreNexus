from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "examples" / "output" / "photoshop"


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    psd_path = OUTPUT_DIR / "starbridge_ps_demo.psd"
    exported = [
        OUTPUT_DIR / "starbridge_ps_demo.png",
        OUTPUT_DIR / "starbridge_ps_demo.jpg",
    ]
    manifest = {
        "ok": psd_path.exists() and all(path.exists() for path in exported),
        "bridge": "photoshop",
        "task": "sandbox_ps_demo",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document": {
            "name": "starbridge_ps_demo.psd",
            "path": rel(psd_path),
            "width": 1080,
            "height": 1080,
            "color_mode": "RGB",
        },
        "layers_created": [
            "background",
            "color_block_left",
            "color_block_right",
            "color_block_footer",
            "title_text",
            "subtitle_text",
        ],
        "exported_files": [rel(path) for path in exported if path.exists()],
        "commands": [
            "npm.cmd run photoshop:demo:plan",
            "npm.cmd run photoshop:demo",
            "npm.cmd run photoshop:manifest",
        ],
        "warnings": [] if psd_path.exists() else ["Sandbox Photoshop demo outputs were not all found."],
        "next_steps": [
            "Inspect local demo previews.",
            "Do not commit generated PSD, PNG, JPG, or manifest outputs.",
        ],
    }
    manifest_path = OUTPUT_DIR / "demo_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
