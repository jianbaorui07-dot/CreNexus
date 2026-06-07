# v0.1.0-alpha 发布候选说明

`v0.1.0-alpha` 是一个 Windows-first / local-first 的安全桥接候选版。它的目标是让 Codex / Cursor / Claude Code 等 AI coding agents 通过 MCP stdio 发现和调用本机创意软件相关的安全探针、workflow 校验、DXF dry-run plan 和受保护 sandbox demo。它不是破解工具，不绕过授权，不上传私有资产，不替代 Photoshop、Illustrator、AutoCAD、ComfyUI、Blender 或 CapCut。

## What is included

- MCP stdio server：支持 `initialize`、`tools/list`、`tools/call`，返回结构化 JSON。
- Tool registry：区分 stable、experimental、planned，并暴露 risk metadata。
- `starbridge.status`：统一状态检查，read-only，CI safe。
- `comfyui.workflow_validate`：离线校验公开 ComfyUI workflow JSON，read-only，CI safe。
- AutoCAD / DXF headless：CAD plan validate、summarize、dry-run，以及显式确认后的 sandbox DXF 写入。
- 安全层：路径脱敏、敏感文本 redaction、安全检查、preflight、`.gitignore` 输出保护。
- Photoshop / Illustrator sandbox demo 入口：默认 dry-run；真实写入或导出必须显式确认并限制到 `examples/output/...`。
- CapCut / Jianying draft probe：只检查可执行文件和草稿目录配置形状，不读取草稿内容。

## What is not included

- 不包含模型、LoRA、VAE、ControlNet、生成图片、PSD、AI、DWG、DXF 真实输出、视频、token、cookie、账号或客户素材。
- 不承诺 Photoshop / Illustrator / AutoCAD / CapCut 在 CI 中可用。
- 不做自动登录、验证码、OAuth 授权、订阅绕过或许可绕过。
- 不读取私有 PSD、AI、DWG、DXF、`.blend`、剪映草稿内容或商业工程文件。
- 不把本机路径、安装路径、桌面目录、文档目录或 AppData 写入公开仓库。

## CI checklist

这些命令必须在 CI 或本地候选检查中通过：

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

CI runner 固定为 `windows-2022`，避免 `windows-latest` 漂移。缺少本机软件时，探针必须返回 `ok=false`、`warning` 或 soft-exit JSON，不能抛裸 traceback 导致 CI 失败。

## Security checklist

- 写入能力默认 `dry_run=true`。
- `dry_run=false` 时必须显式提供 `confirm_write=true` 或 `confirm_export=true`。
- DXF 输出只能在 `examples/cad/output`。
- Photoshop 输出只能在 `examples/output/photoshop`。
- Illustrator 输出只能在 `examples/output/illustrator`。
- 所有 MCP 结果必须 sanitize，不能泄露 `C:\Users`、`Desktop`、`Documents`、`AppData`、`/Users`、`/home` 等路径。
- `examples/output/` 和 `examples/cad/output/` 中的真实输出必须被 `.gitignore` 忽略。

## Local smoke test checklist

```powershell
python examples\bridge_status.py
python examples\bridge_status.py --json
python examples\bridge_status.py --json --redact-paths --soft-exit
python examples\bridge_status.py --probe-executables
python examples\comfy_bridge\comfy_probe.py
python scripts\test_autocad_mcp.py
npm.cmd run starbridge:tools:safe
npm.cmd run photoshop:demo:plan
npm.cmd run illustrator:demo:plan
```

Photoshop、Illustrator、AutoCAD 和 CapCut 的真实桌面能力只在本机已安装、已授权、用户明确运行时验证。没有本机环境时，只记录 unavailable / skipped，不伪造成功证据。

## Known limitations

- ComfyUI live probe 需要本机 ComfyUI 已启动；CI 只要求 workflow validate 和 soft failure。
- AutoCAD desktop automation 需要 Windows、AutoCAD、COM/pywin32 和授权；CI 不依赖这些条件。
- Photoshop / Illustrator COM demo 需要本机授权 Adobe desktop；真实写入不是 release 级生产能力。
- CapCut / Jianying 仍停留在 draft directory probe，不读取或写入草稿。
- Blender 目前只做环境探针；safe scene script 仍是 planned。

## Safe demo commands

```powershell
npm.cmd run bridge:status:safe
npm.cmd run starbridge:tools:safe
npm.cmd run comfy:workflow:validate
npm.cmd run cad:dxf:dry-run
npm.cmd run photoshop:demo:plan
npm.cmd run illustrator:demo:plan
python -m starbridge_mcp.mcp_server
```

这些命令用于验证 v0.1.0-alpha 的安全边界和结构化输出，不代表已经能控制真实商业工程文件。
