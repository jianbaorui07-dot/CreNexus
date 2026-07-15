# StarBridge v0.2 Capability Matrix

这份矩阵只记录当前仓库可以公开发布和测试的能力边界。`stable` 表示有离线测试或 CI 安全验证；`experimental` 表示已有探针或 sandbox demo，但仍依赖本机软件或人工确认；`planned` 表示路线图能力，不写成已完成；`not implemented` 表示明确不支持的方向，例如登录绕过、私有素材读取或未确认的真实桌面写入。

这里有两层状态词：

- `bridge_status.json` 的 `maturity` 描述整条软件桥的公开成熟度，当前只使用 `stable`、`prototype`、`planned`、`research`、`deprecated`。
- MCP tool registry 的 `current_status` 描述单个工具是否可调用，当前对外归一为 `stable`、`experimental`、`planned`。

因此，一个 bridge 可以是 `prototype`，同时其中某些只读 tool 是 `stable`；这表示整条桥还未生产化，但该工具已有离线测试或安全验证。

| Bridge | Capability categories | Stable | Experimental | Planned | Evidence / job lifecycle | Writes files | CI safe | Needs local app | Safety notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| StarBridge core | discovery, planning, execution, validation, evidence, cleanup | `starbridge.status`, `starbridge.tools`, `starbridge.control_plan`, `starbridge.operation_context`, `starbridge.safe_roots`, `starbridge.evidence_init`, `starbridge.evidence_validate`, `starbridge.job_status`, MCP stdio `tools/list` / `tools/call` | none | more client adapters | `operation_context` returns a sanitized before/after delta and logical evidence refs; `EvidenceManifest` and `JobStatus` remain limited to safe roots | ignored JSON only | Yes | No | no desktop launch, no private file reads, guarded candidates are never executed by the planner |
| ComfyUI | discovery, planning, execution, validation, evidence | `comfyui.queue_snapshot`, `comfyui.progress_monitor`, `comfyui.job_snapshot`, `comfyui.workflow_validate`, `comfy.workflow_lifecycle_summary`, `comfy.workflow_visualize` | `comfyui.system_probe`, local `txt2img` submit script | guarded cancel, dry-run queue payload, WebSocket auto-reconnect | queue snapshot returns hashed job IDs and backpressure；progress monitor returns monotonic live progress；job snapshot provides a redacted terminal-status read after disconnects without returning workflow/output/error content | plan/validate/visualize/lifecycle: No；live queue/job snapshot: one direct loopback GET；live progress: one bounded direct loopback WebSocket | Yes；missing routes, dependency, or local services return structured status | Only for live probe/snapshot/progress or generation | do not expose raw prompt IDs/node IDs, WebSocket payloads, workflow, exception text, previews, checkpoints, generated images, or local output paths |
| AutoCAD / DXF headless | planning, execution, validation, evidence, cleanup | `autocad_dxf.validate_cad_plan`, `autocad_dxf.summarize_plan`, DXF dry-run | guarded `write_dxf` with `confirm_write=true` | richer CAD entity schema | evidence is currently manifest-level; no desktop launch required | only `examples/cad/output` | Yes | No | path cannot escape sandbox output root |
| CAD / AutoCAD desktop probe | discovery, planning, validation, evidence | `cad_autocad.environment_probe` | real AutoCAD COM/MCP control | guarded desktop CAD demo | status only for now | No | Yes, as unavailable/warning when app is absent | Yes | do not open customer DWG/DXF or write real project outputs |
| Photoshop | discovery, planning, execution, validation, evidence, cleanup | safe status/session shape, `photoshop.session_info`, `ps.get_state`, `ps.get_preview` (base64 for vision) | COM `document_info`, sandbox PSD create/export demo, `ps.camera_raw.tune` dry-run planning, 5 recipes (remove_background etc with Action Plan) | subject extract MCP tool, verified Camera Raw BatchPlay descriptor fixture | v0.2 evidence captures plan/status/output summary only, not PSD contents | only `examples/output/photoshop` with explicit confirmation; Camera Raw apply blocked until descriptor is recorded | dry-run schema only | Yes | do not open private PSD or publish exports, fonts, brushes, install paths, or automate Camera Raw modal mouse dragging |
| Illustrator | discovery, exact pixel-vector reconstruction, planning, execution, validation, evidence, cleanup | safe status/document shape, `illustrator.preflight` on sanitized summaries | **primary:** exact RGBA pixel grid→grouped rectangle paths→verified raster-free SVG→Illustrator Save As AI；also retains `illustrator.color_vectorize_*`, guarded native Image Trace protocol, and legacy quantized SVG fallback | transactional exact-vector publish；stronger AI save-completion evidence；explicit-confirmation bounded repair orchestration for retained protocols | exact route proves dimensions, pixel coverage, path/subpath/paint counts, zero embedded raster, bytes and SHA-256；sanitized local run produced 742,922 subpaths and a desktop AI | exact route only writes ignored `examples/output/illustrator/exact-pixel`；desktop AI requires explicit request；legacy output stays in `trace-practice` | exact RGBA fixtures and verifier tests on Ubuntu/Windows；other native route remains dry-run/schema/rejection tested | exact SVG needs no app；AI handoff needs live Illustrator | one explicit PNG/JPEG only；ordinary delivery must not use or fall back to Image Trace；never report source path/name or commit source images, AI/SVG/PNG/JSON outputs, private `.ai`, fonts, or brushes |
| Blender | discovery, planning, validation, evidence | `blender.environment_probe`, `blender.scene_plan` fixed dry-run scene, `blender.reference_reconstruction_plan` anti-hallucination planning | none | confirmed render manifest and same-camera reference comparison report | evidence currently limited to probe/status/scene plan/reference reconstruction plan layer | No | Yes | Only for future render scripts | do not open private `.blend`, load textures, run arbitrary user Python, download assets, or claim hidden geometry as fact |
| CapCut / Jianying | discovery, planning, validation, evidence | `jianying_capcut.draft_probe`, `jianying_capcut.draft_structure` redacted top-level summary | none | safe draft skeleton, template replacement research | evidence currently limited to probe/status/draft structure layer | No | Yes | Only for future local validation | do not read `draft_content.json`, draft contents, account state, media paths, or exported videos |

## Unified status vocabulary

- `queued`
- `running`
- `completed`
- `failed`
- `cancelled`
- `needs_user`

## v0.2 evidence boundary

- `python -m starbridge_mcp.server evidence --init --json`
- `python -m starbridge_mcp.server evidence --validate --json`
- `python -m starbridge_mcp.server job-status --json`
- MCP `starbridge.operation_context`（纯内存、白名单状态字段、逻辑 evidence ID）
- MCP `comfyui.queue_snapshot`（默认 plan-only；live 仅允许 loopback `/queue`，不返回 workflow/history）
- MCP `comfyui.progress_monitor`（默认 plan-only；live 使用直接 loopback `/ws`，只返回哈希 ID、数值进度和状态）
- MCP `comfyui.job_snapshot`（默认 plan-only；live 按显式 job UUID 只读 `/api/jobs/{job_id}`，丢弃 workflow/output/error）

这些命令只读或只写入被 `.gitignore` 忽略的 `examples/output/evidence/`，不会启动真实桌面软件，也不会读取私有素材。

## Photoshop Camera Raw tuning

Camera Raw tuning is experimental. V1 supports parameter planning and safe validation. Real Photoshop apply requires a verified local BatchPlay descriptor and explicit confirmation.

`ps.camera_raw.tune` 默认 `dry_run=true`，示例计划位于 `examples/photoshop_bridge/plans/camera_raw_tune_blue_artwork.example.json`。如果调用方设置 `dry_run=false` 和 `confirm_apply=true`，但仓库还没有已审 Camera Raw Filter descriptor fixture，工具必须返回 `camera_raw_batchplay_descriptor_not_recorded`，不得控制 Camera Raw modal UI 的鼠标拖动。
