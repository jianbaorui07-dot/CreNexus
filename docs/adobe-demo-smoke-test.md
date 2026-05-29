# Adobe demo smoke test

## Environment

* OS: Microsoft Windows 11 Home China, version 10.0.26200
* Python: Python 3.14.3
* Node / npm: Node v24.15.0 / npm 11.12.1
* Adobe Illustrator available: unknown
* Adobe Photoshop available: unknown
* Date: 2026-05-29 14:02:22 +08:00

## Commands

| Command | Result | Notes |
| --- | --- | --- |
| `npm.cmd run starbridge:tools:safe` | pass | Safe MCP registry returned JSON and listed Adobe read-only entries. |
| `npm.cmd run illustrator:demo:plan` | pass | Dry-run returned the planned Illustrator sandbox document and output paths. |
| `npm.cmd run photoshop:demo:plan` | pass | Dry-run returned the planned Photoshop sandbox document and output paths. |
| `npm.cmd run illustrator:demo` | skipped | Adobe Illustrator availability was not confirmed in this pass, so no COM write/export run was attempted. |
| `npm.cmd run illustrator:manifest` | skipped | No real Illustrator demo output was generated in this pass. |
| `npm.cmd run photoshop:demo` | skipped | Adobe Photoshop availability was not confirmed in this pass, so no COM write/export run was attempted. |
| `npm.cmd run photoshop:manifest` | skipped | No real Photoshop demo output was generated in this pass. |

## Findings

* Dry-run passed for both Illustrator and Photoshop sandbox demos.
* The safe MCP registry command passed and exposed the current safe tool list.
* This smoke test did not call Adobe COM automation.
* Adobe desktop availability was not probed in this pass to avoid launching or attaching to local creative apps without an explicit real-demo run.
* No real PSD, AI, PNG, JPG, SVG, PDF, or demo manifest output was generated.
* `git check-ignore` confirmed representative generated output paths under `examples/output/illustrator/` and `examples/output/photoshop/` are ignored.

## Safety check

* Demo PSD, AI, PNG, JPG, SVG, PDF, and manifest outputs are covered by `.gitignore`.
* `examples/output/README.md` remains unignored so the output policy is documented.
* No private workstation paths are included in this report.
* No customer material is included.
* No commercial font, commercial brush, or private project file is included.
