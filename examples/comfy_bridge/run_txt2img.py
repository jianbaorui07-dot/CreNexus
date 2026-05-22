from __future__ import annotations

import argparse
import copy
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = os.environ.get("COMFY_BASE_URL", "http://127.0.0.1:8188")
BRIDGE_ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = BRIDGE_ROOT / "workflows" / "txt2img_basic_api.json"
COMFY_OUTPUT = Path(os.environ.get("COMFY_OUTPUT_DIR", str(Path.cwd() / "output" / "comfyui")))


def get_json(path: str):
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(path: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_prompt(args: argparse.Namespace) -> dict:
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    prompt = copy.deepcopy(workflow)

    prompt["4"]["inputs"]["ckpt_name"] = args.ckpt
    prompt["5"]["inputs"]["width"] = args.width
    prompt["5"]["inputs"]["height"] = args.height
    prompt["6"]["inputs"]["text"] = args.prompt
    prompt["7"]["inputs"]["text"] = args.negative
    prompt["3"]["inputs"]["steps"] = args.steps
    prompt["3"]["inputs"]["cfg"] = args.cfg
    prompt["3"]["inputs"]["seed"] = args.seed if args.seed is not None else random.randint(1, 2**48)
    prompt["9"]["inputs"]["filename_prefix"] = args.prefix
    return prompt


def wait_for_outputs(prompt_id: str, timeout: int) -> list[Path]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        history = get_json(f"/history/{prompt_id}")
        if prompt_id in history:
            outputs = []
            for node in history[prompt_id].get("outputs", {}).values():
                for image in node.get("images", []):
                    subfolder = image.get("subfolder") or ""
                    outputs.append(COMFY_OUTPUT / subfolder / image["filename"])
            return outputs
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for ComfyUI prompt {prompt_id}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit a basic txt2img workflow to local ComfyUI.")
    parser.add_argument("--prompt", required=True, help="Positive prompt text.")
    parser.add_argument("--negative", default="low quality, blurry, distorted, watermark, text")
    parser.add_argument("--ckpt", default="AWPainting_v1.2.safetensors")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--cfg", type=float, default=7.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--prefix", default="codex_txt2img")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    try:
        stats = get_json("/system_stats")
    except urllib.error.URLError as exc:
        raise SystemExit(f"ComfyUI is not reachable at {BASE_URL}: {exc}") from exc

    print("ComfyUI:", stats["system"].get("comfyui_version"), BASE_URL)
    result = post_json("/prompt", {"prompt": build_prompt(args)})
    prompt_id = result["prompt_id"]
    print("Queued prompt:", prompt_id)

    outputs = wait_for_outputs(prompt_id, args.timeout)
    if not outputs:
        print("Finished, but no image outputs were reported.")
        return

    print("Outputs:")
    for path in outputs:
        print(path)


if __name__ == "__main__":
    main()
