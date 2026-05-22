# Comfy Bridge Example

This folder contains a safe example bridge for connecting local Codex automation to a local ComfyUI server.

## What It Does

- Checks whether ComfyUI is online at `http://127.0.0.1:8188`.
- Reads system stats and checkpoint names.
- Submits a basic text-to-image workflow through the ComfyUI HTTP API.
- Keeps the visual workflow JSON separate from the API workflow JSON.

## What It Does Not Include

- No account passwords.
- No OAuth tokens.
- No browser cookies.
- No payment data.
- No private model files.
- No generated image output.
- No local browser profile data.

## Files

- `comfy_probe.py` checks ComfyUI status and available checkpoints.
- `run_txt2img.py` submits a minimal text-to-image workflow.
- `workflows/txt2img_basic_api.json` is the API workflow used by the script.
- `workflows/txt2img_basic_visual.json` is the visual workflow that can be opened inside the ComfyUI canvas.

## Usage

Start ComfyUI first, then run:

```powershell
python examples/comfy_bridge/comfy_probe.py
```

Optional local launcher:

```powershell
$env:COMFY_LAUNCHER="<path-to-Start_ComfyUI.cmd>"
& $env:COMFY_LAUNCHER
```

Check the full StarBridge local environment:

```powershell
python examples/bridge_status.py
```

Generate an image:

```powershell
python examples/comfy_bridge/run_txt2img.py --prompt "a quiet futuristic tea house in a garden"
```

Optional environment variables:

- `COMFY_BASE_URL`, default `http://127.0.0.1:8188`
- `COMFY_OUTPUT_DIR`, optional explicit ComfyUI output directory
- `COMFY_ROOT` or `COMFYUI_PATH`, optional explicit ComfyUI root for status checks
- `COMFY_LAUNCHER` or `COMFY_START_SCRIPT`, optional explicit ComfyUI launch script for status checks

New downloaded source projects, installers, and research bundles should go under your local download inbox, configured outside Git with `STARBRIDGE_DOWNLOAD_INBOX`. Do not place model files, generated images, browser profiles, tokens, or private assets in this Git workspace.

## Visual Workflow

Open this file inside ComfyUI:

```text
examples/comfy_bridge/workflows/txt2img_basic_visual.json
```

The visual workflow contains these nodes:

- `CheckpointLoaderSimple`
- `EmptyLatentImage`
- `CLIPTextEncode` positive prompt
- `CLIPTextEncode` negative prompt
- `KSampler`
- `VAEDecode`
- `SaveImage`
