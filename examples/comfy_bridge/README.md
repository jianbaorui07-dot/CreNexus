# ComfyUI 图像生成桥示例

这个目录保存 Codex 连接本机 ComfyUI 的公开安全示例。所有说明都按中文使用场景组织：先看区域用途，再看运行命令，最后看安全边界。

## 区域一：这个目录做什么

- 检查本机 ComfyUI 是否在线，默认地址是 `http://127.0.0.1:8188`。
- 只读检查 `/system_stats`、`/object_info` 和基础节点信息。
- 通过 ComfyUI HTTP API 提交基础文生图 workflow。
- 同时保留 API workflow 和可视化 workflow，方便人打开节点图检查。

## 区域二：这个目录不放什么

- 不放账号、密码、验证码、Cookie、token、OAuth 缓存。
- 不放模型、LoRA、VAE、ControlNet、checkpoint 文件。
- 不放生成图片、客户素材、浏览器资料、付费 API key。
- 不写死本机路径，所有路径都通过环境变量或命令行参数传入。

## 区域三：文件中文标注

| 文件 | 中文用途 |
| --- | --- |
| `bridge_status.json` | 这条桥的统一公开状态：成熟度、依赖、风险和后续步骤 |
| `bridge.json` | 旧版兼容 manifest：入口、支持任务和安全说明 |
| `probe.py` | ComfyUI 只读探针：检查服务、`/system_stats`、`/object_info` 和基础节点 |
| `comfy_probe.py` | 兼容入口：调用 `probe.py` |
| `sample_report.example.json` | 可提交的安全 report 样例 |
| `run_txt2img.py` | 文生图提交脚本：把 prompt 提交给本机 ComfyUI |
| `validate_workflow.py` | 只读 workflow 校验：检查 API format、节点和连线引用 |
| `workflow_templates.py` | 公开 workflow template 快捷入口：list/get/from-template，只生成 JSON，不提交队列 |
| `workflow_lifecycle.py` | 脱敏 job / asset 生命周期摘要：只返回节点统计、资产角色和确认门 |
| `workflow_visualize.py` | 把内联 API workflow 转成 Mermaid 和脱敏节点/连线摘要，不读取 prompt 或模型名 |
| `workflows/txt2img_basic_api.json` | API 工作流：给脚本提交到 `/prompt` 使用 |
| `workflows/txt2img_basic_visual.json` | 可视化工作流：给人在 ComfyUI 画布中打开检查 |

## 区域四：运行前准备

先手动启动 ComfyUI，并确认浏览器能打开：

```text
http://127.0.0.1:8188
```

如果你的 ComfyUI 不在默认地址，优先设置环境变量：

```powershell
$env:STARBRIDGE_COMFYUI_URL="http://127.0.0.1:8188"
```

可选：配置本机启动脚本和输出目录：

```powershell
$env:COMFY_LAUNCHER="<path-to-Start_ComfyUI.cmd>"
$env:COMFY_OUTPUT_DIR="<path-to-ComfyUI-output>"
```

## 区域五：状态检查命令

普通中文报告：

```powershell
python examples/comfy_bridge/probe.py
```

机器可读 JSON：

```powershell
python examples/comfy_bridge/probe.py --json
```

只读校验 workflow，不提交生成任务：

```powershell
python examples/comfy_bridge/validate_workflow.py --json
npm.cmd run comfy:workflow:validate
npm.cmd run comfy:templates:list
npm.cmd run comfy:templates:get
npm.cmd run comfy:templates:from
npm.cmd run comfy:lifecycle:template
```

直接调用模板入口：

```powershell
python examples/comfy_bridge/workflow_templates.py list --json
python examples/comfy_bridge/workflow_templates.py get --template-id txt2img_basic_v1 --json
python examples/comfy_bridge/workflow_templates.py from-template --template-id txt2img_basic_v1 --json
python examples/comfy_bridge/workflow_lifecycle.py --template-id txt2img_basic_v1 --json
```

这些命令只读取仓库内公开模板 registry，生成 placeholder workflow、校验报告和脱敏 lifecycle 摘要；不会访问网络、扫描模型目录、读取私有图片或提交 `/prompt`。

probe report 默认写入：

```text
examples/comfy_bridge/reports/comfyui_probe_report.json
```

`reports/` 已被 `.gitignore` 忽略，不进入 GitHub。

## 区域六：文生图命令

必须显式指定 checkpoint：

```powershell
python examples/comfy_bridge/run_txt2img.py --prompt "一间安静的未来茶室，花园里有柔和灯光" --ckpt "<checkpoint-name>"
```

如果只是本机快速试验，并且你明确接受使用 ComfyUI 返回的第一个 checkpoint，可以显式加：

```powershell
python examples/comfy_bridge/run_txt2img.py --prompt "一间安静的未来茶室" --allow-first-checkpoint
```

指定尺寸、步数、采样器和输出前缀：

```powershell
python examples/comfy_bridge/run_txt2img.py --prompt "中式庭院里的机械花灯" --ckpt "<checkpoint-name>" --width 768 --height 768 --steps 20 --sampler euler --scheduler normal --prefix "codex_demo"
```

## 区域七：命令行参数中文说明

| 参数 | 中文说明 |
| --- | --- |
| `--prompt` | 正向提示词，必填 |
| `--negative` | 反向提示词，默认过滤低质量、模糊、文字水印 |
| `--ckpt` | 指定 checkpoint 名称；建议必传 |
| `--allow-first-checkpoint` | 显式允许使用 ComfyUI 返回的第一个 checkpoint |
| `--width` / `--height` | 输出图宽高 |
| `--steps` | 采样步数 |
| `--cfg` | 提示词引导强度 |
| `--sampler` | KSampler 的 sampler_name |
| `--scheduler` | KSampler 的 scheduler |
| `--seed` | 随机种子；不传时自动生成 |
| `--prefix` | 保存文件前缀 |
| `--timeout` | 等待 ComfyUI 任务完成的最长时间 |
| `--request-timeout` | 单次 HTTP 请求超时时间 |

## 区域八：环境变量中文说明

| 环境变量 | 中文说明 |
| --- | --- |
| `STARBRIDGE_COMFYUI_URL` | ComfyUI API 地址，默认 `http://127.0.0.1:8188` |
| `COMFY_BASE_URL` | 兼容旧配置的 ComfyUI API 地址 |
| `COMFY_OUTPUT_DIR` | ComfyUI 输出目录，用来打印最终图片路径 |
| `COMFY_ROOT` 或 `COMFYUI_PATH` | 本机 ComfyUI 根目录，供总状态检查显示 |
| `COMFY_LAUNCHER` 或 `COMFY_START_SCRIPT` | 本机 ComfyUI 启动脚本路径 |
| `STARBRIDGE_DOWNLOAD_INBOX` | 下载收件箱，放源码包、安装包和调研资料 |

## 区域九：安全边界

新下载的源码项目、安装包和调研资料应放在本机下载收件箱，不放进 Git 仓库。模型、生成图片、浏览器资料、token、私有素材和客户文件都只留本机。
