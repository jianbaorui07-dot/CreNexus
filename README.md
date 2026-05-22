# New Project Workspace

This repository is a mixed local workspace for small frontend demos, Python document/CAD scripts, and an AutoCAD MCP subproject. It is not a single packaged application yet.

## Main Areas

- `src/` - static browser demo with `index.html`, `styles.css`, and `app.js`.
- `virtual-pet/` - standalone static browser demo. Open `virtual-pet/index.html` in a browser.
- `cad-mcp-autocad/` - AutoCAD MCP server project with its own README files and `requirements.txt`.
- `scripts/` - Python utility scripts for report generation and AutoCAD drawing automation.
- `docs/` - project protocols and operating notes.
- `examples/comfy_bridge/` - safe example bridge for local Codex-to-ComfyUI API calls.
- `overtime-analysis-deck/` - slide deck generation workspace.
- `output/`, `scratch/`, `docx_render_check/`, `.codex_video_frames/`, `.codex_video_deps/` - generated artifacts, caches, or render outputs.

## Featured Protocol

This workspace includes **StarBridge Trinity Protocol** (`星桥三联`), a documented process for connecting Codex, GitHub/Jules, local ComfyUI, Blender 5.0, and CAD without publishing private credentials or local cache data.

Start here:

- `docs/starbridge-link-protocol.md`
- `docs/codex-drawing-tool-integrations.md`
- `docs/中文用途索引.md`
- `examples/bridge_status.py`
- `examples/comfy_bridge/README.md`

Quick local bridge check:

```powershell
python examples\bridge_status.py
```

Or through npm:

```powershell
npm run bridge:status
```

## Current Runtime Notes

- Root `package.json` includes convenience scripts for local bridge checks; it does not install dependencies.
- Root `requirements.txt` does not exist. Python dependencies vary by script.
- `cad-mcp-autocad/requirements.txt` lists the Python dependencies for the AutoCAD MCP server.
- This workspace currently does not use a ComfyUI `custom_nodes/` layout.
- New downloaded source projects, installers, and research bundles should go under `E:\00_待整理收件箱\下载`, not into this Git workspace unless they are intentionally curated source files.

## Running Locally

Static browser demos:

```powershell
# Open either file directly in a browser
src\index.html
virtual-pet\index.html
```

AutoCAD MCP subproject:

```powershell
cd cad-mcp-autocad
python -m pip install -r requirements.txt
python src\server.py
```

Python utility scripts:

```powershell
python scripts\<script-name>.py
```

Some scripts require Windows-only automation packages such as `pywin32`, local AutoCAD, or document-generation packages such as `python-docx`, `pandas`, `opencv-python`, and `numpy`. Check imports before running an individual script.

StarBridge status check:

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
npm run bridge:status
npm run bridge:status:json
npm run bridge:status:probe
```

If PowerShell blocks `npm.ps1` because of execution policy, use `npm.cmd` instead:

```powershell
npm.cmd run bridge:status:json
```

The status script checks local ComfyUI, Blender, and CAD bridge readiness without reading credentials, browser data, model files, generated images, or private project assets.

Useful environment variables for bridge detection:

- `COMFY_BASE_URL`, default `http://127.0.0.1:8188`
- `COMFY_ROOT` or `COMFYUI_PATH`, full path to the local ComfyUI directory
- `COMFY_LAUNCHER` or `COMFY_START_SCRIPT`, full path to a local ComfyUI launch script
- `BLENDER_EXE`, full path to `blender.exe`
- `BLENDER_MCP_DIR`, full path to a local Blender MCP bridge directory
- `AUTOCAD_EXE`, full path to `acad.exe`

Known local paths from this workstation:

- ComfyUI launch script: `D:\AIGC\Start_ComfyUI_Codex.cmd`
- ComfyUI root: `D:\AIGC\comfyui安装包\ComfyUI`
- Blender executable: `D:\AIGC\CAD\blender.exe`
- Blender MCP bridge: `D:\AIGC\blender-mcp`
- AutoCAD executable: `D:\AIGC\cad2026\CAD2026\AutoCAD 2026\acad.exe`

## GitHub / Jules Readiness

Before using Jules, push only source files and useful documentation. Avoid committing dependency folders, render outputs, caches, and generated binary artifacts unless they are intentionally part of the project.

Recommended first Jules task: ask Jules to read the repository and report structure, entry points, run methods, risks, and candidate next tasks without changing files.
