from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "examples" / "output" / "illustrator"


def rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ai_path = OUTPUT_DIR / "starbridge_ai_demo.ai"
    exported = [
        OUTPUT_DIR / "starbridge_ai_demo.svg",
        OUTPUT_DIR / "starbridge_ai_demo.png",
        OUTPUT_DIR / "starbridge_ai_demo.pdf",
    ]
    manifest = {
        "ok": ai_path.exists() and all(path.exists() for path in exported),
        "bridge": "illustrator",
        "task": "sandbox_vector_demo",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document": {
            "name": "starbridge_ai_demo.ai",
            "path": rel(ai_path),
            "width": 1080,
            "height": 1080,
            "color_space": "RGB",
        },
        "artboards": [{"index": 0, "width": 1080, "height": 1080}],
        "layers": ["background", "foreground"],
        "objects_created": [
            "background rectangle",
            "title text",
            "subtitle text",
            "circle",
            "rectangle",
            "line",
            "path",
            "accent bar",
        ],
        "exported_files": [rel(path) for path in exported if path.exists()],
        "commands": [
            "npm.cmd run illustrator:demo:plan",
            "npm.cmd run illustrator:demo",
            "npm.cmd run illustrator:manifest",
        ],
        "warnings": [] if ai_path.exists() else ["Sandbox Illustrator demo outputs were not all found."],
        "next_steps": [
            "Inspect local demo exports.",
            "Do not commit generated AI, SVG, PNG, PDF, or manifest outputs.",
        ],
    }
    manifest_path = OUTPUT_DIR / "demo_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
