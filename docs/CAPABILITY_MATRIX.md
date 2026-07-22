# CreNexus Capability Matrix（schema v2）

这份矩阵只记录当前仓库可以公开发布和测试的能力边界。产品版本为 `0.1.0-alpha.1`；标题中的 schema v2 不是产品版本。状态只能使用 `stable / experimental / planned / not_implemented`，具体语义以 [PRODUCT_FACTS](PRODUCT_FACTS.md) 为准。

这里有两层状态词：

- `bridge_status.json` 的 `maturity` 是旧接口兼容字段：`prototype/research` 统一映射到 `experimental`，不能作为产品展示状态。
- MCP tool registry 的 `current_status` 描述单个工具的代码边界，不证明真实桌面软件已连接。
- `recommended` 单独描述主推路线；运行时软件连接必须使用 `connectionState`，默认 `unknown`。

因此，一个 bridge 可以整体为 `experimental`，其中某些纯离线或只读 tool 为 `stable`；这只表示该工具声明的窄范围已有自动验证。

| Bridge | Capability categories | Stable | Experimental | Planned | Evidence / job lifecycle | Writes files | CI safe | Needs local app | Safety notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CreNexus core | discovery, planning, execution, validation, evidence, cleanup | `starbridge.status`, `starbridge.tools`, `starbridge.control_plan`, `starbridge.operation_context`, `starbridge.safe_roots`, `starbridge.evidence_init`, `starbridge.evidence_validate`, `starbridge.job_status`, MCP stdio `tools/list` / `tools/call` | Project、CreativeJob、Workflow Engine、确认门、应用数据持久化和基础交付 | more client adapters | `operation_context` returns a sanitized before/after delta and logical evidence refs；兼容 EvidenceManifest 与桌面应用数据 Evidence 都限制在安全根 | 应用数据原子 JSON、追加事件和真实产物 | Yes | No | no private directory scan；guarded candidates are never executed without bound confirmation |
| ComfyUI | discovery, planning, execution, validation, evidence | `comfyui.queue_snapshot`, `comfyui.progress_monitor`, `comfyui.job_snapshot`, `comfyui.workflow_validate`, `comfy.workflow_lifecycle_summary`, `comfy.workflow_visualize` | `comfyui.system_probe`、local `txt2img` submit、`comfyui-generation-v1` | guarded cancel, WebSocket auto-reconnect | 统一工作流保存参数摘要、workflow hash、输出 basename/hash 和 artifact ID；模拟回环闭环已通过，真实本机验收待完成 | 未确认前只读；确认后单次回环 `/prompt`、有界 `/history` 和 `/view`，复制到应用数据产物目录 | Yes；缺失本机服务时结构化失败且不提交 | Yes | 持久化 plan/Evidence 不含提示词、模型名、workflow、原路径或图片内容；状态不明时不自动重提 |
| AutoCAD / DXF headless | planning, execution, validation, evidence, cleanup | `autocad_dxf.validate_cad_plan`, `autocad_dxf.summarize_plan`, DXF dry-run | guarded `write_dxf` with `confirm_write=true` | richer CAD entity schema | evidence is currently manifest-level; no desktop launch required | only `examples/cad/output` | Yes | No | path cannot escape sandbox output root |
| CAD / AutoCAD desktop probe | discovery, planning, validation, evidence | `cad_autocad.environment_probe` | real AutoCAD COM/MCP control | guarded desktop CAD demo | status only for now | No | Yes, as unavailable/warning when app is absent | Yes | do not open customer DWG/DXF or write real project outputs |
| Photoshop | discovery, planning, execution, validation, evidence, cleanup | safe status/session shape, `photoshop.session_info`, `ps.get_state`, `ps.get_preview` (base64 for vision) | `photoshop-production-v1` fixed copy-first workflow、COM `document_info`、`ps.camera_raw.tune` dry-run planning and sandbox recipes | reviewed real-session validation, verified Camera Raw BatchPlay descriptor fixture | unified job evidence records only host version, counts, artifact IDs/hashes and safety booleans；simulated UXP loop completed | confirmed fixed recipe writes staged PNG/JPEG/PSD/subject outputs only under app-data artifacts；arbitrary descriptors remain blocked | proxy/schema/workflow integration tests run without Adobe；missing UXP returns `needs_user` | Yes | managed source hash + dual path validation；duplicate before write；no document/layer names or absolute paths persisted；real Photoshop write remains unverified |
| DiagramForge / Draw.io | discovery, planning, native generation, validation, incremental patch, rollback, export, batch | `drawio.probe`, `drawio.capabilities`, `drawio.plan`, `drawio.inspect`, `drawio.validate`, `drawio.batch` | guarded `drawio.create`, `drawio.patch`, `drawio.rollback`, headless editable SVG export | optional live Draw.io MCP adapter, optional ELK adapter, Draw.io desktop PDF when installed | stable element IDs, per-element hashes, unrelated-region hash gate, one-level rollback/redo checkpoint, manifest, save/reopen validation | only ignored `sandbox/`, `output/`, or `examples/output/diagramforge/`; writes require confirmation | deterministic compiler, XML roundtrip, nested container, quality, path, transaction, rollback, MCP and batch tests run cross-platform | No for native/SVG; optional Draw.io desktop app for PDF | no private directory scan; live MCP, app availability, headless compile and reopen validation remain separate truth states |
| Illustrator | discovery, exact pixel-vector reconstruction, planning, execution, validation, evidence, cleanup | safe status/document shape, `illustrator.preflight` on sanitized summaries | **recommended:** exact RGBA pixel grid→grouped rectangle paths→verified raster-free SVG→Illustrator Save As AI；also retains `illustrator.color_vectorize_*`, guarded native Image Trace protocol, and legacy quantized SVG fallback | transactional exact-vector publish；stronger AI save-completion evidence；explicit-confirmation bounded repair orchestration for retained protocols | exact route proves dimensions, pixel coverage, path/subpath/paint counts, zero embedded raster, bytes and SHA-256；sanitized local run produced 742,922 subpaths and a desktop AI | exact route only writes ignored `examples/output/illustrator/exact-pixel`；desktop AI requires explicit request；legacy output stays in `trace-practice` | exact RGBA fixtures and verifier tests on Ubuntu/Windows；other native route remains dry-run/schema/rejection tested | exact SVG needs no app；AI handoff needs live Illustrator | one explicit PNG/JPEG only；ordinary delivery must not use or fall back to Image Trace；never report source path/name or commit source images, AI/SVG/PNG/JSON outputs, private `.ai`, fonts, or brushes |
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
