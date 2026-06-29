# StarBridge Canvas

StarBridge Canvas is a local realtime tldraw canvas for Codex-led creative workflows. It is adapted from the `codexhuabu` canvas prototype and stores canvas state inside the active project directory.

## Start

From the repository root:

```powershell
npm run canvas:dev -- -ProjectDir "C:\path\to\your\project"
```

Open the printed local URL, usually:

```text
http://127.0.0.1:43217
```

The browser writes data to:

```text
<project>\canvas\
```

That folder is intentionally ignored by Git because it contains local working state and page assets.

## Realtime Drawing

The canvas uses two local endpoints:

- `/api/canvas` saves and loads the complete tldraw snapshot.
- `/api/canvas-events` streams updates to every open canvas window.
- `/api/canvas-live` receives lightweight drawing events such as added, updated, and removed records.

When one window draws or edits shapes, other windows receive a live event immediately and refresh from the persisted snapshot after the next save. The UI status pill shows whether the realtime stream is connected.

## MCP Bridge

Start the canvas MCP server:

```powershell
npm run canvas:mcp
```

It exposes:

- `get_starbridge_canvas_selection`: reads the persisted browser selection from `canvas/starbridge-selection.json`.
- `insert_starbridge_canvas_image`: copies a local bitmap into the active page assets folder and places it on the running canvas through the canvas API.

Legacy Cowart tool names and environment variables remain supported as aliases during migration.
