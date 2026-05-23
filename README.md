# Codex 本地创作软件接入实验仓库

这个仓库整理 **Codex 接入本机创作软件** 的公开方案。它不替代 ComfyUI、Blender、CAD 或 Photoshop和illustrate而是让 Codex 负责写脚本、跑检查、调用本地接口、记录流程；让专业软件继续负责图像生成、三维场景、工程制图和修图抠图。

公开仓库只保存说明、协议、示例脚本、workflow 和安全检查。不保存个人路径、账号、模型、素材、生成图、客户图纸、授权信息或本机缓存。

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
python examples\bridge_status.py --probe-executables
```

也可以通过 npm 快捷命令运行：

```powershell
npm.cmd run bridge:status:json
```

如果 PowerShell 拦截 `npm.ps1`，优先使用 `npm.cmd`。

## 这个仓库解决什么

它把本地创作工作站拆成四条清楚的软件桥：

| 软件桥 | Codex 负责 | 本地软件负责 | 当前状态 |
| --- | --- | --- | --- |
| ComfyUI 图像生成桥 | 调用 API、提交 workflow、记录输出路径 | 文生图、图生图、修复、放大 | 已有探针和文生图示例 |
| Blender 三维场景桥 | 生成脚本、组织场景参数、沉淀流程 | 建模、材质、灯光、相机、渲染 | 已有接入说明，待补公开安全脚本 |
| CAD 工程制图桥 | 解析规格、生成绘图脚本、调用 MCP/COM | 精确线条、孔位、尺寸、图层、DWG | 已有 AutoCAD MCP 子项目和绘图脚本 |
| Photoshop 修图桥 | 调用 COM/脚本、读取文档、导出结果 | 主体选择、抠图、图层处理、PNG 导出 | 已有诊断、探针和主体抠图实验 |

一句话原则：**Codex 连接和自动化，专业软件生成和处理，私有资产只留本机。**

## 按目标选择入口

| 目标 | 先打开 | 然后运行 |
| --- | --- | --- |
| 了解整体方案 | [docs/中文介绍.md](docs/中文介绍.md) | 不需要运行 |
| 查每个文件用途 | [docs/中文用途索引.md](docs/中文用途索引.md) | 不需要运行 |
| 检查四条桥状态 | [examples/bridge_status.py](examples/bridge_status.py) | `python examples\bridge_status.py` |
| 接入 ComfyUI | [docs/02-codex-comfyui.md](docs/02-codex-comfyui.md) | `python examples\comfy_bridge\comfy_probe.py` |
| 接入 CAD / AutoCAD | [docs/01-codex-cad.md](docs/01-codex-cad.md) | `python scripts\test_autocad_mcp.py` |
| 接入 Photoshop | [docs/03-codex-photoshop.md](docs/03-codex-photoshop.md) | `powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\diagnose_local.ps1` |
| 接入 Blender | [docs/04-codex-blender.md](docs/04-codex-blender.md) | `python examples\bridge_status.py --probe-executables` |
| 查看 Photoshop 详细桥方案 | [docs/photoshop-codex-bridge.md](docs/photoshop-codex-bridge.md) | 按文档选择诊断或实操命令 |
| 查看扩展路线 | [docs/codex-drawing-tool-integrations.md](docs/codex-drawing-tool-integrations.md) | 不需要运行 |

## 仓库区域标注

| 区域 | 目录或文件 | 说明 |
| --- | --- | --- |
| 总览和协议 | `README.md`、`docs/中文介绍.md`、`docs/starbridge-link-protocol.md` | 说明项目定位、四条桥分工和公开边界 |
| 中文索引 | `docs/中文用途索引.md`、`docs/中文标注规范.md` | 标注每个主要文件用途，统一中文说明方式 |
| 状态检查 | `examples/bridge_status.py` | 一次检查 ComfyUI、Blender、CAD、Photoshop 本机配置 |
| 图像生成区 | `examples/comfy_bridge/` | API 探针、文生图脚本和 workflow JSON |
| 工程制图区 | `cad-mcp-autocad/`、`scripts/` | AutoCAD MCP 子项目和自动绘图脚本 |
| Photoshop 示例 | `examples/photoshop_bridge/` | COM 诊断、测试文档、主体抠图和本机报告 |
| 测试 | `tests/` | 对解析器、中文标注和报告生成做回归检查 |
| 安全规则 | `.gitignore`、`AGENTS.md` | 约束哪些内容可以公开，哪些内容只留本机 |

## 运行前配置

真实安装路径不要写进 GitHub。每台电脑用环境变量或本地 `.env` 管理：

| 软件或目录 | 环境变量 |
| --- | --- |
| ComfyUI 启动脚本 | `COMFY_LAUNCHER` 或 `COMFY_START_SCRIPT` |
| ComfyUI 根目录 | `COMFY_ROOT` 或 `COMFYUI_PATH` |
| ComfyUI 输出目录 | `COMFY_OUTPUT_DIR` |
| Blender 可执行文件 | `BLENDER_EXE` |
| Blender MCP 目录 | `BLENDER_MCP_DIR` |
| AutoCAD 可执行文件 | `AUTOCAD_EXE` |
| Photoshop 可执行文件 | `PHOTOSHOP_EXE` |
| 下载收件箱 | `STARBRIDGE_DOWNLOAD_INBOX` |

本地输出、报告、图片、DWG、PSD、缓存和日志应放在 `output/`、`scratch/` 或其他本机私有目录，并保持在 Git 提交之外。

## 常用命令

### 检查四条桥

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
```

### ComfyUI

```powershell
python examples\comfy_bridge\comfy_probe.py
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden"
```

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
```

或直接运行：

```powershell
python -m unittest discover -s tests
```

## 不发布内容

以下内容只留本机，不进入 GitHub：

- 账号、密码、验证码、Cookie、token、OAuth 缓存、浏览器资料和支付信息。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成图片和输出目录。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存和本机插件缓存。
- CAD 客户图纸、商业 DWG、授权文件和真实项目输出。
- Photoshop 安装路径、Creative Cloud 缓存、PSD、商业字体、笔刷、购买素材、源图和导出结果。
- `output/`、`scratch/`、临时文件、日志、报告产物和本机缓存。

## 下一步

| 优先级 | 任务 |
| --- | --- |
| 高 | 给 Blender 增加公开安全的基础场景生成脚本 |
| 高 | 给 ComfyUI 增加 `img2img`、inpaint、upscale 和 workflow 校验示例 |
| 高 | 给 CAD 增加更清楚的 JSON 参数格式和标准零件示例 |
| 中 | 把 Photoshop 的 `extract_subject`、`export_png`、`document_info` 封装成本机 MCP 工具 |
| 中 | 为 Penpot/Figma、Krita 建立接入评估表，先记录许可、依赖、账号要求和安全边界 |

## 协作原则

1. 公开仓库只放可复用、可审查、可安全分享的内容。
2. 本机软件、账号授权、商业素材和客户资产由用户手动管理。
3. 示例脚本要能单独运行，失败时给出清楚的中文提示。
4. 新增能力先补文档和状态检查，再扩展自动化脚本。
