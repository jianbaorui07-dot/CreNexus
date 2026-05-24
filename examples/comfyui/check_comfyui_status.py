from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from starbridge_mcp.bridges import comfyui


def main() -> int:
    result = {
        "status": comfyui.status(),
        "probe": comfyui.probe(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
