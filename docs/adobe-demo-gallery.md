# Adobe demo gallery

## Goal

The Adobe sandbox demos show how StarBridge exposes safe, local-first Photoshop and Illustrator workflows without committing generated assets or private project files.

The gallery is documentation-first. It explains what the demo creates, where local outputs appear, and why those outputs stay out of Git.

## Illustrator demo outputs

Generate locally with:

```powershell
npm.cmd run illustrator:demo
npm.cmd run illustrator:manifest
```

| Output | Purpose | Commit to Git | Why not committed |
| --- | --- | --- | --- |
| `examples/output/illustrator/starbridge_ai_demo.ai` | Sandbox Illustrator source document created from public vector primitives. | No | It is a generated app project file and may vary by local Illustrator version. |
| `examples/output/illustrator/starbridge_ai_demo.svg` | Vector export proof for reviewing shapes and text. | No | It is generated output and belongs to the local verification run. |
| `examples/output/illustrator/starbridge_ai_demo.png` | Preview image for quick visual inspection. | No | Preview images are generated artifacts and should not enter the public repo. |
| `examples/output/illustrator/starbridge_ai_demo.pdf` | PDF proof for export verification. | No | PDF proof files are generated artifacts and may contain tool metadata. |
| `examples/output/illustrator/demo_manifest.json` | Local manifest summarizing created objects and exports. | No | It records local run output and is ignored with other demo artifacts. |

## Photoshop demo outputs

Generate locally with:

```powershell
npm.cmd run photoshop:demo
npm.cmd run photoshop:manifest
```

| Output | Purpose | Commit to Git | Why not committed |
| --- | --- | --- | --- |
| `examples/output/photoshop/starbridge_ps_demo.psd` | Sandbox PSD with named layers and generated color/text content. | No | It is a generated app project file and may vary by local Photoshop version. |
| `examples/output/photoshop/starbridge_ps_demo.png` | Lossless preview export for visual inspection. | No | Preview images are generated artifacts and should remain local. |
| `examples/output/photoshop/starbridge_ps_demo.jpg` | Compressed preview export for compatibility checks. | No | Preview images are generated artifacts and should remain local. |
| `examples/output/photoshop/demo_manifest.json` | Local manifest summarizing document and preview outputs. | No | It records local run output and is ignored with other demo artifacts. |

## Visual evidence placeholder

No real Adobe preview image is committed in this release-polish pass.

If a maintainer runs the demos on an authorized local Adobe setup, they may add a reviewed, low-risk, compressed gallery screenshot under `docs/assets/adobe-demo/`. The screenshot must not include private file paths, customer material, licensed assets, or generated binary source files.

TODO: add a reviewed low-risk preview image after a real local Adobe run.

## Asset folder

`docs/assets/adobe-demo/` is reserved for future reviewed evidence only. It is not a dump location for PSD, AI, PNG, JPG, SVG, PDF, or manifest outputs from `examples/output/`.
