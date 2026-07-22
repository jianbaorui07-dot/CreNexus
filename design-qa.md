# CreNexus desktop design QA

## Visual truth and test state

- Primary reference: user-supplied `91e183e4-4609-4939-b828-290e7a5774af.png`.
- Supporting references: user-supplied `dab818af-7fa5-41a9-b329-2c125012c0fb.png` and `90c68f8c-0159-4f3c-80be-3226f6a332dc.png`.
- Comparison viewport: `1523 × 1033`, matching the primary reference.
- Implementation state: local runtime offline, so dynamic task and software rows intentionally use real loading/empty states instead of fabricated demo data.
- Combined comparison inputs were saved as local-only QA artifacts and are not part of the repository.

## Comparison pass 1

Reference and implementation were placed side by side in one image at the same viewport.

| Severity | Surface | Finding | Fix |
| --- | --- | --- | --- |
| P1 | Typography / layout | The mission title wrapped the final Chinese character onto a third line, breaking the reference's two-line editorial silhouette. | Reduced the desktop display scale and capped it at `66px` while preserving the condensed type and tight leading. |
| P1 | Responsiveness | At `1024px`, the two-column hero minimum widths caused horizontal scrolling and clipped the quick-action area. | Moved the stacked desktop breakpoint to `1080px`; hero, status panel and operation sections now reflow vertically without horizontal overflow. |
| P2 | State color | The disabled primary action inherited legacy opacity and became too pale to remain the page's dominant action. | Added an explicit disabled treatment using the orange design token with full opacity and a clear not-available cursor. |
| P2 | Frame alignment | The application rail was about 18px wider than the source, shifting the entire command surface. | Reduced the desktop rail to `200px`, aligning the content and status panel more closely with the reference frame. |

## Comparison pass 2

- The mission headline holds the intended two-line shape at the reference viewport.
- Black structural panels, warm grid-paper background, square rules, orange action hierarchy and green validated states match the supplied design language.
- The home dashboard and connection workflow share one coherent editorial system; no old rounded SaaS cards remain in the inspected flow.
- The `1024 × 768` compact desktop view stacks the home command surface and removes horizontal overflow.
- Navigation, Home → Connections → Home state changes, disabled controls and accessible names were exercised in the browser.
- Browser diagnostics contained no warnings or errors.

## Accepted state differences

- The reference contains populated sample tasks and installed software. The implementation renders live local data only, so the QA capture shows the real loading/empty state while retaining the same information architecture.
- Native Tauri window controls are not present in the browser preview; they remain owned by the desktop shell.

## Previous result

Previous design QA result: passed.

---

## 2026-07-23 Pixel Reconstruction mode-grid follow-up

- Source visual truth path: user-provided screenshot attachment (local source path intentionally redacted).
- Implementation screenshot path: not persisted; the implementation was inspected through a live Computer Use capture of the alpha.2 desktop build.
- Viewport: `1123 × 795` Windows application window during the final alpha.2 launch.
- Source and implementation pixels: source `1680 × 1123`; implementation `1123 × 795`; no density normalization was possible because the implementation capture was not persisted.
- State: Codex paired, local runtime online, alpha.2 desktop shell running.

### Full-view and focused-region evidence

The source establishes a two-column processing-mode grid, square editorial panels, orange selected-state borders, and a separate pixel-parameter section. The implementation reuses those exact layout and token systems, adds Pixel Reconstruction as the fourth card, and uses the installed Tabler `IconGridDots` asset. Automated frontend coverage verified the default selected state, 512-pixel/64-MB controls, and exact job request. The user ended the visual inspection and asked to publish before a persistent same-state capture of the final mode grid could be recorded, so the focused comparison remains blocked.

### Findings

- [P2] Missing persisted final mode-grid comparison.
  - Location: Image Vectorization processing-mode grid.
  - Impact: the implementation and interactions are tested, but a same-viewport visual comparison is not reproducible from this report.
  - Fix: capture the paired Image Vectorization page at the source viewport and compare the mode-grid region before promoting the draft PR.

### Required fidelity surfaces

- Fonts and typography: existing CreNexus display and monospace system retained; final same-state capture pending.
- Spacing and layout rhythm: existing two-column `.mode-grid` and square record-panel system retained; final same-state capture pending.
- Colors and visual tokens: existing `--primary`, border, surface, and selected-state tokens reused.
- Image quality and asset fidelity: no handcrafted SVG added; the new icon comes from the installed Tabler library.
- Copy and content: Pixel Reconstruction is the default exact-only route, while the other modes remain dual-stage.

### Comparison history and checklist

- Initial implementation placed Pixel Reconstruction only in the lower parameter panel; the user clarified that it must appear in the upper mode selector.
- The implementation was revised to add the fourth selectable card, default it to selected, and make the primary action mode-specific.
- Frontend, Python, Rust, security, product-facts, encoding, and real central-red-carp checks passed.
- Persisting and comparing the final paired workflow-page screenshot remains pending.

final result: blocked
