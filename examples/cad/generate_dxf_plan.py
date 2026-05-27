from __future__ import annotations

import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from starbridge_mcp.bridges.autocad_dxf import summarize_plan, validate_cad_plan, write_dxf  # noqa: E402
from starbridge_mcp.core.security import sanitize_result  # noqa: E402


def main() -> int:
    plan_path = Path(__file__).resolve().with_name("example_plan.json")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    result = {
        "validate": validate_cad_plan(plan),
        "summary": summarize_plan(plan),
        "write": write_dxf(plan, Path("examples/cad/output/safe_example.dxf"), dry_run=True),
    }
    print(json.dumps(sanitize_result(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
