# Changelog

## [0.1.0] - 2026-05-29

### Added

* StarBridge MCP stdio server
* Safe local bridge status and probes
* ComfyUI workflow validation
* AutoCAD DXF dry-run bridge
* Photoshop sandbox demo bridge
* Illustrator sandbox demo bridge
* Adobe demo docs, smoke test, and output safety rules

### Security

* Local-first design
* No customer assets committed
* Demo outputs ignored by Git
* Guarded write/export operations require explicit confirmation

### Known limitations

* Adobe demos require local authorized desktop apps
* Photoshop and Illustrator automation remain experimental
* Image Trace is not implemented yet
* ComfyUI txt2img closed loop is still next priority if not already merged
