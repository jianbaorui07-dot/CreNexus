from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from starbridge_mcp.bridges import jianying


def main() -> int:
    here = Path(__file__).resolve().parent
    spec_path = here / "sample_timeline_spec.json"
    output_path = here / "output" / "draft_plan.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    created = jianying.create_draft_plan(spec)
    if not created["ok"]:
        print(json.dumps(created, ensure_ascii=False, indent=2))
        return 1

    plan = created["details"]["plan"]
    exported = jianying.export_draft_plan(plan, output_path)
    result = {
        "create_draft_plan": created,
        "export_draft_plan": exported,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if exported["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
