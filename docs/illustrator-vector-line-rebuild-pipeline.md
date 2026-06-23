# Illustrator Vector Line Rebuild Pipeline

This document describes a practical StarBridge prototype for turning a PDF-compatible Illustrator file into structured vector data, rebuilt SVG output, and simplified closed contours.

The motivating local test used a one-page Illustrator `.ai` line drawing. The file was PDF-compatible, contained no embedded raster images, and exposed thousands of vector stroke paths. The source artwork and generated private outputs stay local and are not committed to this repository.

## Goal

Build a local-first pipeline that can:

1. Read a PDF-compatible `.ai`, PDF, or SVG vector file.
2. Extract every visible stroke as structured data.
3. Calculate line length, bounding boxes, stroke width, color, and nearest-line spacing.
4. Rebuild the line drawing as SVG.
5. Reduce internal detail while preserving the overall silhouette.
6. Convert dense line work into cleaner closed contour regions for later Illustrator editing.

## Why This Is Separate From Image Generation

Firefly and other image generators are useful for ideation, reference imagery, and style exploration. They are not the most reliable way to preserve exact editable vector geometry.

For CAD-like or industrial-design line drawings, the reliable path is:

```text
existing vector source or reference
  -> local geometry extraction
  -> deterministic rebuild
  -> Illustrator verification and editing
```

## Prototype Stages

### Stage 1: Vector file rebuild

Input:

- PDF-compatible `.ai`
- PDF
- SVG

Output:

- `lines.json`
- `rebuild.svg`
- `numbered_overlay.svg`
- optional PNG preview generated locally

The local validation case found:

- `5300` stroke objects
- `3289` cubic Bezier segments
- `2345` line segments
- uniform stroke width of `0.02 pt`
- no embedded raster images

This validates that the file can be reconstructed as editable vector paths rather than approximated from pixels.

### Stage 2: Internal line reduction

Input:

- `lines.json`

Process:

- estimate the silhouette from the full line set
- mark silhouette-adjacent paths as protected
- rank internal lines by shortness, duplication, and closeness to nearby paths
- remove or merge lower-value internal detail

Output:

- reduced SVG/PDF/AI-compatible file
- reduction report

In the local validation case, a `30%` internal-line reduction preserved the visible outer contour while reducing internal clutter.

### Stage 3: Closed contour integration

Input:

- `lines.json` or a reduced line set

Process:

- rasterize the line skeleton into a temporary high-resolution mask
- dilate and close gaps
- extract external and internal closed contours
- simplify contours while keeping them closed
- export editable SVG/PDF/AI-compatible paths

Observed local variants:

- coarse closed contour version: `30` closed contours
- fine closed contour version: `99` closed contours
- outer-only silhouette version: `1` closed contour

The fine version keeps the overall silhouette and integrates internal line work into cleaner closed shapes.

## Recommended Tool Boundary

Use deterministic local scripts for geometry extraction and rebuild. Use Illustrator MCP, COM, ExtendScript, UXP, or Computer Use after that for:

- opening the generated file
- visual verification
- artboard export
- layer naming
- final designer-controlled edits

Do not rely on mouse-driven GUI automation to draw thousands of paths. GUI automation is useful as the eyes and hands, not the geometry engine.

## Safety Rules

- Do not commit private `.ai` source files.
- Do not commit generated client artwork.
- Do not commit local desktop paths or Creative Cloud account metadata.
- Keep public examples synthetic, minimal, or generated from non-private fixtures.
- Make destructive simplification steps write new files rather than overwriting the source.

## Example Scripts

Prototype scripts live in:

- `examples/illustrator_bridge/vector_rebuild/extract_vector_lines.py`
- `examples/illustrator_bridge/vector_rebuild/reduce_closed_contours.py`

They require optional local packages:

- `PyMuPDF` (`fitz`) for PDF-compatible vector extraction and SVG/PDF rendering.
- `opencv-python` and `numpy` for closed-contour mask processing.

Install example-only dependencies locally when needed:

```powershell
python -m pip install pymupdf opencv-python numpy
```

