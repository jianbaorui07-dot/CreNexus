---
name: starbridge-smart-cutout-ps
description: Intelligently separate multiple visible subjects into disjoint full-canvas transparent layers and assemble a Photoshop-native PSD through StarBridge. Use for 智能抠图, PS分层, 每个物体一个图层, 每栋楼一个图层, instance masks, transparent cutouts, skyline/building separation, or opening an AI-segmented layered result in Photoshop.
---

# StarBridge 智能抠图 PS

Preserve the source pixels while assigning each visible subject to an independently editable Photoshop layer. Do not invent hidden or occluded content unless the user explicitly requests reconstruction.

## Workflow

1. Inspect only the explicitly supplied image at original resolution.
2. Inventory the independently editable visible subjects and name them left-to-right or by semantic identity.
3. Create a JSON prompt spec with one tight box per subject. Give foreground or overlapping subjects higher `priority` so they own shared visible pixels.
4. Add several positive `background.points` only when the background is visually separable, such as a clear sky.
5. Run `scripts/export_instance_layers.py` with an explicit local segmentation model file. Never download a model automatically.
6. Inspect `preview/layer-index.jpg` and `preview/cutout-preview.png`. Tighten boxes or priorities when a mask includes neighboring subjects, lamps, cables, detached noise, or background fringes.
7. Build the PSD with `scripts/build_instance_psd.ps1`. It saves through Photoshop, closes the document, reopens it, and validates the persisted layer structure.
8. Confirm the expected layer count, group names, dimensions, and visible-pixel reconstruction in Photoshop.

For a many-building scene, read `references/skyline-instance-layering.md`. Start a new spec from `references/instance-layer-spec.example.json`; never edit the tracked example with a private source path.

## Commands

Install the optional local segmentation runtime only when the user authorizes dependency installation:

```powershell
python -m pip install ultralytics
```

Export full-canvas RGBA layers and a StarBridge manifest. Keep all generated files in the ignored Photoshop output tree:

```powershell
python .codex\skills\starbridge-smart-cutout-ps\scripts\export_instance_layers.py `
  --input "<explicit-input-image>" `
  --spec "<client-approved-instance-spec.json>" `
  --out-dir "examples/output/photoshop/smart-cutout-job" `
  --model "<explicit-local-segmentation-model-file>" `
  --confirm-write
```

Build, save, reopen, and leave the native PSD open in Photoshop:

```powershell
powershell -ExecutionPolicy Bypass `
  -File .codex\skills\starbridge-smart-cutout-ps\scripts\build_instance_psd.ps1 `
  -ManifestPath "examples/output/photoshop/smart-cutout-job/manifest.json" `
  -OutputPath "examples/output/photoshop/smart-cutout-job/editable.psd" `
  -ConfirmWrite `
  -OpenAfterBuild
```

Use `--force` only after verifying that replacing the existing generated job is intended. Never overwrite a user PSD.

## Output Contract

- Create one full-canvas transparent pixel layer per requested visible subject.
- Put subject layers in `02_主体`; put background and unassigned visible pixels in `04_背景`.
- Keep a locked, hidden original reference in `00_原始参考`.
- Make masks mutually exclusive after priority resolution.
- Make background + remainder + all subjects cover every source pixel exactly once.
- Preserve real occlusion holes instead of hallucinating hidden geometry.
- Emit only redacted relative output paths in command results.

## Compatibility Rule

Do not treat a third-party PSD parser accepting a file as proof of Adobe compatibility. A parser-valid PSD can still be rejected by Photoshop. Use the bundled fixed Photoshop COM/JSX builder for the final save and require `validated_after_reopen=true` before reporting success.

If Photoshop is unavailable, stop after the PNG layers and manifest. Report the result as prepared for Photoshop, not as a completed PSD.

## Safety

- Accept image, spec, and model paths only from explicit runtime parameters.
- Never scan user folders for images or models.
- Never commit source images, model weights, generated PNGs, manifests, JSX, or PSD files.
- Keep writes inside `examples/output/photoshop/` and require `--confirm-write`.
- Do not expose absolute paths, source filenames, model filenames, or private image content in repository documentation or command summaries.
