# Ultra-fine CAD reference trace experiment

This folder contains a local AutoCAD experiment generated from eight user-supplied interior design reference images.

## Files

- `ultra_fine_reference_cad.dxf` - portable DXF with calibrated image underlays and vector trace layers.
- `ultra_fine_reference_cad_dwg_package.zip` - AutoCAD-saved DWG version packaged as an archive because raw DWG files are intentionally not tracked by this repository.
- `*.png` - reference underlay images used by the DXF.

## CAD layers

- `UNDERLAY_IMAGE` - calibrated source image underlays.
- `TRACE_CONTOUR_MAJOR` - main contour entities.
- `TRACE_CONTOUR_FINE` - fine contour entities.
- `TRACE_STRAIGHT_LINES` - detected straight CAD-like linework.
- `TRACE_DARK_PIXELS` - dense gray texture/detail helper layer; hide this layer if the drawing feels too heavy.
- `CALIBRATION_DIM` - visible calibration dimensions.

## Reproduce

Run from the repository root and provide a local folder containing the eight reference PNG files:

```powershell
python examples\cad\make_ultra_fine_reference_cad.py --source-dir <local-reference-image-folder>
```

The script writes output to this folder and uses relative image references in the generated DXF.
