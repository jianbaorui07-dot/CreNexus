# Codex CAD Workflow

## Goal

Make the local Codex + AutoCAD chain reusable, so a new reference image can be turned into a trace-ready CAD workspace quickly and safely.

## Current local bridges

- `codex_autocad_live`: direct AutoCAD drawing MCP
- `starbridge_cad_ascii`: StarBridge status / probe / DXF validation bridge
- `direct_autocad_smoke.py`: direct COM smoke test without the MCP layer
- local OCR engine: `C:\Program Files\Tesseract-OCR\tesseract.exe`
- local OCR data root: `C:\cad_ocr_data`

## One-click verification

Run:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\<USER_HOME>\OneDrive\鏂囨。\New project\cad_exact_trace\verify_codex_cad_integration.ps1"
```

Outputs:

- `C:\cad_exact_trace\codex_cad_stack_report.md`
- `C:\cad_exact_trace\codex_cad_stack_status.json`
- `C:\cad_exact_trace\codex_cad_mcp_test_output.txt`
- `C:\cad_exact_trace\quick_autocad_probe_output.json`

## Create a new trace job from images

Direct Python invocation:

```powershell
& 'C:\Users\<USER_HOME>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\<USER_HOME>\OneDrive\鏂囨。\New project\cad_exact_trace\create_trace_job_from_images.py' `
  --job-name sample-job `
  'C:\path\to\image.png'
```

One-step launcher:

```powershell
powershell -ExecutionPolicy Bypass -File "C:\Users\<USER_HOME>\OneDrive\鏂囨。\New project\cad_exact_trace\run_image_to_cad_job.ps1" `
  -JobName sample-job `
  "C:\path\to\image.png"
```

Default output root:

- `C:\cad_jobs\<job-name>\`

Generated artifacts:

- cleaned images
- `trace_workspace_refs.dxf`
- `auto_trace\trace_starter_vectors.dxf`
- `auto_trace\trace_starter_report.json`
- `auto_trace\debug\*.png`
- `auto_annotations\trace_starter_annotations.dxf`
- `auto_annotations\trace_starter_annotations.json`
- `auto_annotations\debug\*_ocr_overlay.png`
- `auto_annotations\debug\*_ocr_dim_assoc.png`
- `formalized\formal_dimension_skeleton.dxf`
- `formalized\formal_dimension_skeleton.json`
- `formalized\formal_note_skeleton.dxf`
- `formalized\formal_note_skeleton.json`
- `formalized\note_overlay_image-*.png`
- `formalized\redrawn_annotation_draft.dxf`
- `formalized\redrawn_annotation_draft.json`
- `production_preview\production_preview.dxf`
- `production_preview\production_preview.json`
- `final_review\combined_final_review.dxf`
- `final_review\combined_final_review.json`
- `delivery_draft\delivery_draft.dxf`
- `delivery_draft\delivery_draft.json`
- `final_polish\final_polish_draft.dxf`
- `final_polish\final_polish_draft.json`
- `reference_manifest.json`
- `autocad\load_cleaned_refs.scr`
- `autocad\setup_trace_layers.lsp`
- `launch_trace_project.ps1`

## Auto-trace helper layers

- `A-AUTO-LINE`: machine-detected straight segments
- `A-AUTO-CONTOUR`: machine-detected closed outlines
- `A-AUTO-ANCHOR`: reference frame for each source image

These helper layers stay separate from the final production layers so Codex can refine them without pretending they are already correct wall, door, or dimension entities.

## OCR helper layers

- `A-AUTO-TEXT`: OCR text candidates
- `A-AUTO-DIMS`: OCR dimension-like candidates
- `A-AUTO-TEXTBOX`: OCR bounding boxes for review
- `A-AUTO-DIMLINE`: candidate dimension lines associated to recognized dimension text
- `A-AUTO-DIMLINK`: helper links from recognized dimension text to the associated dimension line
- `A-AUTO-DIMEXT`: candidate extension lines near the associated dimension-line endpoints
- `A-AUTO-DIMARROW`: small arrowhead/triangle candidates near trusted dimension-line endpoints

Current OCR mode:

- Tesseract runs from `C:\Program Files\Tesseract-OCR\tesseract.exe`
- OCR data is loaded from `C:\cad_ocr_data\tessdata`
- current active languages are `eng+chi_sim`
- number strings, `mm`, and scale labels are now reasonably useful
- Chinese annotations are partially recoverable, but still need cleanup and review
- associated dimension helpers now try to bind strong dimension strings such as `170`, `100`, `290`, and `800` to nearby dimension lines
- some associated dimensions also recover nearby extension-line candidates, which helps review whether the inferred dimension structure matches the source drawing
- some shorter dimensions now also recover small arrowhead candidates near the dimension-line endpoints

## Formalized dimension skeleton layers

- `A-SKEL-DIM`: formalized dimension lines from trusted associations
- `A-SKEL-EXT`: formalized extension lines from trusted associations
- `A-SKEL-ARROW`: formalized arrowhead candidates from trusted associations
- `A-SKEL-TEXT`: dimension text retained in the formalized skeleton draft

This draft is intentionally narrower than the raw helper layers. It keeps only stronger dimension candidates so you can review a cleaner annotation skeleton before promoting anything to final production layers.

## Formalized note skeleton layers

- `A-SKEL-NOTE`: trusted note text candidates
- `A-SKEL-LEADER`: nearby leader-line candidates bound to trusted notes
- `A-SKEL-NODE`: endpoint markers for leader review

This note draft is also intentionally conservative. It aims to catch the clearer Chinese note blocks and their likely leaders before you decide which ones deserve promotion into final drafting objects.

## Redrawn draft layers

- `A-REDRAW-DIM`: redrawn trusted dimension lines
- `A-REDRAW-EXT`: redrawn trusted extension lines
- `A-REDRAW-ARROW`: redrawn trusted arrowhead candidates
- `A-REDRAW-DTEXT`: redrawn trusted dimension text
- `A-REDRAW-NOTE`: redrawn trusted note text
- `A-REDRAW-LEADER`: redrawn trusted note leaders

This is the cleanest machine-generated draft in the current workflow. It is still not a guaranteed final drawing, but it is closer to a unified CAD review draft than the raw helper layers or the intermediate skeletons.

## Production preview

- `production_preview.dxf` remaps the consolidated redrawn draft onto final-oriented layers
- `A-DIMS` receives the trusted redrawn dimension structure
- `A-TEXT` receives the trusted redrawn notes and leaders

This preview is the closest current artifact to a final review drawing. It is still generated conservatively, but it already looks more like a production-layer export than an analysis workspace.

## Combined final review

- `combined_final_review.dxf` merges the reference underlay context with the production-preview entities
- this gives you one review sheet with `A-REF`, `A-DIMS`, and `A-TEXT` together

This is the easiest current artifact to inspect in AutoCAD when you want to judge how close the machine-generated result is to the original source drawing without manually juggling multiple intermediate files.

## Delivery draft

- `delivery_draft.dxf` is a cleaned near-final export derived from the combined final-review sheet
- it preserves `A-REF`, `A-DIMS`, and `A-TEXT`
- it is intended as the closest current machine-generated handoff before final manual CAD polish

If you only want one file to continue polishing toward final delivery, this is now the best default artifact in the pipeline.

## Final polish draft

- `final_polish_draft.dxf` is a cleaned near-final export derived from the delivery draft
- it keeps the same final-facing layers: `A-REF`, `A-DIMS`, and `A-TEXT`
- it performs light cleanup such as duplicate filtering and a small dimension-text lift where appropriate

This is the best current machine-generated file for the last round of human CAD polishing before final delivery.

## Final production draft

- `final_production_draft.dxf` is a normalized production-facing export derived from the final polish draft
- it preserves the trusted final-facing layers and applies another pass of text and dimension normalization
- it is the best current machine-generated DXF to hand into a direct AutoCAD finalize step

## AutoCAD finalize pass

- `final_production_autocad_polished.dxf` is created by opening the final production draft inside AutoCAD through COM
- the current finalize pass proves that Codex can attach to the active AutoCAD session, open the draft, run a simple viewport command, and save a polished DXF back out
- this is the current bridge point between generated DXF structure and direct in-AutoCAD finishing logic

## Direct smoke test

Run:

```powershell
& 'C:\Users\<USER_HOME>\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' `
  'C:\Users\<USER_HOME>\OneDrive\鏂囨。\New project\cad_exact_trace\direct_autocad_smoke.py'
```

Expected result:

- AutoCAD can be attached or launched
- a simple rectangle and text are drawn
- output is saved to `C:\cad_exact_trace\direct_autocad_smoke.dxf`

## Practical operating model

1. Verify the stack.
2. Build a trace job from the new image set.
3. Inspect `auto_trace\debug\*_overlay.png` to see whether the extracted geometry tracks the source.
4. Inspect `auto_annotations\debug\*_ocr_overlay.png` to review OCR hits before trusting labels.
5. Inspect `auto_annotations\debug\*_ocr_dim_assoc.png` to review which dimension strings were bound to nearby dimension lines.
6. Open the generated DXF and script in AutoCAD.
7. Keep raster references on `A-REF`.
8. Use `A-AUTO-LINE` and `A-AUTO-CONTOUR` as the first-pass geometry scaffold.
9. Use `A-AUTO-DIMS` and `A-AUTO-TEXT` as candidate annotation layers only.
10. Use `A-AUTO-DIMLINE` and `A-AUTO-DIMLINK` to review whether Codex matched the right dimension lines.
11. Use `A-AUTO-DIMEXT` to review whether nearby extension lines were inferred correctly.
12. Use `A-AUTO-DIMARROW` to review whether short dimension arrowheads were inferred in the right place.
13. Open `formalized\formal_dimension_skeleton.dxf` when you want a cleaner draft of trusted dimension structure rather than the full helper-layer soup.
14. Open `formalized\formal_note_skeleton.dxf` and `formalized\note_overlay_image-*.png` when you want a cleaner draft of trusted note-and-leader structure.
15. Open `formalized\redrawn_annotation_draft.dxf` when you want the most consolidated machine-redrawn CAD draft currently available.
16. Open `production_preview\production_preview.dxf` when you want the closest current machine-generated export on final-oriented layers.
17. Open `final_review\combined_final_review.dxf` when you want the most practical single-file review sheet with both reference context and final-oriented machine draft together.
18. Open `delivery_draft\delivery_draft.dxf` when you want the closest current machine-generated near-final handoff file.
19. Open `final_polish\final_polish_draft.dxf` when you want the cleanest current near-final machine export before manual signoff.
20. Open `final_production\final_production_draft.dxf` when you want the normalized production-facing draft.
21. Open `final_production\final_production_autocad_polished.dxf` when you want the latest AutoCAD-side finalize output.
22. Move reviewed final geometry and annotations onto:
   - `A-WALL`
   - `A-FURN`
   - `A-WIND`
   - `A-DOOR`
   - `A-TEXT`
   - `A-DIMS`
23. Use Codex to iteratively refine the DXF-generation scripts or direct AutoCAD bridge calls.

## GitHub sync

- local sync automation now targets the repository `jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software`
- the sync flow exports a lightweight snapshot of the current CAD-exact-trace workspace plus the latest job manifest and final-production metadata
- the scheduled sync interval is 15 minutes
- actual remote push still depends on GitHub authentication being available on this computer

## Honest limit

This stack is now solid enough for repeatable CAD tracing, controlled AutoCAD drawing calls, machine-generated vector starter geometry, and mixed Chinese/English OCR candidates. It is not yet proof that any arbitrary reference image can be converted into a perfectly identical engineering drawing without review.

To reach the target of "same drawing, same details", the remaining gap is now mostly recognition and correction quality:

- stronger Chinese annotation cleanup
- text-note leader endpoint association
- promotion of trusted note and dimension skeletons into more formal CAD objects
- direct AutoCAD redraw from the consolidated draft into final production entities
- layer-cleanup and style normalization for the production preview export
- stronger final-review to production-layer promotion rules
- final manual polish rules for the delivery draft export
- stronger geometry-aware cleanup for the final-polish export
- stronger AutoCAD-native finalize rules beyond the current proof pass
- symbol and hatch classification
- lineweight and layer inference
- snapping extracted geometry onto exact drafting relationships
- correction loops inside AutoCAD
