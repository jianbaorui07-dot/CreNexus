# StarBridge：Codex 本地创意软件 MCP 桥接框架

StarBridge 是一个面向 Codex、Cursor、Claude Code 等 AI 编程助手的本地创意软件桥接框架。它的目标不是保存素材或项目成品，而是把 ComfyUI、Blender、AutoCAD/CAD、Photoshop、Illustrator、剪映/CapCut 等本机软件的状态检查、参数化动作和未来 MCP tools 统一到一个安全、可扩展的入口。

当前仓库仍处在 MVP 阶段：已经有统一 status/probe 入口、真正 MCP stdio server、若干软件的本机探针和公开安全示例；还没有把所有软件动作都封装成稳定写入工具。

## 三分钟验证

这些命令不需要打开客户文件，也不会写真实项目输出：

```powershell
npm.cmd run starbridge:status
npm.cmd run starbridge:tools:safe
npm.cmd run cad:dxf:dry-run
npm.cmd run comfy:workflow:validate
npm.cmd test
```

如果机器没有配置 ComfyUI、AutoCAD、Adobe 或 Blender，普通状态检查仍会输出结构化 JSON；只有显式运行 strict 模式才把未配置的本机软件视为失败：

```powershell
npm.cmd run starbridge:status:strict
```

## 中文阅读指南

- 想先看整体方向：读本 README 和 `docs/starbridge-link-protocol.md`。
- 想按软件查入口：读 `docs/01-codex-cad.md`、`docs/02-codex-comfyui.md`、`docs/03-codex-photoshop.md`、`docs/04-codex-blender.md`、`docs/05-codex-illustrator.md`、`docs/06-codex-jianying.md`。
- 想查中文标注规则：读 `docs/中文用途索引.md` 和 `docs/中文标注规范.md`。
- 想接 MCP 客户端：读 `docs/local-mcp-setup.md`。

## 仓库区域标注

| 中文区域 | 对应目录 | 说明 |
| --- | --- | --- |
| 图像生成区 | `examples/comfy_bridge/` | ComfyUI 探针、workflow 和 txt2img API 示例 |
| 工程制图区 | `cad-mcp-autocad/`、`scripts/` | AutoCAD MCP、CAD JSON、DXF 和公开安全绘图示例 |
| 修图自动化区 | `examples/photoshop_bridge/` | Photoshop COM/PowerShell 诊断和参数化实验 |
| 三维场景区 | `examples/blender_bridge/` | Blender manifest、环境探针和后续 MCP 入口 |
| AI 矢量文件桥 | `examples/illustrator_bridge/`、`docs/05-codex-illustrator.md` | Adobe Illustrator `.ai` 矢量文件探针和路线 |
| 剪映/CapCut 草稿桥 | `examples/capcut_jianying_bridge/` | 剪映可执行文件、CapCut 可执行文件和草稿目录探针 |

## 当前能力矩阵

| 软件方向 | 当前状态 | 已有可运行能力 | 主要缺口 |
| --- | --- | --- | --- |
| ComfyUI | `experimental` | `examples/comfy_bridge/probe.py`、`run_txt2img.py`、workflow 示例、总状态检查 | img2img/inpaint/upscale、统一 MCP tool、输出资产索引 |
| Photoshop | `experimental` | PowerShell 诊断、COM 探针、当前文档信息、主体抠图实验、参数化输入输出 | 稳定 tool registry、动作权限边界、失败恢复 |
| AutoCAD / CAD | `experimental` | `cad-mcp-autocad/` 子项目、`scripts/test_autocad_mcp.py`、根目录 CAD JSON -> DXF MVP、统一探针 | 把 CAD MVP 和 MCP 子项目合并成统一 adapter，区分离线 DXF 与真实 COM 控制 |
| Blender | `planned` | manifest、环境探针、总状态检查 | 公开安全的场景生成、渲染探针、Blender MCP addon 接入 |
| Illustrator | `planned` | manifest、PowerShell COM 探针、总状态检查 | 当前文档只读信息、测试画板、SVG/PDF/PNG 导出 |
| 剪映 / CapCut | `research` | manifest、草稿目录/可执行文件环境探针、路线文档 | 草稿结构只读摘要、最小安全测试草稿、MCP/CLI 选择 |

## 最小使用方式

检查全部本地桥状态：

```powershell
python -m starbridge_mcp.server --json
npm.cmd run starbridge:status
```

只检查某一个桥：

```powershell
python -m starbridge_mcp.server --bridge comfyui --json
python -m starbridge_mcp.server --bridge photoshop --json
python -m starbridge_mcp.server --bridge cad_autocad --json
python -m starbridge_mcp.server --bridge autocad_dxf --json
```

继续兼容旧入口：

```powershell
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
npm.cmd test
```

Windows 本机初始化检查：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_starbridge.ps1
```

查看当前规划/已实现的工具能力清单：

```powershell
python -m starbridge_mcp.server tools --json
python -m starbridge_mcp.server tools --json --safe-only
```

启动真正 MCP stdio server：

```powershell
python -m starbridge_mcp.mcp_server
npm.cmd run starbridge:mcp
```

MCP 客户端可发现这些首批工具：

- `starbridge.status`
- `starbridge.probe`
- `starbridge.tools`
- `comfyui.workflow_validate`
- `autocad_dxf.status`
- `autocad_dxf.validate_cad_plan`
- `autocad_dxf.create_dxf_plan`
- `autocad_dxf.summarize_plan`
- `autocad_dxf.write_dxf`

## 统一返回格式

StarBridge 新入口统一返回：

```json
{
  "ok": false,
  "bridge": "photoshop",
  "action": "status",
  "message": "Photoshop 修图桥: warn",
  "details": {},
  "warnings": [],
  "next_steps": []
}
```

字段固定为 `ok`、`bridge`、`action`、`message`、`details`、`warnings`、`next_steps`，便于后续 MCP 客户端稳定解析。

## 仓库结构

| 路径 | 用途 |
| --- | --- |
| `starbridge_mcp/` | StarBridge 最小统一框架，包含 config、security、result schema 和状态入口 |
| `examples/` | 各软件桥的公开安全探针、manifest 和 ComfyUI/Photoshop 示例 |
| `cad-mcp-autocad/` | AutoCAD MCP 子项目 |
| `scripts/` | 本地检查、CAD/AutoCAD 自动化相关脚本 |
| `docs/` | 中文说明、协议、调研、MCP 接入文档 |
| `tests/` | schema、探针、隐私边界和脚本测试 |
| `third_party_research/` | 本机第三方项目研究目录，已加入 `.gitignore`，不提交 |

## 安全边界

- 不提交真实用户路径、安装路径、账号、token、Cookie、OAuth 缓存。
- 不提交模型、LoRA、VAE、ControlNet、生成图片。
- 不提交 PSD、AI、DWG、DXF、剪映/CapCut 草稿、导出视频、客户素材。
- Photoshop、Illustrator 示例必须通过参数传入输入/输出路径。
- 状态入口会脱敏用户目录、敏感文件扩展名、草稿文件名和密钥字段。
- 需要登录、授权、订阅、验证码或 OAuth 时，用户手动处理。

## 第三方项目借鉴

本轮对同类 GitHub 项目做了只读对比，重点看 Quick Start、MCP 客户端配置、工具清单、workflow 校验、离线 fallback、输出/资产边界和安全确认策略。详细对比见：

- [docs/advanced-project-comparison.md](docs/advanced-project-comparison.md)
- [docs/local-mcp-setup.md](docs/local-mcp-setup.md)

优先借鉴方向：

- P0：Photoshop Windows COM、Illustrator JSX runner、AutoCAD headless DXF fallback、ComfyUI Python workflow/status 分层。
- P1：Blender addon + MCP server 分离、多 CAD adapter、ComfyUI job/asset lifecycle、剪映草稿 CLI 思路。
- P2：工具过宽、安装复杂、许可证不一致或含云账号/API key 的项目只做参考。

本次已补齐的短板：

- 增加 `starbridge.tools` 能力清单，先把安全只读、受保护写入、需要本机软件的动作分层。
- 增加 ComfyUI workflow 只读校验，先区分 API workflow 和 visual workflow，再提交生成任务。
- 增加 npm 快捷命令，减少新用户第一次验证需要记住的 Python 路径。
- 收紧公开发布范围，避免把本机前端 demo、根目录旧 CAD 实验、Vite 依赖和 package-lock 混入 GitHub。

仍然明确保留的缺口：

- 当前 MCP stdio server 只暴露安全 MVP 工具，还没有把 Photoshop、Illustrator、Blender、剪映/CapCut 的写入类动作做成稳定 tool。
- ComfyUI 尚未做 job/asset lifecycle；生成图片路径仍只应留在本机。
- Photoshop、Illustrator、AutoCAD 写入类动作仍需要参数化路径、输出目录限制和用户确认。

## 路线图

1. 保持 `starbridge_mcp.server` 的统一 status/probe 稳定。
2. 把旧 `examples/bridge_status.py` 逐步迁移到 StarBridge core，但保留兼容入口。
3. 扩展 MCP stdio server：优先补 `photoshop.document_info`、`illustrator.document_info`、`blender.scene_probe` 的只读实现。
4. 补 ComfyUI job/asset lifecycle，但输出路径和生成图片继续只留本机。
5. 再封装写入动作，并为每个动作增加输入路径、输出路径、素材类型和隐私检查。

## 验证

本轮验证结果记录在 [docs/optimization-report.md](docs/optimization-report.md)。本地建议先运行：

```powershell
python -m unittest discover -s tests
python examples\bridge_status.py --json
npm.cmd test
```
