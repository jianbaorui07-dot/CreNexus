# Photoshop Masking

Use this note for mask-oriented Photoshop tasks in the local bridge.

## Principles

- Start with `ps.probe`, `ps.document.info`, and `ps.layers.list`.
- Use `ps.preview.export` and `ps.evidence.capture` before asking for any write path.
- Keep mask work inside sandbox copies, never real PSD files.
- Treat COM as fallback and prefer future UXP typed flows for production use.
