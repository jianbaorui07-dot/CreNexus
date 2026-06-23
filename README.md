# 星桥三联：StarBridge Creative Software MCP

[![CI](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml/badge.svg)](https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software/actions/workflows/ci.yml)
![Windows first](https://img.shields.io/badge/Windows-first-2563eb)
![MCP stdio](https://img.shields.io/badge/MCP-stdio-16a34a)
![Local first](https://img.shields.io/badge/local--first-safe-0f766e)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Getting Started

### Quick Install (Windows PowerShell)

```powershell
# Clone
git clone https://github.com/jianbaorui07-dot/Codex-Integration-with-Creative-Industry-Software.git
cd Codex-Integration-with-Creative-Industry-Software

# Python + dev deps
python -m pip install --upgrade pip
pip install -e ".[dev]"

# Node for some bridges (Photoshop node proxy, frontend examples)
npm install
```

### Smoke checks

```powershell
python -m pytest -q || python -m unittest discover -s tests
python scripts\security_check.py
npm.cmd run preflight
npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
```

See [docs/windows-install.md](docs/windows-install.md) for full local setup.

### Adobe AI / Illustrator vector rebuild research

- [Codex + Adobe AI integration map](docs/adobe-ai-agent-integration-map.md) collects Illustrator MCP, Photoshop MCP, Firefly API, n8n, and Adobe App Builder references.
- [Illustrator vector line rebuild pipeline](docs/illustrator-vector-line-rebuild-pipeline.md) documents the local-first `.ai` line extraction, rebuild SVG, internal-line reduction, and closed-contour workflow.
- [Vector rebuild example scripts](examples/illustrator_bridge/vector_rebuild/README.md) provide local prototype scripts for extracting vector lines and generating closed contours.

StarBridge 是一个 Windows-first、local-first 的 MCP stdio server + tool registry + safety verification layer，用来让 Codex / Cursor / Claude Code 以可验证方式接入本机创意软件。它不替代 ComfyUI、Photoshop、Illustrator、AutoCAD、Blender、剪映 / CapCut 或 GUI Computer Use；它只把已经能测试的本地能力收敛成结构化工具，并把 stable、experimental、planned 和 not implemented 明确分开。

当前仓库状态是 **v0.1-alpha 工程原型**。公开仓库只保存说明、协议、示例脚本、workflow、MCP stdio server、状态 manifest、测试和安全检查；模型、素材、生成图、客户文件、账号、密钥、本机安装路径和真实输出都只留在用户本机。

![StarBridge Creative Console preview](docs/assets/starbridge-console-preview.svg)

**GitHub description 建议：** Codex Computer Use + StarBridge MCP + Safety Verification Layer for local creative software, with GUI inspection, structured tools, redacted checks, and CI validation.

## Current Capability Matrix

| Bridge | Stable | Dry-run only | Experimental | Planned |
| --- | --- | --- | --- | --- |
| ComfyUI | Workflow JSON validation; safe status shape when service is offline. | None for validation. | Local HTTP probe and `txt2img` submit script require a running local ComfyUI and explicit checkpoint. | Full txt2img job lifecycle, img2img, inpaint, upscale, asset manifest. |
| Blender | Environment probe plus fixed-template `blender.scene_plan` dry-run. | Scene plan only; no Blender launch. | No public render/write loop in this release. | Confirmed local render manifest. |
| AutoCAD/DXF | CAD plan validation, plan summary, DXF dry-run, sandbox output guard. AutoCAD/DXF plan validate / dry-run / guarded write. | DXF export defaults to dry-run. | Real test DXF write only with `confirm_write=true`, optional `ezdxf`, and `examples/cad/output`. | Richer CAD entity schema and desktop AutoCAD evidence. |
| Photoshop | Safe status/session metadata shape; Node Proxy + UXP v2 probe, document info, layers list, typed BatchPlay validation. | Sandbox demo plan defaults to dry-run; preview export and confirmed BatchPlay require explicit confirmation. | Real COM document info and sandbox PSD/preview export require authorized local Photoshop; UXP v2 requires local Node Proxy and loaded plugin. | Broader UXP preview export evidence and reviewed local smoke evidence. |
| Illustrator | Safe status/document metadata shape plus `illustrator.preflight` for sanitized summaries. | Sandbox artboard/export plan defaults to dry-run. | Real COM document info and sandbox AI/SVG/PDF/PNG export require authorized local Illustrator and explicit confirmation. | Image trace workflows. |
| Jianying/CapCut | Draft directory probe plus redacted top-level `draft_structure` summary. | None. | Local executable/draft directory availability checks. | Safe draft skeleton and template replacement research. |

Photoshop, Illustrator, Blender, and CapCut write flows are experimental or planned unless a reviewed local run proves otherwise.

## 项目状态：v0.1-alpha

当前真实能力分层：

| 状态 | 当前范围 |
| --- | --- |
| stable | MCP stdio server、tool registry、统一 status/probe、路径脱敏、安全检查、preflight、ComfyUI workflow validate、AutoCAD/DXF plan validate / dry-run / guarded write。 |
| experimental | Photoshop sandbox 写入/导出 demo、Illustrator sandbox trace/export demo、ComfyUI txt2img job lifecycle、桌面软件 COM/UXP 探针。写入类默认必须 dry-run 或显式确认，并限制在 demo/sandbox。 |
| planned | Blender confirmed render、CapCut / 剪映 draft skeleton、跨软件 asset handoff、可审计 E2E release evidence。 |
| not implemented | 自动登录、账号授权绕过、读取客户私有工程、提交模型或生成图、无确认写入真实桌面软件。 |

v0.1-alpha 已有且可以验证：

- MCP stdio server：`python -m starbridge_mcp.mcp_server`
- 工具注册表：`npm.cmd run starbridge:tools:safe`
- 总状态与安全状态：`npm.cmd run bridge:status:safe`
- ComfyUI：offline-safe probe、workflow JSON validate；真实生成任务仍依赖本机 ComfyUI 和显式 checkpoint。
- AutoCAD/DXF：自然语言 / JSON plan、`validate_cad_plan`、dry-run、`confirm_write` 受控写入 `examples/cad/output`、manifest/report。
- Adobe / Blender / CapCut：已有部分 probe/demo/metadata-only 入口；Photoshop 另有 Node Proxy + UXP v2 实验链路，但生产级写入闭环仍是 experimental 或 planned。

## 中文阅读指南

第一次打开仓库时，按这三步走：

| 步骤 | 做什么 | 入口 |
| --- | --- | --- |
| 1 | 了解项目范围和安全边界 | 本页 README |
| 2 | 按目标选择一条软件桥 | [docs/中文用途索引.md](docs/中文用途索引.md) |
| 3 | 检查本机环境是否可用 | `python examples\bridge_status.py` |

最短状态检查：

```powershell
npm.cmd run install:check
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --json --redact-paths --soft-exit
python examples\bridge_status.py --probe-executables
```

首次克隆后的本机 bootstrap：

```powershell
npm.cmd run install:bootstrap:dry-run
npm.cmd run install:bootstrap
```

发布前验证：

```powershell
python scripts\starbridge_preflight.py --markdown
python scripts\starbridge_preflight.py --write-report --soft-exit
npm.cmd test
npm.cmd run preflight
npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
python scripts\security_check.py
python scripts\bridge_capability_matrix.py --check
```

CI 候选检查使用下面这些跨平台命令：

```powershell
python scripts/security_check.py
python scripts/collect_bridge_status.py --json
python examples/bridge_status.py --json --redact-paths --soft-exit
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
```

## Release Readiness

* Visual evidence: [docs/adobe-demo-gallery.md](docs/adobe-demo-gallery.md)
* Local smoke test: [docs/adobe-demo-smoke-test.md](docs/adobe-demo-smoke-test.md)
* Draft release notes: [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md)
* Computer Use architecture: [docs/starbridge.md](docs/starbridge.md)
* GitHub comparison notes: [docs/github-comparison.md](docs/github-comparison.md)
* Advanced project core patterns: [docs/advanced-project-core-patterns.md](docs/advanced-project-core-patterns.md)

**English quick summary:** StarBridge is a Windows-first, local-first MCP stdio server and safety bridge for connecting AI coding agents to creative desktop software: ComfyUI, Blender, AutoCAD / DXF, Photoshop, Illustrator, and CapCut / Jianying. It focuses on safe probes, workflow validation, redacted status reports, and guarded automation examples instead of uploading private assets or replacing the creative tools.

**Search keywords:** MCP, Model Context Protocol, Codex, AI agent, creative software automation, ComfyUI workflow, Blender automation, AutoCAD DXF, Photoshop COM, Illustrator scripting, CapCut Jianying, local-first AI tools.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

Copyright (c) 2025 曹瑞 and contributors.

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
| Photoshop 修图桥 | MCP 工具检查 COM/session 线索；Node Proxy + UXP v2 读取文档和图层；脚本读取文档信息 | 主体选择、抠图、图层处理、PNG 导出、typed BatchPlay confirmed path | 已挂 `photoshop.session_info` 和 `ps.*` v2 工具，写入动作仍需确认 |
| AI 矢量文件桥 | MCP 工具检查 Illustrator COM/session 线索 | Illustrator `.ai`、Image Trace、SVG/PDF/PNG 导出 | 已挂 `illustrator.document_info`，导出脚本未开放 |
| 剪映/CapCut 短视频剪辑桥 | MCP 工具检查可执行文件和草稿目录配置 | 时间线剪辑、模板、字幕、导出 | 已挂 `jianying_capcut.draft_probe`，不读草稿内容 |

一句话原则：**Computer Use 管 GUI 观察和交互复现，StarBridge 管结构化安全边界，MCP 管稳定工具调用，Safety layer 管脱敏验证，专业软件管真实生产，私有资产只留本机。**

## 入口

| 目标 | 先打开 | 然后运行 |
| --- | --- | --- |
| 了解整体方案 | [docs/中文介绍.md](docs/中文介绍.md) | 不需要运行 |
| 一键安装和发布路径 | [docs/install-and-publish.md](docs/install-and-publish.md) | `npm.cmd run install:check` |
| 查看可视化 demo | [docs/visual-demo.md](docs/visual-demo.md) | `npm.cmd run frontend:dev` |
| 查看每个文件用途 | [docs/中文用途索引.md](docs/中文用途索引.md) | 不需要运行 |
| 查看能力边界 | [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) | `python scripts\bridge_capability_matrix.py --check` |
| 检查已接入桥状态 | [examples/bridge_status.py](examples/bridge_status.py) | `python examples\bridge_status.py --json --redact-paths --soft-exit` |
| 接入 ComfyUI | [docs/02-codex-comfyui.md](docs/02-codex-comfyui.md) | `python examples\comfy_bridge\comfy_probe.py` |
| 接入 CAD / AutoCAD | [docs/01-codex-cad.md](docs/01-codex-cad.md) | `python scripts\test_autocad_mcp.py` |
| 接入 Photoshop | [docs/03-codex-photoshop.md](docs/03-codex-photoshop.md) | `powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1` |
| 接入 Illustrator / AI 矢量文件桥 | [docs/05-codex-illustrator.md](docs/05-codex-illustrator.md) | `npm.cmd run illustrator:preflight:plan` |
| 接入 Blender | [docs/04-codex-blender.md](docs/04-codex-blender.md) | `npm.cmd run blender:scene:plan` |
| 研究剪映 / CapCut | [docs/06-codex-jianying.md](docs/06-codex-jianying.md) | `npm.cmd run capcut:draft:structure` |
| 判断 Computer Use 还是 MCP | [docs/computer-use-vs-mcp.md](docs/computer-use-vs-mcp.md) | 不需要运行 |
| 查看 Computer Use 安全用法 | [docs/07-codex-computer-use.md](docs/07-codex-computer-use.md) | `npm.cmd run bridge:status:safe` |

## 仓库区域标注

| 区域 | 目录或文件 | 说明 |
| --- | --- | --- |
| 总览和协议 | `README.md`、`docs/中文介绍.md`、`docs/starbridge-link-protocol.md` | 项目定位、本地软件桥分工和公开边界 |
| 中文索引 | `docs/中文用途索引.md`、`docs/中文标注规范.md` | 标注主要文件用途，统一中文说明方式 |
| 状态检查 | `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop、Illustrator、剪映 / CapCut 本机配置 |
| 图像生成区 | `examples/comfy_bridge/` | ComfyUI API 探针、workflow JSON 和 dry-run 示例 |
| 工程制图区 | `cad-mcp-autocad/`、`examples/cad/`、`scripts/test_autocad_mcp.py` | AutoCAD MCP 子项目、DXF plan 和公开安全制图示例 |
| Photoshop 示例 | `examples/photoshop_bridge/`、`node_proxy/photoshop-bridge/`、`uxp/photoshop-bridge/` | COM 诊断、UXP v2、本机报告和 sandbox demo |
| AI 矢量文件桥 | `docs/05-codex-illustrator.md`、`examples/illustrator_bridge/` | Illustrator / `.ai` 矢量文件接入说明和安全边界 |
| MCP server | `starbridge_mcp/` | stdio server、tool registry、安全层、adapter 和 schema |
| 测试 | `tests/` | 解析器、中文标注、报告生成、安全边界和 MCP tool schema 回归检查 |
| 安全规则 | `.gitignore`、`AGENTS.md`、`SECURITY.md` | 约束哪些内容可以公开，哪些内容只留本机 |

## 本机配置

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

## StarBridge MCP

```powershell
python -m starbridge_mcp.server --json
python -m starbridge_mcp.server tools --json --safe-only
python -m starbridge_mcp.server evidence --init --json
python -m starbridge_mcp.server evidence --validate --json
python -m starbridge_mcp.server job-status --json
python -m starbridge_mcp.mcp_server
npm.cmd run starbridge:mcp
```

MCP 客户端可发现首批安全工具：`starbridge.status`、`starbridge.probe`、`starbridge.tools`、`starbridge.evidence_init`、`starbridge.evidence_validate`、`starbridge.job_status`、`comfyui.system_probe`、`comfyui.workflow_validate`、`blender.environment_probe`、`blender.scene_plan`、`cad_autocad.environment_probe`、`photoshop.session_info`、`ps.probe`、`ps.document.info`、`ps.layers.list`、`ps.batchplay.validate`、`illustrator.document_info`、`illustrator.preflight`、`jianying_capcut.draft_probe`、`jianying_capcut.draft_structure`、`autocad_dxf.status`、`autocad_dxf.validate_cad_plan`、`autocad_dxf.create_dxf_plan`、`autocad_dxf.summarize_plan` 和 `autocad_dxf.write_dxf`。

## Release Readiness

- Visual demo: [docs/visual-demo.md](docs/visual-demo.md)
- Install and publish path: [docs/install-and-publish.md](docs/install-and-publish.md)
- Visual evidence: [docs/adobe-demo-gallery.md](docs/adobe-demo-gallery.md)
- Local smoke test: [docs/adobe-demo-smoke-test.md](docs/adobe-demo-smoke-test.md)
- Draft release notes: [RELEASE_NOTES_DRAFT.md](RELEASE_NOTES_DRAFT.md)
- Capability matrix: [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md)
- Client compatibility: [docs/client-compatibility.md](docs/client-compatibility.md)
- Windows install notes: [docs/windows-install.md](docs/windows-install.md)

## 不发布内容

- 历史网页 demo、虚拟宠物 demo、PPT 工作区和无关临时输出。
- 报告生成临时产物、图片素材、样式参考文档。
- 输出目录、缓存目录、日志和临时文件。
- 模型文件、LoRA、VAE、ControlNet、生成图片、ComfyUI 输出目录。
- 私有 `.blend`、贴图、资产库、渲染缓存或商业模型。
- 客户 DWG、商业图纸、授权文件或真实 CAD 输出。
- PSD / AI 私有工程、商业字体、商业笔刷、购买素材、源图和导出结果。
- 剪映 / CapCut 草稿、缓存、导出视频、字幕原稿、账号和会员信息。
- 密码、token、Cookie、OAuth 缓存、浏览器资料和支付信息。

## 下一步

| 优先级 | 任务 |
| --- | --- |
| 高 | 收敛 README 和 docs 的状态词汇，避免 roadmap 能力被误读为已发布能力 |
| 高 | 为 ComfyUI template list/get/from-template 增加更短的本地验证入口 |
| 高 | 继续保持 MCP tools 的 safe-only registry、路径脱敏和 forbidden content 扫描 |
| 中 | 把 Photoshop 的 `extract_subject`、`export_png`、`document_info` 继续收敛成安全 MCP 工具 |
| 中 | 给 Illustrator 增加 `trace_image_to_vector` 参数化示例 |
| 中 | 给 Blender 增加确认后的本机 render manifest |
| 中 | 给剪映 / CapCut 增加公开安全测试草稿 skeleton，不读取私有草稿内容 |

完整路线图见 [ROADMAP.md](ROADMAP.md)。

## For English Readers

StarBridge is a Windows-first, local-first MCP stdio server and safety bridge for connecting AI coding agents to creative desktop software: ComfyUI, Blender, AutoCAD / DXF, Photoshop, Illustrator, and CapCut / Jianying. It focuses on safe probes, workflow validation, redacted status reports, and guarded automation examples instead of uploading private assets or replacing the creative tools.

Start with this README and [docs/local-mcp-setup.md](docs/local-mcp-setup.md). Most project notes are Chinese-first because the current workstation and software setup are Windows-first, but commands, tool names, environment variables, and MCP APIs are kept in English.

**Search keywords:** MCP, Model Context Protocol, Codex, AI agent, creative software automation, ComfyUI workflow, Blender automation, AutoCAD DXF, Photoshop COM, Illustrator scripting, CapCut Jianying, local-first AI tools.
