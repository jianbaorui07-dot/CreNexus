# AutoCAD MCP Setup

这份记录只保留可公开的 AutoCAD MCP 配置方式，不记录个人用户名、真实安装路径、客户图纸路径或本机输出路径。

## GitHub Project

Selected project: https://github.com/daobataotie/CAD-MCP

Reason: it targets Windows CAD through COM and supports AutoCAD, GstarCAD, and ZWCAD. This matches the StarBridge direction: let Codex call local CAD software through a controlled bridge.

## Local Path Policy

Use local environment variables or a local `.env` file for machine-specific paths:

```powershell
$env:AUTOCAD_EXE="C:\Path\To\acad.exe"
$env:STARBRIDGE_OUTPUT_DIR="$env:TEMP\starbridge-output"
```

Do not commit:

- AutoCAD install paths tied to a personal workstation.
- Codex config paths under a user profile.
- Customer DWG files, paid assets, license files, or generated outputs.

## Installed Python Packages

```powershell
python -m pip install --user pywin32 mcp pydantic
```

## Codex MCP Config

Use your local Python and local checkout path. Keep the real config in the Codex local config file, not in Git:

```toml
[mcp_servers.autocad]
command = "python"
args = ["<repo>\\cad-mcp-autocad\\src\\server.py"]
startup_timeout_sec = 60
tool_timeout_sec = 120
```

Restart or reload Codex after editing the config so the MCP tool namespace is available in the app.

## Verification

From the repository root:

```powershell
python scripts\test_autocad_mcp.py
```

Expected result: the script lists MCP tools, draws a rectangle and text in AutoCAD, then saves a test DWG under the local `output` folder. The generated DWG should stay local and should not be committed.
