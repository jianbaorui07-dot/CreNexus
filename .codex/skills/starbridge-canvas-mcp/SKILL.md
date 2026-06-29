---
name: starbridge-canvas-mcp
description: Use StarBridge Canvas from Codex. Use when the task involves opening the local realtime canvas, reading selected tldraw shapes, inserting generated images back into the canvas, debugging canvas realtime sync, or connecting visual ideation to StarBridge creative software workflows.
---

# StarBridge Canvas MCP

## Core Rule

Treat the canvas as a local visual workspace, not as a public asset store. Canvas state, page assets, generated images, annotation screenshots, and project-specific boards stay in the user-selected local `canvas/` directory and should not be committed.

## Read First

Read only the files relevant to the canvas task:

- `docs/starbridge-canvas.md`
- `examples/starbridge_canvas/README.md`
- `examples/starbridge_canvas/src/App.jsx`
- `examples/starbridge_canvas/vite.config.js`
- `examples/starbridge_canvas/mcp/server.mjs`
- `scripts/start_starbridge_canvas.ps1`

## Quick Commands

Start the realtime canvas:

```powershell
npm.cmd run canvas:dev -- -ProjectDir "<project-dir>"
```

Start the canvas MCP server:

```powershell
npm.cmd run canvas:mcp
```

Build-check the canvas:

```powershell
npm.cmd run canvas:build
```

## MCP Client Config

Use this stdio command for local MCP clients that need direct canvas tools:

```json
{
  "mcpServers": {
    "starbridge-canvas": {
      "command": "node",
      "args": ["examples/starbridge_canvas/mcp/server.mjs"]
    }
  }
}
```

Set `STARBRIDGE_CANVAS_URL` if the canvas runs on a non-default port. Legacy `COWART_URL` is accepted only as a migration alias.

## Tool Routing

Use `get_starbridge_canvas_selection` before acting on a selected shape. Use `insert_starbridge_canvas_image` only with an explicit local image path supplied by the current workflow. Prefer inserting new results beside a selected source image or annotation, not overwriting existing canvas content.

Realtime sync uses `/api/canvas-events` and `/api/canvas-live`. If the UI shows reconnecting, verify the local canvas dev server is running before retrying MCP image insertion.

## Safety

Never scan the user's home directory for canvas assets. Never commit `canvas/`, `node_modules/`, build output, generated screenshots, inserted images, or local page assets. Do not print absolute user paths in public docs or PR descriptions unless they are intentionally redacted examples.
