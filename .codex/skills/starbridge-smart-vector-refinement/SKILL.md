---
name: starbridge-smart-vector-refinement
description: Refine raster-to-vector results into seam-free, raster-free cubic Bezier SVG candidates with measured final-render fidelity and lower complexity. Use when the user requests Smart or Artisan vectorization, says an SVG is fragmented or visibly different, reports more than 30% structural difference, wants fewer anchors and more human-drawn curves, needs candidate comparison, or wants a verified Illustrator handoff without Image Trace.
---

# StarBridge Smart Vector Refinement

Turn a weak Smart/Artisan result into a measured curve candidate. Preserve existing modes and artifacts; add a refinement pass instead of replacing the original workflow.

## Read first

- Read `references/quality-gates.md` before tuning candidates.
- Read `docs/vectorization-modes.md` for the existing four modes.
- Use `$starbridge-illustrator-mcp` only for the optional confirmed Illustrator handoff.

## Non-negotiable rules

1. Keep the original source and every accepted prior result. Write candidates only under the ignored `examples/output/vectorization/` tree.
2. For customer delivery, establish the `exact` raster-free baseline first, then run Artisan or an explicitly requested Smart/Lightweight pass. Never use Illustrator Image Trace and never fall back to it.
3. Treat the final SVG as the artifact. Do not score an internal quantized preview and present that score as SVG fidelity.
4. Render the final SVG with a trusted renderer, then compare that render with the explicit reference image.
5. Require zero embedded rasters, zero external references, cubic curves for curve candidates, and bounded subpaths/anchors.
6. Describe the output as automated curve reconstruction. Do not call it hand-drawn or semantically layered unless those properties were separately verified.

## Workflow

### 1. Establish the baseline

Run the existing exact and requested design modes. Record the design candidate's subpaths, anchors, SVG bytes, and actual SVG-render score.

```powershell
python -m pip install -e ".[vectorization]"
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --mode exact --reference-id "<reference-id>"
python -m starbridge_mcp.vectorization.cli --input "<input.png>" --mode smart --reference-id "<reference-id>"
```

If exact reconstruction exceeds a safety limit, stop and report it. Do not trace automatically.

### 2. Generate bounded curve candidates

First inspect the normal Smart/Artisan SVG. If it has cracks, excessive polygon fragments, or more than 30% structural difference, generate three to six stacked-spline candidates. Change one parameter family at a time.

The candidate source may be the ignored Smart `preview.png`; it is only a local intermediate. The published SVG must still contain paths only.

```powershell
python -m pip install -e ".[vector-refinement]"
python .codex\skills\starbridge-smart-vector-refinement\scripts\trace_curve_candidate.py `
  --input "examples/output/vectorization/<reference-id>/smart/preview.png" `
  --output-dir "examples/output/vectorization/<reference-id>/curve-a"
```

The script uses VTracer stacked spline tracing, flattens translation transforms, clamps coordinates to the canvas, normalizes the SVG to StarBridge's safe path contract, and runs the repository SVG verifier. It does not call Illustrator Image Trace.

### 3. Render the final SVG

Render each normalized `vector.svg` to PNG with Illustrator, a browser, or another trusted SVG renderer. Match the SVG canvas and avoid extra color conversion or scaling. Keep the render under the same ignored candidate directory.

If no final SVG render exists, report complexity and safety only. Do not claim a fidelity score.

### 4. Evaluate the actual artifact

```powershell
python .codex\skills\starbridge-smart-vector-refinement\scripts\evaluate_candidate.py `
  --candidate-id "curve-a" `
  --reference "<input.png>" `
  --rendered "examples/output/vectorization/<reference-id>/curve-a/svg-render.png" `
  --svg "examples/output/vectorization/<reference-id>/curve-a/vector.svg" `
  --output "examples/output/vectorization/<reference-id>/curve-a/quality.json"
```

Reject a candidate when any hard gate fails. Among passing candidates, prefer the Pareto result: first preserve visual structure, then reduce subpaths, anchors, and file size. Inspect the image at normal scale and at 200-400% for cracks, missing thin lines, merged faces/text, and broken ornaments.

### 5. Deliver and optionally open Illustrator

Copy only the selected SVG, its actual-render proof, parameters, and reports into a separate local delivery folder. Keep experiments available for rollback.

Open Illustrator only after explicit user request. Do not close existing documents or processes. Confirm the document title contains the selected SVG name, then report that the SVG is open; do not claim it is an `.ai` file until an actual Save As succeeds.

## Iteration rules

- If difference is above 30%, continue tuning or reject; do not hide the metric.
- If a preview looks good but the SVG render has cracks, fix geometry/stacking rather than trusting the preview.
- If forcing a small palette causes a large fidelity regression, keep layered paints and disclose the editability tradeoff.
- If subpaths fall but anchors or visual error rise sharply, reject the false simplification.
- If all candidates fail, retain the best prior artifact and report the blocking gate.

## Required report

Report before/after values for structural difference, normalized MAE, subpaths, anchors, SVG bytes, curves, embedded rasters, and external references. State the remaining limitation, especially when the SVG is still a single technical layer or lacks designer-semantic grouping.
