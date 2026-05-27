# StarBridge 本地 MCP 接入说明

StarBridge 当前已经提供真正 MCP stdio server：Codex、Cursor、Claude Code 或其他 MCP 客户端可以通过同一套 tools 查看各软件桥状态，并调用首批安全只读/受保护 DXF 工具。

## 1. 本机准备

必须由用户手动完成：

- Adobe Photoshop / Illustrator：安装、登录、授权，并确认桌面软件可正常打开。
- AutoCAD / ZWCAD / GstarCAD / BricsCAD：安装、授权；AutoCAD 自动化需要 Windows COM 或对应 MCP 子项目。
- Blender：安装 desktop 或 CLI；如使用 Blender MCP，需要手动安装 addon。
- ComfyUI：本机启动 server，默认 `http://127.0.0.1:8188`。
- 剪映 / CapCut：安装客户端，手动确认草稿目录；不要让脚本自动登录账号。

可先运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_starbridge.ps1
python -m starbridge_mcp.server --json
npm.cmd run starbridge:status
npm.cmd run starbridge:tools:safe
```

如果只检查某一个桥：

```powershell
python -m starbridge_mcp.server --bridge comfyui --json
python -m starbridge_mcp.server --bridge photoshop --json
python -m starbridge_mcp.server --bridge illustrator --json
```

## 2. 本地环境变量

把 `.env.example` 复制成本机 `.env` 或设置 PowerShell 用户环境变量。不要把真实路径、账号、token、模型文件名、素材路径写进公开仓库。

常用变量：

```powershell
$env:STARBRIDGE_COMFYUI_URL="http://127.0.0.1:8188"
$env:COMFY_ROOT="<path-to-ComfyUI>"
$env:BLENDER_EXE="<path-to-blender.exe>"
$env:AUTOCAD_EXE="<path-to-acad.exe>"
$env:PHOTOSHOP_EXE="<path-to-Photoshop.exe>"
$env:ILLUSTRATOR_EXE="<path-to-Illustrator.exe>"
$env:JIANYING_DRAFTS_DIR="<path-to-jianying-drafts>"
$env:CAPCUT_DRAFTS_DIR="<path-to-capcut-drafts>"
```

## 3. Codex / Cursor / Claude Code 配置

CLI-style JSON 状态入口仍然保留：

当前可直接调用的本地命令：

```powershell
npm.cmd run starbridge:status
npm.cmd run starbridge:tools
npm.cmd run starbridge:tools:safe
npm.cmd run starbridge:mcp
npm.cmd run cad:dxf:dry-run
npm.cmd run comfy:workflow:validate
```

MCP stdio 配置：

```json
{
  "mcpServers": {
    "starbridge": {
      "command": "python",
      "args": ["-m", "starbridge_mcp.mcp_server"]
    }
  }
}
```

如果客户端需要从指定仓库目录启动，可使用绝对 `cwd` 或在客户端配置里指定工作目录；不要把本机用户名、安装路径或素材目录写进公开文档。

当前 MCP server 暴露的首批工具：

- `starbridge.status`：全部或单个 bridge 的统一状态。
- `starbridge.probe`：单个 bridge 的只读探针。
- `starbridge.tools`：能力注册表，可用 `safe_only=true` 过滤。
- `comfyui.system_probe`：读取 `/system_stats` 和 `/object_info`，不提交生成任务。
- `comfyui.workflow_validate`：只读校验 ComfyUI API workflow。
- `blender.environment_probe`：检查 Blender 可执行文件和环境线索。
- `cad_autocad.environment_probe`：检查 AutoCAD 可执行文件、COM 注册和 pywin32 线索。
- `photoshop.session_info`：检查 Photoshop COM/session 线索，不打开 PSD、不导出。
- `illustrator.document_info`：检查 Illustrator COM/session 线索，不打开私有 `.ai`。
- `jianying_capcut.draft_probe`：检查剪映/CapCut 可执行文件和草稿目录配置，不读取草稿内容。
- `autocad_dxf.status`：检查离线 DXF bridge。
- `autocad_dxf.validate_cad_plan`：校验 CAD JSON plan。
- `autocad_dxf.create_dxf_plan`：从 prompt 或 spec 生成 CAD plan。
- `autocad_dxf.summarize_plan`：汇总 CAD plan。
- `autocad_dxf.write_dxf`：默认 dry-run；真实写入必须 `confirm_write=true` 且输出在 `examples/cad/output`。

可用一个最小 stdio 请求检查初始化：

```powershell
@'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual-test","version":"1"}}}
{"jsonrpc":"2.0","id":2,"method":"tools/list"}
'@ | python -m starbridge_mcp.mcp_server
```

## 4. 安全边界

- 状态入口和默认 MCP tools 只读，不自动打开客户文件，不写真实素材。
- 输出会脱敏用户目录、token、Cookie、OAuth、PSD/AI/DWG/DXF、模型文件、剪映草稿和导出视频。
- `output/`、`scratch/`、`third_party_research/`、模型、PSD、AI、DWG、DXF、视频和草稿文件已加入 `.gitignore`。
- 需要登录、订阅、验证码、OAuth、Adobe 授权、AutoCAD 授权或 GitHub 授权时，必须由用户手动处理。

## 5. 后续 MCP 工具规划

优先顺序：

1. `starbridge.status`：返回所有桥统一状态。
2. `starbridge.probe(bridge)`：返回单桥探针结果。
3. `comfyui.system_probe` / `comfyui.workflow_validate` 已实现；下一步再做 job/asset 摘要，不直接公开生成图路径。
4. `photoshop.session_info` / `illustrator.document_info` 已挂入 MCP；下一步把只读当前文档摘要做细。
5. `cad_autocad.environment_probe` / `autocad_dxf.*` 已挂入 MCP；真实 AutoCAD COM 仍作为可选。
6. `jianying_capcut.draft_probe` 已挂入 MCP；下一步只读草稿目录结构摘要，不输出素材路径。
