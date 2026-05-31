# GitHub Comparison Notes

This note tracks ideas from comparable public creative-software MCP projects that can be adopted into StarBridge without copying implementation code.

## Compared Projects

| Project | Area | Useful Pattern |
| --- | --- | --- |
| [artokun/comfyui-mcp](https://github.com/artokun/comfyui-mcp) | ComfyUI MCP | Asset IDs, job status, workflow visualization, workflow diff, generation metadata, VRAM checks, progress monitor. |
| [IO-AtelierTech/comfyui-mcp](https://github.com/IO-AtelierTech/comfyui-mcp) | ComfyUI MCP | Explicit API vs UI workflow format separation, schema validation, node discovery, queue/history tools, compatibility notes. |
| [namurokuro/Blender-MCP-Server](https://github.com/namurokuro/Blender-MCP-Server) | Blender MCP | Tool category map, thread-safe operation queue, UI panel start/stop, status monitoring, troubleshooting-first docs. |

## Directly Pullable Ideas

1. Add a richer `ExecutionResult` evidence manifest for generated assets:
   - stable asset IDs
   - source plan ID
   - originating workflow or GUI step IDs
   - output file list
   - screenshots
   - validation status

2. Split ComfyUI plan handling into explicit workflow formats:
   - `api_workflow` for execution and validation
   - `ui_workflow` for editor-only review
   - reject ambiguous workflow plans before execution

3. Add job lifecycle vocabulary across all bridges:
   - `queued`
   - `running`
   - `completed`
   - `failed`
   - `cancelled`
   - `needs_user`

4. Add optional progress/evidence monitoring:
   - structured tools can report job status
   - Computer Use plans can report current GUI step and screenshot evidence
   - no CI path should launch real desktop software

5. Expand bridge capability descriptions by category:
   - discovery
   - planning
   - execution
   - validation
   - evidence
   - cleanup

## Not Directly Pulled Yet

- External source code was not copied.
- Node.js/TypeScript tool implementations were not ported into the Python StarBridge server.
- Blender addon server patterns were not added because this repository keeps real desktop automation behind probes, sandbox plans, and explicit user approval.
- Model download, registry search, and custom node installation were not added because they need stricter token, license, cache, and path policies first.

## Recommended Next PR

Implement `EvidenceManifest` and `JobStatus` dataclasses, then expose:

- `starbridge evidence init`
- `starbridge evidence add-screenshot`
- `starbridge evidence validate`
- `starbridge job-status`

Those additions would reuse the Computer Use planning layer added in PR #6 while preserving StarBridge's local-first safety boundary.

