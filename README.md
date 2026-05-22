# Codex 软件接入实验仓库

这个仓库用来整理 **Codex 接入本地创作软件** 的方法。目标很简单：让 Codex 写脚本、跑检查、调用本机软件；让 ComfyUI、Blender、CAD、Photoshop 继续负责图像、三维、制图和修图。

公开仓库只放说明、协议、示例脚本和安全检查。不放个人路径、账号、模型、素材、生成图、客户图纸、授权信息和本机缓存。

## 项目总目录

| 编号 | 项目 | 先看这个 | 当前状态 |
| --- | --- | --- | --- |
| 1 | Codex 接入 CAD | `docs/01-codex-cad.md` | 已有 AutoCAD MCP 子项目和绘图脚本 |
| 2 | Codex 接入 ComfyUI | `docs/02-codex-comfyui.md` | 已有 API 探针和文生图 workflow 示例 |
| 3 | Codex 接入 Photoshop | `docs/03-codex-photoshop.md` | 已有 COM 探针和主体抠图实验脚本 |
| 4 | Codex 接入 Blender | `docs/04-codex-blender.md` | 已有状态检查入口，待补生成脚本 |

## 怎么读这个仓库

1. 先看本页，了解仓库范围。
2. 再看 `docs/starbridge-link-protocol.md`，了解总协议。
3. 按需要打开上面的 4 个单项中文介绍。
4. 真要运行时，再看 `examples/` 和对应脚本。

## 主要文件

| 路径 | 用途 |
| --- | --- |
| `docs/starbridge-link-protocol.md` | 总协议：四条本地软件桥怎么组织 |
| `docs/codex-drawing-tool-integrations.md` | 绘画、图像、设计、三维、制图工具路线图 |
| `docs/中文用途索引.md` | 全仓库中文索引 |
| `examples/bridge_status.py` | 检查 ComfyUI / Blender / CAD / Photoshop 状态 |
| `examples/comfy_bridge/` | ComfyUI API 示例 |
| `examples/photoshop_bridge/` | Photoshop COM 和抠图实验示例 |
| `cad-mcp-autocad/` | AutoCAD MCP 子项目 |
| `scripts/` | CAD 自动绘图示例 |

## 快速检查

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --probe-executables
```

也可以用 npm：

```powershell
npm.cmd run bridge:status:json
```

## 本机路径怎么处理

不要把真实路径写进 GitHub。每台电脑用环境变量或本地 `.env` 管理：

| 软件 | 环境变量 |
| --- | --- |
| ComfyUI 启动脚本 | `COMFY_LAUNCHER` 或 `COMFY_START_SCRIPT` |
| ComfyUI 根目录 | `COMFY_ROOT` 或 `COMFYUI_PATH` |
| ComfyUI 输出目录 | `COMFY_OUTPUT_DIR` |
| Blender 可执行文件 | `BLENDER_EXE` |
| Blender MCP 目录 | `BLENDER_MCP_DIR` |
| AutoCAD 可执行文件 | `AUTOCAD_EXE` |
| Photoshop 可执行文件 | `PHOTOSHOP_EXE` |
| 下载收件箱 | `STARBRIDGE_DOWNLOAD_INBOX` |

## 四个接入方向

### CAD

```powershell
python scripts\test_autocad_mcp.py
```

用于验证 AutoCAD MCP。生成的 DWG 只留本机，不提交。

### ComfyUI

```powershell
python examples\comfy_bridge\comfy_probe.py
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden"
```

用于读取本地 ComfyUI 状态并提交基础文生图任务。

### Photoshop

先手动打开已授权的 Photoshop，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\com_probe.ps1 -OutputPath "$env:TEMP\codex_photoshop_probe.png"
```

主体抠图实验：

```powershell
powershell -ExecutionPolicy Bypass -File examples\photoshop_bridge\scripts\extract_subject_to_png.ps1 -InputPath "<source-image>" -OutputPath "$env:TEMP\subject.png"
```

### Blender

先在本机配置 `BLENDER_EXE`，然后运行：

```powershell
python examples\bridge_status.py --probe-executables
```

## 不发布内容

以下内容只留本机：

- 账号、密码、验证码、Cookie、token、OAuth 缓存。
- ComfyUI 模型、LoRA、VAE、ControlNet、生成图片。
- Blender 私有 `.blend`、贴图、资产库、渲染缓存。
- CAD 客户图纸、商业 DWG、授权文件。
- Photoshop 安装路径、Creative Cloud 缓存、PSD、商业字体、笔刷、购买素材、源图和导出结果。
- `output/`、`scratch/`、临时文件、日志和缓存。

## 下一步

- 给 Blender 增加公开安全的基础场景生成脚本。
- 给 ComfyUI 增加 `img2img`、inpaint、upscale 示例。
- 给 CAD 增加更清楚的 JSON 参数格式。
- 给 Photoshop 增加 UXP 面板和本地 MCP 工具封装。
