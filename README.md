# 星桥三联：StarBridge Creative Software MCP

[![CI](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml/badge.svg)](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml)
![Windows first](https://img.shields.io/badge/Windows-first-2563eb)
![MCP stdio](https://img.shields.io/badge/MCP-stdio-16a34a)
![Local first](https://img.shields.io/badge/local--first-safe-0f766e)

## Current Capability Matrix

| Bridge | Stable | Dry-run only | Experimental | Planned |
| --- | --- | --- | --- | --- |
| ComfyUI | Workflow JSON validation; safe status shape when service is offline. | None for validation. | Local HTTP probe and `txt2img` submit script require a running local ComfyUI and explicit checkpoint. | Full txt2img job lifecycle, img2img, inpaint, upscale, asset manifest. |
| Blender | Environment probe for executable and optional MCP directory hints. | None. | No public write loop in this release. | Safe generated scene script and render manifest. |
| AutoCAD/DXF | CAD plan validation, plan summary, DXF dry-run, sandbox output guard. | DXF export defaults to dry-run. | Real test DXF write only with `confirm_write=true`, optional `ezdxf`, and `examples/cad/output`. | Richer CAD entity schema and desktop AutoCAD evidence. |
| Photoshop | Safe status/session metadata shape; no private PSD opening. | Sandbox demo plan defaults to dry-run. | Real COM document info and sandbox PSD/preview export require authorized local Photoshop and explicit confirmation. | Subject extraction MCP tool and reviewed local smoke evidence. |
| Illustrator | Safe status/document metadata shape; no private `.ai` opening. | Sandbox artboard/export plan defaults to dry-run. | Real COM document info and sandbox AI/SVG/PDF/PNG export require authorized local Illustrator and explicit confirmation. | Preflight and image trace workflows. |
| Jianying/CapCut | Draft directory probe shape only; no draft content read. | None. | Local executable/draft directory availability checks. | Safe draft skeleton and manifest research. |

Photoshop, Illustrator, Blender, and CapCut write flows are experimental or planned unless a reviewed local run proves otherwise.

**GitHub description 建议：** Codex Computer Use + StarBridge MCP + Safety Verification Layer for local creative software, with GUI inspection, structured tools, redacted checks, and CI validation.

## 项目状态：v0.1-alpha

这个仓库当前是 **v0.1-alpha 工程原型**，不是完整多软件生产平台。定位是 Windows-first、local-first 的 **MCP stdio server + tool registry + safety verification layer**，用于让 Codex / Cursor / Claude Code 以可验证方式接入本机创意软件。StarBridge 不替代 ComfyUI、Photoshop、Illustrator、AutoCAD、Blender、剪映/CapCut 或 GUI Computer Use；它只把已经能测试的本地能力收敛成结构化工具，并把实验能力和计划能力明确分开。`StarBridge v0.2` 的重点是 `EvidenceManifest + JobStatus`，而不是继续扩张软件数量。

当前真实能力分层：

| 状态 | 当前范围 |
| --- | --- |
| stable | MCP stdio server、tool registry、统一 status/probe、路径脱敏、安全检查、preflight、ComfyUI workflow validate、AutoCAD/DXF plan validate / dry-run / guarded write。 |
| experimental | Photoshop sandbox 写入/导出 demo、Illustrator sandbox trace/export demo、Blender scene script 方向、ComfyUI txt2img/img2img/upscale job lifecycle、CapCut / 剪映 draft write 研究。写入类默认必须 dry-run 或显式确认，并限制在 demo/sandbox。 |
| planned | 多软件完整生产闭环、真实项目素材生命周期、跨软件 asset handoff、可审计 E2E release evidence。 |
| not implemented | 自动登录、账号授权绕过、读取客户私有工程、提交模型/生成图/客户图纸、无确认写入真实桌面软件。 |

v0.1-alpha 已有且可以验证：

- MCP stdio server：`python -m starbridge_mcp.mcp_server`
- 工具注册表：`npm.cmd run starbridge:tools:safe`
- 总状态与安全状态：`npm.cmd run bridge:status:safe`
- ComfyUI：offline-safe probe、workflow JSON validate；真实生成任务仍依赖本机 ComfyUI 和显式 checkpoint。
- AutoCAD/DXF：自然语言/JSON plan、`validate_cad_plan`、dry-run、`confirm_write` 受控写入 `examples/cad/output`、manifest/report。
- Adobe / Blender / CapCut：已有部分 probe/demo 入口，但生产级写入闭环仍是 experimental 或 planned。

关键文档：

- [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)：逐桥能力矩阵，区分 reads/writes/dry-run/真实软件依赖。
- [docs/RELEASE_V0_1_ALPHA.md](docs/RELEASE_V0_1_ALPHA.md)：v0.1-alpha 只承诺当前真实可运行能力。
- [docs/comfyui-agent-workflow-protocol.md](docs/comfyui-agent-workflow-protocol.md)：ComfyUI 智能体自动搭建、修复、运行 workflow 的可视化协议。
- [docs/client-compatibility.md](docs/client-compatibility.md)：Claude Desktop / Cursor / Codex / mock stdio 兼容状态。
- [docs/windows-install.md](docs/windows-install.md)：Windows 本地开发安装说明。
- [SECURITY.md](SECURITY.md)：公开仓库安全边界。

最短运行路径：

```powershell
python -m pytest
npm.cmd test
npm.cmd run preflight
npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
python scripts\security_check.py
python scripts\collect_bridge_status.py --json
python scripts\bridge_capability_matrix.py --check
python scripts\starbridge_preflight.py --markdown
python scripts\starbridge_preflight.py --write-report --soft-exit
python examples\bridge_status.py --json --redact-paths --soft-exit
python examples\cad\generate_dxf_plan.py
```

CI 候选检查使用下面这些命令：

```powershell
python -m compileall .
python -m unittest discover -s tests
python scripts/security_check.py
python scripts/collect_bridge_status.py --json
python examples/bridge_status.py --json --redact-paths --soft-exit
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
```

See [docs/demo-illustrator.md](docs/demo-illustrator.md) and [docs/demo-photoshop.md](docs/demo-photoshop.md). Real outputs go to `examples/output/` and are ignored by Git.

## Release Readiness

* Visual evidence: [docs/adobe-demo-gallery.md](docs/adobe-demo-gallery.md)
* Local smoke test: [docs/adobe-demo-smoke-test.md](docs/adobe-demo-smoke-test.md)
* Draft release notes: [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md)
* Computer Use architecture: [docs/starbridge.md](docs/starbridge.md)
* GitHub comparison notes: [docs/github-comparison.md](docs/github-comparison.md)

**English quick summary:** StarBridge is a Windows-first, local-first MCP stdio server and safety bridge for connecting AI coding agents to creative desktop software: ComfyUI, Blender, AutoCAD / DXF, Photoshop, Illustrator, and CapCut / Jianying. It focuses on safe probes, workflow validation, redacted status reports, and guarded automation examples instead of uploading private assets or replacing the creative tools.

**Search keywords:** MCP, Model Context Protocol, Codex, AI agent, creative software automation, ComfyUI workflow, Blender automation, AutoCAD DXF, Photoshop COM, Illustrator scripting, CapCut Jianying, local-first AI tools.

这个仓库整理 **Codex 接入本机创作软件** 的公开方案。新定位不是“用 StarBridge 替代 Computer Use”，而是把两者分工清楚：Computer Use 看真实 GUI、点击和复现问题；StarBridge MCP 把稳定动作做成参数化工具；Safety layer 在两者外侧做路径脱敏、权限边界、只读检查和发布前体检。成熟的只读检查、workflow 校验和受保护 DXF 能力继续通过 MCP stdio tools 交给 Codex / Cursor / Claude Code 调用。

公开仓库只保存说明、协议、示例脚本、workflow、MCP stdio server、工具注册表和安全检查。不保存个人路径、账号、模型、素材、生成图、客户图纸、授权信息或本机缓存。

## 中文阅读指南

如果你第一次打开这个仓库，按这三步走就够了：

| 步骤 | 做什么 | 入口 |
| --- | --- | --- |
| 1 | 了解项目范围和安全边界 | 本页 README |
| 2 | 按目标选择一条软件桥 | [中文用途索引](docs/中文用途索引.md) |
| 3 | 检查本机环境是否可用 | `python examples\bridge_status.py` |

最短状态检查：

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --json --redact-paths --soft-exit
python examples\bridge_status.py --probe-executables
```

也可以通过 npm 快捷命令运行：

```powershell
npm.cmd run bridge:status:json
npm.cmd run bridge:status:safe
```

如果 PowerShell 拦截 `npm.ps1`，优先使用 `npm.cmd`。

## For English Readers

Start with this README and [docs/local-mcp-setup.md](docs/local-mcp-setup.md). Most project notes are Chinese-first because the current workstation and software setup are Windows-first, but commands, tool names, environment variables, and MCP APIs are kept in English.

Useful entry points:

| Goal | Open | Run |
| --- | --- | --- |
| Discover available MCP tools | [docs/local-mcp-setup.md](docs/local-mcp-setup.md) | `npm.cmd run starbridge:tools:safe` |
| Check local bridge status | [examples/bridge_status.py](examples/bridge_status.py) | `npm.cmd run bridge:status:safe` |
| Validate before publishing | [scripts/starbridge_preflight.py](scripts/starbridge_preflight.py) | `npm.cmd run preflight` |
| Learn how to contribute | [CONTRIBUTING.md](CONTRIBUTING.md) | `npm.cmd test` |
| Choose GUI vs MCP path | [docs/computer-use-vs-mcp.md](docs/computer-use-vs-mcp.md) | 不需要运行 |
| Use Computer Use safely | [docs/07-codex-computer-use.md](docs/07-codex-computer-use.md) | `npm.cmd run bridge:status:safe` |

## 这个仓库解决什么

它把本地创作工作站拆成多条清楚的软件桥：

| 软件桥 | Codex 负责 | 本地软件负责 | 当前状态 |
| --- | --- | --- | --- |
| ComfyUI 图像生成桥 | MCP 工具读取系统/节点信息、校验 API workflow | 文生图、图生图、修复、放大 | 已挂 `comfyui.system_probe` / `comfyui.workflow_validate` |
| Blender 三维场景桥 | MCP 工具检查可执行文件和环境线索 | 建模、材质、灯光、相机、渲染 | 已挂 `blender.environment_probe`，待补安全场景脚本 |
| CAD 工程制图桥 | MCP 工具检查 AutoCAD 环境；离线生成/校验 DXF plan | 精确线条、孔位、尺寸、图层、DWG | 已挂 `cad_autocad.environment_probe` 和 `autocad_dxf.*` |
| Photoshop 修图桥 | MCP 工具检查 COM/session 线索，脚本读取文档信息 | 主体选择、抠图、图层处理、PNG 导出 | 已挂 `photoshop.session_info`，写入动作仍需确认 |
| AI 矢量文件桥 | MCP 工具检查 Illustrator COM/session 线索 | Illustrator `.ai`、Image Trace、SVG/PDF/PNG 导出 | 已挂 `illustrator.document_info`，导出脚本未开放 |
| 剪映/CapCut 短视频剪辑桥 | MCP 工具检查可执行文件和草稿目录配置 | 时间线剪辑、模板、字幕、导出 | 已挂 `jianying_capcut.draft_probe`，不读草稿内容 |

一句话原则：**Computer Use 管 GUI 观察和交互复现，StarBridge 管结构化安全边界，MCP 管稳定工具调用，Safety layer 管脱敏验证，专业软件管真实生产，私有资产只留本机。**

## 按目标选择入口

| 目标 | 先打开 | 然后运行 |
| --- | --- | --- |
| 了解整体方案 | [docs/中文介绍.md](docs/中文介绍.md) | 不需要运行 |
| 查每个文件用途 | [docs/中文用途索引.md](docs/中文用途索引.md) | 不需要运行 |
| 检查已接入桥状态 | [examples/bridge_status.py](examples/bridge_status.py) | `python examples\bridge_status.py` |
| 接入 ComfyUI | [docs/02-codex-comfyui.md](docs/02-codex-comfyui.md) | `python examples\comfy_bridge\comfy_probe.py` |
| 接入 CAD / AutoCAD | [docs/01-codex-cad.md](docs/01-codex-cad.md) | `python scripts\test_autocad_mcp.py` |
| 接入 Photoshop | [docs/03-codex-photoshop.md](docs/03-codex-photoshop.md) | `powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1` |
| 接入 Illustrator / AI 矢量文件 | [docs/05-codex-illustrator.md](docs/05-codex-illustrator.md) | `python examples\bridge_status.py --probe-executables` |
| 接入 Blender | [docs/04-codex-blender.md](docs/04-codex-blender.md) | `python examples\bridge_status.py --probe-executables` |
| 研究接入剪映/CapCut | [docs/06-codex-jianying.md](docs/06-codex-jianying.md) | 先按文档做本地草稿目录确认 |
| 查看 Photoshop 详细桥方案 | [docs/photoshop-codex-bridge.md](docs/photoshop-codex-bridge.md) | 按文档选择诊断或实操命令 |
| 判断该用 Computer Use 还是 MCP | [docs/computer-use-vs-mcp.md](docs/computer-use-vs-mcp.md) | 不需要运行 |
| 查看 Computer Use 安全用法 | [docs/07-codex-computer-use.md](docs/07-codex-computer-use.md) | 不需要运行 |
| 查看扩展路线 | [docs/codex-drawing-tool-integrations.md](docs/codex-drawing-tool-integrations.md) | 不需要运行 |

## 仓库区域标注

| 区域 | 目录或文件 | 说明 |
| --- | --- | --- |
| 总览和协议 | `README.md`、`docs/中文介绍.md`、`docs/starbridge-link-protocol.md` | 说明项目定位、本地软件桥分工和公开边界 |
| 中文索引 | `docs/中文用途索引.md`、`docs/中文标注规范.md` | 标注每个主要文件用途，统一中文说明方式 |
| 状态检查 | `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop、Illustrator、剪映/CapCut 本机配置 |
| 图像生成区 | `examples/comfy_bridge/` | API 探针、文生图脚本和 workflow JSON |
| 工程制图区 | `cad-mcp-autocad/`、`scripts/` | AutoCAD MCP 子项目和自动绘图脚本 |
| Photoshop 示例 | `examples/photoshop_bridge/` | COM 诊断、测试文档、主体抠图和本机报告 |
| AI 矢量文件区 | `docs/05-codex-illustrator.md` | Illustrator / `.ai` 矢量文件接入说明和安全边界 |
| 测试 | `tests/` | 对解析器、中文标注和报告生成做回归检查 |
| 安全规则 | `.gitignore`、`AGENTS.md` | 约束哪些内容可以公开，哪些内容只留本机 |

## 运行前配置

真实安装路径不要写进 GitHub。每台电脑用环境变量或本地 `.env` 管理：

| 软件或目录 | 环境变量 |
| --- | --- |
| ComfyUI API 地址 | `STARBRIDGE_COMFYUI_URL` |
| ComfyUI 启动脚本 | `COMFY_LAUNCHER` 或 `COMFY_START_SCRIPT` |
| ComfyUI 根目录 | `COMFY_ROOT` 或 `COMFYUI_PATH` |
| ComfyUI 输出目录 | `COMFY_OUTPUT_DIR` |
| Blender 可执行文件 | `STARBRIDGE_BLENDER_EXE` 或 `BLENDER_EXE` |
| Blender MCP 目录 | `STARBRIDGE_BLENDER_MCP_DIR` 或 `BLENDER_MCP_DIR` |
| AutoCAD 可执行文件 | `STARBRIDGE_AUTOCAD_EXE` 或 `AUTOCAD_EXE` |
| CAD 模式标记 | `STARBRIDGE_CAD_MODE` |
| Photoshop 可执行文件 | `PHOTOSHOP_EXE` |
| Illustrator 可执行文件 | `ILLUSTRATOR_EXE` |
| 剪映可执行文件 | `JIANYING_EXE` |
| CapCut 可执行文件 | `CAPCUT_EXE` |
| 剪映草稿目录 | `JIANYING_DRAFTS_DIR` |
| CapCut 草稿目录 | `CAPCUT_DRAFTS_DIR` |
| 下载收件箱 | `STARBRIDGE_DOWNLOAD_INBOX` |

本地输出、报告、图片、DWG、PSD、缓存和日志应放在 `output/`、`scratch/` 或其他本机私有目录，并保持在 Git 提交之外。

## 常用命令

### 检查已接入桥

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --json --redact-paths --soft-exit
python examples\bridge_status.py --probe-executables
```

### 发布前体检

```powershell
python scripts\starbridge_preflight.py --markdown
python scripts\starbridge_preflight.py --json
python scripts\starbridge_preflight.py --write-report --soft-exit
python scripts\security_check.py
```

### StarBridge MCP

```powershell
python -m starbridge_mcp.server --json
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
python -m starbridge_mcp.mcp_server
npm.cmd run starbridge:mcp
```

MCP 客户端可发现首批安全工具：`starbridge.status`、`starbridge.probe`、`starbridge.tools`、`starbridge.evidence_init`、`starbridge.evidence_validate`、`starbridge.job_status`、`comfyui.system_probe`、`comfyui.workflow_validate`、`blender.environment_probe`、`cad_autocad.environment_probe`、`photoshop.session_info`、`illustrator.document_info`、`jianying_capcut.draft_probe`、`autocad_dxf.status`、`autocad_dxf.validate_cad_plan`、`autocad_dxf.create_dxf_plan`、`autocad_dxf.summarize_plan` 和 `autocad_dxf.write_dxf`。

### Evidence / Job lifecycle

```powershell
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
```

默认 manifest 写入 `examples/output/evidence/manifest.latest.json`。这里只保留脱敏 JSON 证据和状态摘要，不保存客户素材、模型、PSD、AI、DWG 或真实导出结果。

### ComfyUI

```powershell
python examples\comfy_bridge\comfy_probe.py
python examples\comfy_bridge\validate_workflow.py --json
python examples\comfy_bridge\validate_workflow.py --workflow examples\comfy_bridge\workflows\minimal_api_workflow.json --json
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden" --ckpt "<checkpoint-name>"
```

ComfyUI closed loop demo：先用 `npm.cmd run comfy:probe` 和 `npm.cmd run comfy:workflow:validate` 做只读检查；本机 ComfyUI 启动后，再运行 `python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden" --ckpt "<checkpoint-name>"` 提交一次 txt2img。脚本会查询 `/history/{prompt_id}`，在 `examples/output/comfyui/demo_manifest.json` 写入脱敏 lifecycle 摘要；该 manifest 和真实生成图都被 `.gitignore` 忽略，不提交到 GitHub。

### ComfyUI safe workflow loop

本轮 ComfyUI 闭环只开放安全层能力，不真实调用生成队列：

- `comfyui.workflow_validate`：只读校验 API-format workflow JSON，检查 node id、`class_type`、`inputs`、核心 link、输出节点和 prompt 节点，并返回 `valid`、`errors`、`warnings`、`node_count`、`detected_models`、`missing_or_suspicious_fields`。
- `comfyui.workflow_build_plan`：为 `txt2img`、`img2img`、`inpaint`、`upscale` 生成 dry-run plan，包含 `task_type`、`input_requirements`、`workflow_requirements`、`safety_notes`、`expected_outputs`、`blocked_reasons`。
- `comfy.workflow_draft`：为 `txt2img`、`img2img`、`inpaint`、`upscale` 生成 API-like workflow JSON 草案，并立即用 `workflow_validate` 校验。
- `comfy.workflow_compose`：把安全 placeholder 模块组合成 API-like graph，覆盖 checkpoint、prompt encode、latent、load image、VAE encode、KSampler、decode、save、upscale、inpaint mask 等基础模块。
- `img2img`、`inpaint`、`upscale` 当前支持 draft workflow；不会读取本机图片、模型目录或 ComfyUI output，也不会提交 `/prompt`。
- 校验输出会经过 StarBridge sanitizer，真实路径、用户名和模型路径会脱敏。

公开示例：

| 示例 | 路径 |
| --- | --- |
| 最小 API workflow | `examples/comfy_bridge/workflows/minimal_api_workflow.json` |
| img2img dry-run plan | `examples/comfy_bridge/plans/img2img_dry_run_plan.example.json` |
| inpaint dry-run plan | `examples/comfy_bridge/plans/inpaint_dry_run_plan.example.json` |
| upscale dry-run plan | `examples/comfy_bridge/plans/upscale_dry_run_plan.example.json` |
| txt2img draft workflow | `examples/comfy_bridge/workflows/txt2img_draft_workflow.example.json` |
| img2img draft workflow | `examples/comfy_bridge/workflows/img2img_draft_workflow.example.json` |
| inpaint draft workflow | `examples/comfy_bridge/workflows/inpaint_draft_workflow.example.json` |
| upscale draft workflow | `examples/comfy_bridge/workflows/upscale_draft_workflow.example.json` |
| txt2img composed workflow | `examples/comfy_bridge/workflows/txt2img_composed_workflow.example.json` |
| img2img composed workflow | `examples/comfy_bridge/workflows/img2img_composed_workflow.example.json` |
| inpaint composed workflow | `examples/comfy_bridge/workflows/inpaint_composed_workflow.example.json` |
| upscale composed workflow | `examples/comfy_bridge/workflows/upscale_composed_workflow.example.json` |
| complex creative poster composed workflow | `examples/comfy_bridge/workflows/complex_creative_poster_composed_workflow.example.json` |

### ComfyUI workflow draft builder

`comfy.workflow_draft` 是只读草案生成器，用于把基础参数转成可审查的 ComfyUI API-like workflow JSON。它接受 `task_type`、`prompt`、`negative_prompt`、`width`、`height`、`seed`、`steps`、`cfg`、`sampler`、`scheduler`、`denoise`、`scale_by` 等参数。

返回结构包含：

- `valid`：草案是否通过本仓库 `workflow_validate`。
- `workflow`：API-like workflow JSON 草案。
- `validation_report`：完整校验报告。
- `warnings`、`safety_notes`、`next_steps`：说明草案边界和后续人工确认步骤。

所有 draft 都带 `StarBridgeDraftMetadata` 节点，标记 `production_ready=false`、`queue_submission=disabled`、`model_policy=placeholder_only`。模型、源图、mask、upscale model 都使用 placeholder，不使用真实模型路径、真实图片路径或真实输出目录。

### ComfyUI workflow graph composer

`comfy.workflow_compose` 是只读 graph composer，用固定安全模块组合 ComfyUI API-like workflow：

- `checkpoint_loader_placeholder`
- `positive_prompt_encode`
- `negative_prompt_encode`
- `empty_latent_image`
- `load_image_placeholder`
- `vae_encode_placeholder`
- `ksampler`
- `vae_decode`
- `save_image_placeholder`
- `upscale_placeholder`
- `inpaint_mask_placeholder`

返回结构包含 `valid`、`workflow`、`validation_report`、`warnings`、`safety_notes`、`next_steps`。所有 composed workflow 都带 `StarBridgeDraftMetadata`，其中 `draft=true`、`safe_placeholder=true`、`queue_submission=disabled`。Composer 不读取文件系统、不联网、不提交队列，只生成可审查 JSON。

### ComfyUI workflow template registry

`workflow_template_registry` 在 graph composer 之上增加一层公开模板索引，目前注册：

| template_id | task_type | 状态 |
| --- | --- | --- |
| `txt2img_basic_v1` | `txt2img` | `composed_validated` |
| `img2img_basic_v1` | `img2img` | `composed_validated` |
| `inpaint_basic_v1` | `inpaint` | `composed_validated` |
| `upscale_basic_v1` | `upscale` | `composed_validated` |
| `creative_poster_complex_v1` | `complex_creative_poster` | `composed_validated` |

Registry 文件位于 `examples/comfy_bridge/templates/workflow_template_registry.json`。每个模板只声明 `template_id`、`version`、`task_type`、composer modules、required inputs、placeholder policy、validation status、safety level 和 notes；不引用真实模型、真实图片或真实输出目录。

新增 MCP safe read-only tools：

- `comfy.workflow_template_list`：列出模板和 lint 状态。
- `comfy.workflow_template_get`：按 `template_id` 返回单个模板。
- `comfy.workflow_from_template`：用模板调用安全 graph composer，返回 placeholder-only workflow。

这三个 tool 不读取用户文件路径、不联网、不提交 ComfyUI queue；输出 workflow 仍带 `StarBridgeDraftMetadata`、`safe_placeholder=true`、`production_ready=false`、`queue_submission=disabled`。

### CAD / AutoCAD

```powershell
python scripts\test_autocad_mcp.py
python scripts\draw_connection_plate_from_spec.py
python scripts\draw_reference_mechanical_part.py
```

### Photoshop

先手动打开已授权的 Photoshop，再按需要运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\document_info.ps1
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\run_local_practice.ps1
python examples\photoshop_bridge\write_practice_report.py
```

单独运行 COM 探针：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

单独运行主体抠图：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

### 测试

```powershell
npm.cmd test
npm.cmd run preflight
```

或直接运行：

```powershell
python -m unittest discover -s tests
python scripts\starbridge_preflight.py --markdown
```

## 不发布内容

以下内容只留本机，不进入 GitHub：

- 账号、密码、验证码、Cookie、token、OAuth 缓存、浏览器资料和支付信息。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成图片和输出目录。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存和本机插件缓存。
- CAD 客户图纸、商业 DWG、授权文件和真实项目输出。
- Photoshop 安装路径、Creative Cloud 缓存、PSD、商业字体、笔刷、购买素材、源图和导出结果。
- Illustrator 安装路径、Creative Cloud 缓存、AI 私有工程、商业字体、商业画笔、购买素材、源图和导出结果。
- 剪映/CapCut 草稿、缓存、导出视频、账号信息、会员状态、客户素材和字幕原稿。
- `output/`、`scratch/`、临时文件、日志、报告产物和本机缓存。

## 下一步

| 优先级 | 任务 |
| --- | --- |
| 高 | 给 Blender 增加公开安全的基础场景生成脚本 |
| 高 | 给 ComfyUI 增加 `img2img`、inpaint、upscale 和 job/asset 生命周期摘要 |
| 高 | 给 CAD 增加更清楚的 JSON 参数格式和标准零件示例 |
| 中 | 把 Photoshop 的 `extract_subject`、`export_png`、`document_info` 封装成安全 MCP 工具 |
| 中 | 给 Illustrator 增加只读文档信息、测试画板和 `trace_image_to_vector` 参数化示例 |
| 中 | 给剪映增加只读草稿目录探针，再验证最小测试草稿生成 |
| 中 | 为 Penpot/Figma、Krita 建立接入评估表，先记录许可、依赖、账号要求和安全边界 |

完整路线图见 [ROADMAP.md](ROADMAP.md)。

## 协作原则

1. 公开仓库只放可复用、可审查、可安全分享的内容。
2. 本机软件、账号授权、商业素材和客户资产由用户手动管理。
3. 示例脚本要能单独运行，失败时给出清楚的中文提示。
4. 新增能力先补文档和状态检查，再扩展自动化脚本。
