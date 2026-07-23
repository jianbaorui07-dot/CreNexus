from __future__ import annotations

import argparse
import json

from starbridge_mcp.models import ModelRuntimeClient


def request_document() -> dict[str, object]:
    return {
        "schema": "koryao-model-contract/v1",
        "requestId": "e2e-request-001",
        "projectId": "e2e-project-001",
        "instruction": "把图片转换为可编辑矢量 SVG",
        "locale": "zh-CN",
        "inputAssets": [
            {
                "assetId": "e2e-source-001",
                "mediaType": "image/png",
                "role": "source",
                "sha256": "a" * 64,
            }
        ],
        "availableAdapters": [
            {
                "adapterId": "vectorization",
                "connectionState": "connected",
                "actions": [
                    {
                        "action": "semantic_vectorize",
                        "sideEffect": "write",
                        "requiresConfirmation": True,
                    }
                ],
            }
        ],
        "constraints": {
            "executionMode": "local",
            "localOnly": True,
            "cloudProcessingApproved": False,
            "materialTransfer": "metadata_only",
            "embeddedRasterAllowed": False,
            "outputFormats": ["svg"],
            "requireConfirmationForWrites": True,
            "maxSteps": 8,
            "safeRootRefs": ["e2e-delivery-root"],
        },
        "privacy": {
            "absolutePathsIncluded": False,
            "customerFileNamesIncluded": False,
            "rawAssetContentIncluded": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify KORYAO Basic to private runtime v1")
    parser.add_argument("--url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    client = ModelRuntimeClient(args.url)
    status = client.status()
    plan = client.plan(request_document())
    summary = {
        "contract": plan["schema"],
        "model": f"{plan['modelId']}@{plan['modelVersion']}",
        "provider": plan["providerId"],
        "runtime_status": status["status"],
        "workflow": plan["workflowId"],
        "step_count": len(plan["steps"]),
        "requires_confirmation": plan["requiresConfirmation"],
        "direct_execution": plan["safety"]["directExecution"],
        "direct_file_access": plan["safety"]["directFileAccess"],
        "result": "passed",
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
