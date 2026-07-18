# P1 validation icon

`icon.ico` is generated from the existing
`examples/starbridge_canvas/public/starbridge-canvas-logo.svg` artwork so the
Windows resource step can be compiled and the P1 desktop executable can be
validated locally.

This validation icon is not evidence that a reviewed production icon set or a
release installer is ready. Before packaging, review the Windows icon at
16/32/48/128/256 px and add the approved cross-platform icon sizes to
`tauri.conf.json`.
