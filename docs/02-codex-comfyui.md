# 2. Codex 接入 ComfyUI

这份文档说明 Codex 如何接入 ComfyUI。用户口中的 “comful / comfy” 在本仓库统一写作 **ComfyUI**。公开仓库只保存 workflow 示例和 API 调用脚本，不保存模型、LoRA、VAE、ControlNet、生成图或本机路径。

## 接入目标

- 让 Codex 通过 `http://127.0.0.1:8188` 调用本地 ComfyUI。
- 读取系统状态、显卡信息、checkpoint 列表和队列状态。
- 提交 workflow JSON，完成文生图、图生图、修复、放大等任务。
- 后续封装成 MCP 工具，让 Codex 可以稳定调用本地图像生成能力。

## 当前入口

| 文件或目录 | 用途 |
| --- | --- |
| `examples/comfy_bridge/README.md` | ComfyUI 桥接说明 |
| `examples/comfy_bridge/comfy_probe.py` | 只读探针，读取状态和 checkpoint |
| `examples/comfy_bridge/run_txt2img.py` | 基础文生图提交脚本 |
| `examples/comfy_bridge/workflows/txt2img_basic_api.json` | API workflow |
| `examples/comfy_bridge/workflows/txt2img_basic_visual.json` | 可视化 workflow |

## 本地配置

用环境变量记录本机路径，不写进 Git：

```powershell
$env:COMFY_BASE_URL="http://127.0.0.1:8188"
$env:COMFY_ROOT="<path-to-ComfyUI>"
$env:COMFY_LAUNCHER="<path-to-launcher.cmd>"
$env:COMFY_OUTPUT_DIR="<path-to-ComfyUI-output>"
```

## 验证命令

先手动启动 ComfyUI，然后运行：

```powershell
python examples\comfy_bridge\comfy_probe.py
python examples\bridge_status.py --json
```

提交一个基础文生图任务：

```powershell
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden"
```

## 安全边界

- 不提交模型文件、LoRA、VAE、ControlNet、checkpoint、生成输出。
- 不提交浏览器资料、token、账号、付费 API key。
- workflow 示例必须能公开复现，不依赖私有模型路径。
- 输出路径由本机环境变量控制，不写入公开仓库。

## 后续优化

- 增加 `img2img`、inpaint、upscale、批量 prompt 示例。
- 增加 workflow 校验，避免节点缺失时直接提交失败。
- 增加输出结果索引 JSON，但只保存本机路径，不提交图片。
- 评估轻量 MCP 封装，而不是一开始引入过重第三方包。
