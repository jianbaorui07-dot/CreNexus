# 2. Codex 接入 ComfyUI

这份文档说明 ComfyUI 桥的真实状态。当前仓库已有只读探针和基础 txt2img API 示例，状态是 `experimental`，不是完整图像生成平台封装。公开仓库只保存 workflow 示例和 API 调用脚本，不保存模型、LoRA、VAE、ControlNet、生成图或本机路径。

## 当前可运行

| 能力 | 入口 | 说明 |
| --- | --- | --- |
| 只读探针 | `examples/comfy_bridge/comfy_probe.py` | 读取本机 ComfyUI 状态、设备和 checkpoint 信息 |
| 总状态探测 | `examples/bridge_status.py` | 作为所有软件桥的一部分检查 ComfyUI |
| txt2img 示例 | `examples/comfy_bridge/run_txt2img.py` | 提交基础文生图 workflow，成功和失败都输出标准 JSON |
| workflow 示例 | `examples/comfy_bridge/workflows/txt2img_basic_api.json` | API 格式 workflow |

`run_txt2img.py` 已做离线 workflow 节点存在性检查、节点 `class_type` 检查、checkpoint 检查和 CLI 参数化。脚本不会默认选择第一个 checkpoint；必须传 `--ckpt`，或显式加 `--allow-first-checkpoint`。

## 需要本机安装什么

- Python 3.10+。
- 本机 ComfyUI server，默认 API 地址 `http://127.0.0.1:8188`。
- 至少一个可用 checkpoint。
- 如果要查看输出路径，需要本机配置或确认 ComfyUI 输出目录。

建议环境变量：

```powershell
$env:STARBRIDGE_COMFYUI_URL="http://127.0.0.1:8188"
$env:COMFY_ROOT="<path-to-ComfyUI>"
$env:COMFY_LAUNCHER="<path-to-launcher.cmd>"
$env:COMFY_OUTPUT_DIR="<path-to-ComfyUI-output>"
```

## 验证命令

```powershell
npm.cmd run comfy:probe
npm.cmd run status:probe:json
```

直接运行：

```powershell
python examples\comfy_bridge\comfy_probe.py
python examples\comfy_bridge\comfy_probe.py --json
python examples\bridge_status.py --json
```

提交一个基础文生图任务：

```powershell
npm.cmd run comfy:txt2img -- --prompt "a quiet futuristic tea house in a garden" --ckpt "<checkpoint-name>"
```

或直接运行：

```powershell
python examples\comfy_bridge\run_txt2img.py --prompt "a quiet futuristic tea house in a garden" --ckpt "<checkpoint-name>"
```

常用参数：

```powershell
python examples\comfy_bridge\run_txt2img.py `
  --prompt "clean product render on white background" `
  --negative "low quality, blurry, watermark" `
  --ckpt "<checkpoint-name>" `
  --seed 123456 `
  --steps 20 `
  --cfg 7 `
  --sampler euler `
  --scheduler normal `
  --width 512 `
  --height 512
```

失败时会输出类似：

```json
{
  "ok": false,
  "bridge": "comfyui",
  "error": "missing_checkpoint",
  "message": "No checkpoint was specified.",
  "suggestion": "Pass --ckpt with an exact checkpoint name, or add --allow-first-checkpoint to opt in to the first available checkpoint."
}
```

成功时会输出 `prompt_id`、workflow、checkpoint、seed、steps、sampler、scheduler、width、height 和输出路径列表。

## 不能做什么

- 不能提交模型、checkpoint、LoRA、VAE、ControlNet 或生成图片。
- 不能把本机 ComfyUI 根目录、输出目录或模型路径写进仓库。
- 当前没有公开 `img2img`、inpaint、upscale 示例。
- 当前 workflow 校验只覆盖 bundled txt2img 节点映射，不是通用 ComfyUI 图校验器。

## 下一步

1. 增加 `img2img`、inpaint、upscale 的公开安全 workflow。
2. 扩展 workflow 校验，覆盖输入引用、节点类型和常见错误。
3. 把 ComfyUI 队列错误和历史记录错误转成统一 JSON。
4. 增加输出结果索引 JSON，但只保存本机路径，不提交图片。
5. 评估轻量 MCP 封装，先从稳定的 txt2img 开始。
