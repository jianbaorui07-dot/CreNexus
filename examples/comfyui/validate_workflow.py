from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from starbridge_mcp.bridges import comfyui


def main() -> int:
    workflow_path = Path(__file__).with_name("sample_workflow_minimal.json")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    result = {
        "workflow": "examples/comfyui/sample_workflow_minimal.json",
        "validation": comfyui.validate_workflow(workflow),
        "queue_dry_run": comfyui.queue_workflow(workflow, dry_run=True),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["validation"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
