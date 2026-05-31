from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BRIDGE_ID = "comfyui"
DEFAULT_BASE_URL = os.environ.get("STARBRIDGE_COMFYUI_URL") or os.environ.get(
    "COMFY_BASE_URL",
    "http://127.0.0.1:8188",
)
BRIDGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BRIDGE_ROOT.parents[1]
WORKFLOW_PATH = BRIDGE_ROOT / "workflows" / "txt2img_basic_api.json"
DEFAULT_MANIFEST_PATH = REPO_ROOT / "examples" / "output" / "comfyui" / "demo_manifest.json"
REQUIRED_NODE_CLASSES = {
    "3": "KSampler",
    "4": "CheckpointLoaderSimple",
    "5": "EmptyLatentImage",
    "6": "CLIPTextEncode",
    "7": "CLIPTextEncode",
    "8": "VAEDecode",
    "9": "SaveImage",
}


class BridgeError(Exception):
    def __init__(self, error: str, message: str, suggestion: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.suggestion = suggestion
        self.exit_code = exit_code

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": False,
            "bridge": BRIDGE_ID,
            "error": self.error,
            "message": self.message,
            "suggestion": self.suggestion,
        }


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise BridgeError(
            "invalid_arguments",
            message,
            "Run with --help to see required txt2img arguments.",
        )


def print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def short_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def safe_workflow_name(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return path.name


def output_basename(value: str) -> str:
    return Path(str(value).replace("\\", "/")).name


def build_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}"


def get_json(base_url: str, path: str, timeout: int) -> dict[str, Any]:
    with urllib.request.urlopen(build_url(base_url, path), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        build_url(base_url, path),
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def load_workflow(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise BridgeError(
            "workflow_not_found",
            f"Workflow file does not exist: {path}",
            "Use examples/comfy_bridge/workflows/txt2img_basic_api.json or pass --workflow.",
        )
    try:
        workflow = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BridgeError(
            "invalid_workflow_json",
            f"Workflow JSON is invalid: {exc}",
            "Export or repair the workflow JSON before submitting it to ComfyUI.",
        ) from exc
    if not isinstance(workflow, dict):
        raise BridgeError(
            "invalid_workflow",
            "Workflow root must be a JSON object keyed by node id.",
            "Use the ComfyUI API workflow format, not the visual workflow wrapper.",
        )
    validate_workflow(workflow)
    return workflow


def validate_workflow(workflow: dict[str, Any]) -> None:
    for node_id, expected_class in REQUIRED_NODE_CLASSES.items():
        node = workflow.get(node_id)
        if node is None:
            raise BridgeError(
                "missing_node",
                f"Workflow missing node {node_id} for {expected_class}.",
                "Use bundled txt2img_basic_api.json or update the node mapping.",
            )
        if not isinstance(node, dict):
            raise BridgeError(
                "invalid_node",
                f"Workflow node {node_id} must be a JSON object.",
                "Check the workflow export format.",
            )
        actual_class = node.get("class_type")
        if actual_class != expected_class:
            raise BridgeError(
                "invalid_node_class",
                f"Workflow node {node_id} expected {expected_class}, got {actual_class!r}.",
                "Use bundled txt2img_basic_api.json or update the node mapping.",
            )


def node_inputs(workflow: dict[str, Any], node_id: str) -> dict[str, Any]:
    inputs = workflow[node_id].setdefault("inputs", {})
    if not isinstance(inputs, dict):
        raise BridgeError(
            "invalid_node_inputs",
            f"Workflow node {node_id} has invalid inputs.",
            "Re-export the workflow or repair the node inputs object.",
        )
    return inputs


def get_checkpoint_names(base_url: str, timeout: int) -> list[str]:
    loader = get_json(base_url, "/object_info/CheckpointLoaderSimple", timeout)
    names = (
        loader.get("CheckpointLoaderSimple", {})
        .get("input", {})
        .get("required", {})
        .get("ckpt_name", [[]])[0]
    )
    if not isinstance(names, list):
        raise BridgeError(
            "checkpoint_schema_changed",
            "ComfyUI returned checkpoint metadata in an unexpected shape.",
            "Check /object_info/CheckpointLoaderSimple in your local ComfyUI instance.",
        )
    return [str(name) for name in names]


def resolve_checkpoint(args: argparse.Namespace, checkpoints: list[str]) -> str:
    if args.ckpt:
        if args.ckpt not in checkpoints:
            raise BridgeError(
                "checkpoint_not_found",
                f"Checkpoint not found in ComfyUI: {args.ckpt}",
                "Run comfy_probe.py to list available checkpoints, then pass --ckpt with an exact name.",
            )
        return args.ckpt

    if not args.allow_first_checkpoint:
        raise BridgeError(
            "missing_checkpoint",
            "No checkpoint was specified.",
            "Pass --ckpt with an exact checkpoint name, or add --allow-first-checkpoint to opt in to the first available checkpoint.",
        )

    if not checkpoints:
        raise BridgeError(
            "no_checkpoint",
            "ComfyUI did not report any available checkpoints.",
            "Install or enable at least one checkpoint before running txt2img.",
        )
    return checkpoints[0]


def build_prompt(args: argparse.Namespace, workflow: dict[str, Any], checkpoint: str) -> tuple[dict[str, Any], int]:
    prompt = copy.deepcopy(workflow)
    seed = args.seed if args.seed is not None else random.randint(1, 2**48)

    node_inputs(prompt, "4")["ckpt_name"] = checkpoint
    node_inputs(prompt, "5")["width"] = args.width
    node_inputs(prompt, "5")["height"] = args.height
    node_inputs(prompt, "6")["text"] = args.prompt
    node_inputs(prompt, "7")["text"] = args.negative
    sampler_inputs = node_inputs(prompt, "3")
    sampler_inputs["steps"] = args.steps
    sampler_inputs["cfg"] = args.cfg
    sampler_inputs["seed"] = seed
    sampler_inputs["sampler_name"] = args.sampler
    sampler_inputs["scheduler"] = args.scheduler
    node_inputs(prompt, "9")["filename_prefix"] = args.prefix
    return prompt, seed


def output_filenames_from_history(prompt_id: str, history: dict[str, Any]) -> list[str]:
    prompt_history = history.get(prompt_id, {}) if isinstance(history, dict) else {}
    filenames: list[str] = []
    for node in prompt_history.get("outputs", {}).values():
        if not isinstance(node, dict):
            continue
        for image in node.get("images", []):
            if isinstance(image, dict) and image.get("filename"):
                filenames.append(output_basename(str(image["filename"])))
    return filenames


def wait_for_job_status(
    prompt_id: str,
    timeout: int,
    base_url: str,
    request_timeout: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = get_json(base_url, f"/history/{prompt_id}", request_timeout)
        if prompt_id in history:
            filenames = output_filenames_from_history(prompt_id, history)
            return {"status": "completed", "output_count": len(filenames), "output_filenames": filenames}
        time.sleep(2)
    raise BridgeError(
        "timeout",
        f"Timed out waiting for ComfyUI prompt {prompt_id}.",
        "Check the ComfyUI queue, GPU memory, and workflow errors in the ComfyUI console.",
    )


def build_manifest(
    *,
    workflow_path: Path,
    prompt: str,
    job_status: str,
    output_filenames: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    filenames = [output_basename(name) for name in output_filenames or []]
    return {
        "bridge_name": "ComfyUI",
        "workflow_file": safe_workflow_name(workflow_path),
        "prompt_hash": short_hash(prompt),
        "job_status": job_status,
        "output_count": len(filenames),
        "output_filenames": filenames,
        "created_at": utc_now(),
        "errors": errors or [],
        "safe_to_commit": False,
    }


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = JsonArgumentParser(description="Submit a safe txt2img workflow to local ComfyUI.")
    parser.add_argument("--comfy-url", default=DEFAULT_BASE_URL, help="ComfyUI API base URL.")
    parser.add_argument("--workflow", type=Path, default=WORKFLOW_PATH, help="ComfyUI API workflow JSON path.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH, help="Local ignored evidence manifest path.")
    parser.add_argument("--prompt", required=True, help="Positive prompt.")
    parser.add_argument("--negative", default="low quality, blurry, distorted, watermark, text", help="Negative prompt.")
    parser.add_argument("--ckpt", default=None, help="Exact checkpoint name from ComfyUI.")
    parser.add_argument(
        "--allow-first-checkpoint",
        action="store_true",
        help="Explicitly allow using the first checkpoint reported by ComfyUI when --ckpt is omitted.",
    )
    parser.add_argument("--width", type=int, default=512, help="Output width.")
    parser.add_argument("--height", type=int, default=512, help="Output height.")
    parser.add_argument("--steps", type=int, default=20, help="Sampling steps.")
    parser.add_argument("--cfg", type=float, default=7.0, help="Classifier-free guidance scale.")
    parser.add_argument("--sampler", default="euler", help="ComfyUI sampler_name for KSampler.")
    parser.add_argument("--scheduler", default="normal", help="ComfyUI scheduler for KSampler.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed. Omit to generate one locally.")
    parser.add_argument("--prefix", default="codex_txt2img", help="Output filename prefix.")
    parser.add_argument("--timeout", type=int, default=600, help="Maximum wait time in seconds.")
    parser.add_argument("--request-timeout", type=int, default=30, help="Single HTTP request timeout in seconds.")
    parser.add_argument("--soft-exit", action="store_true", help="Return exit code 0 after writing an error manifest when ComfyUI is unavailable.")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> dict[str, Any]:
    workflow = load_workflow(args.workflow)
    stats = get_json(args.comfy_url, "/system_stats", args.request_timeout)
    checkpoint = resolve_checkpoint(args, get_checkpoint_names(args.comfy_url, args.request_timeout))
    prompt, seed = build_prompt(args, workflow, checkpoint)
    response = post_json(args.comfy_url, "/prompt", {"prompt": prompt}, args.request_timeout)
    prompt_id = response.get("prompt_id")
    if not prompt_id:
        raise BridgeError(
            "missing_prompt_id",
            "ComfyUI did not return a prompt_id.",
            "Check the /prompt response and the ComfyUI console for workflow errors.",
        )

    job = wait_for_job_status(str(prompt_id), args.timeout, args.comfy_url, args.request_timeout)
    manifest = build_manifest(
        workflow_path=args.workflow,
        prompt=args.prompt,
        job_status=str(job["status"]),
        output_filenames=list(job["output_filenames"]),
    )
    return {
        "ok": True,
        "bridge": BRIDGE_ID,
        "task": "txt2img",
        "prompt_id": str(prompt_id),
        "workflow": safe_workflow_name(args.workflow),
        "checkpoint_hash": short_hash(checkpoint),
        "seed": seed,
        "steps": args.steps,
        "cfg": args.cfg,
        "sampler": args.sampler,
        "scheduler": args.scheduler,
        "width": args.width,
        "height": args.height,
        "comfyui_version": stats.get("system", {}).get("comfyui_version"),
        "job_status": job["status"],
        "output_count": job["output_count"],
        "output_filenames": job["output_filenames"],
        "manifest_path": safe_workflow_name(args.manifest_path),
        "manifest": manifest,
    }


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except BridgeError as exc:
        print_json(exc.to_payload())
        return exc.exit_code

    def error_payload(error: BridgeError) -> dict[str, Any]:
        payload = error.to_payload()
        payload["manifest"] = build_manifest(
            workflow_path=args.workflow,
            prompt=args.prompt,
            job_status=error.error,
            errors=[error.error],
        )
        write_manifest(payload["manifest"], args.manifest_path)
        return payload

    try:
        payload = run(args)
    except BridgeError as exc:
        print_json(error_payload(exc))
        return 0 if args.soft_exit else exc.exit_code
    except urllib.error.HTTPError as exc:
        error = BridgeError(
            "http_error",
            f"ComfyUI HTTP error {exc.code}: {exc.reason}",
            "Check the ComfyUI console and confirm the workflow is compatible with your installed nodes.",
        )
        print_json(error_payload(error))
        return 0 if args.soft_exit else 1
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        error = BridgeError(
            "comfyui_unavailable",
            f"Unable to connect to ComfyUI at the configured URL: {exc}",
            "Start local ComfyUI, then retry with --comfy-url or STARBRIDGE_COMFYUI_URL.",
        )
        print_json(error_payload(error))
        return 0 if args.soft_exit else 1
    except Exception as exc:  # noqa: BLE001 - CLI must return structured JSON.
        error = BridgeError(
            "unexpected_error",
            str(exc),
            "Run comfy_probe.py first, then retry with explicit --workflow and --ckpt values.",
        )
        print_json(error_payload(error))
        return 0 if args.soft_exit else 1

    write_manifest(payload["manifest"], args.manifest_path)
    print_json(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
