# Illustrator Vector Rebuild Examples

This folder contains local-first prototype scripts for PDF-compatible Illustrator vector rebuild workflows.

These scripts are intentionally file-based. They do not upload artwork, do not call Adobe cloud APIs, and do not require Illustrator to be open. Illustrator or an MCP bridge can be added later for visual verification and final export.

## Scripts

| Script | Purpose |
| --- | --- |
| `extract_vector_lines.py` | Extract stroke paths from PDF-compatible `.ai`, PDF, or SVG files into `lines.json` and `rebuild.svg`. |
| `reduce_closed_contours.py` | Convert dense line work from `lines.json` into simplified closed contour SVG/PDF output. |

## Example

```powershell
python examples\illustrator_bridge\vector_rebuild\extract_vector_lines.py `
  --input "C:\path\to\source.ai" `
  --out "examples\output\vector_rebuild"

python examples\illustrator_bridge\vector_rebuild\reduce_closed_contours.py `
  --lines-json "examples\output\vector_rebuild\lines.json" `
  --out "examples\output\vector_rebuild_closed" `
  --mode fine
```

## Outputs

`extract_vector_lines.py` writes:

- `lines.json`
- `rebuild.svg`
- `summary.json`

`reduce_closed_contours.py` writes:

- `closed_contours.svg`
- `closed_contours.pdf`
- `closed_contours_summary.json`

Private source files and generated artwork should remain local and out of git.

