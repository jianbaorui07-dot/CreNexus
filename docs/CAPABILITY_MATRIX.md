# StarBridge v0.2 Capability Matrix

这份矩阵只记录当前仓库可以公开发布和测试的能力边界。`stable` 表示有离线测试或 CI 安全验证；`experimental` 表示已有探针或 sandbox demo，但仍依赖本机软件或人工确认；`planned` 表示路线图能力，不写成已完成；`not implemented` 表示明确不支持的方向，例如登录绕过、私有素材读取或未确认的真实桌面写入。

| Bridge | Capability categories | Stable | Experimental | Planned | Evidence / job lifecycle | Writes files | CI safe | Needs local app | Safety notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| StarBridge core | discovery, planning, execution, validation, evidence, cleanup | `starbridge.status`, `starbridge.tools`, `starbridge.safe_roots`, `starbridge.evidence_init`, `starbridge.evidence_validate`, `starbridge.job_status`, MCP stdio `tools/list` / `tools/call` | none | more client adapters | `EvidenceManifest` and `JobStatus` CLI are live, sanitized, and limited to `examples/output/evidence`; `safe_roots` exposes repo-relative writable boundaries | ignored JSON only | Yes | No | no desktop launch, no private file reads, all output passes sanitizer |
| ComfyUI | discovery, planning, execution, validation, evidence | `comfyui.workflow_validate` | `comfyui.system_probe`, local `txt2img` submit script | img2img, inpaint, upscale, richer manifest sync | current v0.2 work keeps lifecycle summary at the safety layer; real generation still needs explicit local confirmation | validate/probe: No | Yes for validate; probe soft-exits when offline | Only for live probe or generation | do not expose checkpoints, LoRA, VAE, ControlNet, generated images, or local output paths |
| AutoCAD / DXF headless | planning, execution, validation, evidence, cleanup | `autocad_dxf.validate_cad_plan`, `autocad_dxf.summarize_plan`, DXF dry-run | guarded `write_dxf` with `confirm_write=true` | richer CAD entity schema | evidence is currently manifest-level; no desktop launch required | only `examples/cad/output` | Yes | No | path cannot escape sandbox output root |
| CAD / AutoCAD desktop probe | discovery, planning, validation, evidence | `cad_autocad.environment_probe` | real AutoCAD COM/MCP control | guarded desktop CAD demo | status only for now | No | Yes, as unavailable/warning when app is absent | Yes | do not open customer DWG/DXF or write real project outputs |
| Photoshop | discovery, planning, execution, validation, evidence, cleanup | safe status/session shape, `photoshop.session_info` | COM `document_info`, sandbox PSD create/export demo, `ps.camera_raw.tune` dry-run planning | subject extract MCP tool, verified Camera Raw BatchPlay descriptor fixture | v0.2 evidence captures plan/status/output summary only, not PSD contents | only `examples/output/photoshop` with explicit confirmation; Camera Raw apply blocked until descriptor is recorded | dry-run schema only | Yes | do not open private PSD or publish exports, fonts, brushes, install paths, or automate Camera Raw modal mouse dragging |
| Illustrator | discovery, planning, execution, validation, evidence, cleanup | safe status/document shape | COM `document_info`, sandbox artboard/export demo | preflight, image trace | v0.2 evidence captures plan/status/output summary only, not `.ai` contents | only `examples/output/illustrator` with explicit confirmation | dry-run schema only | Yes | do not read client `.ai`, source image paths, or export directories |
| Blender | discovery, planning, validation, evidence | `blender.environment_probe` | none | safe scene script, render manifest | evidence currently limited to probe/status layer | No | Yes, as unavailable/warning when app is absent | Only for future scene scripts | do not open private `.blend` or run arbitrary user Python |
| CapCut / Jianying | discovery, planning, validation, evidence | `jianying_capcut.draft_probe` | none | safe draft skeleton, manifest research | evidence currently limited to probe/status layer | No | Yes, as unavailable/warning when app is absent | Only for future local validation | do not read `draft_content.json`, draft contents, account state, or exported videos |

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

这些命令只读或只写入被 `.gitignore` 忽略的 `examples/output/evidence/`，不会启动真实桌面软件，也不会读取私有素材。

## Photoshop Camera Raw tuning

Camera Raw tuning is experimental. V1 supports parameter planning and safe validation. Real Photoshop apply requires a verified local BatchPlay descriptor and explicit confirmation.

`ps.camera_raw.tune` 默认 `dry_run=true`，示例计划位于 `examples/photoshop_bridge/plans/camera_raw_tune_blue_artwork.example.json`。如果调用方设置 `dry_run=false` 和 `confirm_apply=true`，但仓库还没有已审 Camera Raw Filter descriptor fixture，工具必须返回 `camera_raw_batchplay_descriptor_not_recorded`，不得控制 Camera Raw modal UI 的鼠标拖动。
