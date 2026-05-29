# StarBridge v0.1.0 draft release notes

## Summary

StarBridge v0.1.0 is a local-first MCP bridge for creative desktop software. This release focuses on safe probes, dry-run workflows, and sandbox demos for Adobe Photoshop and Illustrator.

## Highlights

* Local MCP stdio server
* Safe bridge registry
* Photoshop sandbox PSD/layer demo
* Illustrator sandbox vector export demo
* Guarded outputs under examples/output
* Git ignored generated assets
* CI UTF-8 fix for Windows runner

## How to verify

```powershell
python -m unittest discover -s tests
npm.cmd run security:check
npm.cmd run preflight:json
npm.cmd run starbridge:tools:safe
npm.cmd run illustrator:demo:plan
npm.cmd run photoshop:demo:plan
```

## Not included

* No private PSD / AI files
* No generated binary demo assets
* No customer material
* No Image Trace automation yet
